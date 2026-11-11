package com.easychat.family.designsystem

import com.easychat.family.core.designsystem.XnPalette
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 视觉验收(设计 §3.2):正文组合 ≥4.5:1,大字与交互图形 ≥3:1。
 * 这些是验收目标,主题改动必须让本测试继续为真。
 */
class ContrastTest {

    private fun assertAtLeast(fg: Long, bg: Long, min: Double, label: String) {
        val ratio = XnPalette.contrastRatio(fg, bg)
        assertTrue("$label 对比度 $ratio 应 ≥ $min", ratio >= min)
    }

    // ---- 浅色 ----

    @Test
    fun `正文与背景对比达标(浅色)`() {
        assertAtLeast(XnPalette.LIGHT_TEXT_PRIMARY, XnPalette.LIGHT_BG, 4.5, "textPrimary/background")
        assertAtLeast(XnPalette.LIGHT_TEXT_PRIMARY, XnPalette.LIGHT_SURFACE, 4.5, "textPrimary/surface")
        assertAtLeast(XnPalette.LIGHT_TEXT_SECONDARY, XnPalette.LIGHT_BG, 4.5, "textSecondary/background")
        assertAtLeast(XnPalette.LIGHT_SAGE_TEXT, XnPalette.LIGHT_SAGE_CONTAINER, 4.5, "sageText/sageContainer")
        assertAtLeast(XnPalette.LIGHT_ON_PRIMARY_CONTAINER, XnPalette.LIGHT_PRIMARY_CONTAINER, 4.5, "onPrimaryContainer/primaryContainer")
    }

    @Test
    fun `主要操作与图形对比达标(浅色)`() {
        assertAtLeast(XnPalette.LIGHT_PRIMARY, XnPalette.LIGHT_BG, 3.0, "primary/background(交互图形)")
        assertAtLeast(XnPalette.LIGHT_ON_PRIMARY, XnPalette.LIGHT_PRIMARY, 3.0, "onPrimary/primary(按钮文字按 4.5 验证)")
        assertTrue(
            "按钮文字应按正文标准 ≥4.5",
            XnPalette.contrastRatio(XnPalette.LIGHT_ON_PRIMARY, XnPalette.LIGHT_PRIMARY) >= 4.5,
        )
        assertAtLeast(XnPalette.LIGHT_ERROR, XnPalette.LIGHT_BG, 3.0, "error/background")
    }

    // ---- 深色 ----

    @Test
    fun `正文与背景对比达标(深色)`() {
        assertAtLeast(XnPalette.DARK_TEXT_PRIMARY, XnPalette.DARK_BG, 4.5, "textPrimary/background")
        assertAtLeast(XnPalette.DARK_TEXT_PRIMARY, XnPalette.DARK_SURFACE, 4.5, "textPrimary/surface")
        assertAtLeast(XnPalette.DARK_TEXT_SECONDARY, XnPalette.DARK_BG, 4.5, "textSecondary/background")
        assertAtLeast(XnPalette.DARK_TEXT_SECONDARY, XnPalette.DARK_SURFACE, 4.5, "textSecondary/surface")
        assertAtLeast(XnPalette.DARK_SAGE_TEXT, XnPalette.DARK_SAGE_CONTAINER, 4.5, "sageText/sageContainer")
    }

    @Test
    fun `主要操作与图形对比达标(深色)`() {
        assertAtLeast(XnPalette.DARK_PRIMARY, XnPalette.DARK_BG, 3.0, "primary/background")
        assertTrue(
            "按钮文字应按正文标准 ≥4.5",
            XnPalette.contrastRatio(XnPalette.DARK_ON_PRIMARY, XnPalette.DARK_PRIMARY) >= 4.5,
        )
        assertAtLeast(XnPalette.DARK_ERROR, XnPalette.DARK_SURFACE, 3.0, "error/surface")
    }
}
