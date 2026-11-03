"""命令黑名单 AI 辅助生成服务

管理员用中文描述想拦截的行为，LLM 生成正则 + 正反例。
"""
import json
import re
from typing import Dict, Any

from backend.utils.log_utils import log

logger = log


# 参照 Hermes DANGEROUS_PATTERNS 的写法风格，挑几条有代表性的做 few-shot
_STYLE_EXAMPLES = r"""
参照下面几条内置规则的写法风格（词边界 \b、区分参数位置、避免只按子串裸匹配导致误伤）：

1. 递归删除：r'\brm\s+(-[^\s]*\s+)*/'  说明："delete in root path"
2. 覆盖系统配置：r'>\s*(?:/etc/|...)'  说明："overwrite system config"（用 >\s* 锚定"写入"这个动作，
   而不是只要命令里出现路径字符串就命中）
3. SQL 无 WHERE 的 DELETE：r'\bDELETE\s+FROM\b(?![^\n]*\bWHERE\b)'  说明："SQL DELETE without WHERE"
   （用负向前瞻排除掉带 WHERE 的安全用法，而不是见 DELETE FROM 就拦）

核心原则：
- 用 \b 做词边界，避免把普通单词里包含关键词的子串也匹配上（例如别把文件名里含 "rm" 的词也拦住）。
- 尽量区分"这个路径/参数是读还是写目标"，只在确实构成危险操作时命中，不要见关键词就拦。
- 大小写不敏感由外层统一处理，正则本身不需要写 (?i)。
""".strip()


def _extract_json_object(text_value: str) -> Dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象。"""
    match = re.search(r"\{.*\}", text_value, flags=re.S)
    if not match:
        raise ValueError("模型输出中未找到 JSON 内容")
    return json.loads(match.group(0))


def _strip_raw_string_wrapper(pattern: str) -> str:
    """剥掉 LLM 可能输出的 Python r'...' 原始字符串包裹。"""
    raw_string_wrap = re.compile(r"^r?(['\"])(.*)\1$", re.S)
    match = raw_string_wrap.match(pattern)
    return match.group(2) if match else pattern


def generate_pattern_suggestion(description: str, user_id: int) -> Dict[str, Any]:
    """调用当前用户配置的 LLM，为一条命令黑名单规则起草正则 + 正反例。

    返回 {"pattern": str, "should_match": [str,...], "should_not_match": [str,...]}。
    """
    description = (description or "").strip()
    if not description:
        raise ValueError("请先填写这条规则要拦截的命令行为描述")

    prompt = (
        "你是一个终端命令安全审查助手，负责把管理员用中文描述的\"想拦截的危险命令行为\"，"
        "转成一条 Python re 语法的正则表达式草稿，用于命令执行前的黑名单拦截。\n\n"
        f"{_STYLE_EXAMPLES}\n\n"
        f"管理员的描述：{description}\n\n"
        "请只输出严格的 JSON（不要 Markdown 代码块，不要任何解释文字）。"
        "pattern 字段的值必须是正则表达式本身的纯文本，不要加 Python 的 r'...'/r\"...\" 原始字符串"
        "包裹或任何额外引号——例如要写 \\brm\\s+/data，而不是 r'\\brm\\s+/data' 或 \"\\\\brm\\\\s+/data\"。"
        "格式：\n"
        '{"pattern": "正则表达式字符串", '
        '"should_match": ["应该被这条正则命中的示例命令，2~3条"], '
        '"should_not_match": ["容易被误伤、但不应该被命中的示例命令，2~3条"]}'
    )

    try:
        from backend.utils.traced_llm import traced_llm
        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="command_blacklist",
            user_id=int(user_id or 0),
            source="admin",
            temperature=0,
            max_tokens=2048,
        )
        text_value = (resp.content or "").strip()
    except Exception as e:
        logger.error(f"[CommandBlacklistAI] LLM 调用失败: {e}")
        raise RuntimeError(f"LLM 调用失败: {e}")

    try:
        result = _extract_json_object(text_value)
    except Exception as e:
        logger.error(f"[CommandBlacklistAI] 解析失败: raw={text_value[:500]!r} error={e}")
        raise RuntimeError("模型返回内容无法解析为规则建议，请重试或换一种描述方式") from e

    pattern = str(result.get("pattern") or "").strip()
    pattern = _strip_raw_string_wrapper(pattern)
    if not pattern:
        raise RuntimeError("模型未能生成有效的正则表达式，请重试或换一种描述方式")

    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise RuntimeError(f"模型生成的正则不合法：{e}")

    should_match = [str(x) for x in (result.get("should_match") or []) if str(x).strip()]
    should_not_match = [str(x) for x in (result.get("should_not_match") or []) if str(x).strip()]

    return {
        "pattern": pattern,
        "should_match": should_match,
        "should_not_match": should_not_match,
    }
