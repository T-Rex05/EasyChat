package com.easychat.family.feature.chat

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.easychat.family.app.XiaoNuanApplication
import com.easychat.family.core.model.MessageDto
import com.easychat.family.core.model.SessionDto
import com.easychat.family.core.model.StreamPostBody
import com.easychat.family.core.network.ChatEvent
import com.easychat.family.core.network.ChatEventEnvelope
import com.easychat.family.core.network.ChatRepository
import com.easychat.family.core.network.RequestFailure
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * 聊天状态机(设计 §8.3):
 * draft → submitting → streaming → completed;
 * 分支 recovering(断流自动恢复 1/2/4/8s,上限 4 次)、cancel_requested、cancelled、failed。
 * 历史无消息 ID:刷新时以整段快照替换(设计 §6.5),草稿按会话独立保存。
 */
data class UiMessage(
    val id: String,
    val role: String, // user | assistant
    val content: String,
    val createdAt: String,
)

enum class ChatPhase { IDLE, SUBMITTING, STREAMING, RECOVERING, CANCEL_REQUESTED, COMPLETED, CANCELLED, FAILED }

data class ChatDetailState(
    val sessionId: String = "",      // canonical sess_…(进入已有会话时有值)
    val threadId: String = "",       // 本地会话键(legacy 格式或 sess_…)
    val runId: String = "",
    val clientMsgId: String = "",
    val messages: List<UiMessage> = emptyList(),
    val draft: String = "",
    val phase: ChatPhase = ChatPhase.IDLE,
    val statusText: String = "",
    val errorText: String = "",
    val loadingHistory: Boolean = false,
) {
    val busy: Boolean get() = phase in setOf(
        ChatPhase.SUBMITTING, ChatPhase.STREAMING, ChatPhase.RECOVERING, ChatPhase.CANCEL_REQUESTED,
    )
}

class ChatViewModel(app: Application) : AndroidViewModel(app) {

    private val container = (app as XiaoNuanApplication).container
    private val repo: ChatRepository = container.chat

    private val _detail = MutableStateFlow(ChatDetailState())
    val detail: StateFlow<ChatDetailState> = _detail.asStateFlow()

    private val _sessions = MutableStateFlow<List<SessionDto>>(emptyList())
    val sessions: StateFlow<List<SessionDto>> = _sessions.asStateFlow()

    private val _sessionsLoading = MutableStateFlow(false)
    val sessionsLoading: StateFlow<Boolean> = _sessionsLoading.asStateFlow()

    private val _sessionsError = MutableStateFlow("")
    val sessionsError: StateFlow<String> = _sessionsError.asStateFlow()

    private var streamJob: Job? = null
    private var lastSeq: Long? = null
    private var attempts = 0

    fun loadSessions(offset: Int = 0) {
        viewModelScope.launch {
            _sessionsLoading.value = true
            _sessionsError.value = ""
            try {
                val list = repo.listSessions(offset = offset)
                _sessions.value = if (offset == 0) list else _sessions.value + list
            } catch (failure: RequestFailure) {
                _sessionsError.value = friendly(failure)
            } finally {
                _sessionsLoading.value = false
            }
        }
    }

    /** 进入已有会话(canonical session_id;微信来源由路由参数另管)。 */
    fun openExisting(sessionId: String) {
        _detail.value = ChatDetailState(sessionId = sessionId, threadId = sessionId)
        refreshHistory()
    }

    /** 新建 App 对话:thread_id 用兼容格式,canonical 会话由服务端解析(设计 §7.1)。 */
    fun openNew() {
        _detail.value = ChatDetailState(threadId = ChatRepository.newThreadId())
    }

    /** 带着微信这段聊一聊:预填可编辑背景草稿,发送才提交(设计 §5.3)。 */
    fun openNewWithQuote(quote: String) {
        _detail.value = ChatDetailState(
            threadId = ChatRepository.newThreadId(),
            draft = "我们刚才在微信聊到:\n$quote\n\n接着这个继续说:",
        )
    }

    fun refreshHistory() {
        val sessionId = _detail.value.sessionId
        if (sessionId.isBlank()) return
        viewModelScope.launch {
            _detail.value = _detail.value.copy(loadingHistory = true)
            try {
                val messages = repo.messages(sessionId)
                _detail.value = _detail.value.copy(
                    loadingHistory = false,
                    messages = messages.map { UiMessage("${it.role}-${it.created_at}", it.role, it.content, it.created_at) },
                )
            } catch (failure: RequestFailure) {
                _detail.value = _detail.value.copy(loadingHistory = false, errorText = friendly(failure))
            }
        }
    }

    fun onDraftChange(v: String) {
        _detail.value = _detail.value.copy(draft = v)
    }

    /** 发送:恢复期保持原 client_msg_id 与正文;编辑后用新 id(设计 §7.2)。 */
    fun send() {
        val s = _detail.value
        val text = s.draft.trim()
        if (text.isEmpty() || s.busy) return
        val resume = s.phase == ChatPhase.RECOVERING
        val clientMsgId = if (resume && s.clientMsgId.isNotBlank()) s.clientMsgId else ChatRepository.newClientMsgId()
        val body = StreamPostBody(
            message = text,
            thread_id = s.threadId,
            client_msg_id = clientMsgId,
        )
        attempts = 0
        lastSeq = null
        val userMsg = UiMessage(
            id = "u-$clientMsgId", role = "user", content = text,
            createdAt = com.easychat.family.core.util.XnTime.formatIso(null),
        )
        _detail.value = s.copy(
            clientMsgId = clientMsgId,
            draft = "",
            messages = if (resume) _detail.value.messages else _detail.value.messages + userMsg,
            phase = ChatPhase.SUBMITTING,
            statusText = "正在想一想",
            errorText = "",
        )
        startStream(body)
    }

