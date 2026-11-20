<template>
  <div class="page-container superagent-page">
    <header class="page-header">
      <div>
        <h1>超级代理</h1>
        <p class="hint">提交编码需求、查看执行轨迹和 Draft PR。</p>
      </div>
      <div class="header-actions">
        <button v-if="caps.manage" class="btn btn-secondary" :aria-expanded="showOps" @click="toggleOps">
          运维面板
        </button>
        <button v-if="caps.manage" class="btn btn-secondary" :aria-expanded="showSettings" @click="toggleSettings">
          仓库配置
        </button>
        <button v-if="caps.create" type="button" class="btn btn-primary" @click="taskDialog?.showModal()">新建任务</button>
      </div>
    </header>

    <section v-if="caps.view && caps.create" class="agent-status" aria-label="任务受理状态">
      <span class="badge" :class="gateReasons.length ? 'badge-warning' : 'badge-success'">
        {{ gateReasons.length ? '暂不可受理' : '可受理任务' }}
      </span>
      <span v-if="gateReasons.length" class="status-copy">{{ gateReasons.join(' · ') }}</span>
      <span v-else-if="caps.repo_url" class="status-copy">{{ caps.repo_url }}</span>
    </section>

    <!-- 运维面板（仅 manage） -->
    <div v-if="showOps && caps.manage" class="card ops-card">
      <div class="ops-grid" v-if="opsMetrics">
        <div class="ops-cell">
          <span class="ops-label">Runner / 凭证 / 开关</span>
          <span>{{ opsMetrics.runner_ready ? '✅ runner' : '⛔ runner' }}
            {{ opsMetrics.credentials_ready ? '✅ 凭证' : '⛔ 凭证' }}
            {{ opsMetrics.enabled ? '✅ 已启用' : '⛔ 停用' }}</span>
        </div>
        <div class="ops-cell">
          <span class="ops-label">任务分布</span>
          <span>{{ Object.entries(opsMetrics.tasks_by_status).map(([k, v]) => `${k}:${v}`).join(' ') || '无任务' }}</span>
        </div>
        <div class="ops-cell">
          <span class="ops-label">执行 attempt</span>
          <span>{{ opsMetrics.attempts.succeeded }}/{{ opsMetrics.attempts.total }} 成功 · 失败 {{ opsMetrics.attempts.failed }} · 均 {{ opsMetrics.attempts.avg_duration_seconds }}s</span>
        </div>
        <div class="ops-cell">
          <span class="ops-label">验证</span>
          <span>{{ opsMetrics.verification.verify_commands }} 条命令 · 受阻 {{ opsMetrics.verification.blocked }}/{{ opsMetrics.verification.total }} · {{ opsMetrics.verification.allow_unverified_draft ? '允许未验证发布' : '强制门禁' }}</span>
        </div>
        <div class="ops-cell">
          <span class="ops-label">回执</span>
          <span>{{ Object.entries(opsMetrics.deliveries_by_status).map(([k, v]) => `${k}:${v}`).join(' ') || '无投递' }}</span>
        </div>
        <div class="ops-cell">
          <span class="ops-label">Webhook 待处理</span>
          <span>{{ opsMetrics.webhook_pending }}</span>
        </div>
      </div>
      <div v-else class="muted">加载中…</div>
    </div>

    <!-- 仓库配置（仅 manage） -->
    <form v-if="showSettings && caps.manage" class="card settings-card" @submit.prevent="saveSettings">
      <div class="form-row">
        <label class="form-label">启用</label>
        <label class="switch">
          <input v-model="settingsDraft.enabled" type="checkbox" />
          <span>{{ settingsDraft.enabled ? '已启用' : '已停用' }}</span>
        </label>
      </div>
      <div class="form-group">
        <label class="form-label">目标仓库（GitHub HTTPS）</label>
        <input v-model="settingsDraft.repo_url" class="input" placeholder="https://github.com/owner/repo.git" />
      </div>
      <div class="form-row">
        <div class="form-group grow">
          <label class="form-label">基线分支</label>
          <input v-model="settingsDraft.base_branch" class="input" placeholder="main" />
        </div>
        <div class="form-group grow">
          <label class="form-label">并发上限（当前版本实际串行）</label>
          <input v-model.number="settingsDraft.max_concurrent" class="input" type="number" min="1" max="4" disabled />
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">
          GitHub Token（PAT，需 repo 权限）
          <span v-if="settings && settings.has_github_token" class="muted">已保存（{{ settings.github_token_mask }}），留空表示不修改</span>
        </label>
        <input v-model="settingsDraft.github_token" class="input" type="password" placeholder="ghp_...（写入后仅存密文）" autocomplete="off" />
      </div>
      <div class="form-group">
        <label class="form-label">验证命令（JSON 数组，可选）</label>
        <textarea v-model="settingsDraft.verify_profile" class="textarea" rows="3"
          placeholder='[{"name":"pytest","command":"python -m pytest -q","timeout_seconds":600}]'></textarea>
        <p class="muted">验证由控制端在工作区执行；失败任务默认仍可出 Draft PR（PR 中记录证据），关闭下方开关后失败即受阻。</p>
      </div>
      <div class="form-row">
        <label class="switch">
          <input v-model="settingsDraft.allow_unverified_draft" type="checkbox" />
          <span>验证失败/未配置时仍允许发布 Draft PR（PR 内记录缺失证据）</span>
        </label>
      </div>
      <div class="actions">
        <button class="btn btn-primary" type="submit" :disabled="savingSettings">保存配置</button>
      </div>
    </form>

    <!-- 新建任务（create 权限 + gate 可用才可提交；不可用时按钮置灰并给原因） -->
    <dialog v-if="caps.create" ref="taskDialog" class="task-dialog" aria-labelledby="new-agent-task" @cancel="guardTaskClose">
      <form class="create-card" @submit.prevent="createTask">
        <div class="dialog-heading">
          <h2 id="new-agent-task">新建编码任务</h2>
          <button type="button" class="btn btn-sm btn-secondary" :disabled="creating" @click="taskDialog?.close()">关闭</button>
        </div>
        <div class="form-group">
          <label class="form-label" for="agent-task-title">任务标题</label>
          <input id="agent-task-title" v-model="draft.title" class="input" placeholder="给导出功能增加 CSV 格式" maxlength="120" required autofocus />
        </div>
        <div class="form-group">
          <label class="form-label" for="agent-task-requirement">需求描述</label>
          <textarea id="agent-task-requirement" v-model="draft.requirement" class="textarea" rows="5" placeholder="写清目标、涉及范围和验收标准" required></textarea>
        </div>
        <div class="form-group">
          <label class="form-label" for="agent-task-context">补充上下文（可选）</label>
          <textarea id="agent-task-context" v-model="draft.context_extra" class="textarea" rows="2" placeholder="相关链接、已知结论、约束条件…"></textarea>
        </div>
        <p v-if="createError" class="error-banner" role="alert">{{ createError }}</p>
        <div class="actions">
          <span v-if="gateReasons.length" class="muted">{{ gateReasons.join('；') }}</span>
          <button class="btn btn-primary" type="submit" :disabled="creating || gateReasons.length > 0">
            {{ creating ? '正在提交…' : '提交任务' }}
          </button>
        </div>
      </form>
    </dialog>

    <div v-if="error" class="error-banner" role="alert">{{ error }}</div>
    <div class="task-list-heading">
      <h2 class="task-list-title">任务记录</h2>
      <div v-if="caps.view && caps.manage" class="task-user-filter">
        <label class="form-label" for="agent-task-user">任务用户</label>
        <select id="agent-task-user" v-model="taskOwnerId" class="input" :disabled="loadingTaskUsers" @change="changeTaskOwner">
          <option value="">全部用户</option>
          <option v-for="user in taskUsers" :key="user.user_id" :value="user.user_id">{{ user.username }}</option>
        </select>
        <p v-if="taskUsersError" class="muted" role="alert">
          用户选项加载失败 <button type="button" class="link-btn" @click="loadTaskUsers">重试</button>
        </p>
      </div>
    </div>
    <div v-if="loading && !tasks.length" class="empty" role="status">加载中…</div>
    <div v-else-if="tasks.length === 0" class="empty">
      <strong>暂无编码任务</strong>
      <p v-if="caps.create" class="hint">点击「新建任务」，或在微信发送 /开发 后附上需求。</p>
    </div>

    <div v-else class="list">
      <article v-for="t in tasks" :key="t.task_id" class="card item">
        <div class="item-head">
          <div class="task-heading">
            <h3>{{ t.title }}</h3>
            <div class="task-meta">
              <span class="badge" :class="statusBadge(t)">{{ statusText(t) }}</span>
              <span v-if="t.phase">{{ phaseText(t.phase) }}</span>
              <SessionChannelBadge v-if="t.source === 'web' || t.source === 'wechat'" :channel="t.source" />
              <span v-else>{{ sourceText(t.source) }}</span>
              <time :datetime="t.created_at">{{ shortTime(t.created_at) }}</time>
            </div>
          </div>
          <div class="task-actions">
            <a v-if="t.pr_url" class="link-btn" :href="t.pr_url" target="_blank" rel="noopener">
              Draft PR #{{ t.pr_number }}{{ prStateSuffix(t.pr_state) }}
            </a>
            <button
              v-if="canCancel(t)"
              class="btn btn-sm btn-danger"
              @click="cancel(t)"
            >{{ t.status === 'cancel_requested' ? '取消中…' : '取消' }}</button>
            <button
              v-if="canRetry(t)"
              class="btn btn-sm btn-secondary"
              @click="retry(t)"
            >重试</button>
          </div>
        </div>
        <p class="content req">{{ t.requirement }}</p>
        <p v-if="t.result_summary" class="content summary">{{ t.result_summary }}</p>
        <p v-if="t.error" class="content err">{{ t.error }}</p>
        <p class="muted">
          <template v-if="t.branch">分支 {{ t.branch }} · </template>{{ t.attempts }} 次执行
          <template v-if="t.finished_at"> · 结束 {{ shortTime(t.finished_at) }}</template>
        </p>
        <button class="link-btn task-details" :aria-expanded="expanded === t.task_id" @click="toggleDetail(t)">{{ expanded === t.task_id ? '收起轨迹' : '执行轨迹' }}</button>
        <div v-if="expanded === t.task_id" class="events">
          <p v-if="detailError" class="muted" role="alert">{{ detailError }} <button type="button" class="link-btn" @click="refreshDetail(t.task_id)">重试</button></p>
          <div v-else-if="detailInFlight && !detailEvents.length" class="muted" role="status">正在加载轨迹…</div>
          <div v-else-if="detailEvents.length === 0" class="muted">暂无事件</div>
          <div v-for="e in detailEvents" :key="e.event_id" class="event">
            <span class="event-kind" :class="`k-${e.kind}`">{{ eventText(e.kind) }}</span>
            <span class="event-detail">{{ e.detail }}</span>
            <span class="muted">{{ shortTime(e.created_at) }}</span>
          </div>
        </div>
        <!-- 追问回答 / 补充输入（waiting_input / blocked / failed 时可见） -->
        <form v-if="expanded === t.task_id && canSupplement(t)" class="supplement" @submit.prevent="submitSupplement(t)">
          <input v-model="supplementText" class="input grow" placeholder="回答代理的问题，或补充需求…" required />
          <button class="btn btn-sm btn-primary" type="submit" :disabled="supplementing">发送并重新入队</button>
        </form>
        <!-- 逐项验收（工作包四）：轮次、检查项、证据与接受/打回 -->
        <div v-if="expanded === t.task_id" class="acceptance">
          <div class="acc-head">
            <strong>逐项验收</strong>
            <span v-if="latestRound(t.task_id)" class="muted">
              第 {{ latestRound(t.task_id)!.round_no }} 轮 · 结论 {{ latestRound(t.task_id)!.verdict }}
              · {{ shortTime(latestRound(t.task_id)!.created_at) }}
            </span>
            <span v-else-if="!acceptanceLoading" class="muted">尚无验收轮次（由验收工具或人工提交）</span>
            <span v-else class="muted">加载中…</span>
          </div>
          <template v-for="round in acceptanceRounds[t.task_id] || []" :key="round.id">
            <div v-if="round.round_no === latestRound(t.task_id)?.round_no" class="acc-round">
              <div v-for="c in round.checks" :key="c.id" class="acc-check">
                <span class="acc-badge" :class="`s-${c.status}`">{{ c.status }}</span>
                <span class="acc-title" :title="c.observation">{{ c.title }}</span>
                <span v-if="c.decision === 'accepted'" class="acc-decision ok">已接受</span>
                <span v-else-if="c.decision === 'rejected'" class="acc-decision bad">已打回</span>
                <span class="acc-actions">
                  <button v-for="(ev, i) in c.evidence" :key="i" class="link-btn" type="button"
                     :title="ev.description"
                     @click="previewEvidence(t, round.id, c.item_id, i)">证据{{ c.evidence.length > 1 ? i + 1 : '' }}</button>
                  <button v-if="!c.decision" class="btn btn-sm btn-secondary"
                          @click="decide(t, c.id, 'accepted')">接受</button>
                  <button v-if="!c.decision" class="btn btn-sm btn-danger"
                          @click="rejectingId = c.id">打回</button>
                </span>
                <div v-if="rejectingId === c.id" class="acc-reject-form">
                  <input v-model="rejectNote[c.id]" class="input grow"
                         placeholder="打回说明（将成为代理返工的处理输入）" />
                  <button class="btn btn-sm btn-danger" @click="decide(t, c.id, 'rejected')">提交打回</button>
                  <button class="btn btn-sm btn-secondary" @click="rejectingId = null">取消</button>
                </div>
              </div>
            </div>
            <div v-else class="acc-history muted">历史轮次 #{{ round.round_no }}：{{ round.verdict }}（保留可追溯）</div>
          </template>
        </div>
      </article>
    </div>

    <div v-if="nextCursor && tasks.length > 0" class="more">
      <button class="btn btn-secondary btn-sm" @click="loadMore">加载更多</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import SessionChannelBadge from '@/components/SessionChannelBadge.vue'
