<template>
  <div class="memory-page">
    <header class="page-header">
      <div>
        <h1>记忆管理</h1>
        <p class="muted">查看记住的内容、来源和修订记录。</p>
      </div>
      <button v-if="access.edit" type="button" class="btn btn-primary" :aria-expanded="showAdd" @click="openAdd">
        新增记忆
      </button>
    </header>

    <p v-if="auth.ready && !access.view" role="alert">当前账号没有查看记忆的权限。</p>
    <template v-if="access.view">
      <form v-if="showAdd && access.edit" class="card add-card" @submit.prevent="remember">
        <div class="form-row">
          <label>类型
            <select v-model="draft.kind" class="select">
              <option v-for="(label, value) in memoryKinds" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label>归属
            <select v-model="draft.scope" class="select">
              <option value="default">默认角色</option>
              <option value="shared">账号共享</option>
              <option v-for="persona in activePersonas" :key="persona.id!" :value="persona.id">{{ persona.name }}</option>
            </select>
          </label>
          <label>来源
            <input v-model="draft.source" class="input" placeholder="例如：我的工作笔记" required />
          </label>
        </div>
        <label>记忆内容
          <textarea v-model="draft.content" class="textarea" rows="3" maxlength="2000" required></textarea>
        </label>
        <label>来源引文（可选）
          <input v-model="draft.quote" class="input" />
        </label>
        <div class="actions">
          <label class="checkbox"><input v-model="draft.pinned" type="checkbox" /> 固定</label>
          <button class="btn btn-secondary" type="button" :disabled="adding" @click="showAdd = false">取消</button>
          <button class="btn btn-primary" type="submit" :disabled="adding || !draft.content.trim() || !draft.source.trim()">保存</button>
        </div>
      </form>

      <div class="toolbar">
        <form class="filters" role="search" @submit.prevent="runQuery(false)">
          <input v-model="query" class="input" type="search" aria-label="检索记忆" placeholder="搜索内容、标签或 ID" />
          <button class="btn btn-secondary" type="submit">检索</button>
          <select v-model="scope" class="select" aria-label="记忆范围" @change="changeScope">
            <option value="all">全部范围</option>
            <option value="default">默认角色</option>
            <option value="shared">账号共享</option>
            <option v-for="role in scopeRoles" :key="role.id" :value="role.id">{{ role.name }}</option>
          </select>
          <button v-if="canPreviewRecall" class="btn btn-secondary" type="button" :disabled="!query.trim()" @click="runQuery(true)">
            模拟召回
          </button>
        </form>
        <div class="view-group" role="group" aria-label="记忆视图">
          <button type="button" class="btn btn-secondary" :aria-pressed="view === 'list'" @click="view = 'list'">列表</button>
          <button type="button" class="btn btn-secondary" :aria-pressed="view === 'graph'" @click="view = 'graph'">星图</button>
        </div>
      </div>

      <p v-if="previewing" class="banner muted" role="status">模拟 {{ previewRoleName }} 的对话召回，包含该角色可用的共享记忆。</p>
      <p v-if="!previewing && !loading && items.length === 200" class="banner muted" role="status">本次最多显示 200 条记忆，可缩小范围或搜索。</p>
      <p v-if="error" class="banner error" role="alert">{{ error }}</p>
      <p v-if="notice" class="banner muted" role="status">{{ notice }}</p>

      <div class="workspace" :class="{ 'with-details': !!selectedId }">
        <section ref="resultsPanel" class="results" aria-label="记忆结果" tabindex="-1" :aria-busy="loading">
          <div v-if="view === 'graph'" class="graph-tools">
            <label>分组
              <select v-model="grouping" class="select" aria-label="星图分组">
                <option value="kind">按类型</option>
                <option value="tag">按标签</option>
              </select>
            </label>
          </div>
          <p v-if="loading" class="empty" role="status">正在加载记忆…</p>
          <p v-else-if="!pageItems.length && !error" class="empty">
            {{ appliedQuery || scope !== 'all' ? '没有符合条件的记忆。' : '暂无记忆。' }}
          </p>
          <MemoryStarMap
            v-else-if="view === 'graph'" :items="pageItems" :grouping="grouping" :selected="selectedId"
            @select="select"
          />
          <ul v-else class="memory-list">
            <li v-for="item in pageItems" :key="item.memory_id">
              <button
                type="button" class="card memory-card" :aria-pressed="selectedId === item.memory_id"
                @click="select(item.memory_id)"
              >
                <span class="memory-meta">
                  <span class="kind-tag">{{ memoryKindLabel(item.kind) }}</span>
                  <span>{{ scopeName(item) }}</span>
                  <span>v{{ item.version }}</span>
                  <span v-if="item.pinned">固定</span>
                  <span v-if="item.status === 'archived'">已替代</span>
                </span>
                <span class="summary">{{ item.content }}</span>
                <span v-if="item.tags?.length" class="memory-tags">{{ item.tags.map(tag => '#' + tag).join(' · ') }}</span>
              </button>
            </li>
          </ul>
          <nav v-if="pageCount > 1 && !loading" class="pagination" aria-label="记忆分页">
            <button type="button" class="btn btn-secondary" :disabled="page === 1" @click="page--">上一页</button>
            <span role="status">{{ page }} / {{ pageCount }}</span>
            <button type="button" class="btn btn-secondary" :disabled="page === pageCount" @click="page++">下一页</button>
          </nav>
        </section>

        <aside v-if="selectedId" class="card detail" aria-labelledby="memory-detail-title">
          <div class="detail-header">
            <h2 id="memory-detail-title" ref="detailHeading" tabindex="-1">记忆详情</h2>
            <button type="button" class="btn btn-secondary btn-sm" @click="closeDetail">关闭详情</button>
          </div>
          <p v-if="detailLoading" role="status">正在加载详情…</p>
          <p v-if="detailError" role="alert" class="banner error">{{ detailError }}</p>
          <template v-if="detail">
            <p class="memory-meta">
              <span class="kind-tag">{{ memoryKindLabel(detail.kind) }}</span>
              <span>{{ scopeName(detail) }}</span>
              <span>当前 v{{ detail.version }}</span>
              <span v-if="detail.pinned">固定</span>
              <span v-if="detail.status === 'archived'">已替代</span>
            </p>
            <p class="content">{{ detail.content }}</p>
            <p class="muted">{{ formatDateTime(detail.recorded_at) }} · {{ detail.memory_id }}</p>
            <p v-if="detail.tags?.length" class="memory-tags">{{ detail.tags.map(tag => '#' + tag).join(' · ') }}</p>
            <p v-if="detail.supersedes">
              <button type="button" class="btn btn-secondary btn-sm" @click="select(detail.supersedes ?? '')">查看被替代的记忆</button>
            </p>

            <div v-if="access.edit" class="actions detail-actions">
              <button type="button" class="btn btn-secondary btn-sm" v-if="detail.status === 'active'" :disabled="mutating || editing" @click="startEdit">修订</button>
              <button type="button" class="btn btn-secondary btn-sm" v-if="detail.status === 'active'" :disabled="mutating" @click="changeSharing">
                {{ detail.is_shared ? '取消共享' : '设为共享' }}
              </button>
              <button type="button" class="btn btn-danger btn-sm" :disabled="mutating" @click="confirmForget = !confirmForget; editing = false">遗忘</button>
            </div>

            <form v-if="editing && access.edit" class="edit-form" @submit.prevent="saveEdit">
              <label>修订内容
                <textarea v-model="editContent" class="textarea" rows="4" maxlength="2000" required></textarea>
              </label>
              <div class="actions">
                <button type="button" class="btn btn-secondary btn-sm" :disabled="mutating" @click="editing = false">取消</button>
                <button class="btn btn-primary btn-sm" type="submit" :disabled="mutating || !editContent.trim()">提交修订</button>
              </div>
            </form>
            <div v-if="confirmForget && access.edit" class="confirmation">
              <p>遗忘会清除这条记忆、修订和来源摘录。原始聊天记录仍保留。</p>
              <div class="actions">
                <button type="button" class="btn btn-secondary btn-sm" :disabled="mutating" @click="confirmForget = false">取消</button>
                <button type="button" class="btn btn-danger btn-sm" :disabled="mutating" @click="forgetSelected">确认遗忘</button>
              </div>
            </div>

            <section class="detail-section" aria-labelledby="memory-sources-title">
              <h3 id="memory-sources-title">来源</h3>
              <p v-if="!detail.source_refs?.length" class="muted">暂无来源。</p>
              <ul v-else class="sources">
                <li v-for="(source, index) in detail.source_refs" :key="index">
                  <span class="muted">{{ sourceLabels[source.kind] ?? source.kind }}</span>
                  <span>{{ source.ref }}</span>
                  <blockquote v-if="source.quote">{{ source.quote }}</blockquote>
                </li>
              </ul>
            </section>

            <section class="detail-section" aria-labelledby="memory-revisions-title">
              <h3 id="memory-revisions-title">修订记录</h3>
              <p v-if="requestedVersion && requestedVersion !== detail.version" class="muted">
                本轮请求加入 v{{ requestedVersion }}，当前为 v{{ detail.version }}。
              </p>
              <p v-if="revisionsLoading" role="status">正在加载修订记录…</p>
              <p v-if="revisionsError" role="alert" class="banner error">{{ revisionsError }}</p>
              <p v-else-if="!revisionsLoading && !revisions.length" class="muted">暂无修订记录。</p>
              <details v-for="row in revisions" :key="row.version" :open="row.version === requestedVersion">
                <summary>v{{ row.version }} <span class="muted">{{ formatDateTime(row.created_at) }}</span></summary>
                <p v-if="row.reason" class="muted">{{ row.reason }}</p>
                <p class="content">{{ row.content }}</p>
                <ul v-if="row.source_refs?.length" class="sources muted">
                  <li v-for="(source, index) in row.source_refs" :key="index">
                    <span>{{ sourceLabels[source.kind] ?? source.kind }} · {{ source.ref }}</span>
                    <blockquote v-if="source.quote">{{ source.quote }}</blockquote>
                  </li>
                </ul>
              </details>
              <button
                v-if="moreRevisions" type="button" class="btn btn-secondary btn-sm"
                :disabled="revisionsLoading" @click="loadRevisions(detail.memory_id, revisions.length)"
              >加载更多修订</button>
            </section>
          </template>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { isAxiosError } from 'axios'