    private fun startStream(body: StreamPostBody, lastEventId: String? = null) {
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            repo.stream(body, lastEventId).collect { envelope ->
                onEvent(body, envelope)
            }
            // Flow 正常结束且未收到终态:断流,进入恢复
            val st = _detail.value
            if (st.busy && st.phase != ChatPhase.CANCEL_REQUESTED) {
                enterRecovering(body)
            }
        }
    }

    private suspend fun onEvent(body: StreamPostBody, envelope: ChatEventEnvelope) {
        envelope.seq?.let { lastSeq = it }
        when (val e = envelope.event) {
            is ChatEvent.Start -> {
                _detail.value = _detail.value.copy(runId = e.runId, phase = ChatPhase.STREAMING, statusText = "")
                if (e.threadId.isNotBlank() && e.threadId != _detail.value.threadId) {
                    _detail.value = _detail.value.copy(threadId = e.threadId)
                }
                // canonical session 解析:新会话首条消息后即可从列表读回(sess_…)
                if (_detail.value.sessionId.isBlank()) resolveSessionId()
            }
            is ChatEvent.Token -> appendStreamingToken(e.text)
            is ChatEvent.Thinking -> _detail.value = _detail.value.copy(statusText = shortThinking(e.text))
            is ChatEvent.StreamReset -> resetStreaming()
            is ChatEvent.Complete -> {
                val st = _detail.value
                _detail.value = st.copy(
                    phase = ChatPhase.COMPLETED,
                    statusText = "",
                    messages = replaceStreamingFinal(st.messages, e.finalContent),
                )
            }
            is ChatEvent.Failed -> {
                val st = _detail.value
                if (st.phase == ChatPhase.CANCEL_REQUESTED) {
                    _detail.value = st.copy(phase = ChatPhase.CANCELLED, statusText = "", errorText = "")
                } else {
                    _detail.value = st.copy(phase = ChatPhase.FAILED, statusText = "", errorText = e.message)
                }
            }
        }
    }

    private suspend fun enterRecovering(body: StreamPostBody) {
        if (attempts >= 4) {
            _detail.value = _detail.value.copy(
                phase = ChatPhase.FAILED,
                statusText = "",
                errorText = "连接暂时断开了,你写的内容还在。点发送可以再试一次",
            )
            return
        }
        attempts += 1
        val backoff = (1L shl (attempts - 1)) * 1000 // 1/2/4/8s(设计 §7.2)
        _detail.value = _detail.value.copy(phase = ChatPhase.RECOVERING, statusText = "连接暂时断开了,正在恢复…")
        delay(backoff)
        if (_detail.value.phase == ChatPhase.RECOVERING) {
            startStream(body, lastSeq?.toString())
        }
    }

    private suspend fun resolveSessionId() {
        // 新会话:从会话列表里按最新匹配 thread 的标题定位 canonical id(轻量兜底,WP3 换契约)
        try {
            val sessions = repo.listSessions(limit = 10)
            sessions.firstOrNull()?.let { if (it.source == "web") _detail.value = _detail.value.copy(sessionId = it.session_id) }
        } catch (_: Exception) {
        }
    }

    private fun appendStreamingToken(text: String) {
        val st = _detail.value
        val list = st.messages.toMutableList()
        val last = list.lastOrNull()
        if (last != null && last.id == STREAMING_ID) {
            list[list.lastIndex] = last.copy(content = last.content + text)
        } else {
            list.add(UiMessage(STREAMING_ID, "assistant", text, ""))
        }
        _detail.value = st.copy(messages = list)
    }

    private fun resetStreaming() {
        val st = _detail.value
        val list = st.messages.filterNot { it.id == STREAMING_ID }
        _detail.value = st.copy(messages = list)
    }

    private fun replaceStreamingFinal(messages: List<UiMessage>, finalContent: String): List<UiMessage> {
        val list = messages.toMutableList()
        val idx = list.indexOfFirst { it.id == STREAMING_ID }
        if (idx >= 0) {
            list[idx] = list[idx].copy(content = finalContent.ifBlank { list[idx].content })
        } else if (finalContent.isNotBlank()) {
            list.add(UiMessage("a-final-${System.currentTimeMillis()}", "assistant", finalContent, ""))
        }
        return list
    }

    /** 用户明确点击停止:请求服务端取消,再按实际终态收尾(设计 §7.3)。 */
    fun cancel() {
        val st = _detail.value
        if (!st.busy) return
        _detail.value = st.copy(phase = ChatPhase.CANCEL_REQUESTED, statusText = "正在停止…")
        viewModelScope.launch {
            val ok = repo.cancel(st.runId, st.threadId, st.clientMsgId)
            if (!ok) {
                // 未找到进行中的请求:直接按本地状态收尾
                _detail.value = _detail.value.copy(phase = ChatPhase.CANCELLED, statusText = "")
            }
        }
    }

    fun clearError() {
        _detail.value = _detail.value.copy(errorText = "")
    }

    private fun shortThinking(text: String): String = when {
        text.length > 24 -> text.take(24) + "…"
        text.isBlank() -> "正在想一想"
        else -> text
    }

    private fun friendly(failure: RequestFailure): String = when (failure) {
        is RequestFailure.Http -> failure.error.displayText()
        is RequestFailure.Network -> "连接暂时断开了,请稍后再试"
        RequestFailure.Cancelled -> ""
    }

    companion object {
        private const val STREAMING_ID = "streaming-assistant"
    }
}
