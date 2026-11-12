package com.easychat.family.feature.life

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSectionHeader
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag
import com.easychat.family.core.model.InboxItemDto
import com.easychat.family.core.model.MemoryDto
import com.easychat.family.core.model.ScheduleDto
import com.easychat.family.core.util.XnTime
import java.time.LocalDateTime

/**
 * 生活(设计 §5.4-5.6 + §4):日程 / 记下的事 / 收藏 三分区真实数据;
 * 日程支持 暂停/恢复/删除/详情(触发实例),新建用明确表单(WP4)。
 * 厨房为预留入口,随真实能力发布。
 */
@Composable
fun LifeScreen(onNewReminder: () -> Unit = {}) {
    val vm: LifeViewModel = viewModel()
    val state by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf("日程") }
    var showNew by rememberSaveable { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("生活", Modifier.weight(1f), style = MaterialTheme.typography.displaySmall)
            XnIcon(R.drawable.ic_nav_life, contentDescription = "刷新", onClick = { vm.refresh() })
        }
        SegmentedTabs(selected = tab, onSelect = { tab = it })
        if (state.message.isNotBlank()) {
            XnCard(Modifier.fillMaxWidth(), onClick = vm::clearMessage) {
                Text(state.message, style = MaterialTheme.typography.bodyLarge)
                Text("知道了", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            }
        }
        when (tab) {
            "日程" -> ScheduleSection(state, vm, onNewReminder = { showNew = true })
            "记下的事" -> MemorySection(state.memories)
            else -> BookmarkSection(state.bookmarks)
        }
        // 厨房预留入口(设计 §9):随真实能力发布
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth()) {
                XnIcon(R.drawable.ic_kitchen, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                Column(Modifier.padding(start = XnSpacing.md)) {
                    Text("厨房 · 后续规划", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "菜谱、今日菜单、做菜模式和买菜清单,之后会在这里出现。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        Spacer(Modifier.padding(bottom = XnSpacing.sm))
    }

    if (showNew) {
        NewReminderDialog(
            onDismiss = { showNew = false },
            onCreate = { title, text, at ->
                vm.createSchedule(title, text, at) { ok -> if (ok) showNew = false }
            },
        )
    }

    state.detail?.let { detail ->
        ScheduleDetailDialog(
            detail = detail,
            onToggle = { vm.setEnabled(detail.schedule, it) },
            onDelete = { vm.delete(detail.schedule) },
            onDismiss = vm::closeDetail,
        )
    }
}

@Composable
private fun ScheduleSection(state: LifeUiState, vm: LifeViewModel, onNewReminder: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
        XnSectionHeader("提醒计划", iconRes = R.drawable.ic_calendar, actionText = "新建提醒", onAction = onNewReminder)
        when (val s = state.schedules) {
            is com.easychat.family.feature.today.BlockState.Ready -> {
                if (s.data.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text(
                            "还没有提醒。点右上角「新建提醒」,或直接在微信里跟我说。",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                    }
                }
                s.data.forEach { schedule -> ScheduleRow(schedule, vm) }
            }
            is com.easychat.family.feature.today.BlockState.Error -> XnCard(Modifier.fillMaxWidth(), onClick = vm::refresh) {
                Text(s.text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
                Text("点这里重试", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            }
            com.easychat.family.feature.today.BlockState.Loading -> XnCard(Modifier.fillMaxWidth()) {
                Text("正在读取…", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun ScheduleRow(schedule: ScheduleDto, vm: LifeViewModel) {
    XnCard(Modifier.fillMaxWidth(), onClick = { vm.openDetail(schedule) }) {
        XnRow(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(end = XnSpacing.lg)) {
                val timeText = if (schedule.next_run_at > 0.0) {
                    XnTime.formatNextRun(
                        schedule.next_run_at.toLong(),
                        now = LocalDateTime.now(XnTime.DEFAULT_ZONE),
                    )
                } else schedule.at_time
                Text(timeText, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
                Text(repeatText(schedule), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(Modifier.weight(1f)) {
                Text(schedule.title.ifBlank { schedule.text.take(20).ifBlank { "提醒" } }, style = MaterialTheme.typography.titleMedium)
                XnRow(verticalAlignment = Alignment.CenterVertically) {
                    XnSourceChip(if (schedule.enabled) "已启用" else "已暂停")
                    if (schedule.content_kind == "briefing") XnSourceChip("简报")
                }
            }
        }
    }
}

private fun repeatText(schedule: ScheduleDto): String = when (schedule.kind) {
    "once" -> "一次"
    "daily" -> "每天"
    "weekly" -> "每周"
    "interval" -> "每隔 ${schedule.interval_seconds / 60} 分钟"
    else -> schedule.kind
}

@Composable
private fun MemorySection(state: com.easychat.family.feature.today.BlockState<List<MemoryDto>>) {
    Column(verticalArrangement = Arrangement
.spacedBy(XnSpacing.md)) {
        when (state) {
            is com.easychat.family.feature.today.BlockState.Ready -> {
                if (state.data.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text("还没有记下的事。跟我说「记住…」,我就会帮你记住。", style = MaterialTheme.typography.bodyLarge)
                    }
                }
                state.data.forEach { memory -> MemoryRow(memory) }
            }
            is com.easychat.family.feature.today.BlockState.Error -> XnCard(Modifier.fillMaxWidth()) {
                Text(state.text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
            }
            com.easychat.family.feature.today.BlockState.Loading -> XnCard(Modifier.fillMaxWidth()) {
                Text("正在读取…", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun MemoryRow(memory: MemoryDto) {
    XnCard(Modifier.fillMaxWidth()) {
        XnRow(Modifier.fillMaxWidth()) {
            XnIcon(R.drawable.ic_note, contentDescription = null)
            Column(Modifier.weight(1f).padding(start = XnSpacing.md)) {
                Text(memory.content, style = MaterialTheme.typography.bodyLarge)
                XnRow(verticalAlignment = Alignment.CenterVertically) {
                    XnSourceChip(kindText(memory.kind))
                    XnUpdatedTag(XnTime.formatIso(memory.recorded_at))
                }
                Text(
                    if (memory.source_type == "user_confirmed") "你确认过的记录" else "小暖整理的,点此确认或修改",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

private fun kindText(kind: String): String = when (kind) {
    "preference" -> "偏好"
    "event" -> "重要的事"
    "fact" -> "生活信息"
    "experience" -> "经历"
    else -> kind
}

@Composable
private fun BookmarkSection(state: com.easychat.family.feature.today.BlockState<List<InboxItemDto>>) {
    Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
        when (state) {
            is com.easychat.family.feature.today.BlockState.Ready -> {
                if (state.data.isEmpty()) {
                    XnCard(Modifier.fillMaxWidth()) {
                        Text("收藏是空的。微信里发「/存 链接」,或在网页上收藏,都会出现在这里。", style = MaterialTheme.typography.bodyLarge)
                    }
                }
                state.data.forEach { item ->
                    XnCard(Modifier.fillMaxWidth()) {
                        XnRow(Modifier.fillMaxWidth()) {
                            XnIcon(R.drawable.ic_bookmark, contentDescription = null)
                            Column(Modifier.weight(1f).padding(start = XnSpacing.md)) {
                                Text(item.title.ifBlank { item.url.ifBlank { "收藏" } }, style = MaterialTheme.typography.titleMedium)
                                if (item.summary.isNotBlank()) {
                                    Text(item.summary, style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                XnUpdatedTag(domainOf(item.url) + " · " + XnTime.formatIso(item.created_at))
                            }
                        }
                    }
                }
            }
            is com.easychat.family.feature.today.BlockState.Error -> XnCard(Modifier.fillMaxWidth()) {
                Text(state.text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
            }
            com.easychat.family.feature.today.BlockState.Loading -> XnCard(Modifier.fillMaxWidth()) {
                Text("正在读取…", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

private fun domainOf(url: String): String = try {
    java.net.URI(url).host ?: ""
} catch (_: Exception) {
    ""
}

@Composable
private fun SegmentedTabs(selected: String, onSelect: (String) -> Unit) {
    XnRow {
        listOf("日程", "记下的事", "收藏").forEach { label ->
            val isSel = label == selected
            Surface(
                shape = CircleShape,
                color = if (isSel) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surface,
                contentColor = if (isSel) MaterialTheme.colorScheme.onPrimaryContainer
                else MaterialTheme.colorScheme.onSurfaceVariant,
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                onClick = { onSelect(label) },
            ) {
                Text(
                    label,
                    Modifier.padding(horizontal = XnSpacing.lg, vertical = XnSpacing.sm),
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            Spacer(Modifier.padding(horizontal = 4.dp))
        }
    }
}

/** 新建提醒(设计 §5.4 明确表单):确认区自然语言复述下一次提醒时间。 */
@Composable
private fun NewReminderDialog(onDismiss: () -> Unit, onCreate: (String, String, LocalDateTime) -> Unit) {
    var title by rememberSaveable { mutableStateOf("") }
    var text by rememberSaveable { mutableStateOf("") }
    var date by rememberSaveable { mutableStateOf("") }
    var time by rememberSaveable { mutableStateOf("") }
    val parsed = runCatching {
        LocalDateTime.of(
            java.time.LocalDate.parse(date.trim()),
            java.time.LocalTime.parse(time.trim()),
        )
    }.getOrNull()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("新建提醒", style = MaterialTheme.typography.titleLarge) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
                OutlinedTextField(title, { title = it }, label = { Text("提醒什么(标题)") }, singleLine = true,
                    shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(text, { text = it }, label = { Text("补充说明(可选)") },
                    shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(date, { date = it }, label = { Text("日期(如 2026-11-12)") }, singleLine = true,
                    shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(time, { time = it }, label = { Text("时间(如 15:00)") }, singleLine = true,
                    shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth())
                Text(
                    parsed?.let {
                        "记好后,会在 " + XnTime.formatNextRun(
                            it.atZone(XnTime.DEFAULT_ZONE).toEpochSecond(),
                            now = LocalDateTime.now(XnTime.DEFAULT_ZONE),
                        ) + " 通过微信提醒你。"
                    } ?: "请填写日期和时间,到时间会通过微信提醒你。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { parsed?.let { onCreate(title, text, it) } }, enabled = parsed != null) {
                Text("记好")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("先不建") } },
    )
}

/** 详情:下次提醒 + 最近触发(未来=预计提醒,真实实例=实际状态,设计 §5.4)。 */
@Composable
private fun ScheduleDetailDialog(
    detail: ScheduleDetailState,
    onToggle: (Boolean) -> Unit,
    onDelete: () -> Unit,
    onDismiss: () -> Unit,
) {
    var confirmDelete by rememberSaveable { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(detail.schedule.title.ifBlank { "提醒" }, style = MaterialTheme.typography.titleLarge) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
                if (detail.nextRunText.isNotBlank()) {
                    Text(detail.nextRunText, style = MaterialTheme.typography.bodyLarge)
                }
                Text(
                    "投递渠道:微信" + if (detail.schedule.enabled) "" else "(已暂停)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text("最近触发", style = MaterialTheme.typography.titleMedium)
                if (detail.occurrencesLoading) {
                    Text("正在读取…", style = MaterialTheme.typography.bodyMedium)
                } else if (detail.occurrences.isEmpty()) {
                    Text("还没有触发过。", style = MaterialTheme.typography.bodyMedium)
                } else {
                    detail.occurrences.take(5).forEach { occ ->
                        XnRow(Modifier.fillMaxWidth()) {
                            Text(XnTime.formatIso(occ.scheduled_at), style = MaterialTheme.typography.bodyMedium)
                            Spacer(Modifier.weight(1f))
                            XnSourceChip(occurrenceStateText(occ.state, occ.missed))
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onToggle(!detail.schedule.enabled) }) {
                Text(if (detail.schedule.enabled) "暂停" else "恢复")
            }
        },
        dismissButton = {
            Row {
                TextButton(onClick = { if (confirmDelete) onDelete() else confirmDelete = true }) {
                    Text(if (confirmDelete) "再点一次确认删除" else "删除", color = MaterialTheme.colorScheme.error)
                }
                TextButton(onClick = onDismiss) { Text("关闭") }
            }
        },
    )
}

private fun occurrenceStateText(state: String, missed: Int): String = when {
    missed > 0 -> "错过 " + missed + " 次"
    state == "pending" -> "预计提醒"
    state == "queued" -> "已投递"
    state == "sent" -> "已投递"
    else -> state
}
