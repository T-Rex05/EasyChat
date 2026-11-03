"""
LLM 自动生成会话标题 — 后台异步任务，失败静默

新会话入口落库后即调度（fire-and-forget），用一次低成本 LLM 调用生成标题，
写入 conversations.session_title（仅当仍为空），刷新后侧边栏显示。
开关：env AUTO_SESSION_TITLE=true|false（默认 true）。
"""
import asyncio
import os
from typing import Optional

from backend.utils.log_utils import log

logger = log

_TITLE_PROMPT = (
    "请为以下对话的第一条用户消息生成一个不超过15字的会话标题。"
    "只输出标题本身，不要引号、标点或解释。\n\n用户消息：{message}"
)


def auto_title_enabled() -> bool:
    """env AUTO_SESSION_TITLE 开关（默认开）。"""
    return os.getenv("AUTO_SESSION_TITLE", "true").strip().lower() in ("1", "true", "yes", "on")


def _clean_title(raw: str) -> str:
    """清洗 LLM 输出：去掉引号与换行，截断到 30 字符。"""
    title = (raw or "").strip()
    title = title.replace(chr(34), "")   # 双引号
    title = title.replace(chr(39), "")   # 单引号
    title = title.replace("\n", " ").replace("\r", " ").strip()
    return title[:30]


async def generate_title_with_llm(model_config: dict, message: str, timeout: float = 15.0) -> str:
    """调 LLM 生成标题（OpenAI 兼容 /chat/completions）。失败抛异常由上层静默。"""
    import httpx

    model = (model_config.get("model_name") or "").split("[")[0]  # 剥离 [128k] 等后缀
    base_url = (model_config.get("api_url") or "").rstrip("/")
    api_key = model_config.get("api_key") or ""
    if not base_url or not api_key or not model:
        return ""

    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个简洁的会话标题生成器。"},
            {"role": "user", "content": _TITLE_PROMPT.format(message=message[:500])},
        ],
        "max_tokens": 30,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    title = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return _clean_title(title)


async def auto_title_task(session_id: str, user_id: int, first_message: str) -> Optional[str]:
    """后台任务：生成标题并写入 conversations.session_title（仅当仍为空）。返回标题或 None。"""
    try:
        if not auto_title_enabled():
            return None
        from backend.controller.agent_controller import get_current_model_config
        from backend.service.scene_registry import scenes
        # 使用场景路由：title 场景，可配置最便宜的模型
        cfg = get_current_model_config(user_id, scene=scenes.TITLE)
        if not cfg or not cfg.get("api_key"):
            return None
        title = await generate_title_with_llm(cfg, first_message)
        if not title:
            return None

        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE conversations SET session_title = %s "
                "WHERE session_id = %s AND (session_title IS NULL OR session_title = '')",
                (title, session_id),
            )
            conn.commit()
        finally:
            conn.close()
        logger.debug(f"自动标题: {session_id} → {title}")
        return title
    except Exception as e:
        logger.warning(f"自动标题生成失败（静默）: {e}")
        return None


def schedule_auto_title(session_id: str, user_id: int, first_message: str):
    """在事件循环中调度标题任务（fire-and-forget，不阻塞主流程）。"""
    if not auto_title_enabled() or not session_id or not first_message:
        return None
    try:
        return asyncio.create_task(auto_title_task(session_id, user_id, first_message))
    except Exception:
        return None