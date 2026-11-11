package com.easychat.family.app

import android.app.Application
import com.easychat.family.core.network.ApiClient
import com.easychat.family.core.network.AuthRepository
import com.easychat.family.core.network.ChatRepository
import com.easychat.family.core.network.ChatStreamClient
import com.easychat.family.core.network.UnauthorizedHandler
import com.easychat.family.core.storage.ConnectionStore
import com.easychat.family.core.storage.TokenStore

/** 手工依赖装配(单模块规模不需要 Hilt;设计 §8)。 */
class AppContainer(app: Application) {
    val conn = ConnectionStore(app)
    val tokens = TokenStore(app)

    /** 401 且刷新失败 → 置位;UI 侧观察后退出到登录页并清除。 */
    val sessionExpired = kotlinx.coroutines.flow.MutableStateFlow(false)

    val api = ApiClient(
        tokens = tokens,
        conn = conn,
        unauthorizedHandler = UnauthorizedHandler { sessionExpired.value = true },
    )
    val streams = ChatStreamClient(api)
    val auth = AuthRepository(api, tokens, conn)
    val chat = ChatRepository(api, streams)

    fun clearSessionExpiredFlag() {
        sessionExpired.value = false
    }
}
