package com.easychat.family.core.storage

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking
import java.util.Base64

private val Context.secureStore by preferencesDataStore(name = "xn_secure")
private val Context.prefStore by preferencesDataStore(name = "xn_prefs")

/** 凭证:Keystore 加密后落 DataStore;退出/切换账号必须 [clear](设计 §8.1)。 */
class TokenStore(private val context: Context) {

    private val key = stringPreferencesKey("auth_token_b64")

    suspend fun store(token: String) {
        val blob = XnKeystore.encrypt(token.toByteArray(Charsets.UTF_8))
        val b64 = Base64.getEncoder().encodeToString(blob)
        context.secureStore.edit { it[key] = b64 }
    }

    suspend fun token(): String? {
        val b64 = context.secureStore.data.first()[key] ?: return null
        return try {
            String(XnKeystore.decrypt(Base64.getDecoder().decode(b64)), Charsets.UTF_8)
        } catch (_: Exception) {
            // 密钥被系统清除/换机恢复:按未登录处理(fail-closed,不使用不可信数据)
            clear()
            null
        }
    }

    /** 网络层在 IO 线程读取;提供同步视图避免回调链(仅限 IO 线程)。 */
    fun tokenBlocking(): String? = runBlocking { token() }

    suspend fun clear() {
        context.secureStore.edit { it.remove(key) }
    }
}

/** 连接与账号快照(server_identity 是缓存分区键,设计 §8.1)。 */
class ConnectionStore(private val context: Context) {

    private val baseUrlKey = stringPreferencesKey("server_base_url")
    private val usernameKey = stringPreferencesKey("username")
    private val userIdKey = stringPreferencesKey("user_id")
    private val sessionEpochKey = stringPreferencesKey("session_epoch")

    suspend fun saveServer(url: String) {
        context.prefStore.edit { it[baseUrlKey] = url.trim().trimEnd('/') }
    }

    fun baseUrl(): String = runBlocking {
        context.prefStore.data.first()[baseUrlKey] ?: ""
    }

    fun baseUrlBlocking(): String = baseUrl()

    suspend fun saveAccount(userId: Int, username: String) {
        context.prefStore.edit {
            it[userIdKey] = userId.toString()
            it[usernameKey] = username
        }
    }

    fun username(): String = runBlocking { context.prefStore.data.first()[usernameKey] ?: "" }
    fun userId(): Int = runBlocking { context.prefStore.data.first()[userIdKey]?.toIntOrNull() ?: 0 }

    /** 每次登录/登出自增:缓存与草稿按 server+owner+epoch 分区失效(设计 §6.5/§8.1)。 */
    suspend fun bumpSessionEpoch(): Int {
        val next = (context.prefStore.data.first()[sessionEpochKey]?.toIntOrNull() ?: 0) + 1
        context.prefStore.edit { it[sessionEpochKey] = next.toString() }
        return next
    }

    suspend fun clearAccount() {
        context.prefStore.edit {
            it.remove(userIdKey)
            it.remove(usernameKey)
        }
    }
}
