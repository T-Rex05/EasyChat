<template>
  <div class="page-container superagent-page">
    <header class="page-header">
      <div>
        <h2>超级代理</h2>
        <p class="hint">在微信里描述需求，后台代理在独立工作区完成编码并自动提交 Pull Request，结果回信给你。</p>
      </div>
      <button v-if="canManage" class="btn btn-secondary" @click="showSettings = !showSettings">
        {{ showSettings ? '收起配置' : '仓库配置' }}
      </button>
    </header>

    <!-- 仓库配置（仅 superagent.manage） -->
    <form v-if="showSettings && canManage" class="card settings-card" @submit.prevent="saveSettings">
      <div class="form-row">
        <label class="form-label">启用</label>
        <label class="switch">
          <input v-model="settingsDraft.enabled" type="checkbox" />
          <span>{{ settingsDraft.enabled ? '已启用' : '已停用' }}</span>
        </label>
      </div>
      <div class="form-group">
        <label class="form-label">目标仓库（HTTPS）</label>
        <input v-model="settingsDraft.repo_url" class="input" placeholder="https://github.com/owner/repo.git" />
      </div>
      <div class="form-row">
        <div class="form-group grow">
          <label class="form-label">基线分支</label>
          <input v-model="settingsDraft.base_branch" class="input" placeholder="main" />
        </div>
        <div class="form-group grow">
          <label class="form-label">并发上限</label>
          <input v-model.number="settingsDraft.max_concurrent" class="input" type="number" min="1" max="4" />
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">
          GitHub Token（ PAT，需 repo 权限）
          <span v-if="settings && settings.has_github_token" class="muted">已保存（{{ settings.github_token_mask }}），留空表示不修改</span>
        </label>
        <input v-model="settingsDraft.github_token" class="input" type="password" placeholder="ghp_...（写入后仅存密文）" autocomplete="off" />
      </div>
      <p class="muted">代理以工作分支提交代码并创建 PR；token 只用于 push 与调 GitHub API，不会写进仓库配置。</p>
      <div class="actions">
        <button class="btn btn-primary" type="submit" :disabled="savingSettings">保存配置</button>
      </div>
    </form>

    <!-- 新建任务 -->
    <form class="card create-card" @submit.prevent="createTask">
      <div class="form-group">
        <label class="form-label">任务标题</label>
        <input v-model="draft.title" class="input" placeholder="例如：给导出功能增加 CSV 格式" maxlength="120" required />
      </div>
      <div class="form-group">
        <label class="form-label">需求描述（要自包含：目标、验收标准、涉及范围）</label>
        <textarea v-model="draft.requirement" class="textarea" rows="4" placeholder="代理会独立工作，写清楚它需要知道的一切；信息不足时它会拒绝而非猜测。" required></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">补充上下文（可选）</label>
        <textarea v-model="draft.context_extra" class="textarea" rows="2" placeholder="相关链接、已知结论、约束条件…"></textarea>
      </div>
      <div class="actions">
        <span v-if="!gateReady" class="muted">超级代理未启用或未配置仓库，提交前请先完成配置。</span>
        <button class="btn btn-primary" type="submit" :disabled="creating || !gateReady">提交任务</button>
      </div>
    </form>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="tasks.length === 0" class="empty">还没有编码任务。在微信里直接描述需求，或在这里提交。</div>

    <div v-else class="list">
      <article v-for="t in tasks" :key="t.task_id" class="card item">
        <div class="item-head">
          <strong>{{ t.title }}</strong>
          <span class="badge" :class="statusBadge(t.status)">{{ statusText(t.status) }}</span>
          <span class="badge badge-info">{{ sourceText(t.source) }}</span>
          <a v-if="t.pr_url" class="link-btn" :href="t.pr_url" target="_blank" rel="noopener">查看 PR #{{ t.pr_number }}</a>
          <button
            v-if="t.status === 'queued' || t.status === 'running'"
            class="btn btn-sm btn-danger"
            @click="cancel(t)"
          >取消</button>
          <button
            v-if="t.status === 'failed' || t.status === 'cancelled'"
            class="btn btn-sm btn-secondary"
            @click="retry(t)"
          >重试</button>
        </div>
        <p class="content req">{{ t.requirement }}</p>
        <p v-if="t.result_summary" class="content summary">摘要：{{ t.result_summary }}</p>
        <p v-if="t.error" class="content err">失败原因：{{ t.error }}</p>
        <p class="muted">
          分支 {{ t.branch }} · 第 {{ t.attempts }} 次执行 · 创建 {{ shortTime(t.created_at) }}
          <template v-if="t.finished_at"> · 完成 {{ shortTime(t.finished_at) }}</template>
        </p>
        <button class="link-btn" @click="toggleEvents(t)">{{ expanded === t.task_id ? '收起轨迹' : '执行轨迹' }}</button>
        <div v-if="expanded === t.task_id" class="events">
          <div v-if="events.length === 0" class="muted">暂无事件</div>
          <div v-for="e in events" :key="e.event_id" class="event">
            <span class="event-kind" :class="`k-${e.kind}`">{{ eventText(e.kind) }}</span>
            <span class="event-detail">{{ e.detail }}</span>
            <span class="muted">{{ shortTime(e.created_at) }}</span>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  cancelSuperagentTask,
  createSuperagentTask,
  getSuperagentSettings,
  listSuperagentEvents,
  listSuperagentTasks,
  retrySuperagentTask,
  updateSuperagentSettings,
  type SuperagentEvent,
  type SuperagentSettings,
  type SuperagentTask,
} from '@/api/superagent'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canManage = computed(() => {
  if (authStore.userRole === 'super_admin') return true
  return authStore.permissions.includes('superagent.manage')
})