import {
  forgetMemory, getMemory, getMemoryRevisions, listMemories, recallMemories, rememberMemory, reviseMemory, setMemorySharing,
  type MemoryRecord, type MemoryRevision,
} from '@/api/memoryManagement'
import { listPersonas, type Persona } from '@/api/personas'
import MemoryStarMap from '@/components/memory/MemoryStarMap.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/dateTime'
import { extractErrorMessage } from '@/utils/errorMessage'
import { matchesMemoryScope, memoryAccess, memoryKinds, memoryKindLabel, memoryLocator, memoryVersion } from '@/utils/memoryView'

const PAGE_SIZE = 12
const sourceLabels: Record<string, string> = { manual: '手动', message: '消息', wechat: '微信', channel_event: '渠道消息' }
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const access = computed(() => memoryAccess(auth.permissions, auth.capabilities?.modules?.memory, auth.userRole === 'super_admin'))
const items = ref<MemoryRecord[]>([])
const personas = ref<Persona[]>([])
const activePersonas = computed(() => personas.value.filter(role => role.id && role.active))
const view = ref<'list' | 'graph'>('list')
const grouping = ref<'kind' | 'tag'>('kind')
const scope = ref('all')
const query = ref('')
const appliedQuery = ref('')
const previewing = ref(false)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const showAdd = ref(false)
const adding = ref(false)
const draft = reactive({ kind: 'fact', content: '', source: '', quote: '', pinned: false, scope: 'default' })
const selectedId = computed(() => memoryLocator(route.query.memory))
const requestedVersion = computed(() => {
  const version = memoryVersion(route.query.version)
  return version ? Number(version) : undefined
})
const detail = ref<MemoryRecord>()
const detailHeading = ref<HTMLElement>()
const resultsPanel = ref<HTMLElement>()
const detailLoading = ref(false)
const detailError = ref('')
const revisions = ref<MemoryRevision[]>([])
const revisionsLoading = ref(false)
const revisionsError = ref('')
const moreRevisions = ref(false)
const editing = ref(false)
const editContent = ref('')
const confirmForget = ref(false)
const mutating = ref(false)
let returnFocus: HTMLElement | null = null

