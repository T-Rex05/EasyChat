package com.easychat.family.feature.life

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnEmptyState
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnMockBadge
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSectionHeader
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.core.designsystem.XnUpdatedTag

/**
 * 生活(设计 §4/§5.4-5.6):日程 / 记下的事 / 收藏 三个分区,厨房为后续规划
 * 入口(按真实发布能力显示,WP1 只展示预留说明)。
 * WP1 全部为示例数据;WP3/WP4 接入真实 schedules/memory/inbox。
 */
@Composable
fun LifeScreen() {
    var tab by rememberSaveable { mutableStateOf("日程") }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("生活", Modifier.weight(1f), style = MaterialTheme.typography.displaySmall)
            XnMockBadge()
        }
        SegmentedTabs(selected = tab, onSelect = { tab = it })
        when (tab) {
            "日程" -> ScheduleSection()
            "记下的事" -> MemorySection()
            else -> BookmarkSection()
        }
        // 厨房预留入口(设计 §9):随真实能力发布,当前只显示说明
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth()) {
                XnIcon(R.drawable.ic_kitchen, contentDescription = null, tint = XnSageTint())
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
}

@Composable
private fun XnSageTint() = MaterialTheme.colorScheme.secondary

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

@Composable
private fun ScheduleSection() {
    Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
        // 周日历(WP1 静态;WP4 按时区/重复规则计算)
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth(), spacingDp = 4) {
                listOf("一", "二", "三", "四", "五", "六", "日").forEachIndexed { index, day ->
                    val dayNum = 17 + index
                    val isSel = index == 2
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(day, style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Box(
                            Modifier.padding(top = XnSpacing.xs).background(
                                if (isSel) MaterialTheme.colorScheme.primary else androidx.compose.ui.graphics.Color.Transparent,
                                CircleShape,
                            ).padding(horizontal = 10.dp, vertical = 6.dp),
                        ) {
                            Text(
                                "$dayNum",
                                style = MaterialTheme.typography.labelMedium,
                                color = if (isSel) MaterialTheme.colorScheme.onPrimary
                                else MaterialTheme.colorScheme.onSurface,
                            )
                        }
                    }
                }
            }
        }
        ScheduleRow("15:00", "取快递", "微信里记下的", "一次", enabled = true)
        ScheduleRow("18:30", "准备晚饭", "微信里记下的", "每天", enabled = true)
        ScheduleRow("08:00", "早间简报", "已设置", "每天", enabled = false, disabledHint = "已暂停")
    }
}

@Composable
private fun ScheduleRow(
    time: String,
    title: String,
    source: String,
    repeat: String,
    enabled: Boolean,
    disabledHint: String? = null,
) {
    XnCard(Modifier.fillMaxWidth()) {
        XnRow(Modifier.fillMaxWidth()) {
            Column(Modifier.width20()) {
                Text(time, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
                Text(repeat, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                XnRow(verticalAlignment = Alignment.CenterVertically) {
                    XnSourceChip(source)
                    if (!enabled) XnSourceChip(disabledHint ?: "已暂停")
                }
            }
            XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
        }
    }
}

private fun Modifier.width20() = this.then(Modifier.padding(end = XnSpacing.lg))

@Composable
private fun MemorySection() {
    Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
        MemoryRow("偏好", "晚饭喜欢清淡一些", "你确认过的记录", "周二 18:40")
        MemoryRow("重要的事", "周末想做番茄炒蛋", "小暖整理的,点此确认或修改", "昨天 20:12")
        MemoryRow("生活信息", "降压药放在餐桌左边抽屉", "小暖整理的,点此确认或修改", "11月8日 21:05")
    }
}

@Composable
private fun MemoryRow(kind: String, content: String, confirmState: String, time: String) {
    XnCard(Modifier.fillMaxWidth()) {
        XnRow(Modifier.fillMaxWidth()) {
            XnIcon(R.drawable.ic_note, contentDescription = null)
            Column(Modifier.weight(1f).padding(start = XnSpacing.md)) {
                Text(content, style = MaterialTheme.typography.bodyLarge)
                XnRow(verticalAlignment = Alignment.CenterVertically) {
                    XnSourceChip(kind)
                    XnUpdatedTag(time)
                }
                Text(
                    confirmState,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            XnIcon(R.drawable.ic_chevron_right, contentDescription = null)
        }
    }
}

@Composable
private fun BookmarkSection() {
    Column(verticalArrangement = Arrangement.spacedBy(XnSpacing.md)) {
        BookmarkRow("腌笃鲜的做法(下厨房)", "xiachufang.com", "春笋和咸肉一起炖,汤白味鲜…", "11月9日")
        BookmarkRow("适合老人的拉伸操", "bilibili.com", "十分钟低强度,跟着视频做…", "11月7日")
    }
}

@Composable
private fun BookmarkRow(title: String, domain: String, summary: String, time: String) {
    XnCard(Modifier.fillMaxWidth()) {
        XnRow(Modifier.fillMaxWidth()) {
            XnIcon(R.drawable.ic_bookmark, contentDescription = null)
            Column(Modifier.weight(1f).padding(start = XnSpacing.md)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(
                    summary,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                XnUpdatedTag("$domain · $time")
            }
        }
    }
}
