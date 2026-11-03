"""Summarize recorded runs, including failures, without making model requests."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(rows):
    summaries = {}
    for arm in dict.fromkeys(row["arm"] for row in rows):
        group = [row for row in rows if row["arm"] == arm]
        modes = {(row.get("runtime_arm"), row.get("result_policy"), row.get("task_state_projection")) for row in group}
        if len(modes) > 1:
            raise ValueError("Inconsistent policies under the same profile name")
        complete = all(row.get("usage_complete") for row in group)
        known_in = sum(row.get("input_tokens") or 0 for row in group)
        known_out = sum(row.get("output_tokens") or 0 for row in group)
        agent_times = [row["agent_elapsed_s"] for row in group if row.get("agent_elapsed_s") is not None]
        summaries[arm] = {
            "runs": len(group), "successes": sum(row["passed"] for row in group),
            "format_successes": sum(row.get("format_correct", False) for row in group),
            "usage_complete": complete, "usage_missing_runs": sum(not r.get("usage_complete") for r in group),
            "input_tokens": known_in if complete else None, "output_tokens": known_out if complete else None,
            "total_tokens": known_in + known_out if complete else None,
            "known_input_tokens": known_in, "known_output_tokens": known_out,
            "uncached_input": sum(r.get("uncached_input") or 0 for r in group) if complete else None,
            "cache_read": sum(r.get("cache_read") or 0 for r in group) if complete else None,
            "model_calls": sum(row.get("accounting", {}).get("calls", 0) for row in group),
            "median_agent_s": statistics.median(agent_times) if agent_times else None,
            "total_agent_s": sum(agent_times) if len(agent_times) == len(group) else None,
            "median_wall_s": statistics.median(row["elapsed_s"] for row in group),
            "api_cost": None, "cost_status": "No API tariff/bill provided; local compute/power not measured",
        }
    return summaries


def audit(run_root, rows):
    tools = {arm: Counter() for arm in {r["arm"] for r in rows}}
    missing_mcp = []
    projections = Counter()
    projection_modes = {arm: Counter() for arm in tools}
    for row in rows:
        run = run_root / f"{row['task']}-{row['repeat']}-{row['arm']}"
        path = run / "transcript.json"
        if not path.exists():
            if row.get("runtime_arm", row["arm"]) == "context_mode":
                missing_mcp.append(run.name)
            continue
        transcript = json.loads(path.read_text(encoding="utf-8"))
        names = [call.get("function", {}).get("name", call.get("name", ""))
                 for message in transcript.get("messages", []) for call in message.get("tool_calls", [])]
        tools[row["arm"]].update(names)
        projections[row["arm"]] += sum(
            bool(message.get("display_metadata", {}).get("task_state_snapshot"))
            for message in transcript.get("messages", []))
        for message in transcript.get("messages", []):
            projection = message.get("display_metadata", {}).get("task_state_snapshot")
            if projection:
                projection_modes[row["arm"]][projection.get("projection_mode", "full")] += 1
        if row.get("runtime_arm", row["arm"]) == "context_mode" and not any(name.startswith("ctx_") for name in names):
            missing_mcp.append(run.name)
    return {"tool_calls": {arm: dict(count) for arm, count in tools.items()},
            "context_mode_runs_without_recorded_mcp": missing_mcp,
            "task_state_projections": dict(projections),
            "task_state_projection_modes": {arm: dict(modes) for arm, modes in projection_modes.items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.input/"results.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.input/"manifest.json").read_text(encoding="utf-8"))
    summary = summarize(rows)
    details = audit(args.input, rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"summary.json").write_text(json.dumps({
        "summary": summary, "audit": details, "manifest": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output/"results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = [
        "# 本地模型上下文模块开发集对照",
        "",
        f"模型：{manifest['model']}。{len(manifest.get('cases', []))}类开发任务，重复{manifest.get('repeats', 'unknown')}次，并发{manifest.get('parallel', 'unknown')}；不是正式holdout统计结论。",
        (f"原版context-mode commit：{manifest['context_mode_sha']}，配置为MCP工具集；实际调用见审计，未安装宿主hooks。"
         if any(row.get("runtime_arm", row["arm"]) == "context_mode" for row in rows)
         else "本批profiles未包含原版context-mode运行。"),
        "",
        "| 组别 | 内容正确 | 格式合规 | 输入token合计 | 输出token合计 | 模型请求数 | Agent中位耗时(s) | 含启动中位耗时(s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in dict.fromkeys([*manifest.get("arms", []), *summary]):
        if arm not in summary:
            continue
        value = summary[arm]
        agent_median = f"{value['median_agent_s']:.2f}" if value["median_agent_s"] is not None else "unknown"
        lines.append(f"| {arm} | {value['successes']}/{value['runs']} | {value['format_successes']}/{value['runs']} | "
                     f"{value['input_tokens']} | {value['output_tokens']} | {value['model_calls']} | "
                     f"{agent_median} | {value['median_wall_s']:.2f} |")
    lines += [
        "", "输入合计包含缓存命中；原始provider usage逐次保存，思考已包含在输出时不重复累计。",
        "未提供API单价/账单、GPU功耗、硬件租价或电费数据，总成本记未知，不记成0，也不宣称节省人民币。",
        "各组原始失败、重试、恢复均纳入统计。缺失usage时整组总token标未知，已知小计单列。",
        "", "## 逐任务记录", "",
        "| 任务 | 组别 | 内容正确 | 格式正确 | 输入 | 输出 | Agent(s) | 完整墙钟(s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda r: (r["task"], r["repeat"], r["arm"])):
        agent = f"{row['agent_elapsed_s']:.2f}" if row.get("agent_elapsed_s") is not None else "unknown"
        lines.append(f"| {row['task']} | {row['arm']} | {row['passed']} | {row.get('format_correct')} | "
                     f"{row['input_tokens']} | {row['output_tokens']} | {agent} | {row['elapsed_s']:.2f} |")
    lines += ["", "## 工具轨迹审计", "", "~~~json", json.dumps(details, ensure_ascii=False, indent=2), "~~~",
              "", "## 复现边界", "",
              "- off/rules使用相同工具协议；context-mode使用自身原版工具，属于系统比较。",
              "- 关闭了旧语义上下文压缩；每个profile的result_policy/task_state_projection见manifest，不混算full/delta/off。",
              "- 这组fixture主要是JSON/聚合/回读任务，不代表真实业务的全场景表现。",
              "- 运行顺序用seed=731随机化；缓存没有强制清空，服务端其他负载未知。",
              "- 模型标识以配置与逐调用记录为准；权重/服务构建及源码/配置/fixture哈希按manifest提供，不推断缺失版本。",
              "- 原始逐调用账本、完整轨迹与模型输出保存在仓库外本次运行目录。",
              "", f"原始目录：{args.input.as_posix()}"]
    (args.output/"report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
