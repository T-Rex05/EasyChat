package com.easychat.family.core.network

/**
 * SSE 帧解析(纯逻辑,设计 §7.2):id/data 行、多行 data 以 \n 连接、空行分发、
 * `:` 心跳注释忽略、`retry:` 指令记录。已完成帧才交给 [onFrame]。
 *
 * 不做字符集处理:字节→字符串由上层按 UTF-8 分块解码后逐行喂入。
 */
class SseFrameParser(private val onFrame: (id: String?, data: String) -> Unit) {

    private var dataLines = mutableListOf<String>()
    private var eventId: String? = null
    private var sawField = false
    var retryMs: Long? = null
        private set

    /** 喂入一行(不带行尾符)。 */
    fun feedLine(line: String) {
        when {
            line.isEmpty() -> dispatch()
            line.startsWith(":") -> Unit // 心跳/注释
            else -> {
                val colon = line.indexOf(':')
                val field = if (colon < 0) line else line.substring(0, colon)
                var value = if (colon < 0) "" else line.substring(colon + 1)
                if (value.startsWith(" ")) value = value.substring(1)
                sawField = true
                when (field) {
                    "data" -> dataLines.add(value)
                    "id" -> if (!value.contains('\u0000')) eventId = value
                    "retry" -> value.toLongOrNull()?.let { retryMs = it }
                }
            }
        }
    }

    /** 流结束时冲洗未分发缓冲(服务端偶发缺结尾空行)。 */
    fun flush() {
        if (sawField) dispatch()
    }

    private fun dispatch() {
        val hadData = sawField
        val data = dataLines.joinToString("\n")
        val id = eventId
        dataLines = mutableListOf()
        eventId = null
        sawField = false
        // 规范:只有 data 字段出现的块才分发;仅 id/retry 的块更新状态但不回调
        if (hadData && data.isNotEmpty()) onFrame(id, data)
    }
}
