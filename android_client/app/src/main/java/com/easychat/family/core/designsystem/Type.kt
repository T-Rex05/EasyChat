package com.easychat.family.core.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * 排版系统(设计 §3.3):系统中文字体优先、离线可用;字号/行高按设计表固定,
 * 关键信息随系统字体缩放(sp 天然缩放)。
 *
 * 对应关系:
 *   displaySmall = 页面标题 26sp/34sp medium
 *   titleLarge   = 卡片标题 20sp/28sp medium
 *   bodyLarge    = 正文     17sp/27sp regular
 *   bodyMedium   = 辅助文字 14sp/20sp regular
 *   labelLarge   = 按钮/标签 15sp/20sp medium
 */
val XnTypography = Typography(
    displaySmall = TextStyle(
        fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Medium,
    ),
    titleLarge = TextStyle(
        fontSize = 20.sp, lineHeight = 28.sp, fontWeight = FontWeight.Medium,
    ),
    titleMedium = TextStyle(
        fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.Medium,
    ),
    bodyLarge = TextStyle(
        fontSize = 17.sp, lineHeight = 27.sp, fontWeight = FontWeight.Normal,
    ),
    bodyMedium = TextStyle(
        fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Normal,
    ),
    bodySmall = TextStyle(
        fontSize = 12.sp, lineHeight = 17.sp, fontWeight = FontWeight.Normal,
    ),
    labelLarge = TextStyle(
        fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium,
    ),
    labelMedium = TextStyle(
        fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium,
    ),
    labelSmall = TextStyle(
        fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium,
    ),
)
