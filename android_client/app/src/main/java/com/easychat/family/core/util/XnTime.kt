package com.easychat.family.core.util

import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * 时间展示工具,对齐真实后端契约(WP0 核验):
 * - `next_run_at` 为**秒级 epoch float**(scheduling/contracts.py::ScheduleView);
 * - 历史/记录时间为 ISO-8601 文本(UTC)。
 * 界面展示用户时区,默认 Asia/Shanghai(设计 §1)。
 */
object XnTime {

    val DEFAULT_ZONE: ZoneId = ZoneId.of("Asia/Shanghai")

    private val hm = DateTimeFormatter.ofPattern("HH:mm")
    private val md = DateTimeFormatter.ofPattern("M月d日")
    private val full = DateTimeFormatter.ofPattern("M月d日 HH:mm")

    /** 秒级 epoch → 用户时区时间。显式按秒转换,避免秒/毫秒混用(设计 §7 要求)。 */
    fun fromEpochSeconds(epochSeconds: Long, zone: ZoneId = DEFAULT_ZONE): LocalDateTime =
        LocalDateTime.ofInstant(Instant.ofEpochSecond(epochSeconds), zone)

    /**
     * 下次提醒时间文案:「今天 15:00」「明天 15:00」「周四 15:00」「11月20日 15:00」。
     * [now] 由调用方传入(可注入测试);未来计划在 UI 层加「预计提醒」前缀(设计 §5.4)。
     */
    fun formatNextRun(epochSeconds: Long, zone: ZoneId = DEFAULT_ZONE, now: LocalDateTime): String {
        val target = fromEpochSeconds(epochSeconds, zone)
        val hmText = hm.format(target)
        return when {
            target.toLocalDate() == now.toLocalDate() -> "今天 $hmText"
            target.toLocalDate() == now.toLocalDate().plusDays(1) -> "明天 $hmText"
            target.isBefore(now.plusDays(7)) -> "${weekdayCn(target.dayOfWeek.value)} $hmText"
            else -> "${md.format(target)} $hmText"
        }
    }

    /** ISO 时间文本 → 用户时区展示:同日 HH:mm,否则「M月d日 HH:mm」。 */
    fun formatIso(iso: String?, zone: ZoneId = DEFAULT_ZONE, now: LocalDateTime = LocalDateTime.now(zone)): String {
        if (iso.isNullOrBlank()) return ""
        return try {
            val t = LocalDateTime.ofInstant(Instant.parse(normalizeIso(iso)), zone)
            if (t.toLocalDate() == now.toLocalDate()) hm.format(t) else full.format(t)
        } catch (_: Exception) {
            ""
        }
    }

    /** 后端可能给 "2026-11-11T12:00:00"(无时区后缀)或带 Z/偏移;统一按 UTC 解析。 */
    private fun normalizeIso(iso: String): String = when {
        iso.endsWith("Z") || iso.contains("+") || iso.matches(Regex(""".*-\d{2}:\d{2}$""")) -> iso
        else -> "${iso}Z"
    }

    /** 问候语(设计 §3.4)。 */
    fun greeting(hour: Int): String = when (hour) {
        in 5..8 -> "早上好"
        in 9..11 -> "上午好"
        in 12..13 -> "中午好"
        in 14..17 -> "下午好"
        else -> "晚上好"
    }

    private fun weekdayCn(isoDay: Int): String = when (isoDay) {
        1 -> "周一"; 2 -> "周二"; 3 -> "周三"; 4 -> "周四"; 5 -> "周五"; 6 -> "周六"; else -> "周日"
    }
}
