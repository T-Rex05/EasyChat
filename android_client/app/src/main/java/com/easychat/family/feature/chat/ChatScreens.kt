package com.easychat.family.feature.chat

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnAvatar
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnEmptyState
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnPrimaryButton
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag
import com.easychat.family.core.util.XnTime

/** 聊天列表(设计 §5.3):标题、来源、时间;筛选 全部/微信/App;数据来自 /api/history。 */
@Composable
fun ChatListScreen(
    vm: ChatViewModel,
    onOpenChat: (String) -> Unit,
    onNewChat: () -> Unit,
) {
    var filter by rememberSaveable { mutableStateOf("全部") }
    val sessions by vm.sessions.collectAsStateWithLifecycle()
    val loading by vm.sessionsLoading.collectAsStateWithLifecycle()
    val error by vm.sessionsError.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) { vm.loadSessions() }

    Column(Modifier.fillMaxSize().padding(horizontal = XnSpacing.page)) {
        Row(Modifier.fillMaxWidth().padding(vertical = XnSpacing.md), verticalAlignment = Alignment.CenterVertically) {
            Text("聊天", Modifier.weight(1f), style = MaterialTheme.typography.displaySmall)
            XnIcon(R.drawable.ic_plus, contentDescription = "新对话", onClick = onNewChat)
        }
        FilterChips(selected = filter, onSelect = { filter = it })
        if (error.isNotBlank()) {
            Text(
                error,
                Modifier.padding(vertical = XnSpacing.sm),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
            )
        }
        val filtered = sessions.filter {
            when (filter) {
                "微信" -> it.source == "wechat"
                "App" -> it.source == "web"
                else -> true
            }
        }
        if (filtered.isEmpty() && !loading && error.isBlank()) {
            XnEmptyState(
                iconRes = R.drawable.ic_nav_chat,
                title = "还没有对话",
                hint = "点右上角 + 开启和小暖的第一次聊天;微信里聊过的也会出现在这里。",
            )
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
            items(filtered, key = { it.session_id }) { session ->
                XnCard(Modifier.fillMaxWidth(), onClick = { onOpenChat(session.session_id) }) {
                    XnRow(Modifier.fillMaxWidth()) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                session.title.ifBlank { "未命名对话" },
                                style = MaterialTheme.typography.titleMedium,
                                maxLines = 2,
                            )
                            XnRow(verticalAlignment = Alignment.CenterVertically) {
                                XnSourceChip(if (session.source == "wechat") "微信" else "App")
                                XnUpdatedTag(XnTime.formatIso(session.updated_at))
                            }
                        }
                        XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
                    }
                }
            }
            if (loading) {
                item {
                    Row(Modifier.fillMaxWidth().padding(XnSpacing.lg), horizontalArrangement = Arrangement.Center) {
                        CircularProgressIndicator(Modifier.height(24.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChips(selected: String, onSelect: (String) -> Unit) {
    XnRow(Modifier.padding(bottom = XnSpacing.sm)) {
        listOf("全部", "微信", "App").forEach { label ->
            val isSel = label == selected
            Surface(
                shape = CircleShape,
                color = if (isSel) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                contentColor = if (isSel) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
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

/**
 * 对话详情(设计 §5.3/§8.3):流式状态机 UI——正在想一想/流式正文/恢复中/停止;
 * 微信会话只读,底部「带着这段聊一聊」生成独立 App 会话可编辑草稿。
 */
@Composable
fun ChatDetailScreen(
    vm: ChatViewModel,
    wechat: Boolean,
    onBack: () -> Unit,
    onContinueChat: () -> Unit,
) {
    val state by vm.detail.collectAsStateWithLifecycle()
    val listState = rememberLazyListState()
    var manualScroll by remember { mutableStateOf(false) }

    // 新消息自动到底;用户上滑阅读时保持位置(设计 §5.3)
    LaunchedEffect(state.messages.size, state.phase) {
        if (!manualScroll) {
            listState.animateScrollToItem((state.messages.size - 1).coerceAtLeast(0))
        }
    }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding()) {
        XnRow(
            Modifier.fillMaxWidth().padding(horizontal = XnSpacing.page, vertical = XnSpacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            XnIcon(R.drawable.ic_back, contentDescription = "返回", onClick = onBack)
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(if (wechat) "微信对话" else "小暖", style = MaterialTheme.typography.titleLarge)
                if (wechat) XnSourceChip("微信里的对话")
            }
            Spacer(Modifier.widthIn(min = 48.dp))
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).padding(horizontal = XnSpacing.page),
            verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
        ) {
            if (state.loadingHistory) {
                item {
                    Row(Modifier.fillMaxWidth().padding(XnSpacing.lg), horizontalArrangement = Arrangement.Center) {
                        CircularProgressIndicator()
                    }
                }
            }
            items(state.messages, key = { it.id }) { message ->
                if (message.role == "user") UserBubble(message) else AssistantBubble(message)
            }
            if (state.statusText.isNotBlank()) {
                item {
                    XnRow(verticalAlignment = Alignment.CenterVertically) {
                        XnAvatarSmall()
                        Text(
                            state.statusText,
                            Modifier.padding(start = XnSpacing.md),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        if (state.errorText.isNotBlank() && !wechat) {
            Surface(
                Modifier.fillMaxWidth().padding(horizontal = XnSpacing.page, vertical = XnSpacing.sm),
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.errorContainer,
                contentColor = MaterialTheme.colorScheme.onErrorContainer,
            ) {
                XnRow(Modifier.padding(XnSpacing.md)) {
                    Text(state.errorText, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    TextButtonLabel("知道了", onClick = vm::clearError)
                }
            }
        }

        if (wechat) {
            Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
                XnPrimaryButton(
                    "带着这段聊一聊",
                    onContinueChat,
                    Modifier.fillMaxWidth().padding(XnSpacing.page),
                )
            }
        } else {
            InputBar(
                draft = state.draft,
                busy = state.busy,
                onDraftChange = vm::onDraftChange,
                onSend = vm::send,
                onStop = vm::cancel,
            )
        }
    }
}

@Composable
private fun TextButtonLabel(label: String, onClick: () -> Unit) {
    androidx.compose.material3.TextButton(onClick = onClick) { Text(label) }
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
private fun UserBubble(message: UiMessage) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End) {
        Surface(
            shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        ) {
            Text(
                message.content,
                Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.md).widthIn(max = 300.dp),
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        if (message.createdAt.isNotBlank()) {
            XnUpdatedTag(XnTime.formatIso(message.createdAt), Modifier.padding(top = XnSpacing.xs, end = XnSpacing.xs))
        }
    }
}

@Composable
private fun AssistantBubble(message: UiMessage) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.Start) {
        XnRow(verticalAlignment = Alignment.Top) {
            XnAvatarSmall()
            Surface(
                shape = MaterialTheme.shapes.medium,
                color = MaterialTheme.colorScheme.surface,
                contentColor = MaterialTheme.colorScheme.onSurface,
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                modifier = Modifier.padding(start = XnSpacing.md),
            ) {
                Text(
                    message.content.ifBlank { "…" },
                    Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.md).widthIn(max = 300.dp),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        if (message.createdAt.isNotBlank()) {
            XnUpdatedTag(XnTime.formatIso(message.createdAt), Modifier.padding(top = XnSpacing.xs, start = 44.dp))
        }
    }
}

@Composable
private fun InputBar(
    draft: String,
    busy: Boolean,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        XnRow(
            Modifier.fillMaxWidth().padding(XnSpacing.page),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            XnIcon(R.drawable.ic_plus, contentDescription = "添加附件(即将可用)", onClick = {})
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
            if (busy) {
                // 生成中显示停止按钮(设计 §5.3)
                XnIcon(R.drawable.ic_stop, contentDescription = "停止", onClick = onStop)
            } else {
                XnIcon(
                    R.drawable.ic_send,
                    contentDescription = "发送",
                    onClick = { if (draft.isNotBlank()) onSend() },
                )
            }
        }
    }
}
