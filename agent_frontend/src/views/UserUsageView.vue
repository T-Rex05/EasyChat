<template>
  <div class="usage-page">
    <div class="page-header">
      <div>
        <h2>全局调用明细</h2>
        <p class="hint">按用户查看模型调用记录（需要「查看全局用量」权限）。时间按 {{ tzDisplay }} 显示。</p>
      </div>
      <div class="filters">
        <select v-model="selectedUid" class="select" @change="loadCalls">
          <option :value="0">全部用户</option>
          <option v-for="u in users" :key="u.user_id" :value="u.user_id">{{ u.username }}</option>
        </select>
        <button class="btn btn-secondary btn-sm" @click="reloadAll">刷新</button>
      </div>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <section class="card">
      <h3>调用记录（{{ page }} / {{ totalPages }} 页，共 {{ total }} 条）</h3>
      <div v-if="calls.length === 0" class="empty">暂无调用记录</div>
      <table v-else class="table">
        <thead>
          <tr><th>时间</th><th>用户</th><th>来源</th><th>模型</th><th>输入</th><th>输出</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in calls" :key="c.call_id">
            <td>{{ formatDateTime(c.created_at) }}</td>
            <td>{{ usernameOf(c.owner_id) }}</td>
            <td>{{ c.source || '—' }}</td>
            <td>{{ c.model || '—' }}</td>
            <td>{{ c.input_tokens }}</td>
            <td>{{ c.output_tokens }}</td>
            <td :class="c.status && c.status !== 'ok' ? 'st-bad' : 'st-ok'">{{ c.status || 'ok' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="pager">
        <button class="btn btn-sm btn-secondary" :disabled="page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="muted">第 {{ page }} 页</span>
        <button class="btn btn-sm btn-secondary" :disabled="page >= totalPages" @click="goto(page + 1)">下一页</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// 全局调用明细页（WP-B）：trace.manage 专属；用户选项来自 /api/usage/users 最小字段。
import { computed, onMounted, ref } from 'vue'
import request from '@/api/request'
import { formatDateTime, timezoneLabel, DEFAULT_TIMEZONE } from '@/utils/dateTime'

interface UserOption { user_id: number; username: string; last_call: string }
interface Call { call_id: string; owner_id: number; created_at: string; source?: string; model?: string; input_tokens: number; output_tokens: number; status?: string }

const users = ref<UserOption[]>([])
const calls = ref<Call[]>([])
const selectedUid = ref(0) // 0=全部
const page = ref(1)
const total = ref(0)
const pageSize = 50
const error = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const tzDisplay = computed(() => timezoneLabel(localStorage.getItem('userTimezone') || DEFAULT_TIMEZONE))

function usernameOf(uid: number): string {
  return users.value.find(u => u.user_id === uid)?.username || `#${uid}`
}

async function loadUsers() {
  const res = await request.get<{ users: UserOption[]; total: number }>('/api/usage/users', { params: { limit: 500 } })
  users.value = res.data.users || []
}

async function loadCalls() {
  error.value = ''
  try {
    const params: Record<string, number> = { limit: pageSize, offset: (page.value - 1) * pageSize }
    if (selectedUid.value > 0) params.owner_id = selectedUid.value
    const res = await request.get<Call[]>('/api/usage/calls', { params })
    calls.value = res.data || []
    // 总数:仅"全部"时按选项接口统计,单选时以本页是否满页近似(后端未提供 count,保持窄接口不扩权)
    if (selectedUid.value === 0) {
      const all = await request.get<{ total: number }>('/api/usage/users', { params: { limit: 1 } })
      // users.total 是"用户数"而非调用数;调用总数用一次大 limit 估算代价高——以当前页是否满页给出可翻页提示
      total.value = calls.value.length < pageSize ? (page.value - 1) * pageSize + calls.value.length : page.value * pageSize + 1
      void all
    } else {
      total.value = calls.value.length < pageSize ? (page.value - 1) * pageSize + calls.value.length : page.value * pageSize + 1
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message || e?.message || '加载失败（需要查看全局用量权限）'
  }
}

function goto(p: number) {
  page.value = p
  loadCalls()
}

async function reloadAll() {
  page.value = 1
  await Promise.all([loadUsers().catch(() => { users.value = [] }), loadCalls()])
}

onMounted(async () => {
  try {
    await loadUsers()
  } catch {
    error.value = '无权查看用户选项（需要「查看全局用量」权限）'
    return
  }
  await loadCalls()
})
</script>

<style scoped>
.usage-page { max-width: 1100px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.filters { display: flex; gap: 8px; }
.card { padding: 16px; margin-bottom: 16px; }
.card h3 { margin: 0 0 12px; }
.empty { color: var(--text-tertiary); padding: 16px 0; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border-primary, #e5e7eb); }
.pager { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
.err { color: #b42318; margin: 0 0 12px; }
.st-ok { color: #1d7f3c; }
.st-bad { color: #b42318; }
.muted { color: var(--text-tertiary); font-size: 12px; }
@media (max-width: 760px) {
  .page-header { flex-direction: column; }
  .table { font-size: 12px; }
}
</style>
