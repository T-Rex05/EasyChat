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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnCard
import com.easychat.family.core.designsystem.XnIcon
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
        Text("你好,我是小暖。想聊的时候,来这里坐坐。", style = MaterialTheme.typography.bodyLarge)
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
 * 服务器配置(设计 §5.1):地址输入 + 依次验证 /healthz、/readyz。
 * 状态文案:「连接成功 / 正在启动 / 地址暂时连不上」(真实请求,WP2)。
 */
@Composable
fun ServerConfigScreen(vm: OnboardingViewModel, onConnected: () -> Unit, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.check) {
        if (state.check?.connected == true) onConnected()
    }
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
            value = state.serverUrl,
            onValueChange = vm::onServerUrlChange,
            label = { Text("服务器地址") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        XnCard(Modifier.fillMaxWidth()) {
            XnRow(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                if (state.check == null && !state.checking) {
                    TextButton(onClick = {}) { Text("扫码配置(即将可用)") }
                } else {
                    Spacer(Modifier.weight(1f))
                }
            }
            ConnectionRow("基础连通(/healthz)", state, waiting = state.check == null && !state.checking)
            ConnectionRow("服务就绪(/readyz)", state, waiting = state.check == null && !state.checking)
            if (state.check != null) {
                ConnectionRow("连接类型", state, waiting = false)
            }
            if (state.check != null) {
                Text(
                    state.check!!.displayText(),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (state.check!!.connected) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error,
                )
            }
            if (state.errorText.isNotBlank()) {
                Text(
                    state.errorText,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
        XnPrimaryButton(
            if (state.checking) "正在连接…" else "连接",
            vm::checkConnection,
            Modifier.fillMaxWidth(),
            enabled = !state.checking,
        )
    }
}

@Composable
private fun ConnectionRow(label: String, state: OnboardingUiState, waiting: Boolean, ok: Boolean? = null) {
    val status = when (label) {
        "基础连通(/healthz)" -> when {
            waiting -> "还没连接"
            state.check?.healthzOk == true -> "连接成功"
            else -> "没连上"
        }
        "服务就绪(/readyz)" -> when {
            waiting -> "还没连接"
            state.check?.readyzOk == true -> "连接成功"
            state.check?.readyzStarting == true -> "正在启动"
            else -> "没连上"
        }
        else -> state.check?.scheme ?: ""
    }
    val color = when {
        ok == true -> MaterialTheme.colorScheme.primary
        status == "连接成功" -> MaterialTheme.colorScheme.primary
        status == "正在启动" -> MaterialTheme.colorScheme.onSurfaceVariant
        waiting -> MaterialTheme.colorScheme.onSurfaceVariant
        else -> MaterialTheme.colorScheme.error
    }
    XnRow(Modifier.fillMaxWidth().padding(vertical = XnSpacing.xs)) {
        Text(label, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.weight(1f))
        Text(status, style = MaterialTheme.typography.bodyMedium, color = color)
    }
}

/** 登录(设计 §5.1):现有 username/password;成功读 /api/auth/me 同步身份。 */
@Composable
fun LoginScreen(vm: OnboardingViewModel, onLoggedIn: () -> Unit, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
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
            value = state.username,
            onValueChange = vm::onUsernameChange,
            label = { Text("用户名") },
            singleLine = true,
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.password,
            onValueChange = vm::onPasswordChange,
            label = { Text("密码") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth(),
        )
        if (state.errorText.isNotBlank()) {
            Text(
                state.errorText,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
            )
        }
        XnRow(verticalAlignment = Alignment.CenterVertically) {
            XnPrimaryButton(if (state.loggingIn) "正在登录…" else "登录", { vm.login(onLoggedIn) }, Modifier.weight(1f), enabled = !state.loggingIn)
            if (state.loggingIn) {
                CircularProgressIndicator(Modifier.padding(start = XnSpacing.md).size(24.dp))
            }
        }
    }
}
