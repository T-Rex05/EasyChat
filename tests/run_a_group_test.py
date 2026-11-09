"""
A 组自动化测试脚本 - 通过审计日志提取工具调用数据
"""
import json
import os
import re
import sys
import time
import requests
import importlib.util
from datetime import datetime
from pathlib import Path

# Windows 编码修复
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 项目根目录
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
os.chdir(PROJECT_ROOT)

# 导入 ab_test_recorder
spec = importlib.util.spec_from_file_location('ab_test_recorder', 'tests/ab_test_recorder.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ABTestRecorder = mod.ABTestRecorder
TEST_CASES = mod.TEST_CASES

BASE_URL = "http://localhost:8001"
LOG_FILE = "data/logs/audit.log"


def get_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin", "password": "admin123"
    })
    return resp.json()["token"]


def get_log_position():
    """获取当前日志文件位置"""
    try:
        return os.path.getsize(LOG_FILE)
    except OSError:
        return 0


def parse_log_since(position):
    """解析从指定位置开始的日志，提取工具调用数据"""
    result = {
        "tool_calls_total": 0,
        "tools_breakdown": {},
        "tool_details": [],
        "duration_total_ms": 0,
        "memory_count": 0,
        "kb_chunks": 0,
        "code_mode_calls": [],
    }

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            f.seek(position)
            new_content = f.read()
    except Exception:
        return result

    # 提取 "🔧 工具调用 | 共N次" 和后续行
    # 格式: 🔧 工具调用 | 共5次
    #        1⃝ run_python({...})
    #        2⃝ terminal({...})
    #        ...
    # 📊 摘要 | 总耗时=57851ms | 记忆=9条 | KB=0chunks | 工具=5次

    # 找所有摘要行
    summary_pattern = r"📊\s*摘要\s*\|\s*总耗时=(\d+)ms\s*\|\s*记忆=(\d+)条\s*\|\s*KB=(\d+)chunks\s*\|\s*工具=(\d+)次"
    for m in re.finditer(summary_pattern, new_content):
        result["duration_total_ms"] = int(m.group(1))
        result["memory_count"] = int(m.group(2))
        result["kb_chunks"] = int(m.group(3))
        result["tool_calls_total"] = int(m.group(4))

    # 找工具调用列表
    # 🔧 工具调用 | 共N次
    #   1⃝ run_python({...})
    tool_section = re.findall(
        r"🔧\s*工具调用\s*\|\s*共(\d+)次\n((?:.*\n)*?)(?=📊|🔧|\Z)",
        new_content
    )
    for total, block in tool_section:
        result["tool_calls_total"] = int(total)
        # 解析每个工具调用
        tool_pattern = r"\d+⃝\s+(\w+)\(\{(.+?)\}\)"
        for tm in re.finditer(tool_pattern, block):
            tool_name = tm.group(1)
            args_str = tm.group(2)
            result["tools_breakdown"][tool_name] = result["tools_breakdown"].get(tool_name, 0) + 1
            result["tool_details"].append({
                "name": tool_name,
                "args_preview": args_str[:200],
            })

    # 解析 code_mode_complete 行
    code_mode_pattern = r"code_mode_complete\s*\|\s*success=(\w+)\s*output_len=(\d+)\s*duration=([\d.]+)ms\s*attempts=(\d+)\s*code_preview=\s*(.+)"
    for cm in re.finditer(code_mode_pattern, new_content):
        result["code_mode_calls"].append({
            "success": cm.group(1) == "True",
            "output_len": int(cm.group(2)),
            "duration_ms": float(cm.group(3)),
            "code_preview": cm.group(5)[:200],
        })

    return result


def analyze_batch_operations(code_mode_calls):
    """分析批量操作使用情况"""
    batch_search = 0
    batch_read = 0
    single_search = 0
    single_read = 0

    for call in code_mode_calls:
        code = call.get("code_preview", "")
        # 批量搜索
        if re.search(r'search_files\(\s*\[', code):
            batch_search += 1
        elif "search_files(" in code:
            single_search += 1
        # 批量读取
        if re.search(r'read_file\(\s*\[', code):
            batch_read += 1
        elif "read_file(" in code:
            single_read += 1

    return {
        "batch_search_count": batch_search,
        "batch_read_count": batch_read,
        "single_search_count": single_search,
        "single_read_count": single_read,
    }


