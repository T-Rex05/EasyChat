package com.easychat.family.core.network

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** 服务端 SSE 事件(帧 data JSON;WP0 核验 assistant/routes.py)。 */
@Serializable
data class SseData(
    val type: String = "",
    val content: String = "",
    val thread_id: String = "",
    val conversation_id: String = "",
    val final_content: String = "",
    val message: String = "",
    val error: String = "",
)

sealed interface ChatEvent {
    /** start:thread_id 为客户端原值,conversation_id = 服务端 run_id(两者都要保存)。 */
    data class Start(val threadId: String, val runId: String) : ChatEvent
    data class Token(val text: String) : ChatEvent
    data class Thinking(val text: String) : ChatEvent
    data object StreamReset : ChatEvent
    /** chat_complete:final_content 为最终正文,与流式累积内容核对。 */
    data class Complete(val finalContent: String) : ChatEvent
    data class Failed(val message: String) : ChatEvent
}

/** 带序号的事件 envelopes;seq 即 SSE id,恢复时作为 Last-Event-ID 传回(服务端 +1)。 */
data class ChatEventEnvelope(val seq: Long?, val event: ChatEvent)

object ChatEventCodec {
    private val json = Json { ignoreUnknownKeys = true }

    fun decode(data: String): ChatEvent? = try {
        val d = json.decodeFromString<SseData>(data)
        when (d.type) {
            "start" -> ChatEvent.Start(d.thread_id, d.conversation_id)
            "token" -> ChatEvent.Token(d.content)
            "thinking_step" -> ChatEvent.Thinking(d.content)
            "stream_reset" -> ChatEvent.StreamReset
            "chat_complete" -> ChatEvent.Complete(d.final_content)
            "error" -> ChatEvent.Failed(d.message.ifBlank { d.error.ifBlank { "出了点小问题,请稍后再试" } })
            else -> null // 未知事件:记录诊断并忽略,保持已知流程可运行(设计 §7.2)
        }
    } catch (_: Exception) {
        null
    }
}