import { formatDateTime } from '@/utils/dateTime'
import {
  appendSuperagentTaskInput,
  cancelSuperagentTask,
  createSuperagentTask,
  getSuperagentCapabilities,
  getSuperagentOpsMetrics,
  decideAcceptanceCheck,
  fetchAcceptanceEvidence,
  getSuperagentSettings,
  listAcceptanceRounds,
  listSuperagentEvents,
  listSuperagentTasks,
  listSuperagentTaskUsers,
  retrySuperagentTask,
  updateSuperagentSettings,
  type AcceptanceRound,
  type SuperagentCapabilities,
  type SuperagentEvent,
  type SuperagentOpsMetrics,
  type SuperagentSettings,
  type SuperagentTask,
  type SuperagentTaskUser,
} from '@/api/superagent'

const caps = ref<SuperagentCapabilities>({
  view: true, create: false, cancel: false, manage: false,
  enabled: false, configured: false, credentials_ready: false,
  runner_ready: false, reasons: [], repo_url: '',
})

const settings = ref<SuperagentSettings | null>(null)
const settingsDraft = reactive({
  enabled: false, repo_url: '', base_branch: 'main', max_concurrent: 1,
  github_token: '', verify_profile: '[]', allow_unverified_draft: true,
})
const showSettings = ref(false)
const showOps = ref(false)
const opsMetrics = ref<SuperagentOpsMetrics | null>(null)
const savingSettings = ref(false)

