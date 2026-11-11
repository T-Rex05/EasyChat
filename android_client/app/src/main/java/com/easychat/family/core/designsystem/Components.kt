package com.easychat.family.core.designsystem

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/** 基础卡片:1dp 暖色边线 + 轻阴影(设计 §3.2),统一内容内边距 16dp。 */
@Composable
fun XnCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    contentPadding: PaddingValues = PaddingValues(XnSpacing.lg),
    content: @Composable ColumnScope.() -> Unit,
) {
    val border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
    if (onClick != null) {
        Card(
            modifier = modifier,
            onClick = onClick,
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            border = border,
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) { Column(Modifier.padding(contentPadding), content = content) }
    } else {
        Card(
            modifier = modifier,
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            border = border,
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) { Column(Modifier.padding(contentPadding), content = content) }
    }
}

/** 主要按钮(高度 54dp,主色填充,文字对比已由主题保证)。 */
@Composable
fun XnPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        modifier = modifier.heightIn(min = XnSizes.primaryButtonHeight),
        enabled = enabled,
        shape = MaterialTheme.shapes.large,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

/** sage 辅助按钮(看日程等次级入口)。 */
@Composable
fun XnSageButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.heightIn(min = XnSizes.primaryButtonHeight),
        enabled = enabled,
        shape = MaterialTheme.shapes.large,
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = XnSage.container,
            contentColor = XnSage.text,
        ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

/** 区块标题 + 可选「查看更多」。 */
@Composable
fun XnSectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    iconRes: Int? = null,
    actionText: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Row(
        modifier = modifier.fillMaxWidth().heightIn(min = XnSizes.touchTarget),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (iconRes != null) {
                XnIcon(iconRes, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.size(XnSpacing.sm))
            }
            Text(title, style = MaterialTheme.typography.titleLarge)
        }
        if (actionText != null && onAction != null) {
            TextButton(onClick = onAction) {
                Text(actionText, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/**
 * 来源/状态胶囊(sage 底色):「微信里记下的」「已保存」等。
 * 来源标签只能来自已验证的服务端字段(WP4 前客户端不虚构)。
 */
@Composable
fun XnSourceChip(text: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.extraSmall,
        color = XnSage.container,
        contentColor = XnSage.text,
    ) {
        Text(
            text,
            Modifier.padding(horizontal = XnSpacing.sm, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

/** 模拟数据标记(WP1 验收要求:示例内容必须显式可见)。 */
@Composable
fun XnMockBadge(modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = CircleShape,
        color = Color.Transparent,
        contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Text(
            "示例数据",
            Modifier.padding(horizontal = XnSpacing.md, vertical = XnSpacing.xs),
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

/** 空状态(图标 + 主句 + 提示,文案见设计 §3.4)。 */
@Composable
fun XnEmptyState(
    iconRes: Int,
    title: String,
    hint: String? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier.fillMaxWidth().padding(vertical = XnSpacing.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(XnSpacing.sm),
    ) {
        XnIcon(iconRes, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        if (hint != null) {
            Text(
                hint,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/** 「更新于 HH:mm」等状态角标。 */
@Composable
fun XnUpdatedTag(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        modifier = modifier,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** 圆形文字头像。 */
@Composable
fun XnAvatar(label: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.size(XnSizes.avatarSmall),
        shape = CircleShape,
        color = MaterialTheme.colorScheme.primaryContainer,
        contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
    ) {
        androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** 线性图标统一入口(矢量资源统一圆角线性风格,设计 §3.2);带 onClick 时保证 48dp 触控。 */
@Composable
fun XnIcon(
    resId: Int,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.primary,
    contentDescription: String? = null,
    onClick: (() -> Unit)? = null,
) {
    if (onClick != null) {
        androidx.compose.foundation.layout.Box(
            modifier
                .size(48.dp)
                .clickable(onClickLabel = contentDescription, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Image(
                painter = painterResource(resId),
                contentDescription = contentDescription,
                modifier = Modifier.size(24.dp),
                colorFilter = androidx.compose.ui.graphics.ColorFilter.tint(tint),
            )
        }
    } else {
        Image(
            painter = painterResource(resId),
            contentDescription = contentDescription,
            modifier = modifier.size(24.dp),
            colorFilter = androidx.compose.ui.graphics.ColorFilter.tint(tint),
        )
    }
}

/** 水平布局速记:带默认间距的 Row。 */
@Composable
fun XnRow(
    modifier: Modifier = Modifier,
    spacingDp: Int = 8,
    verticalAlignment: Alignment.Vertical = Alignment.CenterVertically,
    content: @Composable RowScope.() -> Unit,
) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(spacingDp.dp), verticalAlignment = verticalAlignment, content = content)
}
