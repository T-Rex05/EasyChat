<template>
  <div class="usage-page">
    <header class="page-header">
      <div>
        <h2>用量与 Token 排行</h2>
        <nav v-if="canManageGlobal" class="usage-nav" aria-label="用量视图">
          <RouterLink to="/trace" :aria-current="!globalOpen ? 'page' : undefined" :class="{ selected: !globalOpen }">用量概览</RouterLink>
          <RouterLink :to="{ path: '/trace', hash: '#global-detail' }" :aria-current="globalOpen ? 'page' : undefined" :class="{ selected: globalOpen }">全局调用明细</RouterLink>
        </nav>
      </div>
      <div v-if="!globalOpen" class="filters">
        <select v-model.number="days" class="select" @change="loadRanking">
          <option :value="1">今日</option>
          <option :value="7">近 7 天</option>
          <option :value="30">近 30 天</option>
          <option :value="90">近 90 天</option>
        </select>
        <button class="btn btn-secondary" @click="loadAll">刷新</button>
      </div>
    </header>

    <UserUsageView v-if="globalOpen" />
    <template v-else>
      <div v-if="error" class="error-banner">{{ error }}</div>

      <section class="card">
        <h3>我的每日用量</h3>
        <div v-if="daily.length === 0" class="empty">暂无用量</div>
        <div v-else class="daily-list">
          <div v-for="d in daily" :key="d.stat_date" class="daily-row">
            <span>{{ d.stat_date }}</span>
            <span :title="String(d.input_tokens)">输入 {{ formatUsageCount(d.input_tokens) }}</span>
            <span :title="String(d.output_tokens)">输出 {{ formatUsageCount(d.output_tokens) }}</span>
            <span :title="String(d.total_tokens)">合计 {{ formatUsageCount(d.total_tokens) }}</span>
            <span class="muted" :title="String(d.call_count)">调用 {{ formatUsageCount(d.call_count) }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <h3>Token 排行（{{ days }} 天）</h3>
        <div v-if="ranking.length === 0" class="empty">暂无排行数据</div>
        <table v-else class="table">
          <thead><tr><th>#</th><th>用户</th><th>输入</th><th>输出</th><th>合计</th><th>调用次数</th></tr></thead>
          <tbody>
            <tr v-for="(row, idx) in ranking" :key="row.owner_id ?? idx">
              <td>{{ idx + 1 }}</td>
              <td><UsageOwnerBadge :label="row.username || String(row.owner_id ?? '—')" /></td>
              <td :title="String(row.input_tokens)">{{ formatUsageCount(row.input_tokens) }}</td>
              <td :title="String(row.output_tokens)">{{ formatUsageCount(row.output_tokens) }}</td>
              <td :title="String(row.total_tokens)">{{ formatUsageCount(row.total_tokens) }}</td>
              <td :title="String(row.call_count)">{{ formatUsageCount(row.call_count) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h3>最近调用（本人）</h3>
        <p v-if="ownerPendingHint" class="empty">{{ ownerPendingHint }}</p>
        <template v-else>
          <UsageSessionGroup v-for="group in groups" :key="group.session_id ?? ''" :group="group" />
          <p v-if="groupError" role="alert">{{ groupError }}</p>
          <div v-else-if="!groups.length && !loadingGroups" class="empty">暂无调用记录</div>
          <button v-if="hasMoreGroups || groupError || loadingGroups" class="btn btn-secondary" type="button"
                  :disabled="loadingGroups" @click="loadMyCalls()">
            {{ loadingGroups ? '加载中…' : groupError ? '重试' : '加载更多会话' }}
          </button>
        </template>
      </section>

    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import UsageSessionGroup, { type CallGroup } from '@/components/UsageSessionGroup.vue'
import UsageOwnerBadge from '@/components/UsageOwnerBadge.vue'
import request from '@/api/request'
import { formatUsageCount } from '@/utils/usageNumbers'
import { resolveMyUid } from '@/utils/globalUsage'
import { useAuthStore } from '@/stores/auth'
import UserUsageView from './UserUsageView.vue'

interface Daily { stat_date: string; input_tokens: number; output_tokens: number; total_tokens: number; call_count: number }
interface RankRow { owner_id?: number; username?: string; input_tokens: number; output_tokens: number; total_tokens: number; call_count: number }
const route = useRoute()
const auth = useAuthStore()
const days = ref(7)
const daily = ref<Daily[]>([])
const ranking = ref<RankRow[]>([])
const groups = ref<CallGroup[]>([])
const loadingGroups = ref(false)
const hasMoreGroups = ref(false)
const groupError = ref('')
let groupOffset = 0
let requestVersion = 0
const error = ref('')
const ownerPendingHint = ref('')

// capabilities 为唯一判定来源；未加载时退回原子权限（与侧栏口径一致）
const canManageGlobal = computed(() => {
  const cap = auth.capabilities
  if (cap?.super_admin) return true
  if (cap?.modules?.trace) return !!cap.modules.trace.manage
  return auth.permissions.includes('trace.manage')
})

const globalOpen = computed(() => auth.ready && canManageGlobal.value && route.hash === '#global-detail')

async function loadRanking() {
  error.value = ''
  try {
    const res = await request.get<{ ranking: RankRow[] }>('/api/usage/ranking', { params: { days: days.value, limit: 50 } })
    ranking.value = res.data.ranking
  } catch (e: any) {
    error.value = e?.message || '排行加载失败（需要 trace.view）'
  }
}

async function loadMyCalls(reset = false) {
  if (reset) {
    requestVersion++
    groups.value = []
    groupOffset = 0
    hasMoreGroups.value = false
    loadingGroups.value = false
  }
  if (loadingGroups.value) return
  if (!resolveMyUid(auth.userId)) {
    ownerPendingHint.value = '身份尚未就绪，暂不加载本人调用记录'
    return
  }
  ownerPendingHint.value = ''
  groupError.value = ''
  loadingGroups.value = true
  const version = requestVersion
  try {
    const { data } = await request.get<{ groups: CallGroup[]; has_more: boolean }>('/api/usage/me/call-groups', {
      params: { limit: 20, offset: groupOffset },
    })
    if (version !== requestVersion) return
    const seen = new Set(groups.value.map(g => g.session_id))
    groups.value.push(...data.groups.filter(g => !seen.has(g.session_id)))
    hasMoreGroups.value = data.has_more
    groupOffset += data.groups.length
  } catch {
    if (version === requestVersion) groupError.value = '会话加载失败。'
  } finally {
    if (version === requestVersion) loadingGroups.value = false
  }
}

async function loadAll() {
  await Promise.all([
    loadRanking(),
    request.get<Daily[]>('/api/usage/me/daily', { params: { days: 30 } })
      .then(r => { daily.value = r.data }).catch(() => { daily.value = [] }),
    loadMyCalls(true),
  ])
}

watch(() => auth.ready && !globalOpen.value, (showOverview) => {
  if (showOverview) loadAll()
}, { immediate: true })
</script>

<style scoped>
.usage-page { max-width: 1100px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.usage-nav { display: flex; gap: 6px; margin-top: 12px; }
.usage-nav a { color: var(--text-secondary); text-decoration: none; padding: 6px 12px; border-radius: 6px; }
.usage-nav a.selected { background: var(--bg-primary); color: var(--text-primary); box-shadow: inset 0 -2px currentColor; font-weight: 600; }
.page-header { flex-wrap: wrap; gap: 8px; }
.filters { display: flex; gap: 8px; }
.filters .btn { white-space: nowrap; }
.card { padding: 16px; margin-bottom: 16px; }
.card h3 { margin: 0 0 12px; font-size: 15px; }
.daily-list { display: grid; gap: 6px; }
.daily-row { display: grid; grid-template-columns: 120px 1fr 1fr 1fr 1fr; gap: 8px; font-size: 13px; padding: 6px 0; border-bottom: 1px solid var(--border-primary); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border-primary); }
.table th { color: var(--text-tertiary); font-weight: 500; }
.muted { color: var(--text-tertiary); }
.empty { color: var(--text-tertiary); text-align: center; padding: 24px 0; }
.error-banner { background: rgba(220, 53, 69, 0.12); color: #c82333; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
</style>
