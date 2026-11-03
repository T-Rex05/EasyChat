<template>
  <div class="usage-page">
    <header class="page-header">
      <div>
        <h2>用量与 Token 排行</h2>
        <p class="hint">数据来自 usage 账本；无凭证时不会产生调用记录。</p>
      </div>
      <div class="filters">
        <select v-model.number="days" class="select" @change="loadRanking">
          <option :value="1">今日</option>
          <option :value="7">近 7 天</option>
          <option :value="30">近 30 天</option>
          <option :value="90">近 90 天</option>
        </select>
        <button class="btn btn-secondary" @click="loadAll">刷新</button>
      </div>
    </header>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="card">
      <h3>我的每日用量</h3>
      <div v-if="daily.length === 0" class="empty">暂无用量</div>
      <div v-else class="daily-list">
        <div v-for="d in daily" :key="d.stat_date" class="daily-row">
          <span>{{ d.stat_date }}</span>
          <span>输入 {{ d.input_tokens }}</span>
          <span>输出 {{ d.output_tokens }}</span>
          <span class="muted">调用 {{ d.call_count }}</span>
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
            <td>{{ row.username || row.owner_id }}</td>
            <td>{{ row.input_tokens }}</td>
            <td>{{ row.output_tokens }}</td>
            <td>{{ row.total_tokens }}</td>
            <td>{{ row.call_count }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h3>最近调用</h3>
      <div v-if="calls.length === 0" class="empty">暂无调用记录</div>
      <table v-else class="table">
        <thead><tr><th>时间</th><th>模型</th><th>输入</th><th>输出</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="c in calls" :key="c.call_id">
            <td>{{ c.created_at }}</td>
            <td>{{ c.model || '—' }}</td>
            <td>{{ c.input_tokens }}</td>
            <td>{{ c.output_tokens }}</td>
            <td>{{ c.status || 'ok' }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import request from '@/api/request'

interface Daily { stat_date: string; input_tokens: number; output_tokens: number; call_count: number }
interface RankRow { owner_id?: number; username?: string; input_tokens: number; output_tokens: number; total_tokens: number; call_count: number }
interface Call { call_id: string; created_at: string; model?: string; input_tokens: number; output_tokens: number; status?: string }

const days = ref(7)
const daily = ref<Daily[]>([])
const ranking = ref<RankRow[]>([])
const calls = ref<Call[]>([])
const error = ref('')

async function loadRanking() {
  error.value = ''
  try {
    const res = await request.get<{ ranking: RankRow[] }>('/api/usage/ranking', { params: { days: days.value, limit: 50 } })
    ranking.value = res.data.ranking
  } catch (e: any) {
    error.value = e?.message || '排行加载失败（需要 trace.view）'
  }
}

async function loadAll() {
  await Promise.all([
    loadRanking(),
    request.get<Daily[]>('/api/usage/me/daily', { params: { days: 30 } })
      .then(r => { daily.value = r.data }).catch(() => { daily.value = [] }),
    request.get<Call[]>('/api/usage/calls', { params: { limit: 50 } })
      .then(r => { calls.value = r.data }).catch(() => { calls.value = [] }),
  ])
}

onMounted(loadAll)
</script>

<style scoped>
.usage-page { max-width: 1100px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.filters { display: flex; gap: 8px; }
.card { padding: 16px; margin-bottom: 16px; }
.card h3 { margin: 0 0 12px; font-size: 15px; }
.daily-list { display: grid; gap: 6px; }
.daily-row { display: grid; grid-template-columns: 120px 1fr 1fr 1fr; gap: 8px; font-size: 13px; padding: 6px 0; border-bottom: 1px solid var(--border-primary); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border-primary); }
.table th { color: var(--text-tertiary); font-weight: 500; }
.muted { color: var(--text-tertiary); }
.empty { color: var(--text-tertiary); text-align: center; padding: 24px 0; }
.error-banner { background: rgba(220, 53, 69, 0.12); color: #c82333; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
</style>
