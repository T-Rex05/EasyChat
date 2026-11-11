package com.easychat.family.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private fun c(argb: Long) = Color(argb.toInt())

private val LightScheme = ColorScheme(
    primary = c(XnPalette.LIGHT_PRIMARY),
    onPrimary = c(XnPalette.LIGHT_ON_PRIMARY),
    primaryContainer = c(XnPalette.LIGHT_PRIMARY_CONTAINER),
    onPrimaryContainer = c(XnPalette.LIGHT_ON_PRIMARY_CONTAINER),
    inversePrimary = c(XnPalette.DARK_PRIMARY),
    secondary = c(XnPalette.LIGHT_SAGE_TEXT),
    onSecondary = c(XnPalette.LIGHT_ON_PRIMARY),
    secondaryContainer = c(XnPalette.LIGHT_SAGE_CONTAINER),
    onSecondaryContainer = c(XnPalette.LIGHT_SAGE_TEXT),
    tertiary = c(XnPalette.LIGHT_PRIMARY),
    onTertiary = c(XnPalette.LIGHT_ON_PRIMARY),
    tertiaryContainer = c(XnPalette.LIGHT_SAGE_CONTAINER),
    onTertiaryContainer = c(XnPalette.LIGHT_SAGE_TEXT),
    background = c(XnPalette.LIGHT_BG),
    onBackground = c(XnPalette.LIGHT_TEXT_PRIMARY),
    surface = c(XnPalette.LIGHT_SURFACE),
    onSurface = c(XnPalette.LIGHT_TEXT_PRIMARY),
    surfaceVariant = c(0xFFF4EAE0),
    onSurfaceVariant = c(XnPalette.LIGHT_TEXT_SECONDARY),
    surfaceTint = c(XnPalette.LIGHT_PRIMARY),
    inverseSurface = c(XnPalette.DARK_SURFACE),
    inverseOnSurface = c(XnPalette.DARK_TEXT_PRIMARY),
    error = c(XnPalette.LIGHT_ERROR),
    onError = c(XnPalette.LIGHT_ON_PRIMARY),
    errorContainer = c(0xFFF6DCD8),
    onErrorContainer = c(0xFF6B231C),
    outline = c(XnPalette.LIGHT_OUTLINE),
    outlineVariant = c(XnPalette.LIGHT_OUTLINE),
    scrim = c(0xFF3F3029),
    surfaceBright = c(XnPalette.LIGHT_SURFACE),
    surfaceDim = c(0xFFF2E9DF),
    surfaceContainer = c(0xFFFAF3EA),
    surfaceContainerHigh = c(XnPalette.LIGHT_SURFACE),
    surfaceContainerHighest = c(XnPalette.LIGHT_SURFACE),
    surfaceContainerLow = c(0xFFF8F1E8),
    surfaceContainerLowest = c(XnPalette.LIGHT_SURFACE),
)

private val DarkScheme = ColorScheme(
    primary = c(XnPalette.DARK_PRIMARY),
    onPrimary = c(XnPalette.DARK_ON_PRIMARY),
    primaryContainer = c(XnPalette.DARK_PRIMARY_CONTAINER),
    onPrimaryContainer = c(XnPalette.DARK_ON_PRIMARY_CONTAINER),
    inversePrimary = c(XnPalette.LIGHT_PRIMARY),
    secondary = c(XnPalette.DARK_SAGE_TEXT),
    onSecondary = c(XnPalette.DARK_ON_PRIMARY),
    secondaryContainer = c(XnPalette.DARK_SAGE_CONTAINER),
    onSecondaryContainer = c(XnPalette.DARK_SAGE_TEXT),
    tertiary = c(XnPalette.DARK_PRIMARY),
    onTertiary = c(XnPalette.DARK_ON_PRIMARY),
    tertiaryContainer = c(XnPalette.DARK_SAGE_CONTAINER),
    onTertiaryContainer = c(XnPalette.DARK_SAGE_TEXT),
    background = c(XnPalette.DARK_BG),
    onBackground = c(XnPalette.DARK_TEXT_PRIMARY),
    surface = c(XnPalette.DARK_SURFACE),
    onSurface = c(XnPalette.DARK_TEXT_PRIMARY),
    surfaceVariant = c(0xFF352E28),
    onSurfaceVariant = c(XnPalette.DARK_TEXT_SECONDARY),
    surfaceTint = c(XnPalette.DARK_PRIMARY),
    inverseSurface = c(XnPalette.LIGHT_SURFACE),
    inverseOnSurface = c(XnPalette.LIGHT_TEXT_PRIMARY),
    error = c(XnPalette.DARK_ERROR),
    onError = c(XnPalette.DARK_ON_PRIMARY),
    errorContainer = c(0xFF4A2822),
    onErrorContainer = c(XnPalette.DARK_ERROR),
    outline = c(XnPalette.DARK_OUTLINE),
    outlineVariant = c(XnPalette.DARK_OUTLINE),
    scrim = c(0xFF171310),
    surfaceBright = c(0xFF36302A),
    surfaceDim = c(XnPalette.DARK_BG),
    surfaceContainer = c(0xFF322B25),
    surfaceContainerHigh = c(XnPalette.DARK_SURFACE),
    surfaceContainerHighest = c(XnPalette.DARK_SURFACE),
    surfaceContainerLow = c(0xFF2A241F),
    surfaceContainerLowest = c(XnPalette.DARK_SURFACE),
)

/** 小暖主题:浅/深两套暖色(设计 §3.2),排版与形状见 [XnTypography]/[XnShapes]。 */
@Composable
fun XnTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkScheme else LightScheme,
        typography = XnTypography,
        shapes = XnShapes,
        content = content,
    )
}

/** sage 辅助色语义访问(提醒/保存状态底色,设计 §3.2 sageContainer/sageText)。 */
object XnSage {
    val container: Color
        @Composable get() = MaterialTheme.colorScheme.secondaryContainer
    val text: Color
        @Composable get() = MaterialTheme.colorScheme.onSecondaryContainer
}