const scopeRoles = computed(() => {
  const roles = new Map<string, string>()
  for (const role of personas.value) {
    if (role.id) roles.set(role.id, role.active ? role.name : role.name + '（已归档）')
  }
  for (const record of items.value) {
    if (record.persona_id && !roles.has(record.persona_id)) roles.set(record.persona_id, record.persona_id)
  }
  return [...roles].map(([id, name]) => ({ id, name }))
})
const previewPersona = computed(() => activePersonas.value.find(role => role.id === scope.value))
const canPreviewRecall = computed(() => scope.value === 'all' || scope.value === 'default' || !!previewPersona.value)
const previewRoleName = computed(() => previewPersona.value?.name ?? '默认角色')
const visible = computed(() => previewing.value ? items.value : items.value.filter(item => matchesMemoryScope(item, scope.value)))
const pageCount = computed(() => Math.max(1, Math.ceil(visible.value.length / PAGE_SIZE)))
const pageItems = computed(() => visible.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
watch(pageCount, count => { page.value = Math.min(page.value, count) })

function scopeName(record: MemoryRecord): string {
  if (record.is_shared) return '账号共享'
  if (!record.persona_id) return '默认角色'
  return scopeRoles.value.find(role => role.id === record.persona_id)?.name ?? record.persona_id
}

async function loadPersonas() {
  try {
    personas.value = await listPersonas()
  } catch (cause) {
    console.warn('加载记忆角色失败', cause)
  }
}

let listGeneration = 0
async function load() {
  const generation = ++listGeneration
  if (!auth.ready || !access.value.view) {
    items.value = []
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = previewing.value
      ? await recallMemories(appliedQuery.value, previewPersona.value?.id ?? undefined)
      : await listMemories({
        persona_id: scope.value === 'all' ? undefined : scope.value,
        query: appliedQuery.value || undefined,
        include_archived: true,
        limit: 200,
      })
    if (generation === listGeneration) items.value = result
  } catch (cause) {
    if (generation === listGeneration) {
      items.value = []
      error.value = extractErrorMessage(cause) || '加载记忆失败。'
    }
  } finally {
    if (generation === listGeneration) loading.value = false
  }
}
watch([() => auth.ready, () => access.value.view, scope, appliedQuery, previewing], load, { immediate: true })
watch([() => auth.ready, () => access.value.view], ([ready, allowed]) => {
  if (ready && allowed) void loadPersonas()
}, { immediate: true })

function runQuery(preview: boolean) {
  page.value = 1
  const term = query.value.trim()
  if (preview && (!term || !canPreviewRecall.value)) return
  if (term === appliedQuery.value && preview === previewing.value) {
    void load()
  } else {
    previewing.value = preview
    appliedQuery.value = term
  }
}

function changeScope() {
  page.value = 1
  previewing.value = false
}

function select(id: string) {
  if (!memoryLocator(id)) return
  if (!selectedId.value && document.activeElement instanceof HTMLElement) returnFocus = document.activeElement
  void router.replace({ name: 'Memory', query: { memory: id } })
}

async function closeDetail() {
  await router.replace({ name: 'Memory' })
  if (returnFocus?.isConnected) returnFocus.focus()
  else resultsPanel.value?.focus()
  returnFocus = null
}

let detailGeneration = 0
watch([selectedId, () => auth.ready, () => access.value.view], async ([id, ready, allowed]) => {
  const generation = ++detailGeneration
  detail.value = undefined
  detailError.value = ''
  revisions.value = []
  moreRevisions.value = false
  revisionsError.value = ''
  editing.value = false
  confirmForget.value = false
  detailLoading.value = false
  revisionsLoading.value = false
  if (!id || !ready || !allowed) return
  detailLoading.value = true
  await nextTick()
  if (generation !== detailGeneration) return
  detailHeading.value?.focus()
  try {
    const record = await getMemory(id)
    if (generation !== detailGeneration) return
    detail.value = record
    void loadRevisions(record.memory_id)
  } catch (cause) {
    if (generation !== detailGeneration) return
    const status = isAxiosError(cause) ? cause.response?.status : undefined
    detailError.value = status === 403 || status === 404
      ? '这条记忆已遗忘、找不到或当前账号无权查看。'
      : extractErrorMessage(cause) || '加载记忆详情失败。'
  } finally {
    if (generation === detailGeneration) detailLoading.value = false
  }
}, { immediate: true })

let revisionsRequest = 0
async function loadRevisions(id: string, offset = 0) {
  const generation = detailGeneration
  const requestId = ++revisionsRequest
  revisionsLoading.value = true
  revisionsError.value = ''
  try {
    const rows = await getMemoryRevisions(id, offset)
    if (generation !== detailGeneration || requestId !== revisionsRequest) return
    revisions.value = offset ? [...revisions.value, ...rows] : rows
    moreRevisions.value = rows.length === 50
  } catch (cause) {
    if (generation !== detailGeneration || requestId !== revisionsRequest) return
    revisionsError.value = extractErrorMessage(cause) || '加载修订记录失败。'
  } finally {
    if (generation === detailGeneration && requestId === revisionsRequest) revisionsLoading.value = false
  }
}

function openAdd() {
  showAdd.value = !showAdd.value
  if (showAdd.value) {
    draft.scope = scope.value === 'shared' || activePersonas.value.some(p => p.id === scope.value) ? scope.value : 'default'
  }
}

async function remember() {
  if (!access.value.edit || adding.value) return
  adding.value = true
  error.value = ''
  notice.value = ''
  try {
    await rememberMemory({
      kind: draft.kind,
      content: draft.content,
      source_refs: [{ kind: 'manual', ref: draft.source.trim(), quote: draft.quote }],
      pinned: draft.pinned,
      persona_id: ['default', 'shared'].includes(draft.scope) ? undefined : draft.scope,
      is_shared: draft.scope === 'shared',
    })
    Object.assign(draft, { content: '', source: '', quote: '', pinned: false })
    showAdd.value = false
    notice.value = '记忆已保存。'
    await load()
  } catch (cause) {
    error.value = extractErrorMessage(cause) || '保存记忆失败。'
  } finally {
    adding.value = false
  }
}

function startEdit() {
  if (!detail.value || !access.value.edit) return
  editing.value = true
  confirmForget.value = false
  detailError.value = ''
  editContent.value = detail.value.content
}

async function saveEdit() {
  const record = detail.value
  const generation = detailGeneration
  if (!record || !access.value.edit || mutating.value) return
  mutating.value = true
  detailError.value = ''
  try {
    const updated = await reviseMemory(record.memory_id, record.version, editContent.value)
    if (generation === detailGeneration) {
      detail.value = updated
      editing.value = false
      void loadRevisions(updated.memory_id)
    }
    await load()
  } catch (cause) {
    if (generation !== detailGeneration) return
    if (isAxiosError(cause) && cause.response?.status === 409) {
      try {
        const current = await getMemory(record.memory_id)
        if (generation === detailGeneration) {
          detail.value = current
          detailError.value = '版本已更新。请核对当前内容后重新提交，输入已保留。'
          void loadRevisions(current.memory_id)
        }
      } catch (refreshError) {
        if (generation === detailGeneration) {
          detailError.value = extractErrorMessage(refreshError) || '版本已更新，但无法读取当前记忆。'
        }
      }
    } else {
      detailError.value = extractErrorMessage(cause) || '修订失败。'
    }
  } finally {
    mutating.value = false
  }
}

async function changeSharing() {
  const record = detail.value
  const generation = detailGeneration
  if (!record || !access.value.edit || mutating.value) return
  if (!window.confirm(record.is_shared
    ? '取消共享后，只有原归属角色可在对话中召回这条记忆。继续吗？'
    : '将这条记忆共享给账号中的所有对话角色？')) return
  mutating.value = true
  detailError.value = ''
  try {
    const updated = await setMemorySharing(record.memory_id, !record.is_shared)
    if (generation === detailGeneration) detail.value = updated
    await load()
  } catch (cause) {
    if (generation === detailGeneration) detailError.value = extractErrorMessage(cause) || '更改记忆归属失败。'
  } finally {
    mutating.value = false
  }
}

async function forgetSelected() {
  const record = detail.value
  const generation = detailGeneration
  if (!record || !access.value.edit || mutating.value) return
  mutating.value = true
  detailError.value = ''
  try {
    await forgetMemory(record.memory_id)
    items.value = items.value.filter(item => item.memory_id !== record.memory_id)
    if (generation === detailGeneration) await closeDetail()
    notice.value = '记忆已遗忘。'
    await load()
  } catch (cause) {
    if (generation === detailGeneration) detailError.value = extractErrorMessage(cause) || '遗忘失败。'
  } finally {
    mutating.value = false
  }
}
</script>

<style scoped>
.memory-page { max-width: 1280px; margin: 0 auto; padding: clamp(14px, 4vw, 42px); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 22px; }
.page-header h1 { margin: 0 0 4px; font-size: clamp(21px, 3vw, 30px); }
.muted { color: var(--text-secondary); font-size: 13px; margin: 0; overflow-wrap: anywhere; }
.toolbar, .filters, .view-group, .actions, .form-row, .detail-header, .graph-tools label, .pagination {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
}
.toolbar { justify-content: space-between; margin-bottom: 16px; }
.filters { flex: 1; }
.filters input { flex: 1; min-width: min(100%, 155px); max-width: 360px; }
.filters .select, .graph-tools .select { width: auto; max-width: 100%; }
.filters .select { min-width: min(100%, 130px); }
.view-group button[aria-pressed=true] { background: var(--bg-active); border-color: var(--brand); font-weight: 600; }
.add-card { padding: 16px; margin-bottom: 16px; display: grid; gap: 10px; }
.form-row { align-items: flex-end; }
.form-row label { flex: 1 1 125px; }
.add-card label, .edit-form label { display: grid; gap: 4px; font-size: 13px; }
.add-card .checkbox { display: flex; align-items: center; gap: 5px; }
.textarea, .add-card input:not([type=checkbox]), .form-row .select { width: 100%; }
.textarea { resize: vertical; }
.actions { justify-content: flex-end; }
.workspace { display: grid; gap: 16px; align-items: start; }
.workspace.with-details { grid-template-columns: minmax(0, 1fr) minmax(295px, 0.75fr); }
.memory-list { display: grid; gap: 8px; list-style: none; padding: 0; margin: 0; }
.memory-card { display: grid; gap: 7px; width: 100%; text-align: left; padding: 12px 16px; cursor: pointer; border: 1px solid var(--border-secondary); box-shadow: none; border-radius: 9px; }
.memory-card:hover, .memory-card[aria-pressed=true] { border-color: var(--brand); background: var(--bg-active); }
.memory-card:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.memory-meta { display: flex; align-items: center; flex-wrap: wrap; column-gap: 10px; row-gap: 4px; margin: 0; color: var(--text-secondary); font-size: 12px; }
.kind-tag { background: var(--bg-active); color: var(--brand); font-weight: 600; border-radius: 4px; padding: 2px 7px; }
.summary { color: var(--text-primary); overflow: hidden; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.memory-tags { color: var(--text-secondary); font-size: 12px; overflow-wrap: anywhere; margin: 0; }
.graph-tools { margin-bottom: 10px; }
.graph-tools label { font-size: 13px; }
.pagination { justify-content: center; margin: 14px 0 4px; }
.detail { padding: 16px; min-width: 0; }
.detail-header { justify-content: space-between; margin-bottom: 12px; }
.detail-header h2 { margin: 0; font-size: 18px; }
.detail-header h2:focus { outline: 2px solid var(--brand); outline-offset: 3px; }
.detail-section, .edit-form, .confirmation { border-top: 1px solid var(--border-secondary); margin-top: 12px; padding-top: 12px; }
.detail-section h3 { margin: 0 0 7px; font-size: 14px; }
.detail-actions { justify-content: flex-start; margin-top: 12px; }
.content { white-space: pre-wrap; overflow-wrap: anywhere; margin: 7px 0; line-height: 1.6; }
.sources { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
.sources li { display: grid; overflow-wrap: anywhere; }
.sources blockquote { margin: 3px 0 0; padding-left: 8px; border-left: 2px solid var(--border-secondary); color: var(--text-secondary); white-space: pre-wrap; }
.detail details { margin: 6px 0; }
.detail summary { cursor: pointer; }
.confirmation p { margin: 0 0 8px; color: var(--text-secondary); }
.edit-form { display: grid; gap: 8px; }
.empty { text-align: center; padding: 30px 0; color: var(--text-secondary); }
.banner { margin: 0 0 10px; padding: 8px 10px; border-radius: 6px; }
.error { color: var(--text-primary); background: var(--bg-danger); border-left: 3px solid var(--text-danger); }
@media (max-width: 1020px) {
  .workspace.with-details { grid-template-columns: minmax(0, 1fr); }
  .detail { grid-row: 1; }
}
@media (max-width: 700px) {
  .toolbar, .filters { display: grid; }
  .toolbar { grid-template-columns: minmax(0, 1fr); }
  .filters { grid-template-columns: minmax(0, 1fr) auto; }
  .filters .btn { justify-self: start; }
  .filters .select { width: 100%; }
}
</style>
