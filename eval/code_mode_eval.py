#!/usr/bin/env python3
"""
Code Mode Agent 级评测脚本
===========================
评测维度：
  E1. 模式选择（Mode Selection）— 该不该用 Code Mode
  E2. 代码正确性（Code Correctness）— 生成的代码能不能跑
  E3. 结果准确性（Result Accuracy）— 最终回答对不对
  E4. 边界场景（Edge Cases）— 安全拦截 + 错误恢复

复用四维评测框架模式：SSE 调用 + LLM Judge 评分

用法：
    python eval/code_mode_eval.py --token <jwt_token>
    python eval/code_mode_eval.py --token <jwt_token> --cases CM-S1,CM-C1
    python eval/code_mode_eval.py --token <jwt_token> --category mode_selection
    python eval/code_mode_eval.py --token <jwt_token> --verbose
"""

import json
import os
import sys
import time
import argparse
import hashlib
import threading
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


# Windows 控制台 UTF-8 输出
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


# ============================================================
# 配置
# ============================================================

SCRIPT_DIR = Path(__file__).parent
DATASET_FILE = SCRIPT_DIR / "dataset" / "dataset_code_mode.jsonl"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "report" / "code_mode"

# 全局 token 和 user_id
_TOKEN = ""
_USER_ID = 0

# Code Mode 专属 LLM Judge Prompt
CODE_MODE_JUDGE_PROMPT = """## 评测任务 — Code Mode 专项

**用户问题**：
{question}

**Agent 回答**：
{response}

**评测重点**：
- 模式选择：Agent 是否合适地选择了 Code Mode（run_python）或直接调用工具？
  {mode_selection_criteria}
- 代码正确性：Agent 生成的代码是否能正确执行？工具调用参数是否正确？
- 结果准确性：Agent 最终回答是否准确包含预期信息？
- 边界处理：安全检查、错误恢复是否合理？

**评分要求**：
{judge_hint}

**评分维度**：
{rubric}

**输出要求**：你必须且只能输出一个合法的 JSON 对象，不要输出任何其他文字。
JSON 格式如下：

{{
    "scores": {{
        "correctness": {{"score": 3, "reason": "得分理由"}},
        "completeness": {{"score": 3, "reason": "得分理由"}},
        "code_quality": {{"score": 3, "reason": "得分理由"}},
        "efficiency": {{"score": 3, "reason": "得分理由"}}
    }},
    "mode_used": "code_mode",
    "mode_appropriate": true,
    "pass": true,
    "overall_reason": "总体评价"
}}

字段说明：
- mode_used 只能是以下三选一："code_mode"、"direct_tool"、"none"
- mode_appropriate 只能是 true 或 false
- pass 只能是 true 或 false
- score 为 1-5 的整数
"""


# ============================================================
# 工具函数
# ============================================================

def load_dataset() -> list:
    """加载 Code Mode 评测数据集"""
    if not DATASET_FILE.exists():
        print(f"[ERROR] 数据集文件不存在: {DATASET_FILE}")
        return []
    cases = []
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    print(f"[INFO] 加载 {len(cases)} 个 Code Mode 评测用例")
    return cases


def parse_jwt_user_id(token: str) -> int:
    """从 JWT 解析 user_id"""
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload.get("uid", 0))
    except Exception:
        return 0


