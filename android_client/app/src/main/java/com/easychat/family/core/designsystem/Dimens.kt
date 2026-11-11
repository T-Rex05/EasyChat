package com.easychat.family.core.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/** 间距(设计 §3.3:4/8/12/16/24/32,页面边距 20dp)。 */
object XnSpacing {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
    val page = 20.dp
}

/** 形状(设计 §3.3:卡片 20dp、弹层 28dp、输入区 24dp)。 */
val XnShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(20.dp),   // 卡片
    large = RoundedCornerShape(24.dp),    // 输入区
    extraLarge = RoundedCornerShape(28.dp), // 弹层
)

/** 触控与控件尺寸(设计 §3.3:点击区域 ≥48dp,主按钮 52~56dp)。 */
object XnSizes {
    val touchTarget = 48.dp
    val primaryButtonHeight = 54.dp
    val avatarSmall = 36.dp
    val assistantBubbleAvatar = 32.dp
    /** 首页主图占首屏比例目标 20%~25%(设计 §3.2),按 844dp 设计高估算。 */
    val heroHeight = 190.dp
}

/** 动效时长(设计 §3.3:点击 120ms、状态 180ms、页面过渡 240ms)。 */
object XnMotion {
    const val pressMs = 120
    const val stateMs = 180
    const val pageMs = 240
}
