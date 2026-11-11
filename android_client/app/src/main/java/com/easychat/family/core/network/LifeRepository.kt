package com.easychat.family.core.network

import com.easychat.family.core.model.InboxListResponse
import com.easychat.family.core.model.MemoryListResponse
import com.easychat.family.core.model.ScheduleListResponse
import com.easychat.family.core.model.SessionDto

/**
 * 生活聚合仓储(设计 §6.3 基本查看版):直接调用各模块公开读取接口,
 * 各区块独立错误状态;模块关闭/权限不足由调用方按 ApiError 呈现。
 */
class LifeRepository(private val api: ApiClient) {

    suspend fun schedules(): ScheduleListResponse = api.get("/api/schedules")

    suspend fun memories(): MemoryListResponse = api.get("/api/memory")

    suspend fun inbox(limit: Int = 50): InboxListResponse = api.get("/api/inbox?limit=$limit")

    suspend fun wechatSessions(limit: Int = 10): List<SessionDto> =
        api.get<SessionListResponseContainer>("/api/history?offset=0&limit=$limit")
            .sessions.filter { it.source == "wechat" }

    /** 微信绑定状态(我的页):只展示当前身份可读字段。 */
    suspend fun bindings(): BindingsResponse = api.get("/api/channels/bindings")
}

@kotlinx.serialization.Serializable
data class SessionListResponseContainer(val sessions: List<SessionDto> = emptyList())

@kotlinx.serialization.Serializable
data class BindingsResponse(val bindings: List<BindingDto> = emptyList())

@kotlinx.serialization.Serializable
data class BindingDto(
    val id: String = "",
    val platform: String = "",
    val account_id: String = "",
    val external_user_id: String = "",
    val user_id: Int = 0,
    val status: Int = 0,
)
