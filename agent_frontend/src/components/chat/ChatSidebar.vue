<template>
  <div class="chat-sidebar">
    <div class="sidebar-header">
      <h3>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><line x1="7" y1="9" x2="17" y2="9"/><line x1="7" y1="13" x2="14" y2="13"/></svg>
        <span>历史记录</span>
      </h3>
      <div class="header-actions">
        <button v-if="historyFilter === 'conversation'" @click="newChat" class="btn-new-chat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新对话
        </button>
        <button v-if="historyFilter === 'schedule'" @click="openNewCronModal" class="btn-new-chat btn-new-cron">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建定时任务
        </button>
      </div>
    </div>

    <!-- 筛选标签 -->
    <div class="filter-tabs">
      <button
        :class="['filter-tab', { active: historyFilter === 'conversation' }]"
        @click="setFilter('conversation')"
      >
        对话
      </button>
      <button
        :class="['filter-tab', { active: historyFilter === 'schedule' }]"
        @click="setFilter('schedule')"
      >
        定时任务
      </button>
    </div>

    <!-- 历史列表（对话模式） -->
    <div v-if="historyFilter === 'conversation'" class="history-list" @scroll="handleScroll">
      <div v-if="loading" class="loading-indicator">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>

      <div v-else-if="sortedHistory.length === 0" class="empty-state">
        暂无历史对话
      </div>

      <div
        v-for="chat in sortedHistory"
        :key="chat.id"
        :class="['history-item', { active: chat.id === selectedChatId }]"
        @click="selectChat(chat.id)"
      >
        <div class="history-item-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
        </div>
        <div class="history-item-content">
          <!-- 重命名编辑输入框（inline） -->
          <input
            v-if="editingId === chat.id"
            v-model="editingTitle"
            class="history-item-title-input"
            :placeholder="chat.title || chat.user_question || '新对话'"
            @click.stop
            @keydown.enter.prevent="saveRename(chat.id)"
            @keydown.esc="cancelRename"
            @blur="saveRename(chat.id)"
            ref="renameInput" />
          <template v-else>
            <div class="history-item-title" :title="chat.title || chat.user_question || '新对话'">
              {{ chat.title || chat.user_question || '新对话' }}
            </div>
            <div class="history-item-time">{{ formatTime(chat.update_time || chat.create_time) }}</div>
          </template>
        </div>
        <!-- 操作按钮 -->
        <div class="history-item-actions">
          <button @click.stop="startRename(chat)" class="btn-rename" title="重命名">✏️</button>
          <button @click.stop="deleteChat(chat.id)" class="btn-delete" title="删除">🗑️</button>
        </div>
      </div>

      <div v-if="hasMore" class="load-more-indicator">
        加载中...
      </div>
    </div>

    <!-- 定时任务列表 -->
    <div v-else class="history-list">
      <div v-if="cronLoading" class="loading-indicator">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      </div>
      <div v-else-if="cronJobs.length === 0" class="empty-state">
        暂无定时任务，点击上方「新建定时任务」创建
      </div>
      <div
        v-for="job in cronJobs"
        :key="'cron-' + job.id"
        :class="['cron-job-item', {
          'cron-executed': job.last_exec_status === 1,
          'cron-pending': job.last_exec_status === -1 || job.last_exec_status === 0,
          'cron-failed': job.last_exec_status === 2,
          'cron-disabled': !job.enabled
        }]"
      >
        <div class="cron-job-main">
          <div class="cron-job-header">
            <span :class="['cron-status-dot', job.last_exec_status === 1 ? 'dot-green' : job.last_exec_status === 2 ? 'dot-red' : 'dot-yellow']"></span>
            <span class="cron-job-name" :title="job.name">{{ job.name }}</span>
            <span v-if="job.last_exec_status === 2" class="cron-badge-failed">执行失败</span>
            <span v-else-if="job.last_exec_status === -1" class="cron-badge-pending">待执行</span>
            <span v-else-if="job.last_exec_status === 0" class="cron-badge-running">执行中</span>
            <span v-else-if="!job.enabled" class="cron-badge-off">已禁用</span>
          </div>
          <div class="cron-job-meta">
            <span class="cron-meta-item">{{ scheduleLabel(job) }}</span>
            <span class="cron-meta-item">{{ deliverText(job.deliver_to) }}</span>
            <span class="cron-meta-item">{{ (job.report_format || 'pdf').toUpperCase() }}</span>
          </div>
          <div class="cron-job-time">
            <span v-if="job.next_run_at && job.enabled" class="cron-meta-next">⭢ {{ formatTimeShort(job.next_run_at) }}</span>
            <span v-else-if="job.last_run_at" class="cron-meta-last">✓ {{ formatTimeShort(job.last_run_at) }}</span>
            <span v-else class="cron-meta-pending">待执行</span>
          </div>
          <div class="cron-job-actions">
            <button @click.stop="viewJobExecutions(job)" :title="'查看结果'" class="btn-cron-act">📊 结果</button>
            <button @click.stop="editCronJob(job)" class="btn-cron-act" title="编辑">✏️ 编辑</button>
            <button @click.stop="deleteCronJobHandler(job.id)" class="btn-cron-act" title="删除">🗑️ 删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 执行结果 Modal ── -->
    <div v-if="showExecutionsModal" class="modal-overlay" @click.self="closeExecutionsModal">
      <div class="modal-card cron-executions-modal">
        <div class="modal-header">
          <h4>📊 执行历史 - {{ selectedJob?.name }}</h4>
          <button @click="closeExecutionsModal" class="modal-close-btn">&times;</button>
        </div>
        <div class="modal-body modal-body-no-pad">
          <div v-if="executionsLoading" class="loading-indicator">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
          <div v-else-if="executions.length === 0" class="empty-state" style="padding:40px;">
            暂无执行记录
          </div>
          <div v-else class="executions-split">
            <!-- 左侧：记录列表 -->
            <div class="executions-sidebar" :style="{ width: execSidebarWidth + 'px' }">
              <div
                v-for="exec in executions"
                :key="exec.id"
                :class="['exec-sidebar-item', { active: selectedExecId === exec.id }]"
                @click="selectedExecId = exec.id"
              >
                <span :class="['exec-sb-status', exec.status === 1 ? 'ok' : exec.status === 2 ? 'fail' : exec.status === 3 ? 'warn' : 'pending']">
                  {{ exec.status === 1 ? '✅' : exec.status === 2 ? '❌' : exec.status === 3 ? '⚠️' : '⏳' }}
                </span>
                <div class="exec-sb-info">
                  <div class="exec-sb-time">{{ formatTimeShort(exec.started_at) }}</div>
                  <div class="exec-sb-meta">
                    <span v-if="exec.finished_at">{{ calculateDuration(exec.started_at, exec.finished_at) }}</span>
                    <span v-if="exec.deliver_status" class="exec-sb-deliver">{{ exec.deliver_status.includes('ok') ? '✅' : '⚠️' }}</span>
                  </div>
                </div>
              </div>
            </div>
            <!-- 拖拽分隔条 -->
            <div class="exec-resize-handle" @mousedown="startResizeExecSidebar"></div>
            <!-- 右侧：详情 -->
            <div class="executions-detail" v-if="selectedExec">
              <div class="exec-detail-header">
                <span :class="['execution-status', `status-${selectedExec.status}`]">
                  {{ selectedExec.status === 1 ? '✅ 成功' : selectedExec.status === 2 ? '❌ 失败' : selectedExec.status === 3 ? '⚠️ 质量问题' : '⏳ 执行中' }}
                </span>
                <span class="execution-time">{{ formatTime(selectedExec.started_at) }}</span>
                <span v-if="selectedExec.finished_at" class="execution-duration">
                  耗时: {{ calculateDuration(selectedExec.started_at, selectedExec.finished_at) }}
                </span>
                <span class="execution-spacer"></span>
                <button
                  v-if="selectedExec.result_text"
                  class="btn-view-toggle"
                  :class="{ active: getExecViewMode(selectedExec.id) === 'preview' }"
                  @click="toggleExecViewMode(selectedExec.id)"
                >
                  {{ getExecViewMode(selectedExec.id) === 'preview' ? '📝 预览' : '💻 源码' }}
                </button>
              </div>
              <div class="execution-deliver" :class="{ 'deliver-failed': selectedExec.deliver_status?.includes('failed') }">
                投递状态: {{ deliverStatusText(selectedExec.deliver_status) }}
              </div>
              <div v-if="selectedExec.quality_issues" class="execution-quality">
                ⚠️ 报告质量提示: {{ selectedExec.quality_issues }}
              </div>
              <div class="execution-result" v-if="selectedExec.result_text">
                <div v-if="getExecViewMode(selectedExec.id) === 'preview'" class="result-preview" v-html="renderMarkdown(selectedExec.result_text)"></div>
                <pre v-else class="result-content">{{ selectedExec.result_text }}</pre>
              </div>
              <div class="execution-error" v-if="selectedExec.error_message">
                <div class="error-label">错误信息:</div>
                <pre class="error-content">{{ selectedExec.error_message }}</pre>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="closeExecutionsModal" class="btn-modal-cancel">关闭</button>
        </div>
      </div>
    </div>

    <!-- ── 新建定时任务 Modal ── -->
    <div v-if="showCronModal" class="modal-overlay" @click.self="closeCronModal">
      <div class="modal-card cron-form-modal">
        <div class="modal-header">
          <h4>{{ editingCronJob ? '编辑定时任务' : '新建定时任务' }}</h4>
          <button @click="closeCronModal" class="modal-close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <label class="modal-label">任务名称</label>
          <input v-model="cronForm.name" class="modal-input" placeholder="如：每日安全报告" maxlength="30" />

          <label class="modal-label">提示词（AI 报告内容指令）</label>
          <textarea v-model="cronForm.prompt" class="modal-textarea" rows="8" placeholder="告诉 AI 要生成什么报告内容..."></textarea>

          <label class="modal-label">调度规则</label>
          <div class="modal-row">
            <select v-model="cronForm.schedule_type" class="modal-select" @change="onScheduleTypeChange">
              <option value="once">一次性执行</option>
              <option value="daily">每天</option>
              <option value="cron">Cron 表达式</option>
              <option value="interval">间隔执行</option>
            </select>
            <template v-if="cronForm.schedule_type === 'once'">
              <input v-model="cronForm._onceDate" class="modal-input" type="date" @change="onOnceDateTimeChange" />
              <input v-model="cronForm._onceTime" class="modal-input" type="time" @change="onOnceDateTimeChange" style="width:110px;" />
            </template>
            <input v-else-if="cronForm.schedule_type === 'daily'" v-model="cronForm._dailyTime" class="modal-input" type="time" />
            <input v-else-if="cronForm.schedule_type === 'cron'" v-model="cronForm.schedule_value" class="modal-input" placeholder="分 时 日 月 周，如 0 9 * * *" />
            <input v-else v-model="cronForm.schedule_value" class="modal-input" placeholder="数字+单位，如 30m / 1h / 3600s" />
          </div>
          <div class="modal-hint">
            {{ scheduleHint }}
          </div>

          <label class="modal-label">投递渠道</label>
          <div v-if="deliveryLoading" style="font-size:12px;color:var(--text-tertiary);padding:4px 0;">加载中...</div>
          <template v-else>
            <div class="modal-row" style="flex-wrap:wrap;gap:8px;">
              <label class="radio-label" style="margin-right:8px;">
                <input type="radio" v-model="cronForm.deliver_to" value="wechat" /> 📱 微信
              </label>
              <label class="radio-label" style="margin-right:8px;">
                <input type="radio" v-model="cronForm.deliver_to" value="email" /> 📧 邮箱
              </label>
              <label class="radio-label">
                <input type="radio" v-model="cronForm.deliver_to" value="both" /> 📱📧 两者
              </label>
            </div>

            <!-- 微信绑定显示 -->
            <div v-if="cronForm.deliver_to === 'wechat' || cronForm.deliver_to === 'both'" class="delivery-detail">
              <span class="delivery-detail-label">📱 微信:</span>
              <span v-if="deliveryOptions?.wechat_binding" class="delivery-detail-value" style="color:#27ae60;">
                ✅ {{ deliveryOptions.wechat_binding.nickname || deliveryOptions.wechat_binding.open_id }}
              </span>
              <span v-else class="delivery-detail-warn">⚠️ 未绑定微信，请先在「系统配置 → 用户绑定」中绑定</span>
            </div>

            <!-- 邮箱配置选择 -->
            <div v-if="cronForm.deliver_to === 'email' || cronForm.deliver_to === 'both'" class="delivery-detail">
              <div class="delivery-detail-row">
                <span class="delivery-detail-label">📤 发件箱:</span>
                <select v-if="deliveryOptions?.email_senders?.length" v-model="cronForm.email_sender_id" class="modal-select" style="flex:1;font-size:12px;">
                  <option v-for="s in deliveryOptions.email_senders" :key="s.id" :value="s.id">
                    {{ s.email }} {{ s.is_current ? '(当前)' : '' }}
                  </option>
                </select>
                <span v-else class="delivery-detail-warn">⚠️ 未配置，请先在「系统配置 → 邮箱配置」中配置</span>
              </div>
              <div class="delivery-detail-row" style="margin-top:4px;">
                <span class="delivery-detail-label">📥 收件箱:</span>
                <select v-if="deliveryOptions?.email_receivers?.length" v-model="cronForm.email_receiver_id" class="modal-select" style="flex:1;font-size:12px;">
                  <option v-for="r in deliveryOptions.email_receivers" :key="r.id" :value="r.id">
                    {{ r.email }} {{ r.is_current ? '(当前)' : '' }}
                  </option>
                </select>
                <span v-else class="delivery-detail-warn">⚠️ 未配置，请先在「系统配置 → 个人邮箱」中添加</span>
              </div>
            </div>

            <!-- 报告格式选择 -->
            <div style="margin-top:8px;">
              <span class="modal-label" style="margin-top:2px;">报告格式</span>
              <div class="modal-row" style="gap:8px;">
                <label class="radio-label"><input type="radio" v-model="cronForm.report_format" value="pdf" /> 📄 PDF</label>
                <label class="radio-label"><input type="radio" v-model="cronForm.report_format" value="markdown" /> 📝 Markdown</label>
                <label class="radio-label"><input type="radio" v-model="cronForm.report_format" value="text" /> 📃 纯文本</label>
              </div>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button @click="closeCronModal" class="btn-modal-cancel">取消</button>
          <button @click="saveCronJob" class="btn-modal-save" :disabled="!cronForm.name || !cronForm.prompt || cronSaving">
            {{ cronSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore } from '@/stores/chat'
import { getUserSessions, deleteSession, renameSession } from '@/api/session'
import { useAuthStore } from '@/stores/auth'
import {
  getCronJobs, createCronJob, updateCronJob, deleteCronJob,
  getDeliveryOptions, getCronExecutions,
  type CronJob, type DeliveryOptions,
} from '@/api/cron'

const sidebarStore = useSidebarStore()
const chatStore = useChatStore()
const authStore = useAuthStore()

// ── 重命名相关状态 ──
const editingId = ref<string>('')
const editingTitle = ref<string>('')
const renameInput = ref<HTMLInputElement | null>(null)

// ── 定时任务状态 ──
const cronJobs = ref<CronJob[]>([])
const cronLoading = ref(false)
const showCronModal = ref(false)
const editingCronJob = ref<CronJob | null>(null)
const deliveryOptions = ref<DeliveryOptions | null>(null)
const deliveryLoading = ref(false)
const cronForm = ref({
  name: '',
  prompt: '',
  schedule_type: 'daily',
  schedule_value: '09:00',
  deliver_to: 'wechat' as string,
  report_format: 'pdf' as string,
  _dailyTime: '09:00',
  _onceDate: '',
  _onceTime: '09:00',
  email_sender_id: null as number | null,
  email_receiver_id: null as number | null,
})

// ── 执行结果 Modal 状态 ──
const showExecutionsModal = ref(false)
const selectedJob = ref<CronJob | null>(null)
const executions = ref<any[]>([])
const executionsLoading = ref(false)
const selectedExecId = ref<number | null>(null)
const execViewModes = ref<Record<number, 'preview' | 'source'>>({})
const execSidebarWidth = ref(260)
const execResizing = ref(false)

const selectedExec = computed(() => 
  executions.value.find(e => e.id === selectedExecId.value) || null
)

function startResizeExecSidebar(e: MouseEvent) {
  execResizing.value = true
  const startX = e.clientX
  const startW = execSidebarWidth.value
  const onMove = (ev: MouseEvent) => {
    execSidebarWidth.value = Math.max(180, Math.min(500, startW + ev.clientX - startX))
  }
  const onUp = () => {
    execResizing.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function getExecViewMode(execId: number): 'preview' | 'source' {
  return execViewModes.value[execId] || 'preview'
}

function toggleExecViewMode(execId: number) {
  execViewModes.value[execId] = getExecViewMode(execId) === 'preview' ? 'source' : 'preview'
}

// 调度类型切换时重置默认值
function onScheduleTypeChange() {
  const t = cronForm.value.schedule_type
  if (t === 'once') {
    cronForm.value.schedule_value = cronForm.value._onceDate
      ? `${cronForm.value._onceDate} ${cronForm.value._onceTime}`
      : ''
  } else if (t === 'daily') {
    cronForm.value.schedule_value = cronForm.value._dailyTime || '09:00'
  } else if (t === 'cron') {
    cronForm.value.schedule_value = '0 9 * * *'
  } else {
    cronForm.value.schedule_value = '30m'
  }
}

// 一次性日期/时间变化时更新 schedule_value
function onOnceDateTimeChange() {
  if (cronForm.value._onceDate && cronForm.value._onceTime) {
    cronForm.value.schedule_value = `${cronForm.value._onceDate} ${cronForm.value._onceTime}`
  }
}

// 开始重命名（进入 inline 编辑态并聚焦）
async function startRename(chat: { id: string; title?: string; user_question?: string }) {
  editingId.value = chat.id
  editingTitle.value = chat.title || chat.user_question || ''
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

// 取消重命名
function cancelRename() {
  editingId.value = ''
  editingTitle.value = ''
}

// 保存重命名
async function saveRename(chatId: string) {
  if (editingId.value !== chatId) return
  const newTitle = editingTitle.value.trim()
  // 先退出编辑态，避免 @blur 与保存重复触发
  editingId.value = ''
  const previousTitle = sidebarStore.chatHistory.find((c) => c.id === chatId)?.title
  if (!newTitle || newTitle === previousTitle) return

  try {
    await renameSession(chatId, newTitle)
    sidebarStore.updateInHistory(chatId, { title: newTitle, user_question: newTitle })
  } catch (error: any) {
    console.error('重命名失败:', error)
    alert(error?.response?.data?.detail || '重命名失败，请重试')
  }
}

// 计算属性
const historyFilter = computed(() => sidebarStore.historyFilter)
const sortedHistory = computed(() => sidebarStore.sortedHistory)
const loading = computed(() => sidebarStore.loading)
const hasMore = computed(() => sidebarStore.hasMore)
const currentChatId = computed(() => chatStore.currentChatId)

// 选中的会话 ID
// 直接返回 currentChatId，不依赖 messages.length
// 这样可以避免切换会话时的闪烁问题
const selectedChatId = computed(() => chatStore.currentChatId)

// 加载历史
async function loadHistory(append = false) {
  // 对话模式：原有逻辑
  if (historyFilter.value === 'conversation') {
    sidebarStore.setLoading(true)
    try {
      const userId = authStore.userId
      const offset = append ? sidebarStore.offset : 0
      const result = await getUserSessions(userId, offset, sidebarStore.pageSize, 'conversation')
      const normalized = (result.sessions || []).map((s) => ({
        ...s, id: s.id || (s as any).session_id || '',
        title: s.title || s.user_question || '',
      }))
      if (append) {
        sidebarStore.appendChatHistory(normalized)
      } else {
        sidebarStore.setChatHistory(normalized)
      }
      sidebarStore.setHasMore(result.has_more)
      sidebarStore.setOffset(offset + normalized.length)
    } catch (error) {
      console.error('加载历史失败:', error)
    } finally {
      sidebarStore.setLoading(false)
    }
    return
  }

  // 定时任务模式：加载 cron jobs
  cronLoading.value = true
  try {
    const userId = authStore.userId
    const result = await getCronJobs(Number(userId))
    cronJobs.value = result.jobs || []
  } catch (error) {
    console.error('加载定时任务失败:', error)
    cronJobs.value = []
  } finally {
    cronLoading.value = false
  }
}

// 设置筛选
function setFilter(filter: string) {
  sidebarStore.setFilter(filter)
  loadHistory(false)
}

// ── 定时任务操作 ──

/** 翻译 cron 表达式为人可读格式 */
function translateCron(scheduleType: string, scheduleValue: string): string {
  if (scheduleType === 'once') return scheduleValue ? `一次性 ${scheduleValue}` : '一次性'
  if (scheduleType === 'daily') return `每天 ${scheduleValue}`
  if (scheduleType === 'interval') {
    const v = scheduleValue || ''
    const num = parseInt(v)
    if (v.includes('m') || v.includes('min')) return `每 ${num} 分钟`
    if (v.includes('h') || v.includes('hr')) return `每 ${num} 小时`
    if (v.includes('d')) return `每 ${num} 天`
    if (v.includes('s')) return `每 ${num} 秒`
    return `每 ${v}`
  }
  // cron 表达式翻译
  const parts = (scheduleValue || '').trim().split(/\s+/)
  if (parts.length >= 5) {
    const [min, hour, dom, , dow] = parts
    const days = ['日', '一', '二', '三', '四', '五', '六']
    let result = ''
    if (dow !== '*' && dom === '*') {
      // 按星期几执行
      const dowNums = dow.split(',').map(Number).filter(n => !isNaN(n))
      if (dowNums.length > 0) {
        const dayNames = dowNums.map(d => days[d % 7]).join('、')
        result = `每周${dayNames}`
      }
    } else if (dom !== '*') {
      result = `每月${dom}号`
    }
    if (min !== '*' || hour !== '*') {
      const h = hour === '*' ? '0' : hour
      const m = min === '*' ? '0' : min
      result += ` ${h.padStart(2, '0')}:${m.padStart(2, '0')}`
    }
    if (result) return result
  }
  return scheduleValue || '自定义'
}

/** 调度规则可读标签 */
function scheduleLabel(job: CronJob): string {
  return translateCron(job.schedule_type, job.schedule_value)
}

/** 投递渠道文本 */
function deliverText(d: string): string {
  if (d === 'wechat') return '微信'
  if (d === 'email') return '邮箱'
  if (d === 'both') return '微信+邮箱'
  return d
}

/** 时间显示（含年份） */
function formatTimeShort(timeStr?: string): string {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 投递状态中文化 */
function deliverStatusText(status: string): string {
  if (!status) return '⏳ 未投递'
  return status
    .replace(/email:ok/gi, '📧 邮件已发送')
    .replace(/email:failed/gi, '📧 邮件失败（请检查邮箱配置）')
    .replace(/wechat:ok/gi, '💬 微信已发送')
    .replace(/wechat:failed/gi, '💬 微信失败（原因见下方）')
    .replace(/;\s*/g, ' · ')
}

/** 简易 Markdown 渲染（标题/加粗/代码块/列表） */
function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text
    // 转义 HTML
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 代码块 ```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
  // 行内代码 `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 标题
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  // 加粗
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // 无序列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  // 换行
  html = html.replace(/\n\n/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  return `<p>${html}</p>`
}

/** 查看任务执行结果 */
async function viewJobExecutions(job: CronJob) {
  selectedJob.value = job
  showExecutionsModal.value = true
  executionsLoading.value = true
  try {
    const result = await getCronExecutions(job.id, 20)
    executions.value = result.executions || []
    selectedExecId.value = executions.value[0]?.id || null
  } catch (error) {
    console.error('加载执行历史失败:', error)
    executions.value = []
  } finally {
    executionsLoading.value = false
  }
}

/** 关闭执行结果 Modal */
function closeExecutionsModal() {
  showExecutionsModal.value = false
  selectedJob.value = null
  selectedExecId.value = null
  executions.value = []
}

/** 计算执行耗时 */
function calculateDuration(startedAt: string, finishedAt?: string): string {
  if (!finishedAt) return '-'
  const start = new Date(startedAt).getTime()
  const end = new Date(finishedAt).getTime()
  const diffMs = end - start
  if (diffMs < 1000) return '<1s'
  if (diffMs < 60000) return `${Math.round(diffMs / 1000)}s`
  const minutes = Math.floor(diffMs / 60000)
  const seconds = Math.round((diffMs % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

/** 调度提示 */
const scheduleHint = computed(() => {
  const t = cronForm.value.schedule_type
  const v = cronForm.value.schedule_value || ''
  const translated = translateCron(t, v)
  if (t === 'cron' && v && translated !== v) {
    return `→ ${translated}（输入: ${v}）`
  }
  if (translated && translated !== v) return `→ ${translated}`
  if (t === 'once') return '一次性任务：执行完成后保留记录，可修改时间再次执行。'
  if (t === 'cron') return '标准 5 字段 cron: 分 时 日 月 周。如 "0 9 * * *" = 每天9点。输入后自动翻译'
  if (t === 'interval') return '数字+单位: 30m=30分钟, 1h=1小时。输入后自动翻译'
  return ''
})

/** 加载投递选项 */
async function loadDeliveryOptions() {
  deliveryLoading.value = true
  try {
    const userId = authStore.userId
    const result = await getDeliveryOptions(Number(userId))
    deliveryOptions.value = result.data

    // 自动选中当前邮箱（仅新建时，编辑时保留已有选择）
    if (!editingCronJob.value) {
      const curSender = result.data.email_senders?.find(s => s.is_current)
      const curReceiver = result.data.email_receivers?.find(r => r.is_current)
      cronForm.value.email_sender_id = curSender?.id ?? result.data.email_senders?.[0]?.id ?? null
      cronForm.value.email_receiver_id = curReceiver?.id ?? result.data.email_receivers?.[0]?.id ?? null
    }
  } catch (error) {
    console.error('加载投递选项失败:', error)
  } finally {
    deliveryLoading.value = false
  }
}

/** 打开新建 Modal */
function openNewCronModal() {
  editingCronJob.value = null
  cronForm.value = {
    name: '', prompt: '', schedule_type: 'daily', schedule_value: '09:00',
    deliver_to: 'wechat', report_format: 'pdf',
    _dailyTime: '09:00', _onceDate: '', _onceTime: '09:00',
    email_sender_id: null, email_receiver_id: null,
  }
  showCronModal.value = true
  loadDeliveryOptions()
}

/** 编辑定时任务 */
function editCronJob(job: CronJob) {
  editingCronJob.value = job
  const isOnce = job.schedule_type === 'once'
  let onceDate = '', onceTime = '09:00'
  if (isOnce && job.schedule_value) {
    const parts = job.schedule_value.split(/[ T]/)
    onceDate = parts[0] || ''
    onceTime = parts[1]?.substring(0, 5) || '09:00'
  }
  cronForm.value = {
    name: job.name,
    prompt: job.prompt,
    schedule_type: job.schedule_type,
    schedule_value: job.schedule_value,
    deliver_to: job.deliver_to,
    report_format: job.report_format || 'pdf',
    _dailyTime: job.schedule_type === 'daily' ? job.schedule_value : '09:00',
    _onceDate: onceDate,
    _onceTime: onceTime,
    email_sender_id: job.email_sender_id ?? null,
    email_receiver_id: job.email_receiver_id ?? null,
  }
  showCronModal.value = true
  loadDeliveryOptions()
}

/** 关闭 Modal */
function closeCronModal() {
  showCronModal.value = false
  editingCronJob.value = null
}

/** 保存定时任务 */
const cronSaving = ref(false)

async function saveCronJob() {
  if (!cronForm.value.name || !cronForm.value.prompt) return

  // 处理不同类型的时间值
  let scheduleValue = cronForm.value.schedule_value
  const scheduleType = cronForm.value.schedule_type

  if (scheduleType === 'daily') {
    // 每天：使用时间选择器的值
    scheduleValue = cronForm.value._dailyTime || '09:00'
  } else if (scheduleType === 'once') {
    // 一次性任务：组合日期和时间
    if (cronForm.value._onceDate && cronForm.value._onceTime) {
      scheduleValue = `${cronForm.value._onceDate} ${cronForm.value._onceTime}`
    } else if (cronForm.value._onceDate) {
      scheduleValue = `${cronForm.value._onceDate} 09:00`
    } else {
      alert('请选择执行日期')
      return
    }
  } else if (scheduleType === 'cron') {
    // Cron 表达式：验证非空
    if (!scheduleValue || !scheduleValue.trim()) {
      alert('请输入 Cron 表达式')
      return
    }
  } else if (scheduleType === 'interval') {
    // 间隔执行：验证非空
    if (!scheduleValue || !scheduleValue.trim()) {
      alert('请输入执行间隔')
      return
    }
  }

  cronSaving.value = true

  try {
    const userId = authStore.userId
    const senderId = (cronForm.value.deliver_to === 'email' || cronForm.value.deliver_to === 'both')
      ? (cronForm.value.email_sender_id ?? null) : null
    const receiverId = (cronForm.value.deliver_to === 'email' || cronForm.value.deliver_to === 'both')
      ? (cronForm.value.email_receiver_id ?? null) : null

    if (editingCronJob.value) {
      await updateCronJob(editingCronJob.value.id, {
        name: cronForm.value.name,
        prompt: cronForm.value.prompt,
        schedule_type: cronForm.value.schedule_type,
        schedule_value: scheduleValue,
        deliver_to: cronForm.value.deliver_to,
        report_format: cronForm.value.report_format,
        email_sender_id: senderId,
        email_receiver_id: receiverId,
      }, Number(userId))
      alert('✅ 已保存')
    } else {
      // 新建模式：创建后自动关闭
      await createCronJob({
        user_id: Number(userId),
        name: cronForm.value.name,
        prompt: cronForm.value.prompt,
        schedule_type: cronForm.value.schedule_type,
        schedule_value: scheduleValue,
        deliver_to: cronForm.value.deliver_to,
        report_format: cronForm.value.report_format,
        email_sender_id: senderId,
        email_receiver_id: receiverId,
      })
      closeCronModal()
      alert('✅ 任务已创建')
    }
    loadHistory(false) // 刷新列表
  } catch (error: any) {
    console.error('保存定时任务失败:', error)
    alert(error?.response?.data?.detail || error?.message || '保存失败')
  } finally {
    cronSaving.value = false
  }
}

/** 删除定时任务 */
async function deleteCronJobHandler(jobId: number) {
  if (!confirm('确定要删除这个定时任务吗？')) return
  try {
    const userId = authStore.userId
    await deleteCronJob(jobId, Number(userId))
    loadHistory(false)
  } catch (error: any) {
    console.error('删除失败:', error)
    alert(error?.response?.data?.detail || '删除失败')
  }
}

// 选择聊天
async function selectChat(chatId: string) {
  // 去重判断必须用 selectedChatId（而非 currentChatId）。
  // 刚进入页面时 currentChatId 可能从 sessionStorage 恢复上一次的残留值，
  // 若恰等于列表第一条的 id，会导致首次点击无反应。
  if (chatId === selectedChatId.value) return

  // 注意：不要在触发事件前调用 chatStore.setCurrentChatId(chatId)。
  // 一旦提前设置，loadChatHistory 里的守卫
  // （messages.length > 0 && currentChatId === chatId）会恒成立而跳过加载，
  // 导致"第一次点击能跳转、后续点击无反应"。currentChatId 由 loadChatHistory 统一设置。
  // 触发加载消息
  window.dispatchEvent(new CustomEvent('chat:loadHistory', { detail: { chatId } }))
}

// 删除聊天
async function deleteChat(chatId: string) {
  if (!confirm('确定要删除这个对话吗？')) return

  try {
    await deleteSession(chatId)
    sidebarStore.removeFromHistory(chatId)

    // 如果删除的是当前对话，清空消息
    if (chatId === currentChatId.value) {
      chatStore.clearMessages()
      chatStore.setCurrentChatId('')
    }
  } catch (error) {
    console.error('删除对话失败:', error)
  }
}

// 新建对话
function newChat() {
  chatStore.clearMessages()
  chatStore.setCurrentChatId('')
}

// 滚动加载更多
function handleScroll(e: Event) {
  const target = e.target as HTMLElement
  if (target.scrollTop + target.clientHeight >= target.scrollHeight - 100) {
    if (!loading.value && hasMore.value) {
      loadHistory(true)
    }
  }
}

// 格式化时间
function formatTime(time?: string): string {
  if (!time) return ''
  const date = new Date(time)
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 追踪本轮新增的会话 ID
const newlyAddedIds = new Set<string>()

// 初始化加载
onMounted(() => {
  loadHistory(false)

  // 监听聊天完成事件，从后端重新加载历史列表
  const handleRefreshHistory = async () => {
    // 聊天完成后从后端重新加载，确保列表完整且顺序正确
    await loadHistory(false)
  }
  window.addEventListener('chat:refreshHistory', handleRefreshHistory)

  // 监听新会话事件，立即添加到历史列表
  const handleNewSession = (e: Event) => {
    const detail = (e as CustomEvent).detail
    const now = new Date().toLocaleString('zh-CN')

    // 先移除已存在的重复项
    sidebarStore.removeFromHistory(detail.chatId)

    const newChat = {
      id: detail.chatId,
      title: detail.title,
      user_question: detail.title,
      update_time: now,
      create_time: now,
      is_schedule: 0,
    }
    // 添加到列表顶部
    sidebarStore.prependChatHistory(newChat)
    newlyAddedIds.add(detail.chatId)
  }
  window.addEventListener('chat:newSession', handleNewSession)

  // 组件卸载时移除监听器
  onUnmounted(() => {
    window.removeEventListener('chat:refreshHistory', handleRefreshHistory)
    window.removeEventListener('chat:newSession', handleNewSession)
  })

  // 监听认证状态：登录后重新加载历史列表
  watch(() => authStore.isAuthenticated, (isAuth) => {
    if (isAuth) {
      loadHistory(false)
    }
  })
})

// 暴露方法给父组件
defineExpose({
  loadHistory,
})
</script>

<style scoped>
.chat-sidebar {
  width: 280px;
  border-right: 1px solid var(--border-primary);
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-header {
  padding: 16px 16px 14px;
  border-bottom: 1px solid var(--border-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-header h3 svg {
  width: 17px;
  height: 17px;
  color: var(--brand);
}

.btn-new-chat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.btn-new-chat svg {
  width: 13px;
  height: 13px;
}

.btn-new-chat:hover {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-light);
}

.filter-tabs {
  display: flex;
  padding: 10px 12px 6px;
  gap: 6px;
  border-bottom: 1px solid var(--border-primary);
}

.filter-tab {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  position: relative;
}

.filter-tab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.filter-tab.active {
  background: var(--brand-light);
  color: var(--brand);
  font-weight: 500;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 2px;
  border: 1px solid transparent;
}

.history-item:hover {
  background: var(--bg-hover);
}

.history-item.active {
  background: var(--brand-light);
  border-color: var(--border-focus);
}

.history-item-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  flex-shrink: 0;
  transition: background 0.2s, color 0.2s;
}

.history-item-icon svg {
  width: 16px;
  height: 16px;
}

.history-item:hover .history-item-icon {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.history-item.active .history-item-icon {
  background: var(--brand);
  color: #fff;
}

.history-item-content {
  flex: 1;
  min-width: 0;
}

.history-item-title {
  font-size: 13.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
  line-height: 1.35;
}

.history-item-time {
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.history-item-actions {
  display: flex;
  gap: 2px;
  align-items: center;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.history-item:hover .history-item-actions {
  opacity: 1;
}

.btn-rename,
.btn-delete {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 15px;
  transition: transform 0.2s;
  padding: 4px;
  border-radius: 6px;
  color: var(--text-tertiary);
}

.btn-rename:hover,
.btn-delete:hover {
  transform: scale(1.2);
  background: var(--bg-secondary);
}

/* inline 重命名输入框 */
.history-item-title-input {
  width: 100%;
  font-size: 14px;
  padding: 4px 8px;
  border: 1px solid var(--brand);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  box-sizing: border-box;
  margin-bottom: 4px;
}

.history-item-title-input:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--brand-light);
}

.loading-indicator {
  display: flex;
  justify-content: center;
  gap: 4px;
  padding: 20px;
}

.loading-indicator .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-indicator .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-indicator .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.load-more-indicator {
  text-align: center;
  padding: 12px;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* ── Header Actions ── */
.header-actions {
  display: flex;
  gap: 6px;
}

.btn-new-cron {
  border-color: var(--cron-accent, #f0a030) !important;
  color: var(--cron-accent, #f0a030) !important;
}

.btn-new-cron:hover {
  background: #fff8e1 !important;
}

/* ── 定时任务列表项（优化布局） ── */
.cron-job-item {
  display: flex;
  align-items: stretch;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  margin-bottom: 6px;
  cursor: default;
  transition: background 0.2s;
  border-left: 3px solid transparent;
  background: var(--bg-primary);
}

.cron-job-item:hover {
  background: var(--bg-hover);
}

.cron-job-item.cron-executed {
  border-left-color: #4caf50;
}

.cron-job-item.cron-pending:not(.cron-disabled) {
  border-left-color: #f0a030;
}

.cron-job-item.cron-failed {
  border-left-color: #e53935;
}

/* 禁用状态：只调整透明度，不覆盖执行状态的颜色 */
.cron-job-item.cron-disabled {
  opacity: 0.6;
}

/* 禁用且无执行记录时，左边框灰色 */
.cron-job-item.cron-disabled.cron-pending {
  border-left-color: #ccc;
}

.cron-job-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cron-job-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cron-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.cron-status-dot.dot-green {
  background: #4caf50;
  box-shadow: 0 0 4px rgba(76, 175, 80, 0.4);
}

.cron-status-dot.dot-yellow {
  background: #f0a030;
  box-shadow: 0 0 4px rgba(240, 160, 48, 0.4);
}

.cron-status-dot.dot-red {
  background: #e53935;
  box-shadow: 0 0 4px rgba(229, 57, 53, 0.4);
}

.cron-job-name {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cron-badge-off {
  font-size: 10px;
  padding: 2px 6px;
  background: #e0e0e0;
  color: #666;
  border-radius: 4px;
  white-space: nowrap;
}

.cron-badge-failed {
  font-size: 10px;
  padding: 2px 6px;
  background: #ffebee;
  color: #c62828;
  border-radius: 4px;
  white-space: nowrap;
}

.cron-badge-pending {
  font-size: 10px;
  padding: 2px 6px;
  background: #fff8e1;
  color: #f57c00;
  border-radius: 4px;
  white-space: nowrap;
}

.cron-badge-running {
  font-size: 10px;
  padding: 2px 6px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 4px;
  white-space: nowrap;
}

.cron-job-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
}

.cron-job-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.cron-meta-item {
  display: inline-block;
  padding: 1px 6px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 11px;
}

.cron-meta-next {
  color: #4e6ef2;
  font-weight: 500;
}

.cron-meta-last {
  color: var(--text-tertiary);
}

.cron-meta-pending {
  color: var(--text-tertiary);
  font-style: italic;
}

/* 旧的标签样式已移除，改用简洁的 meta 行 */

.cron-time-dot {
  color: #4caf50;
  font-size: 10px;
}

/* 旧的 pending 样式已合并到 .cron-meta-pending */

/* 操作按钮 — 竖排在右侧 */
.cron-job-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.cron-job-item:hover .cron-job-actions {
  opacity: 1;
}

.btn-cron-act {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.btn-cron-act:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ── 执行结果 Modal ── */
.cron-executions-modal {
  width: calc(100vw - 40px);
  min-width: 900px;
  max-width: 1400px;
  height: calc(100vh - 60px);
  min-height: 500px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  resize: both;
}

.modal-body-no-pad {
  padding: 0 !important;
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── 左右分割 ── */
.executions-split {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── 左侧：记录列表 ── */
.executions-sidebar {
  min-width: 180px;
  max-width: 500px;
  border-right: 1px solid var(--border-primary);
  overflow-y: auto;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

/* ── 拖拽分隔条 ── */
.exec-resize-handle {
  width: 5px;
  cursor: col-resize;
  background: var(--border-primary);
  flex-shrink: 0;
  transition: background 0.15s;
}

.exec-resize-handle:hover {
  background: var(--brand);
}

.exec-sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-primary);
  transition: background 0.15s;
}

.exec-sidebar-item:hover {
  background: var(--bg-hover);
}

.exec-sidebar-item.active {
  background: var(--brand-light);
  border-right: 3px solid var(--brand);
}

.exec-sb-status {
  font-size: 14px;
  flex-shrink: 0;
}

.exec-sb-status.warn {
  filter: sepia(0.6) saturate(3);
}

.exec-sb-info {
  min-width: 0;
}

.exec-sb-time {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.exec-sb-meta {
  font-size: 10px;
  color: var(--text-tertiary);
  display: flex;
  gap: 6px;
  margin-top: 1px;
}

/* ── 右侧：详情 ── */
.executions-detail {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.exec-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.executions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.execution-item {
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 16px;
  background: var(--bg-primary);
}

.execution-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.execution-status {
  font-size: 13px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 12px;
}

.execution-status.status-1 {
  background: #e8f5e9;
  color: #2e7d32;
}

.execution-status.status-2 {
  background: #ffebee;
  color: #c62828;
}

.execution-status.status-0 {
  background: #fff3e0;
  color: #ef6c00;
}

/* 质量结算降级码（成功但有质量问题） */
.execution-status.status-3 {
  background: #fff8e1;
  color: #b26a00;
}

.execution-quality {
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #fff8e1;
  color: #b26a00;
  font-size: 12px;
  line-height: 1.5;
}

.execution-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.execution-duration {
  font-size: 12px;
  color: var(--text-tertiary);
}

.execution-spacer {
  flex: 1;
}

/* 预览/源码切换按钮 */
.btn-view-toggle {
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--border-secondary);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.btn-view-toggle:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.btn-view-toggle.active {
  background: var(--brand);
  color: #fff;
  border-color: var(--brand);
}

.execution-deliver {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
  padding: 4px 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  display: inline-block;
}

.execution-deliver.deliver-failed {
  background: #fff5f5;
  color: #c62828;
  border: 1px solid #ffcdd2;
}

.execution-result,
.execution-error {
  margin-top: 10px;
}

.result-preview {
  padding: 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-primary);
}

.result-preview :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 16px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-secondary);
  color: var(--text-primary);
}

.result-preview :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin: 14px 0 6px;
  color: var(--text-primary);
}

.result-preview :deep(h4) {
  font-size: 13px;
  font-weight: 600;
  margin: 10px 0 4px;
  color: var(--text-secondary);
}

.result-preview :deep(p) {
  margin: 4px 0;
}

.result-preview :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

.result-preview :deep(code) {
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
}

.result-preview :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
}

.result-preview :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}

.result-preview :deep(li) {
  margin: 2px 0 2px 20px;
}

.result-content,
.error-content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  line-height: 1.6;
}

.error-content {
  background: #ffebee;
  border-color: #ef9a9a;
  color: #c62828;
}

/* ── Modal ── */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 440px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

/* 定时任务表单 Modal 加宽 */
.cron-form-modal {
  width: 640px;
  max-width: 92vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close-btn {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 0 4px;
  line-height: 1;
}

.modal-close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-top: 10px;
  margin-bottom: 4px;
}

.modal-input,
.modal-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  box-sizing: border-box;
}

.modal-input:focus,
.modal-select:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-light);
}

.modal-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  resize: vertical;
  box-sizing: border-box;
  font-family: inherit;
}

.modal-textarea:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-light);
}

.modal-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.modal-select {
  width: auto;
  flex-shrink: 0;
}

.modal-hint {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-primary);
}

.btn-modal-cancel {
  padding: 8px 18px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
}

.btn-modal-cancel:hover {
  background: var(--bg-hover);
}

.btn-modal-save {
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  background: var(--brand);
  color: #fff;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn-modal-save:hover {
  opacity: 0.9;
}

.btn-modal-exec {
  padding: 8px 18px;
  border: 1px solid var(--brand);
  border-radius: 8px;
  background: transparent;
  color: var(--brand);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn-modal-exec:hover {
  background: var(--brand);
  color: #fff;
}

.btn-modal-exec:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-modal-save:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-modal-save:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ── 投递详情 ── */
.delivery-detail {
  margin-top: 6px;
  padding: 8px 12px;
  background: var(--bg-tertiary, #f7f8fa);
  border-radius: 8px;
  font-size: 12.5px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.delivery-detail-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.delivery-detail-label {
  color: var(--text-secondary);
  font-weight: 500;
  flex-shrink: 0;
}

.delivery-detail-value {
  color: var(--text-primary);
}

.delivery-detail-warn {
  color: #e67e22;
  font-size: 12px;
}
</style>
