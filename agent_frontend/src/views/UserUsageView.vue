<template>
  <div id="global-detail" class="usage-page">
    <div class="page-header">
      <div>
        <h2>全局调用明细</h2>
        <p class="hint">按会话最近消息排序。展开会话可查看每次调用的问答。时间按 {{ tzDisplay }} 显示。</p>
      </div>
      <div class="filters">
        <select v-model.number="selectedUid" class="select" aria-label="筛选用户" @change="onFilterChange()">
          <option :value="0">全部用户</option>
          <option v-for="u in users" :key="u.user_id" :value="u.user_id">{{ u.username }}</option>
        </select>
        <button class="btn btn-secondary btn-sm" @click="reloadAll">刷新</button>
      </div>
    </div>

    <p v-if="error" class="err" role="alert">{{ error }}</p>

    <section class="card">
      <h3>会话调用记录</h3>
      <div v-if="loading" class="empty" role="status">正在加载会话…</div>
      <div v-else-if="!error && !groups.length" class="empty">暂无调用记录</div>
      <UsageSessionGroup
        v-for="group in groups" :key="JSON.stringify([group.owner_id, group.session_id])"
        :group="group" global @forbidden="clearForbidden"
      />
      <div class="pager">
        <button class="btn btn-sm btn-secondary" :disabled="loading || page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="muted">第 {{ page }} 页 · 本页 {{ groups.length }} 组</span>
        <button class="btn btn-sm btn-secondary" :disabled="loading || !nextAvailable" @click="goto(page + 1)">下一页</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// 全局调用明细仅在用户进入该视图后加载。
// trace.manage 专属；用户选项来自 /api/usage/users 最小字段。
import { computed, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import request from '@/api/request'
import UsageSessionGroup, { type CallGroup } from '@/components/UsageSessionGroup.vue'
import { timezoneLabel, DEFAULT_TIMEZONE } from '@/utils/dateTime'
import {
  GLOBAL_PAGE_SIZE, beginLoad, isStaleResponse, onFilterChanged,
} from '@/utils/globalUsage'

interface UserOption { user_id: number; username: string; last_call: string }
const users = ref<UserOption[]>([])
const groups = ref<CallGroup[]>([])
const selectedUid = ref(0) // 0=全部
const page = ref(1)
const nextAvailable = ref(false)
const loading = ref(false)
const error = ref('')
let loadToken = 0

const tzDisplay = computed(() => timezoneLabel(localStorage.getItem('userTimezone') || DEFAULT_TIMEZONE))

function clearForbidden() {
  loadToken++
  groups.value = []
  users.value = []
  loading.value = false
  nextAvailable.value = false
  error.value = '查看各用户的调用和问答需要「管理全局用量」权限。'
}

async function loadGroups(refreshUsers = false) {
  error.value = ''
  groups.value = []
  loading.value = true
  nextAvailable.value = false
  const { nextToken, requestToken } = beginLoad(loadToken)
  loadToken = nextToken
  try {
    if (refreshUsers) {
      const options = await request.get<{ users: UserOption[] }>('/api/usage/users', { params: { limit: 500 } })
      if (isStaleResponse(loadToken, requestToken)) return
      users.value = options.data.users || []
    }
    const params: Record<string, number> = { limit: GLOBAL_PAGE_SIZE, offset: (page.value - 1) * GLOBAL_PAGE_SIZE }
    if (selectedUid.value > 0) params.owner_id = selectedUid.value
    const { data } = await request.get<{ groups: CallGroup[]; has_more: boolean }>('/api/usage/call-groups', { params })
    // 竞态防护：快速切换用户/翻页时，晚到的旧筛选响应必须整批丢弃
    if (isStaleResponse(loadToken, requestToken)) return
    groups.value = data.groups
    nextAvailable.value = data.has_more
  } catch (e) {
    if (isStaleResponse(loadToken, requestToken)) return
    if (isAxiosError(e) && e.response?.status === 403) clearForbidden()
    else error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    if (!isStaleResponse(loadToken, requestToken)) loading.value = false
  }
}

function onFilterChange() {
  // v-model 已同步 selectedUid；此处只需把筛选变化收敛为"回到第 1 页再查询"
  const state = onFilterChanged(selectedUid.value)
  selectedUid.value = state.selectedUid
  page.value = state.page
  loadGroups()
}

function goto(p: number) {
  page.value = p
  loadGroups()
}

async function reloadAll() {
  page.value = 1
  await loadGroups(true)
}

onMounted(reloadAll)
</script>

<style scoped>

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.filters { display: flex; gap: 8px; }
.filters .btn { width: auto; flex: none; white-space: nowrap; }
.card { padding: 16px; margin-bottom: 16px; }
.card h3 { margin: 0 0 12px; }
.empty { color: var(--text-tertiary); padding: 16px 0; }
.pager { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 12px; }
.err { color: #b42318; margin: 0 0 12px; }
.muted { color: var(--text-tertiary); font-size: 12px; }
@media (max-width: 760px) {
  .page-header { flex-direction: column; }
}
</style>