const tasks = ref<SuperagentTask[]>([])
const nextCursor = ref('')
const taskOwnerId = ref<number | ''>('')
const taskUsers = ref<SuperagentTaskUser[]>([])
const loadingTaskUsers = ref(false)
const taskUsersError = ref(false)
const expanded = ref('')
const detailEvents = ref<SuperagentEvent[]>([])
const detailAfterId = ref(0)
const detailError = ref('')
const detailInFlight = ref(false)
let detailVersion = 0
const supplementText = ref('')
const supplementing = ref(false)
const loading = ref(false)
const creating = ref(false)
const taskDialog = ref<HTMLDialogElement | null>(null)
const createError = ref('')
const error = ref('')

// ---- 逐项验收（工作包四） ----
const acceptanceRounds = ref<Record<string, AcceptanceRound[]>>({})
const acceptanceLoading = ref(false)
const rejectNote = ref<Record<number, string>>({}) // check.id -> 打回说明
const rejectingId = ref<number | null>(null) // 正在填写打回说明的检查项

function latestRound(taskId: string): AcceptanceRound | null {
  const rounds = acceptanceRounds.value[taskId]
  return rounds && rounds.length ? rounds[0] : null
}

async function loadAcceptance(taskId: string) {
  acceptanceLoading.value = true
  try {
    acceptanceRounds.value[taskId] = await listAcceptanceRounds(taskId)
  } catch {
    // 验收数据加载失败不阻塞轨迹展示
  } finally {
    acceptanceLoading.value = false
  }
}

