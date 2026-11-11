package com.easychat.family.feature.today

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.easychat.family.app.XiaoNuanApplication
import com.easychat.family.core.model.ScheduleDto
import com.easychat.family.core.model.SessionDto
import com.easychat.family.core.util.XnTime
import com.easychat.family.core.network.RequestFailure
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDateTime

/** 各区块独立状态(设计 §5.2:单个接口失败保留其他区块并在该区块重试)。 */
sealed class BlockState<out T> {
    data object Loading : BlockState<Nothing>()
    data class Ready<T>(val data: T, val fetchedAt: LocalDateTime) : BlockState<T>()
    data class Error(val text: String, val forbidden: Boolean = false, val unavailable: Boolean = false) : BlockState<Nothing>()
}

data class TodayUiState(
    val greeting: String = "",
    val username: String = "",
    val schedules: BlockState<List<ScheduleUi>> = BlockState.Loading,
    val memories: BlockState<List<MemoryUi>> = BlockState.Loading,
    val wechat: BlockState<List<SessionDto>> = BlockState.Loading,
    val refreshedAt: LocalDateTime? = null,
)

data class ScheduleUi(
    val scheduleId: String,
    val timeText: String,
    val title: String,
    val enabled: Boolean,
    val isToday: Boolean,
)

data class MemoryUi(
    val memoryId: String,
    val content: String,
    val kind: String,
    val recordedAt: String,
)

class TodayViewModel(app: Application) : AndroidViewModel(app) {

    private val container = (app as XiaoNuanApplication).container

    private val _state = MutableStateFlow(TodayUiState())
    val state: StateFlow<TodayUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    /** 网络恢复/回到前台/下拉/保存成功时触发(设计 §5.2)。 */
    fun refresh() {
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        _state.value = _state.value.copy(
            greeting = XnTime.greeting(now.hour),
            username = container.conn.username(),
        )
        viewModelScope.launch { loadSchedules(now) }
        viewModelScope.launch { loadMemories() }
        viewModelScope.launch { loadWechat() }
    }

    private suspend fun loadSchedules(now: LocalDateTime) {
        update { it.copy(schedules = BlockState.Loading) }
        // suspend 调用在 update 之外:receiver 不能在挂起前捕获(否则并发回滚)
        val result = runCatching { container.life.schedules().schedules }
        val finishAt = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        update { st ->
            st.copy(
                schedules = result.fold(
                    onSuccess = { list ->
                        val ui = list.filter { it.enabled }.mapNotNull { s ->
                            if (s.next_run_at <= 0.0) return@mapNotNull null
                            val target = XnTime.fromEpochSeconds(s.next_run_at.toLong())
                            ScheduleUi(
                                scheduleId = s.schedule_id,
                                timeText = XnTime.formatNextRun(s.next_run_at.toLong(), now = now),
                                title = s.title.ifBlank { s.text.take(20) },
                                enabled = s.enabled,
                                isToday = target.toLocalDate() == now.toLocalDate(),
                            )
                        }
                        BlockState.Ready(ui, finishAt)
                    },
                    onFailure = { e -> blockError(e, "loadSchedules") },
                ),
                refreshedAt = finishAt,
            )
        }
    }

    private suspend fun loadMemories() {
        update { it.copy(memories = BlockState.Loading) }
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        val result = runCatching { container.life.memories().memories }
        update { st ->
            st.copy(
                memories = result.fold(
                    onSuccess = { list ->
                        BlockState.Ready(
                            list.take(3).map {
                                MemoryUi(it.memory_id, it.content, it.kind, XnTime.formatIso(it.recorded_at))
                            },
                            now,
                        )
                    },
                    onFailure = { e -> blockError(e, "loadMemories") },
                ),
            )
        }
    }

    private suspend fun loadWechat() {
        update { it.copy(wechat = BlockState.Loading) }
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        val result = runCatching { container.life.wechatSessions() }
        update { st ->
            st.copy(
                wechat = result.fold(
                    onSuccess = { BlockState.Ready(it.take(3), now) },
                    onFailure = { e -> blockError(e, "loadWechat") },
                ),
            )
        }
    }

    /** 原子更新:并发 load 的 read-copy-write 不能跨挂起点。 */
    private fun update(reducer: (TodayUiState) -> TodayUiState) {
        _state.update(reducer)
    }

    private fun blockError(e: Throwable, where: String): BlockState.Error {
        if (e !is RequestFailure) {
            android.util.Log.e("XnToday", where + " failed", e)
            return BlockState.Error("读取出了点小问题")
        }
        return when (e) {
            is RequestFailure.Http -> BlockState.Error(e.error.displayText(), e.error.forbidden, e.error.capabilityUnavailable)
            is RequestFailure.Network -> BlockState.Error("连接暂时断开了")
            RequestFailure.Cancelled -> BlockState.Error("")
        }
    }

    private fun errorBlock(failure: RequestFailure): BlockState.Error = when (failure) {
        is RequestFailure.Http -> BlockState.Error(failure.error.displayText(), failure.error.forbidden, failure.error.capabilityUnavailable)
        is RequestFailure.Network -> BlockState.Error("连接暂时断开了")
        RequestFailure.Cancelled -> BlockState.Error("")
    }
}
