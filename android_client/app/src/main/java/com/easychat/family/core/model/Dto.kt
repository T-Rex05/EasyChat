package com.easychat.family.core.model

import kotlinx.serialization.Serializable

/** 后端错误体(WP0 核验:AppError → {error, message, details?};chat busy → {error:str};FastAPI 兜底 detail)。 */
@Serializable
data class ApiErrorBody(
    val error: String = "",
    val message: String = "",
    val details: Map<String, String> = emptyMap(),
    val detail: String = "",
)

// ---- 认证(access/routes.py 实测字段) ----

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class LoginResponse(
    val ok: Boolean = false,
    val token: String = "",
    val user_id: Int = 0,
    val username: String = "",
    val role: String = "",
    val permissions: List<String> = emptyList(),
    val hermes_tools: List<String> = emptyList(),
)

@Serializable
data class MeResponse(
    val id: Int = 0,
    val username: String = "",
    val email: String = "",
    val role: String = "",
    val avatar: String = "",
    val status: Int = 0,
    val created_at: String = "",
    val permissions: List<String> = emptyList(),
    val capabilities: Capabilities = Capabilities(),
)

@Serializable
data class RefreshResponse(
    val ok: Boolean = false,
    val token: String = "",
    val user_id: Int = 0,
    val username: String = "",
    val role: String = "",
    val permissions: List<String> = emptyList(),
    val capabilities: Capabilities = Capabilities(),
)

/** capabilities(access/api.py::capabilities):模块 enabled/read/use/manage 是入口显隐唯一来源。 */
@Serializable
data class Capabilities(
    val modules: Map<String, ModuleCap> = emptyMap(),
    val tools: List<String> = emptyList(),
    val super_admin: Boolean = false,
    val permissions: List<String> = emptyList(),
) {
    val chatEnabled: Boolean get() = modules["chat"]?.use == true
    val memoryViewable: Boolean get() = modules["memory"]?.read == true
    val schedulingUsable: Boolean get() = modules["scheduling"]?.use == true
    val inboxViewable: Boolean get() = modules["inbox"]?.read == true
}

@Serializable
data class ModuleCap(
    val label: String = "",
    val enabled: Boolean = false,
    val read: Boolean = false,
    val use: Boolean = false,
    val manage: Boolean = false,
)

// ---- 历史(assistant/routes.py 实测:消息仅 role/content/created_at,无消息 ID) ----

@Serializable
data class SessionListResponse(
    val sessions: List<SessionDto> = emptyList(),
    val offset: Int = 0,
    val limit: Int = 50,
)

@Serializable
data class SessionDto(
    val session_id: String = "",
    val title: String = "",
    val source: String = "", // "web" | "wechat"
    val created_at: String = "",
    val updated_at: String = "",
)

@Serializable
data class HistoryMessagesResponse(
    val session_id: String = "",
    val messages: List<MessageDto> = emptyList(),
)

@Serializable
data class MessageDto(
    val role: String = "",
    val content: String = "",
    val created_at: String = "",
)

// ---- 聊天流(assistant/routes.py 实测) ----

@Serializable
data class StreamPostBody(
    val message: String,
    val thread_id: String,
    val client_msg_id: String = "",
    val attachment_ids: List<String> = emptyList(),
)

@Serializable
data class CancelResponse(
    val ok: Boolean = false,
    val cancelled: Boolean = false,
    val run_id: String = "",
)

// ---- 附件上传(compat.py:multipart 字段 files,1~10 个) ----

@Serializable
data class UploadedImage(
    val attachment_id: String = "",
    val file_id: String = "",
    val filename: String = "",
    val mime: String = "",
    val data_url: String = "",
)

@Serializable
data class UploadedFile(
    val attachment_id: String = "",
    val file_id: String = "",
    val filename: String = "",
    val size: Long = 0,
    val content_type: String = "",
    val readable: Boolean = false,
    val url: String = "",
)

// ---- 生活聚合(WP3 使用;scheduling/memory/inbox WP0 已核验) ----

@Serializable
data class ScheduleListResponse(val schedules: List<ScheduleDto> = emptyList())

@Serializable
data class ScheduleDto(
    val schedule_id: String = "",
    val title: String = "",
    val text: String = "",
    val kind: String = "", // once | interval | daily | weekly
    val interval_seconds: Int = 0,
    val at_time: String = "",
    val timezone: String = "",
    val next_run_at: Double = 0.0, // 秒级 epoch(XnTime.fromEpochSeconds)
    val enabled: Boolean = false,
    val last_run_at: String? = null,
    val weekday: Int = 0,
    val content_kind: String = "text",
    val briefing_kind: String = "",
    val target: ScheduleTarget = ScheduleTarget(),
)

@Serializable
data class ScheduleTarget(
    val kind: String = "",
    val ref: String = "",
    val channel_account_id: String = "",
)

@Serializable
data class MemoryListResponse(val memories: List<MemoryDto> = emptyList())

@Serializable
data class MemoryDto(
    val memory_id: String = "",
    val kind: String = "", // fact | preference | event | experience
    val content: String = "",
    val source_refs: List<SourceRefDto> = emptyList(),
    val scope: String = "user",
    val event_at: String? = null,
    val recorded_at: String = "",
    val version: Int = 1,
    val status: String = "active",
    val pinned: Boolean = false,
    val confidence: Float = 0.5f,
    val source_type: String = "model_inferred", // user_confirmed | model_inferred
    val tags: List<String> = emptyList(),
)

@Serializable
data class SourceRefDto(val kind: String = "", val ref: String = "", val quote: String = "")

@Serializable
data class InboxListResponse(val items: List<InboxItemDto> = emptyList())

@Serializable
data class InboxItemDto(
    val id: String = "",
    val kind: String = "",
    val title: String = "",
    val url: String = "",
    val file_id: String = "",
    val note: String = "",
    val summary: String = "",
    val tags: List<String> = emptyList(),
    val status: String = "",
    val enrich_state: String = "",
    val created_at: String = "",
    val updated_at: String = "",
)
