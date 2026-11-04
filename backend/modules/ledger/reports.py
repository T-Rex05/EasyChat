"""账本报告渲染：只做确定性排版，不做任何金额计算。

数据来源是 `AnalysisResult`（服务已用受控 SQL 算出并留痕）；渲染失败直接抛错，
不生成半成品文件，也不影响已保存的分析记录。
"""
from __future__ import annotations

import csv
import io

from backend.modules.ledger.contracts import AnalysisResult, GROUP_BY_CATEGORY
from backend.modules.ledger.normalization import format_money
from backend.shared.errors import InvalidInputError

SUPPORTED_FORMATS = ("markdown", "csv")
MIME_MARKDOWN = "text/markdown; charset=utf-8"
MIME_CSV = "text/csv; charset=utf-8"

_BASIS_LABELS = {
    "statement_flow": "账单流水",
    "consumption_net": "消费净额",
    "period_cash_outflow": "本期现金流出",
}

_METRIC_LABELS = {
    "expense": "支出",
    "income": "收入",
    "neutral": "中性（充值/提现等）",
    "refund_received": "退款到账",
    "net": "净额",
}

_COVERAGE_LABELS = {
    "complete": "完整覆盖",
    "partial": "部分覆盖",
    "overlapping": "存在重叠账单",
    "unknown": "无可用账单",
}


def render_report(result: AnalysisResult, *, fmt: str = "markdown") -> tuple[bytes, str, str]:
    if fmt not in SUPPORTED_FORMATS:
        raise InvalidInputError(f"不支持的报告格式: {fmt}")
    if fmt == "csv":
        return _render_csv(result), MIME_CSV, "csv"
    return _render_markdown(result), MIME_MARKDOWN, "md"


def render_report_html(result: AnalysisResult) -> str:
    """PDF 渲染用的极简 HTML（数字与 Markdown 报告同源）。"""
    rows = "".join(
        f"<tr><td>{_METRIC_LABELS.get(m.name, m.name)}</td>"
        f"<td style='text-align:right'>{_money(m.amount_minor, result.currency)}</td></tr>"
        for m in result.metrics
    )
    group_rows = "".join(
        f"<tr><td>{group.get('bucket_label') or group.get('bucket1') or '未分类'}</td>"
        f"<td style='text-align:right'>{_money(int(group.get('expense_minor') or 0), result.currency)}</td></tr>"
        for group in result.groups
    )
    detail_rows = "".join(
        f"<tr><td>{tx.occurred_at[:19]}</td><td>{tx.merchant or '—'}</td>"
        f"<td>{tx.direction}</td>"
        f"<td style='text-align:right'>{_money(tx.amount_minor, tx.currency)}</td></tr>"
        for tx in result.transactions[:200]
    )
    notes = "".join(f"<li>{note}</li>" for note in result.coverage.notes)
    warnings = "".join(f"<li>{w}</li>" for w in result.warnings)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>微信账单分析报告</title>
<style>body{{font-family:sans-serif;margin:32px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #ccc;padding:6px 8px;font-size:13px}}h1{{font-size:20px}}</style></head>
<body>
<h1>微信账单分析报告</h1>
<p>统计口径：{_BASIS_LABELS.get(result.basis, result.basis)}<br>
统计区间：{_period_text(result)}<br>
覆盖情况：{_COVERAGE_LABELS.get(result.coverage.coverage_kind, result.coverage.coverage_kind)}<br>
数据截止：{result.data_cutoff}　分析 ID：{result.analysis_id}</p>
<h2>指标</h2><table><tr><th>指标</th><th>金额</th></tr>{rows}</table>
<h2>分类</h2><table><tr><th>分组</th><th>支出</th></tr>{group_rows}</table>
<h2>明细（最多 200 笔）</h2><table><tr><th>时间</th><th>商户</th><th>方向</th><th>金额</th></tr>{detail_rows}</table>
{f'<h2>数据说明</h2><ul>{notes}</ul>' if notes else ''}
{f'<h2>计算提示</h2><ul>{warnings}</ul>' if warnings else ''}
</body></html>"""


def _money(amount: int, currency: str) -> str:
    return f"{format_money(int(amount), currency)} {currency}"


def _period_text(result: AnalysisResult) -> str:
    period = result.plan.period
    start = period.start or "未指定"
    end = period.end_exclusive or "未指定"
    return f"{start} ~ {end}（不含右端）"


def _render_markdown(result: AnalysisResult) -> bytes:
    lines: list[str] = [
        "# 微信账单分析报告",
        "",
        f"- 统计口径：{_BASIS_LABELS.get(result.basis, result.basis)}",
        f"- 统计区间：{_period_text(result)}",
        f"- 覆盖情况：{_COVERAGE_LABELS.get(result.coverage.coverage_kind, result.coverage.coverage_kind)}",
        f"- 数据截止：{result.data_cutoff}",
        f"- 分析 ID：{result.analysis_id}",
        "",
        "## 指标",
        "",
        "| 指标 | 金额 |",
        "| --- | --- |",
    ]
    for metric in result.metrics:
        lines.append(
            f"| {_METRIC_LABELS.get(metric.name, metric.name)} | "
            f"{_money(metric.amount_minor, result.currency)} |"
        )
    if result.groups:
        lines.extend(["", "## 分组", "", "| 分组 | 支出 | 收入 | 退款 |", "| --- | --- | --- | --- |"])
        for group in result.groups:
            label = str(
                group.get("bucket_label")
                or group.get("bucket1")
                or "未分类"
            )
            lines.append(
                f"| {label} | "
                f"{_money(int(group.get('expense_minor') or 0), result.currency)} | "
                f"{_money(int(group.get('income_minor') or 0), result.currency)} | "
                f"{_money(int(group.get('refund_received_minor') or 0), result.currency)} |"
            )
    if result.transactions:
        lines.extend([
            "", "## 明细（最多 50 笔）", "",
            "| 时间 | 商户 | 方向 | 金额 |", "| --- | --- | --- | --- |",
        ])
        for tx in result.transactions:
            lines.append(
                f"| {tx.occurred_at[:19]} | {tx.merchant or '—'} | {tx.direction} | "
                f"{_money(tx.amount_minor, tx.currency)} |"
            )
    if result.coverage.notes:
        lines.extend(["", "## 数据说明", ""])
        lines.extend(f"- {note}" for note in result.coverage.notes)
    if result.warnings:
        lines.extend(["", "## 计算提示", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _render_csv(result: AnalysisResult) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["指标", "金额（最小单位）", "金额", "货币"])
    for metric in result.metrics:
        writer.writerow([
            metric.name, metric.amount_minor,
            format_money(metric.amount_minor, result.currency), result.currency,
        ])
    writer.writerow([])
    labels = []
    if GROUP_BY_CATEGORY in result.plan.group_by:
        labels.append("分类")
    writer.writerow([*labels, "时间", "商户", "方向", "金额（最小单位）", "金额", "货币", "状态"])
    for tx in result.transactions:
        writer.writerow([
            *([str(tx.category_id or "")] if labels else []),
            tx.occurred_at, tx.merchant, tx.direction,
            tx.amount_minor, format_money(tx.amount_minor, tx.currency),
            tx.currency, tx.status,
        ])
    return buffer.getvalue().encode("utf-8-sig")


__all__ = ["SUPPORTED_FORMATS", "render_report"]
