package com.easychat.family.feature.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnAvatar
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnPrimaryButton
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSageButton
import com.easychat.family.core.designsystem.XnSectionHeader
import com.easychat.family.core.designsystem.XnSizes
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag
import com.easychat.family.core.util.XnTime

/**
 * 今天(设计 §5.2):称呼问候 → 主图 → 问候语 → 两个大按钮 → 今日安排 →
 * 最近记下的事 → 最近微信对话。真实聚合(WP3):schedules/memory/history(source=wechat),
 * 各区块独立加载与重试,「更新于」为真实时间。
 */
@Composable
fun TodayScreen(
    onOpenChat: () -> Unit,
    onOpenLife: () -> Unit,
    onOpenWechatChat: (String) -> Unit,
    onRetry: () -> Unit = {},
) {
    val vm: TodayViewModel = viewModel()
    val state by vm.state.collectAsStateWithLifecycle()

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        XnRow(Modifier.fillMaxWidth()) {
            XnAvatar(state.username.take(1).ifBlank { "暖" })
            Column(Modifier.padding(start = XnSpacing.md)) {
                Text("${state.greeting},${state.username}", style = MaterialTheme.typography.titleLarge)
                XnUpdatedTag(
                    state.refreshedAt?.let { "更新于 ${hm(it)}" } ?: "正在更新…",
                )
            }
            Spacer(Modifier.weight(1f))
            XnIcon(R.drawable.ic_nav_life, contentDescription = "刷新", onClick = { vm.refresh() })
        }

        // 自然光主图占位(真实照片素材 WP5 前替换;占比 ≈首屏 22%)
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
                "自然光家居照片\n(占位)",
                Modifier.padding(XnSpacing.lg),
                color = Color(0xFF6D5D52),
                fontSize = 14.sp,
                lineHeight = 20.sp,
            )
        }

        Text("${state.greeting},今天过得怎么样?", style = MaterialTheme.typography.displaySmall)

        XnRow(Modifier.fillMaxWidth(), spacingDp = 12) {
            XnPrimaryButton("聊一聊", onOpenChat, Modifier.weight(1f))
            XnSageButton("看日程", onOpenLife, Modifier.weight(1f))
        }

        // 今日安排(真实 /api/schedules)
        XnSectionHeader("今天的安排", iconRes = R.drawable.ic_calendar, actionText = "查看日程", onAction = onOpenLife)
        when (val s = state.schedules) {
            is BlockState.Ready -> {
                val todayItems = s.data.filter { it.isToday }
                val upcoming = s.data.filterNot { it.isToday }
                if (todayItems.isEmpty() && upcoming.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text("今天还没有安排。想记点什么,随时告诉我。", style = MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    (todayItems + upcoming).take(2).forEach { item ->
                        XnCard(Modifier.fillMaxWidth(), onClick = onOpenLife) {
                            XnRow(Modifier.fillMaxWidth()) {
                                Text(
                                    item.timeText,
                                    style = MaterialTheme.typography.titleLarge,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                                Column(Modifier.padding(start = XnSpacing.lg)) {
                                    Text(item.title, style = MaterialTheme.typography.titleMedium)
                                    XnRow(verticalAlignment = Alignment.CenterVertically) {
                                        // 来源标签:P0 阶段 schedule 无来源字段(WP0 核验),只显示投递渠道,不虚构「微信里记下的」
                                        XnSourceChip(if (item.isToday) "今天" else "接下来")
                                        XnUpdatedTag("微信提醒")
                                    }
                                }
                                Spacer(Modifier.weight(1f))
                                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
                            }
                        }
                    }
                }
            }
            is BlockState.Error -> ErrorCard(s, onRetry)
            BlockState.Loading -> LoadingCard()
        }

        // 最近记下的事(真实 /api/memory,最多三条)
        XnSectionHeader("最近记下的事", iconRes = R.drawable.ic_note, actionText = "查看更多", onAction = onOpenLife)
        when (val m = state.memories) {
            is BlockState.Ready -> {
                if (m.data.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text("还没有记下的事。跟我说「记住…」,我就会帮你记住。", style = MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    XnCard(Modifier.fillMaxWidth()) {
                        m.data.forEach { memory ->
                            XnRow(Modifier.fillMaxWidth().padding(vertical = XnSpacing.sm)) {
                                XnIcon(R.drawable.ic_note, contentDescription = null)
                                Column(Modifier.padding(start = XnSpacing.md)) {
                                    Text(memory.content, style = MaterialTheme.typography.bodyLarge)
                                    XnUpdatedTag(memory.recordedAt)
                                }
                                Spacer(Modifier.weight(1f))
                                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
                            }
                        }
                    }
                }
            }
            is BlockState.Error -> ErrorCard(m, onRetry)
            BlockState.Loading -> LoadingCard()
        }

        // 最近微信对话(真实 /api/history source=wechat)
        XnSectionHeader("微信里的对话", iconRes = R.drawable.ic_nav_chat, actionText = "全部", onAction = onOpenChat)
        when (val w = state.wechat) {
            is BlockState.Ready -> {
                if (w.data.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text("微信里还没有聊过。绑定微信后,聊过的话会出现在这里。", style = MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    w.data.forEach { session ->
                        XnCard(Modifier.fillMaxWidth(), onClick = { onOpenWechatChat(session.session_id) }) {
                            XnRow(Modifier.fillMaxWidth()) {
                                XnSourceChip("微信")
                                Column(Modifier.padding(start = XnSpacing.md)) {
                                    Text(session.title.ifBlank { "微信对话" }, style = MaterialTheme.typography.titleMedium)
                                    XnUpdatedTag(XnTime.formatIso(session.updated_at))
                                }
                                Spacer(Modifier.weight(1f))
                                XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
                            }
                        }
                    }
                }
            }
            is BlockState.Error -> ErrorCard(w, onRetry)
            BlockState.Loading -> LoadingCard()
        }
        Spacer(Modifier.height(XnSpacing.sm))
    }
}

@Composable
private fun ErrorCard(error: BlockState.Error, onRetry: () -> Unit) {
    XnCard(Modifier.fillMaxWidth(), onClick = onRetry) {
        Text(error.text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
        Text("点这里重试", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
    }
}

@Composable
private fun LoadingCard() {
    XnCard(Modifier.fillMaxWidth()) {
        Text("正在读取…", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}


private fun hm(t: java.time.LocalDateTime): String =
    java.time.format.DateTimeFormatter.ofPattern("HH:mm").format(t)