def call_chat_api(base_url: str, message: str, session_id: str,
                  timeout: int = 120) -> dict:
    """调用 Agent 聊天 API（SSE 流式，收集完整响应）"""
    url = f"{base_url}/chat/stream"
    params = {
        "message": message,
        "thread_id": session_id,
        "token": _TOKEN,
    }
    try:
        resp = requests.get(url, params=params, stream=True, timeout=timeout)
        resp.raise_for_status()

        full_response = []
        trace_id = None
        tool_calls = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")
            if event_type == "token":
                full_response.append(data.get("content", ""))
            elif event_type == "chat_complete":
                trace_id = data.get("trace_id")
            elif event_type == "tool_output":
                tool_calls.append(data.get("tool_name", ""))
            elif event_type == "error":
                return {
                    "success": False,
                    "response": "",
                    "error": data.get("message", "unknown error"),
                    "trace_id": trace_id,
                    "tool_calls": tool_calls,
                }

        return {
            "success": True,
            "response": "".join(full_response),
            "error": None,
            "trace_id": trace_id,
            "tool_calls": tool_calls,
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "response": "",
            "error": str(e),
            "trace_id": None,
            "tool_calls": [],
        }


def call_llm_judge(base_url: str, case: dict, response: str) -> dict:
    """调用 LLM-as-Judge 对 Code Mode 回答评分"""
    rubric = case.get("rubric", {"correctness": 0.5, "completeness": 0.3, "efficiency": 0.2})
    rubric_text = "\n".join([f"- {k}: 权重 {v}" for k, v in rubric.items()])

    # 模式选择评判标准
    should_use = case.get("should_use_code_mode")
    if should_use is True:
        mode_criteria = "此场景涉及多工具编排/数据处理，**应该**使用 Code Mode (run_python)。如果 Agent 使用了 Code Mode 则加分，否则扣分。"
    elif should_use is False:
        mode_criteria = "此场景为简单查询，**不应**使用 Code Mode，直接调用工具即可。如果 Agent 直接调工具则加分，使用了 Code Mode 则扣分。"
    else:
        mode_criteria = "此场景模式选择不强制，两种方式都可接受。"

    prompt = CODE_MODE_JUDGE_PROMPT.format(
        question=case["turns"][-1]["content"],
        response=response[:3000],
        mode_selection_criteria=mode_criteria,
        judge_hint=case.get("judge_hint", "无特殊要求"),
        rubric=rubric_text,
    )

    uid = _USER_ID
    result = call_chat_api(
        base_url=base_url,
        message=prompt,
        session_id=f"{uid}_cmjudge_{hashlib.md5(case['case_id'].encode()).hexdigest()[:8]}",
        timeout=60,
    )

    if not result["success"]:
        return {"scores": {}, "pass": False, "error": result["error"]}

    judge_text = result["response"]

    # 多策略 JSON 提取
    parsed = None

    # 策略1: 提取 markdown 代码块中的 JSON
    import re
    json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', judge_text, re.DOTALL)
    if json_block:
        try:
            parsed = json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    # 策略2: 从第一个 { 到最后一个 }
    if parsed is None:
        json_start = judge_text.find("{")
        json_end = judge_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                parsed = json.loads(judge_text[json_start:json_end])
            except json.JSONDecodeError:
                pass

    # 策略3: 尝试找到最后一个完整的 JSON 对象（从后往前找）
    if parsed is None:
        # 从最后一个 } 往前找到匹配的 {
        for i in range(len(judge_text) - 1, -1, -1):
            if judge_text[i] == '}':
                for j in range(i, -1, -1):
                    if judge_text[j] == '{':
                        try:
                            parsed = json.loads(judge_text[j:i+1])
                            break
                        except json.JSONDecodeError:
                            continue
                if parsed:
                    break

    if parsed:
        return parsed

    return {
        "scores": {},
        "pass": False,
        "error": f"Judge 输出无法解析为 JSON: {judge_text[:300]}",
    }


# ============================================================
# 评测执行
# ============================================================

