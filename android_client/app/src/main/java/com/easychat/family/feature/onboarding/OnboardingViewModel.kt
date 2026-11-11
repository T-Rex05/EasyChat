package com.easychat.family.feature.onboarding

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.easychat.family.app.AppContainer
import com.easychat.family.core.model.Capabilities
import com.easychat.family.core.network.ConnectionCheck
import com.easychat.family.core.network.RequestFailure
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** 连接检查 → 登录 → me 的单向状态流(设计 §5.1)。 */
data class OnboardingUiState(
    val serverUrl: String = "",
    val check: ConnectionCheck? = null,
    val checking: Boolean = false,
    val loggingIn: Boolean = false,
    val username: String = "",
    val password: String = "",
    val errorText: String = "",
    val me: MeSnapshot? = null,
) {
    val connected: Boolean get() = check?.connected == true
}

data class MeSnapshot(
    val userId: Int,
    val username: String,
    val role: String,
    val capabilities: Capabilities,
)

class OnboardingViewModel(app: Application) : AndroidViewModel(app) {

    private val container = (app as com.easychat.family.app.XiaoNuanApplication).container

    private val _state = MutableStateFlow(OnboardingUiState(serverUrl = container.conn.baseUrl()))
    val state: StateFlow<OnboardingUiState> = _state.asStateFlow()

    fun onServerUrlChange(v: String) {
        _state.value = _state.value.copy(serverUrl = v, errorText = "")
    }

    fun onUsernameChange(v: String) {
        _state.value = _state.value.copy(username = v, errorText = "")
    }

    fun onPasswordChange(v: String) {
        _state.value = _state.value.copy(password = v, errorText = "")
    }

    /** 依次验证 /healthz 与 /readyz(设计 §5.1);通过后保存地址。 */
    fun checkConnection() {
        val url = _state.value.serverUrl.trim()
        val valid = Regex("""^https?://[^/\s]+(:\d+)?(/.*)?$""")
        if (!valid.matches(url)) {
            _state.value = _state.value.copy(errorText = "地址要以 http:// 或 https:// 开头,例如 http://192.168.1.10:8001")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(checking = true)
            container.conn.saveServer(url)
            val check = try {
                container.auth.checkConnection()
            } catch (e: Exception) {
                null
            }
            _state.value = _state.value.copy(
                checking = false,
                check = check,
                errorText = if (check == null) "网络出了点小问题,请稍后再试" else "",
            )
        }
    }

    fun login(onSuccess: () -> Unit) {
        val s = _state.value
        if (s.username.isBlank() || s.password.isBlank()) {
            _state.value = s.copy(errorText = "请输入用户名和密码")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(loggingIn = true, errorText = "")
            try {
                container.auth.login(s.username.trim(), s.password)
                val me = container.auth.me()
                container.clearSessionExpiredFlag()
                _state.value = _state.value.copy(
                    loggingIn = false,
                    me = MeSnapshot(me.id, me.username, me.role, me.capabilities),
                )
                onSuccess()
            } catch (failure: RequestFailure.Http) {
                _state.value = _state.value.copy(loggingIn = false, errorText = failure.error.displayText())
            } catch (e: RequestFailure.Network) {
                _state.value = _state.value.copy(loggingIn = false, errorText = "连接暂时断开了,请检查网络后再试")
            } catch (e: Exception) {
                android.util.Log.e("XnLogin", "login failed", e)
                _state.value = _state.value.copy(loggingIn = false, errorText = "登录出了点小问题,请稍后再试")
            }
        }
    }
}
