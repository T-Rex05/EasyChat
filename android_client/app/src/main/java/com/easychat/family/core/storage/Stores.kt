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

    /** 内存缓存:请求路径零阻塞读取(Keystore 解密只在登录/启动时发生一次)。 */
    @Volatile
    private var cachedToken: String? = null

    suspend fun store(token: String) {
        cachedToken = token
        val blob = XnKeystore.encrypt(token.toByteArray(Charsets.UTF_8))
        val b64 = Base64.getEncoder().encodeToString(blob)
        context.secureStore.edit { it[key] = b64 }
    }

    /** 登录后/启动时调用一次:解密落缓存;之后请求走 tokenCached()。 */
    suspend fun load(): String? {
        val b64 = context.secureStore.data.first()[key] ?: return null
        val plain = try {
            String(XnKeystore.decrypt(Base64.getDecoder().decode(b64)), Charsets.UTF_8)
        } catch (_: Exception) {
            // 密钥被系统清除/换机恢复:按未登录处理(fail-closed,不使用不可信数据)
            clear()
            null
        }
        cachedToken = plain
        return plain
    }

    suspend fun token(): String? = cachedToken ?: load()

    /** 请求路径专用:只读内存缓存,绝不触发 DataStore/Keystore(零阻塞)。 */
    fun tokenCached(): String? = cachedToken

    suspend fun clear() {
        cachedToken = null
        context.secureStore.edit { it.remove(key) }
    }
}

/** 连接与账号快照(server_identity 是缓存分区键,设计 §8.1)。 */
class ConnectionStore(private val context: Context) {

    private val baseUrlKey = stringPreferencesKey("server_base_url")
    private val usernameKey = stringPreferencesKey("username")
    private val userIdKey = stringPreferencesKey("user_id")
    private val sessionEpochKey = stringPreferencesKey("session_epoch")

    @Volatile
    private var cachedBaseUrl: String = ""

    suspend fun saveServer(url: String) {
        val trimmed = url.trim().trimEnd('/')
        cachedBaseUrl = trimmed
        context.prefStore.edit { it[baseUrlKey] = trimmed }
    }

    /** 启动时调用一次,之后请求走 baseUrlCached()。 */
    suspend fun load() {
        cachedBaseUrl = context.prefStore.data.first()[baseUrlKey] ?: ""
    }

    fun baseUrl(): String = runBlocking {
        cachedBaseUrl.ifBlank {
            context.prefStore.data.first()[baseUrlKey] ?: ""
        }
    }

    /** 请求路径专用:零阻塞(冷启动由 XiaoNuanApp 预热)。 */
    fun baseUrlCached(): String = cachedBaseUrl

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
