"""微信监听器 - Hermes Agent 决策调用

让微信聊天与 Web 聊天走同一套 Hermes AIAgent 决策引擎
（支持工具调用、技能、多轮记忆、多模态），替代原先的纯 LLM 直连
（backend/controller/wechat/llm.py，已删除）。

设计要点：
- thread_id 直接复用微信会话 ID（``wx_{user_id}_{openid*}``），与 Web 会话
  天然隔离，Hermes 内部按 thread_id 从 SessionDB 恢复完整历史，实现多轮记忆。
- 微信没有审批 UI，通过 ``disabled_toolsets={"terminal"}`` 禁用 terminal
  工具集，从根源杜绝危险命令（file/web/memory 等只读与安全工具仍可用）。
- 微信非流式：不传 thread_queue，直接取最终 final_response，再由 handler
  做 ``_strip_md`` + 分块投递。
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentforge.wechat_listener")

# 微信端禁用的工具集（无审批 UI，危险命令直接不可用）
_WECHAT_DISABLED_TOOLSETS = {"terminal"}


async def run_wechat_hermes(
    user_id: int,
    thread_id: str,
    message: str,
    images: Optional[List[Dict[str, str]]] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 Hermes Agent 决策，返回 ``{"final_response": str, "error": str}``。

    Args:
        user_id: AgentForge 用户 ID。
        thread_id: 微信会话 ID（``wx_...``），作为 Hermes 会话粒度。
        message: 有效消息文本（已注入文件内容，可为空——仅图片场景）。
        images: 微信侧已解密好的图片列表 ``[{"data_url": "...", "mime": "..."}]``。
        username: 当前登录用户名，注入 Hermes 用户上下文。

    返回:
        ``final_response`` 为最终答案（原始 Markdown，DB 存储原始值），
        ``error`` 非空表示调用失败（未配置模型 / 模型不支持图片 / 异常）。
    """
    result: Dict[str, Any] = {"final_response": "", "error": ""}

    from backend.controller.agent_controller import get_current_model_config
    from backend.agents.prompts import get_decision_system_prompt
    from backend.hermes_adapter import get_runtime
    from backend.permission.checker import get_user_hermes_tools

    model_config = get_current_model_config(user_id)
    if not model_config:
        result["error"] = "未配置 LLM 模型，请先在系统配置中设置"
        return result

    has_images = bool(images)
    effective_message: Any = message

    # ── 多模态：图片转 content_blocks（与 Web token_stream_events 一致）──
    if has_images:
        from backend.utils.multimodal_detect import check_model_multimodal
        if not check_model_multimodal(model_config):
            result["error"] = "当前模型不支持图片识别，请切换到多模态模型"
            return result
        content_blocks: List[Dict[str, Any]] = [
            {"type": "text", "text": message or "请描述这张图片"}
        ]
        for img in images:
            data_url = img.get("data_url", "")
            if not data_url:
                continue
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        effective_message = content_blocks if len(content_blocks) > 1 else message

    # ── 动态系统提示词 + 工具集授权（与 Web 一致）──
    available_tools = get_user_hermes_tools(user_id)
    decision_prompt = get_decision_system_prompt(
        user_id=user_id, available_tools=available_tools,
    )

    # ── 取/建 Hermes 运行时（微信禁用 terminal，杜绝危险命令）──
    runtime = get_runtime(
        user_id, model_config, decision_prompt,
        thread_id=thread_id, username=username,
        disabled_toolsets=_WECHAT_DISABLED_TOOLSETS,
    )

    try:
        hermes_result = await runtime.run(
            user_message=effective_message,
            history=None,         # Hermes 内部按 thread_id 从 SessionDB 恢复完整历史
            thread_queue=None,    # 微信非流式，直接取最终结果
            mode="normal",
        )
    except Exception as e:
        logger.error(f"[微信] Hermes 决策失败: {e}", exc_info=True)
        result["error"] = f"处理出错：{e}"
        return result

    result["final_response"] = hermes_result.get("final_response", "") or ""
    return result


def persist_wechat_conversation(
    session_id: str,
    user_id: int,
    question: str,
    answer: str,
) -> Optional[int]:
    """落库微信对话（``source='wechat'``），走与 Web 一致的 conversation_mapper。

    与 Web 持久化使用同一数据访问层，仅 source 标记不同，保证历史列表、
    会话切换等下游逻辑对两种渠道行为一致。
    """
    from backend.controller.chat.persistence import conversation_mapper

    if not conversation_mapper:
        logger.warning("[微信] conversation_mapper 未初始化，跳过落库")
        return None
    try:
        return conversation_mapper.insert_conversation(
            session_id=session_id,
            user_id=user_id,
            user_question=question,
            agent_answer=answer,
            status=1,
            chat_mode="normal",
            source="wechat",
        )
    except Exception as e:
        logger.error(f"[微信] 落库失败: {e}")
        return None