async function decide(t: SuperagentTask, checkId: number, decision: 'accepted' | 'rejected') {
  error.value = ''
  const note = decision === 'rejected' ? (rejectNote.value[checkId] || '') : ''
  try {
    const result = await decideAcceptanceCheck(checkId, decision, note)
    rejectingId.value = null
    rejectNote.value[checkId] = ''
    await loadAcceptance(t.task_id)
    if (result.requeued) await load() // 打回返工已回队：列表状态刷新
  } catch (e: any) {
    error.value = errMsg(e)
  }
}

async function previewEvidence(t: SuperagentTask, roundId: string, itemId: string, index: number) {
  error.value = ''
  try {
    const blob = await fetchAcceptanceEvidence(t.task_id, roundId, itemId, index)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e: any) {
    error.value = errMsg(e)
  }
}
let pollTimer: number | null = null
let activeTimer: number | null = null
let listInFlight = false
let listVersion = 0

const draft = reactive({ title: '', requirement: '', context_extra: '' })
let createSeq = 0

const gateReasons = computed(() => (caps.value.view && caps.value.create ? caps.value.reasons : []))

function errMsg(e: any): string {
  return e?.response?.data?.message || e?.message || '操作失败'
}

async function loadCapabilities() {
  try {
    caps.value = await getSuperagentCapabilities()
  } catch {
    // 无 view 权限：保持默认，列表请求会 403
  }
}

