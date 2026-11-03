"""报告质量检查（借鉴 Eyes report_quality）

cron 报告生成后的轻量质量门禁：空/过短/未闭合代码块/重复段落。
质量不达标不阻断投递，仅标注提示（issues 附在投递正文前）。
"""
from typing import Dict, List

MIN_LEN = 50
MAX_REPEATED_LINES = 3


def check_report(text: str, min_len: int = MIN_LEN) -> Dict[str, object]:
    """检查报告质量，返回 {"ok": bool, "issues": [str]}。"""
    issues: List[str] = []
    content = (text or "").strip()
    if not content:
        return {"ok": False, "issues": ["报告内容为空"]}
    if len(content) < min_len:
        issues.append(f"报告过短（{len(content)} 字符 < {min_len}）")
    # 未闭合代码块
    if content.count("```") % 2 != 0:
        issues.append("存在未闭合的代码块（```）")
    # 重复行检查（超过 N 次出现）
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    seen: Dict[str, int] = {}
    for ln in lines:
        if len(ln) > 4:
            seen[ln] = seen.get(ln, 0) + 1
    repeated = [ln[:30] for ln, n in seen.items() if n > MAX_REPEATED_LINES]
    if repeated:
        issues.append(f"重复段落: {', '.join(repeated[:3])}{'...' if len(repeated) > 3 else ''}")
    return {"ok": not issues, "issues": issues}