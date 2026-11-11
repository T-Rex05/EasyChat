package com.easychat.family.feature.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnAvatar
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnMockBadge
import com.easychat.family.core.designsystem.XnPrimaryButton
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag

/** 会话示例(来源来自 /api/history 的 source 字段;WP2 接真实数据)。 */
private data class SessionMock(
    val id: String,
    val title: String,
    val source: String, // "wechat" | "web"
    val time: String,
)

private val demoSessions = listOf(
    SessionMock("wx_demo_01", "明天下午三点提醒我取快递", "wechat", "今天 20:31"),
    SessionMock("wx_demo_02", "周末想做番茄炒蛋", "wechat", "昨天 20:12"),
    SessionMock("web_demo_01", "和小暖随便聊聊", "web", "今天 09:15"),
)

/** 聊天列表(设计 §5.3):标题、来源、时间;筛选 全部/微信/App。 */
@Composable
fun ChatListScreen(onOpenChat: (String) -> Unit, onOpenWechatChat: (String) -> Unit) {
    var filter by rememberSaveable { mutableStateOf("全部") }
    Column(
        Modifier.fillMaxSize().padding(horizontal = XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.md),
    ) {
        Row(Modifier.fillMaxWidth().padding(vertical = XnSpacing.md), verticalAlignment = Alignment.CenterVertically) {
            Text("聊天", Modifier.weight(1f), style = MaterialTheme.typography.displaySmall)
            XnMockBadge()
        }
        FilterChips(selected = filter, onSelect = { filter = it })
        LazyColumn(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
            items(demoSessions.filter {
                when (filter) {
                    "微信" -> it.source == "wechat"
                    "App" -> it.source == "web"
                    else -> true
                }
            }) { session ->
                XnCard(Modifier.fillMaxWidth(), onClick = {
                    if (session.source == "wechat") onOpenWechatChat(session.id) else onOpenChat(session.id)
                }) {
                    XnRow(Modifier.fillMaxWidth()) {
                        Column(Modifier.weight(1f)) {
                            Text(session.title, style = MaterialTheme.typography.titleMedium, maxLines = 2)
                            XnRow(verticalAlignment = Alignment.CenterVertically) {
                                XnSourceChip(if (session.source == "wechat") "微信" else "App")
                                XnUpdatedTag(session.time)
                            }
                        }
                        XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChips(selected: String, onSelect: (String) -> Unit) {
    XnRow {
        listOf("全部", "微信", "App").forEach { label ->
            val isSel = label == selected
            Surface(
                shape = CircleShape,
                color = if (isSel) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                contentColor = if (isSel) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                onClick = { onSelect(label) },
            ) {
                Text(
                    label,
                    Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.sm),
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            Spacer(Modifier.widthIn(min = 8.dp))
        }
    }
}

/** 对话消息示例(微信会话为只读查看;WP2 接真实历史与流式)。 */
private data class BubbleMock(val fromUser: Boolean, val text: String, val time: String)

private val wxDemoBubbles = listOf(
    BubbleMock(true, "明天下午三点提醒我取快递", "20:31"),
    BubbleMock(false, "好的,已记下:明天 15:00 取快递。到时候我会通过微信提醒你。", "20:31"),
)

private val appDemoBubbles = listOf(
    BubbleMock(true, "今天天气怎么样?", "09:15"),
    BubbleMock(false, "今天多云,15~22°C,适合出门走走。", "09:15"),
)

/**
 * 对话详情(设计 §5.3):暖杏用户气泡、奶白助手气泡、助手头像固定小尺寸;
 * 微信会话只读,底部「带着这段聊一聊」生成独立 App 会话草稿(发送前可编辑)。
 */
@Composable
fun ChatDetailScreen(
    sessionId: String,
    wechat: Boolean,
    onBack: () -> Unit,
    onContinueChat: () -> Unit,
) {
    var draft by rememberSaveable { mutableStateOf("") }
    val bubbles = if (wechat) wxDemoBubbles else appDemoBubbles
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding()) {
        // 顶栏
        XnRow(
            Modifier.fillMaxWidth().padding(horizontal = XnSpacing.page, vertical = XnSpacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            XnIcon(R.drawable.ic_back, contentDescription = "返回", onClick = onBack)
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    if (wechat) "微信对话" else "小暖",
                    style = MaterialTheme.typography.titleLarge,
                )
                if (wechat) XnSourceChip("微信里的对话")
            }
            Spacer(Modifier.widthIn(min = 48.dp))
        }

        // 消息区
        LazyColumn(
            Modifier.weight(1f).padding(horizontal = XnSpacing.page),
            verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
        ) {
            item { XnMockBadge(Modifier.padding(vertical = XnSpacing.sm)) }
            items(bubbles) { bubble ->
                if (bubble.fromUser) {
                    UserBubble(bubble)
                } else {
                    AssistantBubble(bubble)
                }
            }
            if (!wechat) {
                item {
                    XnRow(verticalAlignment = Alignment.CenterVertically) {
                        XnAvatarSmall()
                        Text(
                            "正在想一想…",
                            Modifier.padding(start = XnSpacing.md),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        // 底部:微信=只读 + 带着这段聊一聊;App=输入区(流式时变为停止,WP2)
        if (wechat) {
            Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
                XnPrimaryButton(
                    "带着这段聊一聊",
                    onContinueChat,
                    Modifier.fillMaxWidth().padding(XnSpacing.page),
                )
            }
        } else {
            InputBar(draft = draft, onDraftChange = { draft = it }, onSend = {})
        }
    }
}

@Composable
private fun XnAvatarSmall() {
    Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer) {
        Box(Modifier.height(32.dp).widthIn(min = 32.dp), contentAlignment = Alignment.Center) {
            XnIcon(R.drawable.ic_launcher_foreground, contentDescription = null, modifier = Modifier.height(20.dp))
        }
    }
}

@Composable
private fun UserBubble(bubble: BubbleMock) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End) {
        Surface(
            shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        ) {
            Text(
                bubble.text,
                Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.md)
                    .widthIn(max = 280.dp),
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        XnUpdatedTag(bubble.time, Modifier.padding(top = XnSpacing.xs, end = XnSpacing.xs))
    }
}

@Composable
private fun AssistantBubble(bubble: BubbleMock) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.Start) {
        XnRow(verticalAlignment = Alignment.Top) {
            XnAvatarSmall()
            Surface(
                shape = MaterialTheme.shapes.medium,
                color = MaterialTheme.colorScheme.surface,
                contentColor = MaterialTheme.colorScheme.onSurface,
                border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                modifier = Modifier.padding(start = XnSpacing.md),
            ) {
                Text(
                    bubble.text,
                    Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.md)
                        .widthIn(max = 280.dp),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        XnUpdatedTag(bubble.time, Modifier.padding(top = XnSpacing.xs, start = 44.dp))
    }
}

@Composable
private fun InputBar(draft: String, onDraftChange: (String) -> Unit, onSend: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        XnRow(
            Modifier.fillMaxWidth().padding(XnSpacing.page),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            XnIcon(R.drawable.ic_plus, contentDescription = "添加附件", onClick = {})
            OutlinedTextField(
                value = draft,
                onValueChange = onDraftChange,
                placeholder = { Text("和小暖聊一聊…") },
                shape = MaterialTheme.shapes.large,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MaterialTheme.colorScheme.primary,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outline,
                ),
                modifier = Modifier.weight(1f).padding(horizontal = XnSpacing.md).heightIn(min = 52.dp),
            )
            XnIcon(
                R.drawable.ic_send,
                contentDescription = "发送",
                onClick = onSend,
            )
        }
    }
}
