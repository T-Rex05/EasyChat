package com.easychat.family.feature.onboarding

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
import com.easychat.family.core.designsystem.XnMockBadge
import com.easychat.family.core.designsystem.XnPrimaryButton
import com.easychat.family.core.designsystem.XnRow
import com.easychat.family.core.designsystem.XnSourceChip
import com.easychat.family.core.designsystem.XnSpacing

/** 欢迎页(设计 §5.1):品牌 + 一句话 + 开始使用 + 服务器配置入口。 */
@Composable
fun WelcomeScreen(onStart: () -> Unit, onConfigureServer: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(XnSpacing.page).verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Image(
            painterResource(R.drawable.ic_launcher_foreground),
            contentDescription = null,
            modifier = Modifier.size(96.dp),
        )
        Spacer(Modifier.height(XnSpacing.lg))
        Text("小暖", style = MaterialTheme.typography.displaySmall)
        Text(
            "把日子过得暖一点",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(XnSpacing.xxl))
        Text(
            "你好,我是小暖。想聊的时候,来这里坐坐。",
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            "微信里说过的事、定过的提醒,也都能在这里看到。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(XnSpacing.xxl))
        XnPrimaryButton("开始使用", onStart, Modifier.fillMaxWidth())
        TextButton(onClick = onConfigureServer, modifier = Modifier.padding(top = XnSpacing.sm)) {
            Text("先配置服务器", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/**
 * 服务器配置(设计 §5.1):地址输入 + 连接检查。
 * 连接检查将依次验证 /healthz、/readyz(WP2 接真实请求);此处为 WP1 布局,状态为示例。
 */
@Composable
fun ServerConfigScreen(onConnected: () -> Unit, onBack: () -> Unit) {
    var address by rememberSaveable { mutableStateOf("http://192.168.1.10:8001") }
    Column(
        Modifier.fillMaxSize().padding(XnSpacing.page).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        XnRow(verticalAlignment = Alignment.CenterVertically) {
            XnIcon(R.drawable.ic_back, contentDescription = "返回", onClick = onBack)
            Text("连接服务器", style = MaterialTheme.typography.displaySmall)
        }
        Text(
            "输入家里服务器地址;也可以让家人帮你扫码填好。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = address,
            onValueChange = { address = it },
            label = { Text("服务器地址") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                XnSourceChip("示例数据")
                Spacer(Modifier.weight(1f))
                TextButton(onClick = {}) { Text("扫码配置") }
            }
            ConnectionRow("基础连通(/healthz)", "连接成功")
            ConnectionRow("服务就绪(/readyz)", "连接成功")
            ConnectionRow("连接类型", "HTTP · 家庭内网联调")
        }
        XnPrimaryButton("连接", onConnected, Modifier.fillMaxWidth())
    }
}

@Composable
private fun ConnectionRow(label: String, status: String) {
    XnRow(Modifier.fillMaxWidth().padding(vertical = XnSpacing.xs)) {
        Text(label, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.weight(1f))
        Text(
            status,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}

/** 登录(设计 §5.1):沿用现有 username/password;WP2 接 /api/auth/login。 */
@Composable
fun LoginScreen(onLoggedIn: () -> Unit, onBack: () -> Unit) {
    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    Column(
        Modifier.fillMaxSize().padding(XnSpacing.page).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(XnSpacing.lg),
    ) {
        XnRow(verticalAlignment = Alignment.CenterVertically) {
            XnIcon(R.drawable.ic_back, contentDescription = "返回", onClick = onBack)
            Text("登录", style = MaterialTheme.typography.displaySmall)
        }
        Text(
            "使用你的 EasyChat 账号,和微信里是同一个人。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("用户名") },
            singleLine = true,
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("密码") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        XnPrimaryButton("登录", onLoggedIn, Modifier.fillMaxWidth())
        XnMockBadge()
    }
}
