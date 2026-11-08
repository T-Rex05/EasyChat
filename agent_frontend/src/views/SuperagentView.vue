<template>
  <div class="page-container superagent-page">
    <header class="page-header">
      <div>
        <h2>超级代理</h2>
        <p class="hint">在微信里描述需求（或用 /开发 命令），后台代理在独立工作区完成编码并自动创建 Draft PR，结果回信给你。</p>
      </div>
      <div class="header-actions">
        <button v-if="caps.manage" class="btn btn-secondary" @click="toggleOps">
          {{ showOps ? '收起运维' : '运维面板' }}
        </button>
        <button v-if="caps.manage" class="btn btn-secondary" @click="showSettings = !showSettings">
          {{ showSettings ? '收起配置' : '仓库配置' }}
        </button>
      </div>
    </header>

    <!-- 受理状态提示（capabilities 驱动，普通用户也能看到准确原因） -->
    <div v-if="caps.view && gateReasons.length" class="notice-banner">
      当前暂不能受理新任务：{{ gateReasons.join('；') }}
    </div>

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
    <form v-if="caps.create" class="card create-card" @submit.prevent="createTask">
      <div class="form-group">
        <label class="form-label">任务标题</label>
        <input v-model="draft.title" class="input" placeholder="例如：给导出功能增加 CSV 格式" maxlength="120" required />
      </div>
      <div class="form-group">
        <label class="form-label">需求描述（要自包含：目标、验收标准、涉及范围）</label>
        <textarea v-model="draft.requirement" class="textarea" rows="4" placeholder="代理会独立工作，写清楚它需要知道的一切；信息不足时它会追问而非猜测。" required></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">补充上下文（可选）</label>
        <textarea v-model="draft.context_extra" class="textarea" rows="2" placeholder="相关链接、已知结论、约束条件…"></textarea>
      </div>
      <div class="actions">
        <span v-if="gateReasons.length" class="muted">{{ gateReasons.join('；') }}</span>
        <button class="btn btn-primary" type="submit" :disabled="creating || gateReasons.length > 0">提交任务</button>
      </div>
    </form>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="tasks.length === 0" class="empty">
      还没有编码任务。在微信里发「/开发 <需求>」，或在这里提交。
    </div>

    <div v-else class="list">
      <article v-for="t in tasks" :key="t.task_id" class="card item">
        <div class="item-head">
          <strong>{{ t.title }}</strong>
          <span class="badge" :class="statusBadge(t)">{{ statusText(t) }}</span>
          <span v-if="t.phase" class="badge badge-info">{{ phaseText(t.phase) }}</span>
          <span class="badge badge-info">{{ sourceText(t.source) }}</span>
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
        <p class="content req">{{ t.requirement }}</p>
        <p v-if="t.result_summary" class="content summary">{{ t.result_summary }}</p>
        <p v-if="t.error" class="content err">{{ t.error }}</p>
        <p class="muted">
          分支 {{ t.branch }} · 第 {{ t.attempts }} 次执行 · 创建 {{ shortTime(t.created_at) }}
          <template v-if="t.finished_at"> · 结束 {{ shortTime(t.finished_at) }}</template>
        </p>
        <button class="link-btn" @click="toggleDetail(t)">{{ expanded === t.task_id ? '收起轨迹' : '执行轨迹' }}</button>
        <div v-if="expanded === t.task_id" class="events">
          <div v-if="detailEvents.length === 0" class="muted">暂无事件</div>
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
      </article>
    </div>

    <div v-if="nextCursor && tasks.length > 0" class="more">
      <button class="btn btn-secondary btn-sm" @click="loadMore">加载更多</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  appendSuperagentTaskInput,
  cancelSuperagentTask,
  createSuperagentTask,
  getSuperagentCapabilities,
  getSuperagentOpsMetrics,
  getSuperagentSettings,
  listSuperagentEvents,
  listSuperagentTasks,
  retrySuperagentTask,
  updateSuperagentSettings,
  type SuperagentCapabilities,
  type SuperagentEvent,
  type SuperagentOpsMetrics,
  type SuperagentSettings,
  type SuperagentTask,
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
const expanded = ref('')
const detailEvents = ref<SuperagentEvent[]>([])
const detailAfterId = ref(0)
const supplementText = ref('')
const supplementing = ref(false)
const loading = ref(false)
const creating = ref(false)
const error = ref('')
let pollTimer: number | null = null
let activeTimer: number | null = null
let listInFlight = false
let detailInFlight = false

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
  if (showOps.value && !opsMetrics.value) {
    try {
      opsMetrics.value = await getSuperagentOpsMetrics()
    } catch {
      // 权限瞬变忽略
    }
  }
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
  listInFlight = true
  if (!loadMoreMode) loading.value = true
  error.value = ''
  try {
    const page = await listSuperagentTasks({ limit: 20, cursor: loadMoreMode ? nextCursor.value : '' })
    if (loadMoreMode) {
      const known = new Set(tasks.value.map((t) => t.task_id))
      tasks.value = [...tasks.value, ...page.tasks.filter((t) => !known.has(t.task_id))]
    } else {
      tasks.value = page.tasks
    }
    nextCursor.value = page.next_cursor
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    listInFlight = false
    loading.value = false
  }
}

async function loadMore() {
  await load(true)
}

async function createTask() {
  const seq = ++createSeq
  creating.value = true
  error.value = ''
  try {
    await createSuperagentTask(
      draft.title, draft.requirement, draft.context_extra,
      `web-${seq}-${Date.now()}`,
    )
    draft.title = ''
    draft.requirement = ''
    draft.context_extra = ''
    await load()
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    creating.value = false
  }
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
  await refreshDetail(t.task_id)
}

async function refreshDetail(taskId: string) {
  if (detailInFlight) return
  detailInFlight = true
  try {
    const page = await listSuperagentEvents(taskId, detailAfterId.value)
    if (expanded.value !== taskId) return // 旧响应丢弃
    detailEvents.value = [...detailEvents.value, ...page.events]
    detailAfterId.value = page.next_after_id
  } catch {
    // 详情刷新失败不打断页面
  } finally {
    detailInFlight = false
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
  const map: Record<string, string> = { open: '（open）', merged: '（已合并）', closed: '（已关闭）' }
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
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 19)
}

onMounted(async () => {
  await loadCapabilities()
  loadSettings()
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
  gap: 16px;
  overflow-y: auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.page-header h2 {
  margin: 0 0 4px;
}

.hint {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.notice-banner {
  background: rgba(240, 173, 78, 0.12);
  border: 1px solid rgba(240, 173, 78, 0.4);
  color: #b8860b;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.ops-card {
  padding: 4px 8px;
}

.ops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.item-head strong {
  margin-right: auto;
}

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
  padding: 32px 0;
}

.error-banner {
  background: rgba(217, 83, 79, 0.1);
  border: 1px solid rgba(217, 83, 79, 0.4);
  color: #d9534f;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
}

@media (max-width: 480px) {
  .item-head strong {
    flex-basis: 100%;
  }

  .supplement {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