def run_single_test(test_case, run_num, recorder, token):
    """执行单个测试"""
    test_id = test_case["id"]
    question = test_case["question"]
    scenario = test_case["scenario"]

    print(f"\n{'='*60}")
    print(f"[{test_id}] 场景: {scenario} | 第 {run_num}/3 次")
    print(f"问题: {question}")

    thread_id = f"1_{int(time.time()*1000)}_{test_id}_{run_num}"

    # 记录日志位置
    log_pos = get_log_position()
    start_time = time.time()

    try:
        resp = requests.get(
            f"{BASE_URL}/chat/stream",
            params={"message": question, "thread_id": thread_id, "token": token},
            stream=True,
            timeout=180
        )

        if resp.status_code != 200:
            print(f"  ❌ HTTP {resp.status_code}")
            return False

        # 消费完 SSE 流
        full_response = []
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                    if d.get("type") == "token":
                        full_response.append(d.get("content", ""))
                    elif d.get("type") == "chat_complete":
                        break
                except Exception:
                    pass

        elapsed = time.time() - start_time

        # 等待日志写入完成
        time.sleep(1)

        # 解析日志
        log_data = parse_log_since(log_pos)

        # 如果没有从日志摘要中获取到耗时，使用 SSE 耗时
        if log_data["duration_total_ms"] == 0:
            log_data["duration_total_ms"] = int(elapsed * 1000)

        # 分析批量操作
        batch_ops = analyze_batch_operations(log_data["code_mode_calls"])

        # 工具调用耗时分布（从 code_mode_calls 提取）
        durs = [c["duration_ms"] for c in log_data["code_mode_calls"]]
        avg_dur = sum(durs) / len(durs) if durs else 0
        min_dur = min(durs) if durs else 0
        max_dur = max(durs) if durs else 0

        # 记录
        recorder.record_test(
            test_id=test_id,
            run=run_num,
            question=question,
            tool_calls_total=log_data["tool_calls_total"],
            tools_breakdown=log_data["tools_breakdown"],
            batch_operations=batch_ops,
            duration_total_ms=log_data["duration_total_ms"],
            duration_per_tool_avg_ms=avg_dur,
            duration_per_tool_min_ms=min_dur,
            duration_per_tool_max_ms=max_dur,
            input_tokens=0,
            output_tokens=0,
            behavior={
                "two_phase_pattern_used": batch_ops["batch_search_count"] > 0 and batch_ops["batch_read_count"] > 0,
                "batch_operations_used": batch_ops["batch_search_count"] > 0 or batch_ops["batch_read_count"] > 0,
                "terminal_misuse_count": log_data["tools_breakdown"].get("terminal", 0),
            },
            memory_usage={"prefetch_count": log_data["memory_count"]},
            knowledge_base_usage={"kb_chunks": log_data["kb_chunks"]},
            notes=f"elapsed={elapsed:.1f}s, code_mode_calls={len(log_data['code_mode_calls'])}"
        )

        # 打印摘要
        print(f"  ✅ 完成 | 耗时: {elapsed:.1f}s | 工具: {log_data['tool_calls_total']}次")
        print(f"  工具分布: {log_data['tools_breakdown']}")
        print(f"  批量: 搜索={batch_ops['batch_search_count']} 读取={batch_ops['batch_read_count']}")
        print(f"  单个: 搜索={batch_ops['single_search_count']} 读取={batch_ops['single_read_count']}")
        if log_data["code_mode_calls"]:
            for i, c in enumerate(log_data["code_mode_calls"][:3]):
                print(f"  code[{i}]: {c['duration_ms']:.0f}ms, out={c['output_len']}c, preview={c['code_preview'][:80]}...")

        return True

    except requests.exceptions.Timeout:
        print(f"  ❌ 超时 (>{180}s)")
        recorder.record_test(
            test_id=test_id, run=run_num, question=question,
            tool_calls_total=0, tools_breakdown={}, batch_operations={},
            duration_total_ms=180000, duration_per_tool_avg_ms=0,
            duration_per_tool_min_ms=0, duration_per_tool_max_ms=0,
            input_tokens=0, output_tokens=0,
            errors_total=1, error_details=[{"message": "timeout"}],
            notes="请求超时"
        )
        return False
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("AgentForge A 组自动化测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试用例: {len(TEST_CASES)} 个 × 3 次 = {len(TEST_CASES)*3} 次运行")
    print(f"预计耗时: {len(TEST_CASES)*3*45/60:.0f} 分钟")
    print("=" * 60)

    token = get_token()
    print("✅ Token 获取成功")

    recorder = ABTestRecorder(group="A")

    total = len(TEST_CASES) * 3
    completed = 0
    failed = 0

    for tc in TEST_CASES:
        for run in range(1, 4):
            ok = run_single_test(tc, run, recorder, token)
            if ok:
                completed += 1
            else:
                failed += 1

            # 间隔 3 秒
            time.sleep(3)

            # 每个测试用例完成后保存
            if run == 3:
                recorder.save()
                print(f"\n💾 [{tc['id']}] 完成并保存")
                print(f"进度: {completed + failed}/{total} (完成={completed}, 失败={failed})")

    # 最终
    recorder.save()
    print(f"\n{'='*60}")
    print(f"测试全部完成！成功: {completed}, 失败: {failed}")
    print("结果文件: tests/results/test_results_a.json")
    print(f"{'='*60}")
    recorder.print_summary()


if __name__ == "__main__":
    main()
