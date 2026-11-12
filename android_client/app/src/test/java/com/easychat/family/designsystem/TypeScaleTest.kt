package com.easychat.family.designsystem

import com.easychat.family.core.designsystem.XnTypography
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** 排版验收(设计 §3.3):行高 ≥ 字号,关键层级保持设计值。 */
class TypeScaleTest {

    @Test
    fun `页面标题 26sp 行高 34sp`() {
        val style = XnTypography.displaySmall
        assertEquals(26f, style.fontSize.value)
        assertEquals(34f, style.lineHeight.value)
    }

    @Test
    fun `卡片标题 20sp 行高 28sp`() {
        val style = XnTypography.titleLarge
        assertEquals(20f, style.fontSize.value)
        assertEquals(28f, style.lineHeight.value)
    }

    @Test
    fun `正文 17sp 行高 27sp,辅助 14sp 行高 20sp`() {
        assertEquals(17f, XnTypography.bodyLarge.fontSize.value)
        assertEquals(27f, XnTypography.bodyLarge.lineHeight.value)
        assertEquals(14f, XnTypography.bodyMedium.fontSize.value)
        assertEquals(20f, XnTypography.bodyMedium.lineHeight.value)
    }

    @Test
    fun `所有样式行高不小于字号`() {
        XnTypography.run {
            listOf(displaySmall, titleLarge, titleMedium, bodyLarge, bodyMedium, bodySmall, labelLarge, labelMedium, labelSmall)
        }.forEach { style ->
            assertTrue(
                "${style.fontSize} 行高 ${style.lineHeight} 应 ≥ 字号",
                style.lineHeight.value >= style.fontSize.value,
            )
        }
    }
}