async function toggleOps() {
  showOps.value = !showOps.value
  if (showOps.value) showSettings.value = false
  if (showOps.value && !opsMetrics.value) {
    try {
      opsMetrics.value = await getSuperagentOpsMetrics()
    } catch {
      // 权限瞬变忽略
    }
  }
}

function toggleSettings() {
  showSettings.value = !showSettings.value
  if (showSettings.value) showOps.value = false
}

async function loadSettings() {
  if (!caps.value.manage) return
  try {
    settings.value = await getSuperagentSettings()
    settingsDraft.enabled = settings.value.enabled
    settingsDraft.repo_url = settings.value.repo_url
    settingsDraft.base_branch = settings.value.base_branch || 'main'
    settingsDraft.max_concurrent = settings.value.max_concurrent || 1
    settingsDraft.verify_profile = settings.value.verify_profile || '[]'
    settingsDraft.allow_unverified_draft = settings.value.allow_unverified_draft
  } catch {
    // 忽略（权限变化瞬间的 403）
  }
}

async function saveSettings() {
  savingSettings.value = true
  error.value = ''
  try {
    const payload: Record<string, unknown> = {
      enabled: settingsDraft.enabled,
      repo_url: settingsDraft.repo_url,
      base_branch: settingsDraft.base_branch,
      verify_profile: settingsDraft.verify_profile,
      allow_unverified_draft: settingsDraft.allow_unverified_draft,
    }
    if (settingsDraft.github_token.trim()) payload.github_token = settingsDraft.github_token.trim()
    settings.value = await updateSuperagentSettings(payload)
    settingsDraft.github_token = ''
    await loadCapabilities()
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    savingSettings.value = false
  }
}

async function load(loadMoreMode = false) {
  if (listInFlight) return // 防竞态：同类请求只有一个在途
  const version = ++listVersion
  listInFlight = true
  if (!loadMoreMode) loading.value = true
  error.value = ''
  try {
    const page = await listSuperagentTasks({
      limit: 20,
      cursor: loadMoreMode ? nextCursor.value : '',
      owner_id: taskOwnerId.value === '' ? undefined : taskOwnerId.value,
    })
    if (version !== listVersion) return
    if (loadMoreMode) {
      const known = new Set(tasks.value.map((t) => t.task_id))
      tasks.value = [...tasks.value, ...page.tasks.filter((t) => !known.has(t.task_id))]
    } else {
      tasks.value = page.tasks
    }
    nextCursor.value = page.next_cursor
  } catch (e: any) {
    if (version !== listVersion) return
    if (e?.response?.status === 403) {
      tasks.value = []
      nextCursor.value = ''
    }
    error.value = errMsg(e)
  } finally {
    if (version === listVersion) {
      listInFlight = false
      loading.value = false
    }
  }
}