def run_case(base_url: str, case: dict, output_dir: Path, verbose: bool = False) -> dict:
    """执行单个评测用例"""
    case_id = case["case_id"]
    category = case.get("category", "unknown")
    description = case.get("description", "")

    if verbose:
        print(f"\n  [{case_id}] {description}")

    # 构建多轮对话 session
    session_id = f"{_USER_ID}_cm_{case_id}_{int(time.time())}"
    last_user_msg = ""
    full_response = ""
    all_tool_calls = []
    success = True

    for turn in case["turns"]:
        if turn["role"] == "user":
            last_user_msg = turn["content"]
            result = call_chat_api(base_url, turn["content"], session_id)
            if not result["success"]:
                if verbose:
                    print(f"    ❌ API 调用失败: {result['error']}")
                success = False
                break
            full_response = result["response"]
            all_tool_calls.extend(result.get("tool_calls", []))
            if verbose:
                print(f"    响应长度: {len(full_response)} 字符")
                print(f"    工具调用: {all_tool_calls}")

    # LLM Judge 评分
    judge_result = {}
    if success and full_response:
        judge_result = call_llm_judge(base_url, case, full_response)
        if verbose:
            passed = "✅" if judge_result.get("pass") else "❌"
            print(f"    Judge: {passed} {judge_result.get('overall_reason', '')[:80]}")

    # 保存结果
    record = {
        "case_id": case_id,
        "category": category,
        "description": description,
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "response": full_response,
        "tool_calls": all_tool_calls,
        "judge": judge_result,
        "should_use_code_mode": case.get("should_use_code_mode"),
    }

    # 写入 JSONL
    pred_file = output_dir / "pred_code_mode.jsonl"
    with open(pred_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def generate_report(results: list, output_dir: Path) -> str:
    """生成评测报告"""
    lines = []
    lines.append("# Code Mode Agent 级评测报告")
    lines.append("")
    lines.append(f"**评测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**总用例**: {len(results)}")
    lines.append("")

    # 按维度汇总
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0, "results": []}
        categories[cat]["total"] += 1
        categories[cat]["results"].append(r)
        if r.get("judge", {}).get("pass"):
            categories[cat]["passed"] += 1
        else:
            categories[cat]["failed"] += 1

    # 汇总表
    cat_names = {
        "mode_selection": "E1: 模式选择",
        "code_correctness": "E2: 代码正确性",
        "result_accuracy": "E3: 结果准确性",
        "edge_case": "E4: 边界场景",
    }
    lines.append("## 维度汇总")
    lines.append("")
    lines.append("| 维度 | 用例数 | 通过 | 失败 | 通过率 |")
    lines.append("|------|--------|------|------|--------|")
    total_pass = 0
    total_count = 0
    for cat, data in categories.items():
        name = cat_names.get(cat, cat)
        rate = data["passed"] / data["total"] * 100 if data["total"] > 0 else 0
        lines.append(f"| {name} | {data['total']} | {data['passed']} | {data['failed']} | {rate:.1f}% |")
        total_pass += data["passed"]
        total_count += data["total"]
    overall_rate = total_pass / total_count * 100 if total_count > 0 else 0
    lines.append(f"| **总计** | **{total_count}** | **{total_pass}** | **{total_count - total_pass}** | **{overall_rate:.1f}%** |")
    lines.append("")

    # 模式选择统计
    mode_stats = {"code_mode": 0, "direct_tool": 0, "none": 0, "appropriate": 0, "inappropriate": 0}
    for r in results:
        j = r.get("judge", {})
        mode_used = j.get("mode_used", "none")
        if mode_used in mode_stats:
            mode_stats[mode_used] += 1
        if j.get("mode_appropriate") is True:
            mode_stats["appropriate"] += 1
        elif j.get("mode_appropriate") is False:
            mode_stats["inappropriate"] += 1

    lines.append("## 模式选择分析")
    lines.append("")
    lines.append(f"- Code Mode 使用次数: {mode_stats['code_mode']}")
    lines.append(f"- 直接调工具次数: {mode_stats['direct_tool']}")
    lines.append(f"- 模式选择合理: {mode_stats['appropriate']} 次")
    lines.append(f"- 模式选择不合理: {mode_stats['inappropriate']} 次")
    lines.append("")

    # 各维度详情
    for cat, data in categories.items():
        name = cat_names.get(cat, cat)
        lines.append(f"## {name}")
        lines.append("")
        for r in data["results"]:
            j = r.get("judge", {})
            passed = "✅" if j.get("pass") else "❌"
            lines.append(f"### {r['case_id']}: {r['description']}")
            lines.append(f"- 结果: {passed}")
            lines.append(f"- 模式: {j.get('mode_used', 'N/A')} (合理: {j.get('mode_appropriate', 'N/A')})")
            scores = j.get("scores", {})
            if scores:
                for dim, detail in scores.items():
                    if isinstance(detail, dict):
                        lines.append(f"- {dim}: {detail.get('score', '?')}/5 — {detail.get('reason', '')}")
            if j.get("overall_reason"):
                lines.append(f"- 总评: {j['overall_reason']}")
            if j.get("error"):
                lines.append(f"- **错误**: {j['error']}")
            lines.append("")

    # 结论
    lines.append("## 结论")
    lines.append("")
    if overall_rate >= 80:
        grade = "A（优秀）"
    elif overall_rate >= 60:
        grade = "B（良好）"
    elif overall_rate >= 40:
        grade = "C（合格）"
    else:
        grade = "D（需改进）"
    lines.append(f"**评级**: {grade}")
    lines.append(f"**总通过率**: {overall_rate:.1f}%")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 入口
