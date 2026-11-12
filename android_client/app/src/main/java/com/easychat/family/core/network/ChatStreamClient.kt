package com.easychat.family.core.network

import com.easychat.family.core.model.StreamPostBody
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader

/**
 * POST /chat/stream SSE(WP0 核验):
 * - Bearer 头鉴权(OkHttp 原生,不需要 sse-ticket);
 * - [lastEventId] 传最后已消费序号 → Last-Event-ID 头,服务端从 seq+1 续传;
 * - 断流时 Flow 正常结束,由调用方按 [ChatStreamClient.lastSeq] 决定恢复;
 * - HTTP 错误(409 busy/401/503)以 [ChatEvent.Failed] + [StreamFailure] 发出后关闭。
 */
class ChatStreamClient(
    private val api: ApiClient,
) {
    private val json = JsonHolder.json

    private var lastSeq: Long? = null
    fun consumedSeq(): Long? = lastSeq

    fun open(body: StreamPostBody, lastEventId: String?): Flow<ChatEventEnvelope> = callbackFlow {
        val payload = json.encodeToString(StreamPostBody.serializer(), body)
        val builder = Request.Builder()
            .url(api.baseUrlForStream().trimEnd('/') + "/chat/stream")
            .post(payload.toRequestBody("application/json".toMediaType()))
        api.tokenForStream()?.let { builder.header("Authorization", "Bearer $it") }
        if (!lastEventId.isNullOrBlank()) builder.header("Last-Event-ID", lastEventId)

        val call = api.sseClient().newCall(builder.build())
        val parser = SseFrameParser { id, data ->
            id?.toLongOrNull()?.let { lastSeq = it }
            ChatEventCodec.decode(data)?.let { event ->
                trySend(ChatEventEnvelope(id?.toLongOrNull(), event))
            }
        }
        val thread = Thread {
            try {
                call.execute().use { resp ->
                    if (!resp.isSuccessful) {
                        val err = ApiError.parse(resp.code, resp.body?.string())
                        if (resp.code == 401) api.handleUnauthorized()
                        trySend(ChatEventEnvelope(null, ChatEvent.Failed(err.displayText())))
                        close()
                        return@use
                    }
                    val reader = BufferedReader(InputStreamReader(resp.body!!.byteStream(), Charsets.UTF_8))
                    var line: String?
                    while (reader.readLine().also { line = it } != null) {
                        parser.feedLine(line!!)
                    }
                    parser.flush()
                    close()
                }
            } catch (_: IOException) {
                // 网络断开:正常关闭 Flow,由调用方进入 recovering 分支(设计 §7.2)
                close()
            } catch (_: Exception) {
                trySend(ChatEventEnvelope(null, ChatEvent.Failed("连接出了点小问题,请稍后再试")))
                close()
            }
        }
        thread.name = "xn-sse"
        thread.start()
        awaitClose {
            call.cancel()
        }
    }.flowOn(Dispatchers.IO)
}

/** Json 单例(与 ApiClient 同配置)。 */
internal object JsonHolder {
    val json: kotlinx.serialization.json.Json = kotlinx.serialization.json.Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }
}