async function loadTaskUsers() {
  if (!caps.value.view || !caps.value.manage || loadingTaskUsers.value) return
  loadingTaskUsers.value = true
  taskUsersError.value = false
  try {
    taskUsers.value = await listSuperagentTaskUsers()
  } catch {
    taskUsersError.value = true
  } finally {
    loadingTaskUsers.value = false
  }
}

function changeTaskOwner() {
  tasks.value = []
  nextCursor.value = ''
  expanded.value = ''
  detailVersion++
  listInFlight = false
  void load()
}

async function loadMore() {
  await load(true)
}

async function createTask() {
  if (creating.value || gateReasons.value.length || !caps.value.create) return
  const seq = ++createSeq
  creating.value = true
  createError.value = ''
  try {
    await createSuperagentTask(
      draft.title, draft.requirement, draft.context_extra,
      `web-${seq}-${Date.now()}`,
    )
    draft.title = ''
    draft.requirement = ''
    draft.context_extra = ''
    taskDialog.value?.close()
    await load()
  } catch (e: any) {
    createError.value = errMsg(e)
  } finally {
    creating.value = false
  }
}

function guardTaskClose(event: Event) {
  if (creating.value) event.preventDefault()
}

async function cancel(t: SuperagentTask) {
  error.value = ''
  try {
    await cancelSuperagentTask(t.task_id)
    await load()
    if (expanded.value === t.task_id) await refreshDetail(t.task_id)
  } catch (e: any) {
    error.value = errMsg(e)
  }
}

async function retry(t: SuperagentTask) {
  error.value = ''
  try {
    await retrySuperagentTask(t.task_id)
    await load()
  } catch (e: any) {
    error.value = errMsg(e)
  }
}

async function toggleDetail(t: SuperagentTask) {
  detailVersion++
  detailInFlight.value = false
  detailError.value = ''
  if (expanded.value === t.task_id) {
    expanded.value = ''
    detailEvents.value = []
    detailAfterId.value = 0
    return
  }
  // 切换详情：直接换目标，旧请求结果按 task_id 丢弃（防乱序）
  expanded.value = t.task_id
  detailEvents.value = []
  detailAfterId.value = 0
  supplementText.value = ''
  loadAcceptance(t.task_id) // 验收轮次与轨迹并行加载
  await refreshDetail(t.task_id)
}

async function refreshDetail(taskId: string) {
  if (detailInFlight.value || expanded.value !== taskId) return
  const version = detailVersion
  detailInFlight.value = true
  detailError.value = ''
  try {
    const page = await listSuperagentEvents(taskId, detailAfterId.value)
    if (version !== detailVersion) return
    detailEvents.value = [...detailEvents.value, ...page.events]
    detailAfterId.value = page.next_after_id
  } catch (e) {
    if (version === detailVersion) detailError.value = errMsg(e)
  } finally {
    if (version === detailVersion) detailInFlight.value = false
  }
}

async function submitSupplement(t: SuperagentTask) {
  if (!supplementText.value.trim()) return
  supplementing.value = true
  error.value = ''
  try {
    await appendSuperagentTaskInput(t.task_id, supplementText.value.trim(), `web-sup-${Date.now()}`)
    supplementText.value = ''
    await load()
    await refreshDetail(t.task_id)
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    supplementing.value = false
  }
}

function canCancel(t: SuperagentTask): boolean {
  if (!caps.value.cancel) return false
  return t.status === 'queued' || t.status === 'running' || t.status === 'cancel_requested'
}

function canRetry(t: SuperagentTask): boolean {
  if (!caps.value.create || t.legacy_config_unknown) return false
  return ['failed', 'cancelled', 'blocked', 'interrupted'].includes(t.status)
}

function canSupplement(t: SuperagentTask): boolean {
  if (!caps.value.create) return false
  return ['waiting_input', 'blocked', 'failed'].includes(t.status)
}

