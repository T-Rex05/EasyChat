package com.easychat.family.util

import com.easychat.family.core.util.XnTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * 时间契约(后端核验 WP0):next_run_at 为秒级 epoch;ISO 文本按 UTC 解析、
 * 用户时区展示;时区固定 Asia/Shanghai 验证(设计 §7)。
 */
class XnTimeTest {

    private val zone: ZoneId = ZoneId.of("Asia/Shanghai")
    private val now = LocalDateTime.of(2026, 11, 11, 20, 36)

    @Test
    fun `秒级 epoch 转用户时区`() {
        // 后端给秒级 epoch(scheduling/contracts.py);+08:00 的 2026-11-12 15:00
        // == UTC 07:00。用计算值验证 Instant.ofEpochSecond(秒)语义,不硬编码手算常量。
        val epochSeconds = LocalDateTime.of(2026, 11, 12, 15, 0)
            .atZone(zone).toEpochSecond()
        assertEquals(LocalDateTime.of(2026, 11, 12, 15, 0), XnTime.fromEpochSeconds(epochSeconds, zone))
        // 毫秒误用(差 1000 倍)必须暴露出来:把毫秒值当秒会指向远未来
        val asMillis = LocalDateTime.of(2026, 11, 12, 15, 0)
            .atZone(zone).toInstant().toEpochMilli()
        assertTrue(XnTime.fromEpochSeconds(asMillis, zone).year > 10000)
    }

    @Test
    fun `今天与明天的提醒文案`() {
        val todayAt = now.toLocalDate().atTime(15, 0)
            .atZone(zone).toInstant().toEpochMilli() / 1000
        val tomorrowAt = now.toLocalDate().plusDays(1).atTime(15, 0)
            .atZone(zone).toInstant().toEpochMilli() / 1000
        assertEquals("今天 15:00", XnTime.formatNextRun(todayAt, zone, now))
        assertEquals("明天 15:00", XnTime.formatNextRun(tomorrowAt, zone, now))
    }

    @Test
    fun `一周内显示星期,更远显示日期`() {
        val thursday = now.toLocalDate().plusDays(4).atTime(9, 30)
            .atZone(zone).toInstant().toEpochMilli() / 1000
        val nextMonth = now.toLocalDate().plusDays(20).atTime(8, 0)
            .atZone(zone).toInstant().toEpochMilli() / 1000
        assertEquals("周日 09:30", XnTime.formatNextRun(thursday, zone, now))
        assertTrue(XnTime.formatNextRun(nextMonth, zone, now).contains("月"))
    }

    @Test
    fun `无时区后缀的 ISO 按 UTC 解析`() {
        // 后端 created_at 形如 "2026-11-11T04:31:00"(UTC 无后缀)→ 上海 12:31
        assertEquals("12:31", XnTime.formatIso("2026-11-11T04:31:00", zone, now))
        // 同日时间只显示 HH:mm;不同日显示 月日+时间
        assertEquals("11月10日 20:31", XnTime.formatIso("2026-11-10T12:31:00Z", zone, now))
    }

    @Test
    fun `问候语按时段`() {
        assertEquals("早上好", XnTime.greeting(6))
        assertEquals("中午好", XnTime.greeting(12))
        assertEquals("下午好", XnTime.greeting(15))
        assertEquals("晚上好", XnTime.greeting(20))
        assertEquals("晚上好", XnTime.greeting(2))
    }
}
