package com.easychat.family.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnAvatar
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnMockBadge
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing

/**
 * 我的(设计 §5.7):账号与微信绑定、称呼与陪伴偏好、外观、连接与存储。
 * WP1 为示例布局;WP2 接 /api/auth/me 与 /api/profile,设置项按 capabilities 控制。
 */
@Composable
fun ProfileScreen() {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(XnSpacing.page),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("我的", Modifier.weight(1f), style = MaterialTheme.typography.displaySmall)
            XnMockBadge()
        }

        // 账号与微信绑定
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth()) {
                XnAvatar("兰")
                Column(Modifier.weight(1f).padding(start = XnSpacing.md)) {
                    Text("秀兰阿姨", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "xiaolan@family",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = XnSpacing.md), verticalAlignment = Alignment.CenterVertically) {
                Text("我的微信", style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.weight(1f))
                XnSourceChip("已绑定 · 示例")
            }
        }

        // 称呼与陪伴
        XnCard(Modifier.fillMaxWidth(), onClick = {}) {
            SettingRow("怎么称呼你", "秀兰阿姨")
            SettingRow("小暖怎么和你说话", "温柔")
            SettingRow("安静时间", "22:00 - 07:00")
        }

        // 外观与朗读
        XnCard(Modifier.fillMaxWidth(), onClick = {}) {
            SettingRow("字号", "跟随系统")
            SettingRow("外观", "跟随系统")
            SettingRow("朗读回复", "未开启")
        }

        // 连接与存储
        XnCard(Modifier.fillMaxWidth(), onClick = {}) {
            SettingRow("服务器", "192.168.1.10:8001")
            SettingRow("清理缓存", "")
            SettingRow("版本", "0.1.0(示例)")
        }

        Text(
            "微信绑定与解绑沿用现有授权流程;设置项以服务器返回为准。",
            Modifier.padding(horizontal = XnSpacing.sm),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.padding(bottom = XnSpacing.sm))
    }
}

@Composable
private fun SettingRow(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = XnSpacing.md),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.weight(1f))
        if (value.isNotEmpty()) {
            Text(
                value,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            XnIcon(R.drawable.ic_chevron_right, contentDescription = null,
                modifier = Modifier.padding(start = XnSpacing.sm))
        }
    }
}