function statusText(t: SuperagentTask): string {
  if (t.status === 'cancel_requested') return '取消中'
  const map: Record<string, string> = {
    queued: '排队中', running: '执行中', succeeded: '已完成', failed: '失败',
    cancelled: '已取消', waiting_input: '等待补充', blocked: '受阻',
    awaiting_review: '待评审', interrupted: '已中断',
  }
  return map[t.status] || t.status
}

function statusBadge(t: SuperagentTask): string {
  if (t.status === 'cancel_requested') return 'badge-warning'
  const map: Record<string, string> = {
    queued: 'badge-warning', running: 'badge-info', succeeded: 'badge-success',
    failed: 'badge-danger', cancelled: 'badge-warning', waiting_input: 'badge-warning',
    blocked: 'badge-danger', awaiting_review: 'badge-info', interrupted: 'badge-warning',
  }
  return map[t.status] || 'badge'
}

function phaseText(phase: string): string {
  const map: Record<string, string> = {
    preparing: '准备中', coding: '编码中', verifying: '验证中', publishing: '发布中',
  }
  return map[phase] || phase
}

function prStateSuffix(state: string): string {
  const map: Record<string, string> = { open: '（待审阅）', merged: '（已合并）', closed: '（已关闭）' }
  return map[state] || ''
}

function sourceText(source: string): string {
  const map: Record<string, string> = { wechat: '微信', web: 'Web', tool: '对话代理' }
  return map[source] || source
}

function eventText(kind: string): string {
  const map: Record<string, string> = {
    created: '受理', attempt_started: '执行', started: '开始', progress: '进行',
    question: '追问', blocked: '受阻', pr_created: 'PR', no_changes: '无变更',
    failed: '失败', cancel_requested: '取消请求', cancelled: '取消',
    cancelled_after_publication: '发布后取消', notified: '已回信', input: '补充',
    reconciled: '对账', reverted: '回滚',
  }
  return map[kind] || kind
}

function shortTime(iso: string): string {
  return formatDateTime(iso)
}

onMounted(async () => {
  await loadCapabilities()
  loadSettings()
  void loadTaskUsers()
  await load()
  // 增量轮询：有活跃任务时 4s 刷新列表与展开详情；否则 15s 低频（微信新建任务也能出现）
  pollTimer = window.setInterval(async () => {
    const active = tasks.value.some(
      (t) => ['queued', 'running', 'cancel_requested'].includes(t.status),
    )
    if (!listInFlight) {
      if (active) {
        await load()
        if (expanded.value) await refreshDetail(expanded.value)
      } else {
        await load()
      }
    }
  }, 15000)
  // 活跃任务的高频刷新
  activeTimer = window.setInterval(async () => {
    const active = tasks.value.some(
      (t) => ['queued', 'running', 'cancel_requested'].includes(t.status),
    )
    if (active && !listInFlight) {
      await load()
      if (expanded.value) await refreshDetail(expanded.value)
    }
  }, 4000)
})

onUnmounted(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  if (activeTimer !== null) window.clearInterval(activeTimer)
})
</script>

<style scoped>
.superagent-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 1120px;
  margin-inline: auto;
  overflow-y: auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header h1 {
  margin: 0 0 4px;
  font-size: clamp(23px, 3vw, 31px);
  letter-spacing: -0.02em;
}

.hint {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.agent-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
}

.status-copy { color: var(--text-secondary); overflow-wrap: anywhere; }

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.header-actions .btn { width: auto; white-space: nowrap; }

.superagent-page > .card,
.superagent-page .list > .card {
  padding: 20px 24px;
  min-width: 0;
}

.superagent-page .form-group {
  margin-bottom: 0;
}

.superagent-page .input,
.superagent-page .textarea {
  width: 100%;
  box-sizing: border-box;
}

.ops-card {
  padding: 4px 8px;
}

.ops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 10px;
}

.ops-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.ops-label {
  color: var(--text-tertiary);
  font-weight: 600;
}

.settings-card,
.create-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-dialog {
  width: min(640px, calc(100% - 28px));
  max-height: calc(100dvh - 36px);
  margin: auto;
  box-sizing: border-box;
  padding: clamp(16px, 4vw, 26px);
  color: var(--text-primary);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 14px;
}

.task-dialog:modal, .task-dialog::backdrop { overscroll-behavior: contain; }
.task-dialog::backdrop { background: rgb(17 24 39 / 45%); }
.dialog-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.dialog-heading h2 { margin: 0; font-size: 20px; }
.create-card .error-banner { margin: 0; }

