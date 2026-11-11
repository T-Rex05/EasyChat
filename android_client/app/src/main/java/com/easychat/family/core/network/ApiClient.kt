package com.easychat.family.core.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import com.easychat.family.core.model.RefreshResponse
import com.easychat.family.core.storage.ConnectionStore
import com.easychat.family.core.storage.TokenStore
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

/** 401 时由 ApiClient 触发(刷新失败后),UI 侧据此退出到登录页。 */
fun interface UnauthorizedHandler {
    fun onUnauthorized()
}

/**
 * HTTP 核心:统一 Bearer、401 刷新重试一次、错误体解析、SSE 超时分离。
 * 阻塞调用一律在 Dispatchers.IO。
 */
class ApiClient(
    okHttpClient: OkHttpClient? = null,
    private val tokens: TokenStore,
    private val conn: ConnectionStore,
    private val unauthorizedHandler: UnauthorizedHandler? = null,
) {
    val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    private val http: OkHttpClient = (okHttpClient ?: OkHttpClient())
        .newBuilder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .build()

    /** SSE 专用:读超时 0(长连接,由服务端 retry/心跳保活)。 */
    private val sseHttp: OkHttpClient = http.newBuilder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    /** 普通请求:401 → 单飞刷新 → 重试一次;仍失败抛 [RequestFailure.Http]。 */
    suspend fun <T> call(
        path: String,
        method: String = "GET",
        bodyJson: String? = null,
        parse: (String) -> T,
    ): T {
        android.util.Log.d("XnHttp", "call start " + method + " " + path)
        val started = android.os.SystemClock.elapsedRealtime()
        return withContext(Dispatchers.IO) {
        var last: RequestFailure? = null
        repeat(2) { attempt ->
            val request = buildRequest(path, method, bodyJson)
            try {
                http.newCall(request).execute().use { resp ->
                    val text = resp.body?.string()
                    if (resp.isSuccessful) return@withContext parse(text ?: "")
                    val failure = RequestFailure.Http(ApiError.parse(resp.code, text))
                    if (resp.code == 401 && attempt == 0 && refreshSync()) return@repeat
                    throw failure
                }
            } catch (e: RequestFailure) {
                last = e
                if (e !is RequestFailure.Http || e.error.httpStatus != 401) throw e
            } catch (e: IOException) {
                throw RequestFailure.Network(e)
            }
        }
        throw last ?: RequestFailure.Http(ApiError(401, "unauthenticated", "登录已过期,请重新登录"))
        }
        .also { android.util.Log.d("XnHttp", "call done " + method + " " + path + " " + (android.os.SystemClock.elapsedRealtime() - started) + "ms") }
    }

    suspend inline fun <reified T> get(path: String): T =
        call(path) { json.decodeFromString(it) }

    suspend inline fun <reified T> post(path: String): T =
        call(path, "POST", null) { json.decodeFromString(it) }

    suspend inline fun <reified T, reified B> post(path: String, body: B): T =
        call(path, "POST", json.encodeToString(body)) { json.decodeFromString(it) }

    suspend inline fun <reified T, reified B> put(path: String, body: B): T =
        call(path, "PUT", json.encodeToString(body)) { json.decodeFromString(it) }

    suspend inline fun <reified T> put(path: String): T =
        call(path, "PUT", null) { json.decodeFromString(it) }

    suspend inline fun <reified T, reified B> patch(path: String, body: B): T =
        call(path, "PATCH", json.encodeToString(body)) { json.decodeFromString(it) }

    suspend inline fun <reified T> delete(path: String): T =
        call(path, "DELETE") { json.decodeFromString(it) }

    /** 无鉴权调用(登录前 /healthz /readyz /api/auth/login)。响应在 IO 线程内消费并关闭。 */
    suspend fun rawCall(path: String, method: String = "GET", bodyJson: String? = null): RawHttpResponse =
        withContext(Dispatchers.IO) {
            val b = bodyJson?.toRequestBody("application/json".toMediaType())
            val req = Request.Builder()
                .url(conn.baseUrl().trimEnd('/') + path)
                .method(method, b)
                .build()
            http.newCall(req).execute().use { resp ->
                RawHttpResponse(resp.code, resp.body?.string() ?: "")
            }
        }

    fun buildRequest(path: String, method: String, bodyJson: String?): Request {
        val b = bodyJson?.toRequestBody("application/json".toMediaType())
        val builder = Request.Builder()
            .url(conn.baseUrl().trimEnd('/') + path)
            .method(method, b)
        tokens.tokenCached()?.let { builder.header("Authorization", "Bearer $it") }
        return builder.build()
    }

    /** 阻塞刷新(已在 IO 线程):成功存新 token 并返回 true。 */
    fun refreshSync(): Boolean {
        val current = tokens.tokenCached() ?: return false
        return try {
            val req = Request.Builder()
                .url(conn.baseUrl().trimEnd('/') + "/api/auth/refresh")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .header("Authorization", "Bearer $current")
                .build()
            http.newCall(req).execute().use { resp ->
                val text = resp.body?.string()
                if (!resp.isSuccessful) return false
                val parsed = json.decodeFromString<RefreshResponse>(text ?: return false)
                if (parsed.token.isBlank()) return false
                kotlinx.coroutines.runBlocking { tokens.store(parsed.token) }
                true
            }
        } catch (_: Exception) {
            false
        }
    }

    /** 对外 401 兜底:刷新失败即触发回调。 */
    fun handleUnauthorized() {
        unauthorizedHandler?.onUnauthorized()
    }

    /** SSE 专用(仅 IO 线程调用)。 */
    fun baseUrlForStream(): String = conn.baseUrlCached()

    fun tokenForStream(): String? = tokens.tokenCached()

    fun sseClient(): OkHttpClient = sseHttp
}

/** rawCall 的已消费响应(关闭已在 IO 完成,主线程安全)。 */
data class RawHttpResponse(val code: Int, val body: String)
