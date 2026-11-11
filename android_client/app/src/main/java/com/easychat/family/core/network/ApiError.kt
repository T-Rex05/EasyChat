package com.easychat.family.core.network

import com.easychat.family.core.model.ApiErrorBody
import kotlinx.serialization.json.Json

/**
 * 后端错误映射(WP0 核验,shared/errors.py):
 * - AppError → {error:<code>, message, details?},HTTP 401/403/404/409/422/429/503/504;
 * - chat busy 特化为 {"error": str}(无 message);
 * - FastAPI 校验兜底 {"detail": ...}。
 */
data class ApiError(
    val httpStatus: Int,
    val code: String,
    val message: String,
) {
    val unauthenticated: Boolean get() = httpStatus == 401
    val busy: Boolean get() = httpStatus == 429 || code == "busy"
    val capabilityUnavailable: Boolean get() = code == "capability_unavailable" || httpStatus == 503
    val forbidden: Boolean get() = httpStatus == 403 || code == "forbidden"
    val notFound: Boolean get() = httpStatus == 404 || code == "not_found"

    /** 用户可读文案:优先后端 message,再 detail,再按码归类。 */
    fun displayText(): String = when {
        message.isNotBlank() -> message
        code.isNotBlank() && code != "error" -> codeText(code)
        else -> defaultText(httpStatus)
    }

    private fun codeText(code: String): String = when (code) {
        "unauthenticated" -> "登录已过期,请重新登录"
        "forbidden" -> "当前账号没有这个权限"
        "not_found" -> "内容不存在或已被删除"
        "conflict" -> "内容状态有变化,请刷新后再试"
        "invalid_input" -> "内容格式不对,请修改后再试"
        "busy" -> "小暖正在处理另一条消息,请稍等一下"
        "capability_unavailable" -> "这个功能现在没有开启"
        "storage_unavailable" -> "存储暂时不可用,请稍后再试"
        "dependency_timeout" -> "响应有点慢,请稍后再试"
        else -> "出了点小问题,请稍后再试"
    }

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        private fun defaultText(status: Int): String = when (status) {
            401 -> "登录已过期,请重新登录"
            403 -> "当前账号没有这个权限"
            404 -> "内容不存在或已被删除"
            409 -> "内容状态有变化,请刷新后再试"
            429 -> "请求有点频繁,请稍等一下"
            503 -> "服务暂时不可用,请稍后再试"
            else -> "网络出了点小问题,请稍后再试"
        }

        /** 兼容三类响应体:{error,message} / {"error":str(busy)} / {detail}。 */
        fun parse(httpStatus: Int, body: String?): ApiError {
            if (body.isNullOrBlank()) return ApiError(httpStatus, "", defaultText(httpStatus))
            return try {
                val parsed = json.decodeFromString<ApiErrorBody>(body)
                ApiError(
                    httpStatus = httpStatus,
                    code = parsed.error.ifBlank { "" },
                    message = parsed.message.ifBlank { parsed.detail },
                )
            } catch (_: Exception) {
                ApiError(httpStatus, "", body.take(120))
            }
        }
    }
}

/** 网络层异常:区分 IO 断连(可恢复)与 HTTP 错误。 */
sealed class RequestFailure : Exception() {
    class Http(val error: ApiError) : RequestFailure()
    class Network(cause: Throwable) : RequestFailure()
    object Cancelled : RequestFailure()
}
