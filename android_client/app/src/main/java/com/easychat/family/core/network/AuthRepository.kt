package com.easychat.family.core.network

import com.easychat.family.core.model.LoginRequest
import com.easychat.family.core.model.LoginResponse
import com.easychat.family.core.model.MeResponse
import com.easychat.family.core.storage.ConnectionStore
import com.easychat.family.core.storage.TokenStore

/**
 * 登录/当前用户/退出(设计 §5.1)。
 * 退出与切换账号:清凭证 + 账号快照 + session epoch 自增(缓存分区失效),草稿由上层提示后清理。
 */
class AuthRepository(
    private val api: ApiClient,
    private val tokens: TokenStore,
    private val conn: ConnectionStore,
) {

    suspend fun checkConnection(): ConnectionCheck {
        val health = checkPath("/healthz")
        val ready = checkPath("/readyz")
        return ConnectionCheck(
            healthzOk = health == CheckResult.OK,
            readyzOk = ready == CheckResult.OK,
            readyzStarting = ready == CheckResult.STARTING,
            unreachable = health == CheckResult.UNREACHABLE || ready == CheckResult.UNREACHABLE,
            scheme = if (conn.baseUrl().startsWith("https")) "HTTPS" else "HTTP(内网联调)",
        )
    }

    private suspend fun checkPath(path: String): CheckResult = try {
        val resp = api.rawCall(path)
        when {
            resp.code in 200..299 -> CheckResult.OK
            resp.code == 503 -> CheckResult.STARTING
            else -> CheckResult.FAILED
        }
    } catch (e: Exception) {
        android.util.Log.e("XnConn", "checkPath $path failed", e)
        CheckResult.UNREACHABLE
    }

    suspend fun login(username: String, password: String): LoginResponse {
        val resp = api.post<LoginResponse, LoginRequest>("/api/auth/login", LoginRequest(username, password))
        if (!resp.ok || resp.token.isBlank()) {
            throw RequestFailure.Http(ApiError(401, "", "登录失败,请检查用户名和密码"))
        }
        tokens.store(resp.token)
        conn.saveAccount(resp.user_id, resp.username)
        conn.bumpSessionEpoch()
        return resp
    }

    suspend fun me(): MeResponse = api.get("/api/auth/me")

    /** 退出:清凭证 + 账号信息;返回是否已提升上层清理缓存/草稿。 */
    suspend fun logout() {
        tokens.clear()
        conn.clearAccount()
        conn.bumpSessionEpoch()
    }
}

data class ConnectionCheck(
    val healthzOk: Boolean,
    val readyzOk: Boolean,
    val readyzStarting: Boolean,
    val unreachable: Boolean,
    val scheme: String,
) {
    /** 「连接成功 / 正在启动 / 地址暂时连不上」(设计 §5.1)。 */
    fun displayText(): String = when {
        unreachable -> "地址暂时连不上,请检查服务器和网线"
        readyzStarting -> "服务正在启动,请稍等几秒"
        healthzOk && readyzOk -> "连接成功"
        else -> "服务没有完全就绪,请稍后再试"
    }

    val connected: Boolean get() = healthzOk && readyzOk && !unreachable
}

enum class CheckResult { OK, STARTING, FAILED, UNREACHABLE }
