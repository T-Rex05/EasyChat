package com.easychat.family.feature.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnAvatar
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnMockBadge
import com.easychat.family.core.designsystem.XnPrimaryButton
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSageButton
import com.easychat.family.core.designsystem.XnSectionHeader
import com.easychat.family.core.designsystem.XnSizes
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag

/**
 * 今天(设计 §5.2):称呼问候 → 主图 → 问候语 → 两个大按钮 → 今日安排 →
 * 最近记下的事 → 最近微信对话。WP1 为示例数据(WP3 接入真实聚合)。
 */
@Composable
fun TodayScreen(
    onOpenChat: () -> Unit,
    onOpenLife: () -> Unit,
    onOpenWechatChat: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        // 顶部:头像 + 称呼 + 示例标记
        XnRow(Modifier.fillMaxWidth()) {
            XnAvatar("兰")
            Column(Modifier.padding(start = XnSpacing.md)) {
                Text("晚上好,秀兰阿姨", style = MaterialTheme.typography.titleLarge)
                XnUpdatedTag("更新于 20:36")
            }
            Spacer(Modifier.weight(1f))
            XnMockBadge()
        }

        // 自然光主图占位(WP1:暖色渐变占位,真实照片素材 WP5 前替换;占比按设计 20~25%)
        Box(
            Modifier.fillMaxWidth().height(XnSizes.heroHeight).clip(MaterialTheme.shapes.medium),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier.fillMaxSize().background(
                    Brush.verticalGradient(
                        listOf(Color(0xFFF6E3CF), Color(0xFFEAD3BC), Color(0xFFDCC5A8)),
                    ),
                ),
            )
            Text(
                "自然光家居照片\n(占位,示例数据)",
                Modifier.padding(XnSpacing.lg),
                color = Color(0xFF6D5D52),
                fontSize = 14.sp,
                lineHeight = 20.sp,
            )
        }

        Text(
            "晚上好,今天过得怎么样?",
            style = MaterialTheme.typography.displaySmall,
        )

        // 两个大按钮(设计 §5.2:聊一聊 / 看日程)
        XnRow(Modifier.fillMaxWidth(), spacingDp = 12) {
            XnPrimaryButton("聊一聊", onOpenChat, Modifier.weight(1f))
            XnSageButton("看日程", onOpenLife, Modifier.weight(1f))
        }

        // 今日安排(首屏至少一条真实安排;WP3 接 /api/schedules)
        XnSectionHeader("今天的安排", iconRes = R.drawable.ic_calendar, actionText = "查看日程", onAction = onOpenLife)
        XnCard(Modifier.fillMaxWidth(), onClick = onOpenLife) {
            XnRow(Modifier.fillMaxWidth()) {
                Text(
                    "15:00",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Medium,
                )
                Column(Modifier.padding(start = XnSpacing.lg)) {
                    Text("取快递", style = MaterialTheme.typography.titleMedium)
                    XnRow(verticalAlignment = Alignment.CenterVertically) {
                        XnSourceChip("微信里记下的")
                        XnUpdatedTag("微信提醒")
                    }
                }
                Spacer(Modifier.weight(1f))
                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
            }
        }
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth()) {
                Text(
                    "18:30",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Column(Modifier.padding(start = XnSpacing.lg)) {
                    Text("准备晚饭", style = MaterialTheme.typography.titleMedium)
                    XnRow(verticalAlignment = Alignment.CenterVertically) {
                        XnSourceChip("微信里记下的")
                        XnUpdatedTag("微信提醒")
                    }
                }
                Spacer(Modifier.weight(1f))
                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
            }
        }

        // 最近记下的事(最多三条,设计 §5.2;WP3 接 /api/memory)
        XnSectionHeader("最近记下的事", iconRes = R.drawable.ic_note, actionText = "查看更多", onAction = onOpenLife)
        XnCard(Modifier.fillMaxWidth()) {
            MemoryRow("周末想做番茄炒蛋", "昨天 20:12")
            MemoryRow("晚饭喜欢清淡一些", "周二 18:40")
        }

        // 最近微信对话(WP3 接 /api/history?source=wechat)
        XnSectionHeader("微信里的对话", iconRes = R.drawable.ic_nav_chat, actionText = "全部", onAction = onOpenChat)
        XnCard(Modifier.fillMaxWidth(), onClick = onOpenWechatChat) {
            XnRow(Modifier.fillMaxWidth()) {
                XnSourceChip("微信")
                Column(Modifier.padding(start = XnSpacing.md)) {
                    Text("明天下午三点提醒我取快递", style = MaterialTheme.typography.titleMedium)
                    XnUpdatedTag("今天 20:31")
                }
                Spacer(Modifier.weight(1f))
                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
            }
        }
        Spacer(Modifier.height(XnSpacing.sm))
    }
}

@Composable
private fun MemoryRow(content: String, time: String) {
    XnRow(Modifier.fillMaxWidth().padding(vertical = XnSpacing.sm)) {
        XnIcon(R.drawable.ic_note, contentDescription = null)
        Column(Modifier.padding(start = XnSpacing.md)) {
            Text(content, style = MaterialTheme.typography.bodyLarge)
            XnUpdatedTag(time)
        }
        Spacer(Modifier.weight(1f))
        XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
    }
}
