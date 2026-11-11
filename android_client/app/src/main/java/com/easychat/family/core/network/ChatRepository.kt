package com.easychat.family.core.network

import com.easychat.family.core.model.CancelResponse
import com.easychat.family.core.model.HistoryMessagesResponse
import com.easychat.family.core.model.MessageDto
import com.easychat.family.core.model.SessionDto
import com.easychat.family.core.model.SessionListResponse
import com.easychat.family.core.model.StreamPostBody
import kotlinx.coroutines.flow.Flow
import java.security.SecureRandom
import java.util.UUID

/**
 * 聊天域仓储(WP0 核验 assistant/routes.py):
 * - 历史响应无消息 ID:本地以整段快照替换投影,草稿独立存储(设计 §6.5);
 * - thread_id 兼容格式 `数字_数字`(毫秒+安全随机),canonical session_id 由服务端解析,
 *   start.conversation_id = run_id,两者分别保存(设计 §7.1);
 * - 幂等:同 client_msg_id 重复提交服务端返回原 run(设计 §7.2),恢复期间保持原正文。
 */
class ChatRepository(
    private val api: ApiClient,
    private val streams: ChatStreamClient,
) {

    suspend fun listSessions(offset: Int = 0, limit: Int = 50): List<SessionDto> =
        api.get<SessionListResponse>("/api/history?offset=$offset&limit=$limit").sessions

    suspend fun messages(sessionId: String): List<MessageDto> =
        api.get<HistoryMessagesResponse>("/api/history/${sessionId}").messages

    suspend fun rename(sessionId: String, title: String) {
        api.put<Map<String, String>, Map<String, String>>("/api/history/$sessionId", mapOf("title" to title))
    }

    suspend fun delete(sessionId: String) {
        api.delete<Map<String, String>>("/api/history/$sessionId")
    }

    /** 发起/恢复流。恢复时保持原 thread_id、client_msg_id、正文与附件(设计 §7.2)。 */
    fun stream(body: StreamPostBody, lastEventId: String? = null): Flow<ChatEventEnvelope> =
        streams.open(body, lastEventId)

    /** 停止:run_id 优先(响应含 cancelled 字段);回退 thread_id+client_msg_id。 */
    suspend fun cancel(runId: String, threadId: String = "", clientMsgId: String = ""): Boolean {
        val query = buildString {
            append("/chat/cancel?")
            if (runId.isNotBlank()) append("run_id=${url(runId)}")
            if (threadId.isNotBlank()) {
                if (isNotEmpty() && last() != '?') append('&')
                append("thread_id=${url(threadId)}")
            }
            if (clientMsgId.isNotBlank()) {
                if (isNotEmpty() && last() != '?') append('&')
                append("client_msg_id=${url(clientMsgId)}")
            }
        }
        return try {
            api.post<CancelResponse>(query).cancelled
        } catch (_: RequestFailure) {
            false
        }
    }

    fun consumedSeq(): Long? = streams.consumedSeq()

    companion object {
        private val random = SecureRandom()

        /** 首条消息 thread_id:毫秒时间戳 + 安全随机数字(设计 §7.1 兼容格式)。 */
        fun newThreadId(nowMs: Long = System.currentTimeMillis()): String =
            "${nowMs}_${(1 + random.nextInt(900_000) + 100_000)}"

        fun newClientMsgId(): String = "android-${UUID.randomUUID()}"

        private fun url(v: String): String =
            java.net.URLEncoder.encode(v, "UTF-8")
    }
}
