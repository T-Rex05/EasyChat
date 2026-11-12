package com.easychat.family.core.designsystem

/**
 * 设计 Token 单一来源(设计文档 §3.2)。
 *
 * 纯 Kotlin(不依赖 androidx):Compose 主题与单元测试(WCAG 对比度验收)
 * 消费同一份色值,避免主题与验收各自抄一份。
 */
object XnPalette {

    // ---- 浅色(设计文档 §3.2 表格原值) ----
    const val LIGHT_BG = 0xFFFFF8F0
    const val LIGHT_SURFACE = 0xFFFFFCF8
    const val LIGHT_PRIMARY = 0xFFA94E34
    const val LIGHT_ON_PRIMARY = 0xFFFFFFFF
    const val LIGHT_PRIMARY_CONTAINER = 0xFFF7DDCB
    const val LIGHT_ON_PRIMARY_CONTAINER = 0xFF5C2517
    const val LIGHT_SAGE_CONTAINER = 0xFFE8EDDF
    const val LIGHT_SAGE_TEXT = 0xFF46583B
    const val LIGHT_TEXT_PRIMARY = 0xFF3F3029
    const val LIGHT_TEXT_SECONDARY = 0xFF6D5D52
    const val LIGHT_OUTLINE = 0xFFE7D9CD
    const val LIGHT_ERROR = 0xFFA43B32

    // ---- 深色(保留暖色气质,设计文档 §3.2 建议 + 同族推导) ----
    const val DARK_BG = 0xFF211D19
    const val DARK_SURFACE = 0xFF2D2722
    const val DARK_PRIMARY = 0xFFF0AF91
    const val DARK_ON_PRIMARY = 0xFF4A2013
    const val DARK_PRIMARY_CONTAINER = 0xFF5A3325
    const val DARK_ON_PRIMARY_CONTAINER = 0xFFF7DDCB
    const val DARK_SAGE_CONTAINER = 0xFF2E3328
    const val DARK_SAGE_TEXT = 0xFFB9C7A8
    const val DARK_TEXT_PRIMARY = 0xFFF4E9DD
    const val DARK_TEXT_SECONDARY = 0xFFB5A697
    const val DARK_OUTLINE = 0xFF3F3830
    const val DARK_ERROR = 0xFFE8A79F

    /** WCAG 2.x 相对亮度(线性化),供对比度测试与运行时守卫共用。 */
    fun relativeLuminance(argb: Long): Double {
        val r = channelLuminance(((argb shr 16) and 0xFF).toInt())
        val g = channelLuminance(((argb shr 8) and 0xFF).toInt())
        val b = channelLuminance((argb and 0xFF).toInt())
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }

    /** WCAG 对比度比值(≥1)。正文验收 ≥4.5,大字与图形 ≥3(设计文档 §3.2)。 */
    fun contrastRatio(a: Long, b: Long): Double {
        val la = relativeLuminance(a)
        val lb = relativeLuminance(b)
        val lighter = maxOf(la, lb)
        val darker = minOf(la, lb)
        return (lighter + 0.05) / (darker + 0.05)
    }

    private fun channelLuminance(channel: Int): Double {
        val c = channel / 255.0
        return if (c <= 0.04045) c / 12.92 else Math.pow((c + 0.055) / 1.055, 2.4)
    }
}
