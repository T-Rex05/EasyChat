package com.easychat.family.feature.life

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.easychat.family.app.XiaoNuanApplication
import com.easychat.family.core.model.InboxItemDto
import com.easychat.family.core.model.MemoryDto
import com.easychat.family.core.model.OccurrenceDto
import com.easychat.family.core.model.ScheduleDto
import com.easychat.family.core.network.RequestFailure
import com.easychat.family.core.util.XnTime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDateTime

/** 生活页分段状态(日程/记下的事/收藏)+ 提醒详情(WP4)。 */
data class LifeUiState(
    val schedules: com.easychat.family.feature.today.BlockState<List<ScheduleDto>> =
        com.easychat.family.feature.today.BlockState.Loading,
    val memories: com.easychat.family.feature.today.BlockState<List<MemoryDto>> =
        com.easychat.family.feature.today.BlockState.Loading,
    val bookmarks: com.easychat.family.feature.today.BlockState<List<InboxItemDto>> =
        com.easychat.family.feature.today.BlockState.Loading,
    val message: String = "",
    val detail: ScheduleDetailState? = null,
)

/** 提醒详情:计划 + 触发实例(设计 §5.4)。 */
data class ScheduleDetailState(
    val schedule: ScheduleDto,
    val nextRunText: String,
    val occurrences: List<OccurrenceDto> = emptyList(),
    val occurrencesLoading: Boolean = false,
)

class LifeViewModel(app: Application) : AndroidViewModel(app) {

    private val container = (app as XiaoNuanApplication).container

    private val _state = MutableStateFlow(LifeUiState())
    val state: StateFlow<LifeUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        val logTag = "XnLife"
        viewModelScope.launch(
            kotlinx.coroutines.CoroutineExceptionHandler { _, e ->
                android.util.Log.e(logTag, "uncaught in refresh", e)
            },
        ) { loadSchedules() }
        viewModelScope.launch(
            kotlinx.coroutines.CoroutineExceptionHandler { _, e ->
                android.util.Log.e("XnLife", "uncaught in memories", e)
            },
        ) { loadMemories() }
        viewModelScope.launch(
            kotlinx.coroutines.CoroutineExceptionHandler { _, e ->
                android.util.Log.e("XnLife", "uncaught in bookmarks", e)
            },
        ) { loadBookmarks() }
    }

    private suspend fun loadSchedules() {
        update { it.copy(schedules = com.easychat.family.feature.today.BlockState.Loading) }
        // suspend 调用必须在 update 之外:receiver 不能在挂起前捕获(否则并发回滚)
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        val result = runCatching { container.life.schedules().schedules }
        update { st ->
            st.copy(
                schedules = result.fold(
                    onSuccess = { com.easychat.family.feature.today.BlockState.Ready(it, now) },
                    onFailure = { e -> blockError(e, "loadSchedules") },
                ),
            )
        }
    }

    private suspend fun loadMemories() {
        update { it.copy(memories = com.easychat.family.feature.today.BlockState.Loading) }
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        val result = runCatching { container.life.memories().memories }
        update { st ->
            st.copy(
                memories = result.fold(
                    onSuccess = { list ->
                        com.easychat.family.feature.today.BlockState.Ready(list, now)
                    },
                    onFailure = { e -> blockError(e, "loadMemories") },
                ),
            )
        }
    }

    private suspend fun loadBookmarks() {
        update { it.copy(bookmarks = com.easychat.family.feature.today.BlockState.Loading) }
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        val result = runCatching { container.life.inbox().items }
        update { st ->
            st.copy(
                bookmarks = result.fold(
                    onSuccess = { com.easychat.family.feature.today.BlockState.Ready(it, now) },
                    onFailure = { e -> blockError(e, "loadBookmarks") },
                ),
            )
        }
    }

    // ---- WP4:提醒管理 ----

    fun setEnabled(schedule: ScheduleDto, enabled: Boolean) {
        viewModelScope.launch {
            try {
                container.schedules.setEnabled(schedule.schedule_id, enabled)
                loadSchedules()
                _state.value = _state.value.copy(
                    message = if (enabled) "已恢复提醒" else "已暂停,需要时再打开",
                )
            } catch (failure: RequestFailure) {
                _state.value = _state.value.copy(message = friendly(failure))
            }
        }
    }

    fun delete(schedule: ScheduleDto) {
        viewModelScope.launch {
            try {
                container.schedules.delete(schedule.schedule_id)
                if (_state.value.detail?.schedule?.schedule_id == schedule.schedule_id) closeDetail()
                loadSchedules()
                _state.value = _state.value.copy(message = "已删除这条提醒")
            } catch (failure: RequestFailure) {
                _state.value = _state.value.copy(message = friendly(failure))
            }
        }
    }

    /** 创建:目标默认解析微信绑定;无绑定时报可理解错误(验收场景)。 */
    fun createSchedule(title: String, text: String, atLocal: LocalDateTime, onDone: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                container.schedules.create(
                    title = title.ifBlank { "提醒" },
                    text = text,
                    atLocal = atLocal,
                )
                loadSchedules()
                _state.value = _state.value.copy(message = "记好了,到时间会通过微信提醒你")
                onDone(true)
            } catch (failure: RequestFailure) {
                _state.value = _state.value.copy(message = friendly(failure))
                onDone(false)
            }
        }
    }

    fun openDetail(schedule: ScheduleDto) {
        val now = LocalDateTime.now(XnTime.DEFAULT_ZONE)
        _state.value = _state.value.copy(
            detail = ScheduleDetailState(
                schedule = schedule,
                nextRunText = if (schedule.next_run_at > 0.0) {
                    "预计提醒 " + XnTime.formatNextRun(schedule.next_run_at.toLong(), now = now)
                } else "",
                occurrencesLoading = true,
            ),
        )
        viewModelScope.launch {
            try {
                val occ = container.schedules.occurrences(schedule.schedule_id)
                _state.value = _state.value.copy(
                    detail = _state.value.detail?.copy(occurrences = occ, occurrencesLoading = false),
                )
            } catch (failure: RequestFailure) {
                _state.value = _state.value.copy(
                    detail = _state.value.detail?.copy(occurrencesLoading = false),
                    message = friendly(failure),
                )
            }
        }
    }

    fun closeDetail() {
        _state.value = _state.value.copy(detail = null)
    }

    fun clearMessage() {
        _state.value = _state.value.copy(message = "")
    }

    /** 原子更新:并发 load 的 read-copy-write 不能跨挂起点。 */
    private fun update(reducer: (LifeUiState) -> LifeUiState) {
        _state.update(reducer)
    }

    private fun blockError(e: Throwable, where: String): com.easychat.family.feature.today.BlockState.Error {
        if (e !is RequestFailure) {
            android.util.Log.e("XnLife", where + " failed", e)
            return com.easychat.family.feature.today.BlockState.Error("读取出了点小问题")
        }
        return errorBlock(e)
    }

    private fun errorBlock(failure: RequestFailure) = when (failure) {
        is RequestFailure.Http -> com.easychat.family.feature.today.BlockState.Error(
            failure.error.displayText(), failure.error.forbidden, failure.error.capabilityUnavailable,
        )
        is RequestFailure.Network -> com.easychat.family.feature.today.BlockState.Error("连接暂时断开了")
        RequestFailure.Cancelled -> com.easychat.family.feature.today.BlockState.Error("")
    }

    private fun friendly(failure: RequestFailure): String = when (failure) {
        is RequestFailure.Http -> failure.error.displayText()
        is RequestFailure.Network -> "连接暂时断开了,请稍后再试"
        RequestFailure.Cancelled -> ""
    }
}
