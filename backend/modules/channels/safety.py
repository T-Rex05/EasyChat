"""入站安全兜底：危机表达用固定资源回复，不交给模型自由发挥。"""
from __future__ import annotations

import re

# 只匹配明确的自伤/轻生表达；排除「想死你了」这类口语。
CRISIS_RE = re.compile(
    r"自杀|轻生|不想活|活不下去|结束生命|伤害自己|自残|想死(?!你)|死了算了"
)

CRISIS_REPLY = (
    "我听到你现在很难受。请先保证自己的安全：如果可能马上伤害自己，"
    "请立刻拨打 120 或 110，或去最近的急诊，并联系一个可信任的人陪着你。\n"
    "全国心理援助热线：12356（24 小时，免费）。\n"
    "你不用一个人扛着，等安全下来再回来找我。"
)


def detect_crisis(text: str) -> bool:
    return bool(CRISIS_RE.search(text or ""))