.form-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.form-row .grow {
  flex: 1;
}

.switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.actions .btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-list-heading {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
}

.task-list-title { margin: 0; font-size: 18px; }

.task-user-filter {
  display: grid;
  gap: 4px;
  min-width: min(100%, 180px);
}

.task-user-filter p { margin: 0; }

.item-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px 16px;
  flex-wrap: wrap;
}

.task-heading { flex: 1 1 230px; min-width: 0; }
.task-heading h3 { margin: 0 0 7px; font-size: 17px; overflow-wrap: anywhere; }
.task-meta, .task-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.task-meta { color: var(--text-secondary); font-size: 12px; }
.task-details { margin-top: 12px; }

.link-btn {
  background: none;
  border: none;
  color: var(--brand);
  cursor: pointer;
  font-size: 13px;
  padding: 0;
  text-decoration: none;
}

.link-btn:hover {
  text-decoration: underline;
}

.content {
  margin: 8px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.content.req {
  color: var(--text-secondary);
}

.content.summary {
  color: var(--text-primary);
}

.content.err {
  color: #d9534f;
}

.muted {
  color: var(--text-tertiary);
  font-size: 12px;
}

.events {
  margin-top: 8px;
  border-top: 1px dashed var(--border-primary);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.event {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
}

.event-kind {
  flex-shrink: 0;
  min-width: 44px;
  font-weight: 600;
}

.k-failed,
.k-cancelled,
.k-blocked {
  color: #d9534f;
}

.k-pr_created,
.k-no_changes {
  color: #5cb85c;
}

.k-cancel_requested,
.k-cancelled_after_publication,
.k-question {
  color: #f0ad4e;
}

.event-detail {
  flex: 1;
  word-break: break-word;
  color: var(--text-secondary);
}

.supplement {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.supplement .grow {
  flex: 1;
}

.more {
  display: flex;
  justify-content: center;
}

.empty {
  text-align: center;
  color: var(--text-tertiary);
  padding: 42px 12px;
  background: var(--bg-primary);
  border: 1px dashed var(--border-primary);
  border-radius: 12px;
}

.empty strong { color: var(--text-primary); }
.empty .hint { margin-top: 5px; }
.error-banner {
  background: rgba(217, 83, 79, 0.1);
  border: 1px solid rgba(217, 83, 79, 0.4);
  color: #d9534f;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
}

@media (max-width: 480px) {
  .superagent-page { padding: 16px; }
  .superagent-page > .card, .superagent-page .list > .card { padding: 16px; }
  .page-header, .form-row, .actions { flex-direction: column; align-items: stretch; }
  .header-actions { flex-wrap: wrap; }
  .supplement {
    flex-direction: column;
    align-items: stretch;
  }
}

/* 逐项验收（工作包四） */
.acceptance {
  margin-top: 10px;
  border-top: 1px dashed var(--border-primary, #d8dbe2);
  padding-top: 8px;
}
.acc-head { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: baseline; margin-bottom: 6px; }
.acc-round { display: flex; flex-direction: column; gap: 4px; }
.acc-check {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 3px 6px; border-radius: 6px;
}
.acc-check:hover { background: var(--bg-secondary, #f5f6f8); }
.acc-badge {
  font-size: 11px; padding: 1px 7px; border-radius: 999px; font-weight: 600;
}
.acc-badge.s-pass { background: #e6f6ea; color: #1d7f3c; }
.acc-badge.s-fail { background: #fdeaea; color: #b42318; }
.acc-badge.s-blocked { background: #fff4e0; color: #a35a00; }
.acc-badge.s-skipped { background: #eef0f3; color: #6b7280; }
.acc-title { flex: 1; min-width: 160px; }
.acc-decision { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.acc-decision.ok { background: #e6f6ea; color: #1d7f3c; }
.acc-decision.bad { background: #fdeaea; color: #b42318; }
.acc-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.acc-reject-form {
  display: flex; gap: 6px; width: 100%; padding: 4px 6px;
  background: var(--bg-secondary, #f5f6f8); border-radius: 6px;
}
.acc-history { font-size: 12px; padding: 2px 6px; }
</style>
