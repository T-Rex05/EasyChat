package com.easychat.family.core.network

import com.easychat.family.core.model.OccurrenceDto
import com.easychat.family.core.model.OccurrenceListResponse
import com.easychat.family.core.model.ScheduleDto
import com.easychat.family.core.model.ScheduleListResponse

/**
 * 提醒管理(WP0 核验 scheduling/routes.py):
 * - 创建目标缺省解析用户微信绑定,无绑定 → 422「没有可用的微信绑定…」;
 * - 修改只有 enabled 开关;改时间 = 删除 + 新建(UI 明示);
 * - next_run_at 秒级 epoch(XnTime 转换)。
 */
class SchedulesRepository(private val api: ApiClient) {

    suspend fun list(): ScheduleListResponse = api.get("/api/schedules")

    suspend fun create(
        title: String,
        text: String,
        atLocal: java.time.LocalDateTime,
    ): ScheduleDto {
        // `at` 为 ISO 本地时间文本,按所传 timezone(默认 Asia/Shanghai)解析(WP0 核验 _parse_at)
        val iso = atLocal.format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"))
        val body = ScheduleCreateBody(
            title = title,
            text = text,
            at = iso,
        )
        val resp = api.post<ScheduleCreatedResponse, ScheduleCreateBody>("/api/schedules", body)
        return resp.schedule
    }

    suspend fun setEnabled(scheduleId: String, enabled: Boolean): ScheduleDto {
        val resp = api.patch<SchedulePatchedResponse, ScheduleStatusBody>(
            "/api/schedules/$scheduleId", ScheduleStatusBody(enabled),
        )
        return resp.schedule
    }

    suspend fun delete(scheduleId: String) {
        api.delete<Map<String, String>>("/api/schedules/$scheduleId")
    }

    suspend fun occurrences(scheduleId: String): List<OccurrenceDto> =
        api.get<OccurrenceListResponse>("/api/schedules/$scheduleId/occurrences").occurrences
}

@kotlinx.serialization.Serializable
data class ScheduleCreateBody(
    val title: String = "",
    val text: String = "",
    val at: String = "",
    val every_seconds: Int = 0,
    val daily_at: String = "",
    val weekly_at: String = "",
    val weekday: Int? = null,
    val timezone: String = "Asia/Shanghai",
    val content_kind: String = "text",
    val briefing_kind: String = "",
    val target_kind: String = "",
    val target_ref: String = "",
)

@kotlinx.serialization.Serializable
data class ScheduleStatusBody(val enabled: Boolean)

@kotlinx.serialization.Serializable
data class ScheduleCreatedResponse(val schedule: ScheduleDto)

@kotlinx.serialization.Serializable
data class SchedulePatchedResponse(val schedule: ScheduleDto)