# ============================================================

def main():
    global _TOKEN, _USER_ID

    parser = argparse.ArgumentParser(description="Code Mode Agent 级评测")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001",
                       help="Agent 服务地址 (默认 http://127.0.0.1:8001)")
    parser.add_argument("--token", required=True,
                       help="登录 token")
    parser.add_argument("--cases", default=None,
                       help="指定用例 ID，逗号分隔 (默认全部)")
    parser.add_argument("--category", default=None,
                       help="指定维度 (mode_selection/code_correctness/result_accuracy/edge_case)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR),
                       help="输出目录")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    args = parser.parse_args()

    _TOKEN = args.token
    _USER_ID = parse_jwt_user_id(_TOKEN)
    print(f"[INFO] 用户 user_id={_USER_ID}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载数据集
    cases = load_dataset()
    if not cases:
        print("[ERROR] 无评测用例")
        sys.exit(1)

    # 过滤用例
    if args.cases:
        case_ids = set(c.strip() for c in args.cases.split(","))
        cases = [c for c in cases if c["case_id"] in case_ids]
    if args.category:
        cases = [c for c in cases if c.get("category") == args.category]

    print(f"[INFO] 待评测: {len(cases)} 个用例")
    print(f"[INFO] 服务地址: {args.base_url}")
    print(f"[INFO] 输出目录: {output_dir}")
    print()

    # 清空之前的预测文件
    pred_file = output_dir / "pred_code_mode.jsonl"
    if pred_file.exists():
        pred_file.unlink()

    # 执行评测
    results = []
    start_time = time.time()
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']}: {case.get('description', '')}")
        record = run_case(args.base_url, case, output_dir, verbose=args.verbose)
        results.append(record)

        # 简短状态
        j = record.get("judge", {})
        passed = "✅" if j.get("pass") else "❌"
        mode = j.get("mode_used", "?")
        print(f"  → {passed} mode={mode} | {j.get('overall_reason', '')[:60]}")
        print()

        # 避免 API 限流
        time.sleep(1)

    elapsed = time.time() - start_time
    print(f"[INFO] 评测完成，耗时 {elapsed:.1f}s")

    # 生成报告
    report = generate_report(results, output_dir)

    # 保存报告
    report_file = output_dir / f"code_mode_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    # 控制台输出
    print("\n" + "=" * 60)
    print(report)
    print(f"\n📄 报告已保存: {report_file}")

    # 退出码
    total_passed = sum(1 for r in results if r.get("judge", {}).get("pass"))
    sys.exit(0 if total_passed == len(results) else 0)


if __name__ == "__main__":
    main()