const settings = ref<SuperagentSettings | null>(null)
const settingsDraft = reactive({
  enabled: false,
  repo_url: '',
  base_branch: 'main',
  max_concurrent: 1,
  github_token: '',
})
const showSettings = ref(false)
const savingSettings = ref(false)

const tasks = ref<SuperagentTask[]>([])
const events = ref<SuperagentEvent[]>([])
const expanded = ref('')
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const gateReady = ref(false)
let pollTimer: number | null = null

const draft = reactive({ title: '', requirement: '', context_extra: '' })

function errMsg(e: any): string {
  return e?.response?.data?.message || e?.message || '操作失败'
}

async function loadSettings() {
  if (!canManage.value) return
  try {
    settings.value = await getSuperagentSettings()
    settingsDraft.enabled = settings.value.enabled
    settingsDraft.repo_url = settings.value.repo_url
    settingsDraft.base_branch = settings.value.base_branch || 'main'
    settingsDraft.max_concurrent = settings.value.max_concurrent || 1
    gateReady.value = Boolean(settings.value.enabled && settings.value.repo_url)
  } catch {
    // 无 manage 权限时忽略
  }
}

async function loadGateForUser() {
  if (canManage.value) return
  try {
    await listSuperagentTasks(1)
    gateReady.value = true
  } catch {
    gateReady.value = true // 列表可读即可见提交入口；真正的 gate 由后端校验
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
      max_concurrent: settingsDraft.max_concurrent,
    }
    if (settingsDraft.github_token.trim()) payload.github_token = settingsDraft.github_token.trim()
    settings.value = await updateSuperagentSettings(payload)
    settingsDraft.github_token = ''
    gateReady.value = Boolean(settings.value.enabled && settings.value.repo_url)
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    savingSettings.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await listSuperagentTasks()
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    loading.value = false
  }
}

async function createTask() {
  creating.value = true
  error.value = ''
  try {
    await createSuperagentTask(draft.title, draft.requirement, draft.context_extra)
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

async function toggleEvents(t: SuperagentTask) {
  if (expanded.value === t.task_id) {
    expanded.value = ''
    events.value = []
    return
  }
  expanded.value = t.task_id
  try {
    events.value = await listSuperagentEvents(t.task_id)
  } catch {
    events.value = []
  }
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    queued: '排队中',
    running: '执行中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    queued: 'badge-warning',
    running: 'badge-info',
    succeeded: 'badge-success',
    failed: 'badge-danger',
    cancelled: 'badge-warning',
  }
  return map[status] || 'badge'
}

function sourceText(source: string): string {
  const map: Record<string, string> = { wechat: '微信', web: 'Web', tool: '对话代理' }
  return map[source] || source
}

function eventText(kind: string): string {
  const map: Record<string, string> = {
    created: '受理',
    started: '开始',
    progress: '进行',
    pr_created: 'PR',
    no_changes: '无变更',
    failed: '失败',
    cancelled: '取消',
    notified: '已回信',
  }
  return map[kind] || kind
}

function shortTime(iso: string): string {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 19)
}

onMounted(() => {
  loadSettings()
  loadGateForUser()
  load()
  // 排队/执行中的任务 5 秒轮询刷新；全部终态时自动停止
  pollTimer = window.setInterval(() => {
    const active = tasks.value.some((t) => t.status === 'queued' || t.status === 'running')
    if (active) load()
  }, 5000)
})

onUnmounted(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
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

.k-failed {
  color: #d9534f;
}

.k-pr_created,
.k-no_changes {
  color: #5cb85c;
}

.k-cancelled {
  color: #f0ad4e;
}

.event-detail {
  flex: 1;
  word-break: break-word;
  color: var(--text-secondary);
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
</style>
