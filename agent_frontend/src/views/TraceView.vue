<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getDashboardStats, getTraces, getAllTraces, getTurnDetail, getTraceConfig, updateTraceConfig, getRanking, searchUsers } from '@/api/trace'
import type { DashboardStats, TraceItem, TraceDetail, TraceConfig, UserRanking } from '@/api/trace'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'

const auth = useAuthStore()

// ── Tab ──
const activeTab = ref<'overview' | 'ranking' | 'users'>('overview')

const tabs = computed(() => {
  const all = [
    { key: 'overview' as const, label: '📊 概览', perm: 'trace.view' },
    { key: 'ranking' as const, label: '🏆 排行榜', perm: 'trace.view' },
    { key: 'users' as const, label: '👥 用户', perm: 'trace.manage' },
  ]
  return all.filter(t => auth.hasPerm(t.perm))
})

// ── 状态 ──
const days = ref(7)
const whenPhrase = ref("")  // 自然语言时间短语（本周/本月等，优先于 days）
const stats = ref<DashboardStats | null>(null)
const traces = ref<TraceItem[]>([])
const traceTotal = ref(0)
const currentPage = ref(1)
const pageSize = 20
const loading = ref(false)

// 筛选
const filterSource = ref('')
const filterStatus = ref(-1)

// 排名
const ranking = ref<UserRanking[]>([])
const rankingDays = ref(7)

// 用户选择
const userSearchQuery = ref('')
const searchResults = ref<{ id: number; username: string }[]>([])
const selectedUserId = ref(0)
let searchTimer: any = null

// 展开的 trace
const expandedTrace = ref<TraceDetail | null>(null)
const expandedRow = ref(-1)  // 当前展开的行索引，-1 = 无

// 设置弹窗
const showConfig = ref(false)
const config = ref<TraceConfig>({ trace_detail_enabled: false, trace_max_text_chars: 10000, trace_retention_days: 30 })
const configSaving = ref(false)
const configSaved = ref(false)

const hasManagePerm = computed(() => auth.hasPerm('trace.manage'))

// ── 数据加载 ──
async function loadDashboard() {
  try {
    stats.value = await getDashboardStats(days.value)
  } catch (e) {
    console.error('加载 Dashboard 失败', e)
  }
}

async function loadTraces() {
  loading.value = true
  try {
    const params: any = {
      source: filterSource.value,
      status: filterStatus.value,
      days: days.value,
      when: whenPhrase.value || undefined,
      offset: (currentPage.value - 1) * pageSize,
      limit: pageSize,
    }
    const result = await getTraces(params)
    // API 现在返回 turns（按会话聚合），映射到 traces 数组
    traces.value = (result.turns || []).map((t: any) => ({
      ...t,
      latency_ms: t.total_latency_ms || 0,
      created_at: t.ended_at || t.started_at || '',
    }))
    traceTotal.value = result.total
  } catch (e) {
    console.error('加载 Trace 列表失败', e)
  } finally {
    loading.value = false
  }
}

async function loadRanking() {
  if (!auth.hasPerm('trace.view')) return
  try {
    const data = await getRanking(rankingDays.value)
    ranking.value = data.ranking
  } catch (e) {
    console.error('加载排名失败', e)
  }
}

async function loadUserTraces() {
  if (selectedUserId.value <= 0) return
  loading.value = true
  try {
    const result = await getAllTraces({
      user_id: selectedUserId.value,
      source: filterSource.value,
      status: filterStatus.value,
      days: days.value,
      when: whenPhrase.value || undefined,
      aggregated: 1,  // 按会话聚合，附带用户问题/AI 回复
      offset: (currentPage.value - 1) * pageSize,
      limit: pageSize,
    })
    // 聚合 turns → 列表行（与概览 Tab 一致）
    traces.value = (result.turns || []).map((t: any) => ({
      ...t,
      latency_ms: t.total_latency_ms || 0,
      created_at: t.ended_at || t.started_at || '',
    }))
    traceTotal.value = result.total
  } catch (e) {
    console.error('加载用户记录失败', e)
  } finally {
    loading.value = false
  }
}

async function toggleTraceDetail(trace: TraceItem, idx?: number) {
  if (idx === undefined) return
  if (expandedRow.value === idx) {
    expandedRow.value = -1
    expandedTrace.value = null
    return
  }
  try {
    expandedTrace.value = await getTurnDetail(trace.session_id)
    expandedRow.value = idx
  } catch (e) {
    console.error('加载详情失败', e)
  }
}

async function openConfig() {
  try {
    config.value = await getTraceConfig()
    configSaved.value = false
    showConfig.value = true
  } catch (e) {
    console.error('加载配置失败', e)
  }
}

async function saveConfig() {
  configSaving.value = true
  configSaved.value = false
  try {
    await updateTraceConfig(config.value)
    configSaved.value = true
    setTimeout(() => { showConfig.value = false; configSaved.value = false }, 1500)
  } catch (e) {
    console.error('保存配置失败', e)
  } finally {
    configSaving.value = false
  }
}

function onTabChange(tab: 'overview' | 'ranking' | 'users') {
  activeTab.value = tab
  currentPage.value = 1
  expandedRow.value = -1
  expandedTrace.value = null
  if (tab === 'overview') { loadDashboard() }
  if (tab === 'users') { loadInitialUsers() }
  if (tab === 'ranking') { loadRanking() }
}

// 切换到用户 Tab 时自动加载用户列表
async function loadInitialUsers() {
  if (searchResults.value.length === 0) {
    try {
      searchResults.value = await searchUsers('')
    } catch (e) {
      console.error('加载用户列表失败', e)
    }
  }
}

// ── 用户搜索 ──
function debounceSearchUsers() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (userSearchQuery.value.length >= 1) {
      searchResults.value = await searchUsers(userSearchQuery.value)
    } else {
      searchResults.value = []
    }
  }, 300)
}

function onUserSelected() {
  currentPage.value = 1
  expandedRow.value = -1
  expandedTrace.value = null
  if (selectedUserId.value > 0) {
    loadUserTraces()
  } else {
    traces.value = []
    traceTotal.value = 0
  }
}

// ── 格式化 ──
function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatMs(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 's'
  return n + 'ms'
}

function sourceLabel(s: string): string {
  const map: Record<string, string> = { web: '🌐 Web', wechat: '💬 微信', feishu: '🐦 飞书' }
  return map[s] || s
}

function renderMd(text: string): string {
  if (!text) return ''
  return marked.parse(text, { async: false }) as string
}

function trendWidth(tokens: number): number {
  if (!stats.value?.daily_trend?.length) return 0
  const maxTokens = Math.max(...stats.value.daily_trend.map(d => d.tokens), 1)
  return Math.round((tokens / maxTokens) * 100)
}

function modelWidth(tokens: number): number {
  if (!stats.value?.model_usage?.length) return 0
  const maxTokens = Math.max(...stats.value.model_usage.map(m => m.tokens), 1)
  return Math.round((tokens / maxTokens) * 100)
}

const totalPages = computed(() => Math.ceil(traceTotal.value / pageSize) || 1)

// ── 生命周期 ──
onMounted(() => {
  if (tabs.value.length > 0 && !tabs.value.find(t => t.key === activeTab.value)) {
    activeTab.value = tabs.value[0].key
  }
  loadDashboard()
  loadTraces()
  if (activeTab.value === 'ranking') loadRanking()
})

function setTimeFilter(d: number, phrase: string = '') {
  days.value = d
  whenPhrase.value = phrase
}

watch(days, () => {
  currentPage.value = 1
  if (activeTab.value === 'users' && selectedUserId.value > 0) {
    loadUserTraces()
  } else {
    loadDashboard()
    loadTraces()
  }
})
watch(whenPhrase, () => {
  currentPage.value = 1
  if (activeTab.value === 'users' && selectedUserId.value > 0) {
    loadUserTraces()
  } else {
    loadTraces()
  }
})
watch([filterSource, filterStatus], () => {
  currentPage.value = 1
  if (activeTab.value === 'overview') { loadTraces() }
  if (activeTab.value === 'users' && selectedUserId.value > 0) { loadUserTraces() }
})
watch(rankingDays, () => { loadRanking() })
</script>

<template>
  <div class="trace-view">
    <!-- 头部 + Tab -->
    <div class="trace-header">
      <h2>🔍 LLM 可观测性</h2>
      <div class="header-actions">
        <div class="tab-bar" v-if="tabs.length > 1">
          <button v-for="tab in tabs" :key="tab.key"
            :class="{ active: activeTab === tab.key }"
            @click="onTabChange(tab.key)">
            {{ tab.label }}
          </button>
        </div>
        <button v-if="hasManagePerm" class="btn-config" @click="openConfig">⚙️ 采集设置</button>
      </div>
    </div>

    <!-- 时间选择器 -->
    <div class="time-selector" v-if="activeTab !== 'ranking'">
      <button :class="{ active: !whenPhrase && days === 1 }" @click="setTimeFilter(1)">今天</button>
      <button :class="{ active: !whenPhrase && days === 7 }" @click="setTimeFilter(7)">7天</button>
      <button :class="{ active: !whenPhrase && days === 30 }" @click="setTimeFilter(30)">30天</button>
      <button :class="{ active: !whenPhrase && days === 0 }" @click="setTimeFilter(0)">全部</button>
    </div>

    <!-- ========== 概览 Tab ========== -->
    <template v-if="activeTab === 'overview'">

    <!-- 统计卡片 -->
    <div class="stat-cards" v-if="stats">
      <div class="stat-card">
        <div class="stat-label">总调用数</div>
        <div class="stat-value">{{ stats.summary.total_traces.toLocaleString() }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">总 Token</div>
        <div class="stat-value">{{ formatTokens(stats.summary.total_tokens) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">平均延迟</div>
        <div class="stat-value">{{ formatMs(stats.summary.avg_latency_ms) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">成功率</div>
        <div class="stat-value">{{ (stats.summary.success_rate * 100).toFixed(1) }}%</div>
      </div>
    </div>

    <!-- 每日趋势 -->
    <div class="section" v-if="stats?.daily_trend?.length">
      <h3>📈 每日趋势</h3>
      <div class="bar-chart">
        <div v-for="d in stats.daily_trend" :key="d.date" class="bar-item">
          <div class="bar-label">{{ d.date.slice(5) }}</div>
          <div class="bar-track">
            <div class="bar-fill" :style="{ width: trendWidth(d.tokens) + '%' }" :title="formatTokens(d.tokens) + ' tokens'"></div>
          </div>
          <div class="bar-value">{{ formatTokens(d.tokens) }}</div>
        </div>
      </div>
    </div>

    <!-- 三栏统计 -->
    <div class="three-col">
      <div class="col-section" v-if="stats?.model_usage?.length">
        <h3>📊 模型用量</h3>
        <div v-for="m in stats.model_usage" :key="m.model" class="list-item">
          <span class="item-name">{{ m.model }}</span>
          <span class="item-bar"><span class="bar-fill" :style="{ width: modelWidth(m.tokens) + '%' }"></span></span>
          <span class="item-value">{{ formatTokens(m.tokens) }}</span>
        </div>
      </div>
      <div class="col-section" v-if="stats?.source_distribution?.length">
        <h3>📊 来源分布</h3>
        <div v-for="s in stats.source_distribution" :key="s.source" class="list-item">
          <span class="item-name">{{ sourceLabel(s.source) }}</span>
          <span class="item-value">{{ s.traces }} ({{ s.percentage }}%)</span>
        </div>
      </div>
      <div class="col-section" v-if="stats?.tool_usage?.length">
        <h3>📊 工具调用</h3>
        <div v-for="t in stats.tool_usage" :key="t.tool" class="list-item">
          <span class="item-name">{{ t.tool }}</span>
          <span class="item-value">{{ t.calls }}次 / 均{{ formatMs(t.avg_duration_ms) }}</span>
        </div>
      </div>
    </div>

    <!-- Trace 列表 -->
    <div class="section">
      <h3>📋 调用记录</h3>

      <div class="filter-bar">
        <select v-model="filterSource">
          <option value="">全部来源</option>
          <option value="web">🌐 Web</option>
          <option value="wechat">💬 微信</option>
          <option value="feishu">🐦 飞书</option>
        </select>
        <select v-model="filterStatus">
          <option :value="-1">全部状态</option>
          <option :value="1">✅ 成功</option>
          <option :value="0">❌ 失败</option>
        </select>
        <span class="total-count">共 {{ traceTotal }} 条</span>
      </div>

      <div class="trace-table" v-if="traces.length">
        <div v-for="(t, idx) in traces" :key="t.session_id || idx" class="trace-row">
          <div class="trace-summary" @click="toggleTraceDetail(t, idx)">
            <span class="expand-icon">{{ expandedRow === idx ? '▼' : '▶' }}</span>
            <span class="col-time">{{ t.created_at?.slice(5, 16) }}</span>
            <span class="col-source">{{ sourceLabel(t.source) }}</span>
            <span class="col-model">{{ t.model }}</span>
            <span class="col-tokens">{{ formatTokens(t.total_tokens) }}</span>
            <span class="col-latency">{{ formatMs(t.latency_ms) }}</span>
            <span class="col-api-calls" v-if="(t.api_calls || 0) > 1" :title="(t.api_calls || 0) + ' 次 LLM 调用'">{{ t.api_calls }}x</span>
            <span class="col-status" :class="t.status === 1 ? 'success' : 'error'">
              {{ t.status === 1 ? '✅' : '❌' }}
            </span>
            <span class="col-spans" v-if="t.span_count">🔧{{ t.span_count }}</span>
          </div>

          <!-- 展开详情 -->
          <div v-if="expandedRow === idx && expandedTrace" class="trace-detail">
            <div class="detail-meta">
              <span>模型: {{ expandedTrace.model }}</span>
              <span>来源: {{ sourceLabel(expandedTrace.source || '') }}</span>
              <span>API 调用: {{ expandedTrace.api_calls }} 次</span>
              <span>总延迟: {{ formatMs(expandedTrace.total_latency_ms || 0) }}</span>
            </div>
            <div class="token-breakdown">
              <h4>Token 统计</h4>
              <div class="token-grid">
                <div><strong>总计: {{ formatTokens(expandedTrace.total_tokens || 0) }}</strong></div>
                <div>输入: {{ formatTokens((expandedTrace.input_tokens || 0) + (expandedTrace.cache_read_tokens || 0) + (expandedTrace.cache_write_tokens || 0)) }}</div>
                <div>输出: {{ formatTokens(expandedTrace.output_tokens || 0) }}</div>
                <div v-if="expandedTrace.cache_read_tokens" class="token-sub">其中缓存命中: {{ formatTokens(expandedTrace.cache_read_tokens) }}</div>
                <div v-if="expandedTrace.reasoning_tokens" class="token-sub">其中思考: {{ formatTokens(expandedTrace.reasoning_tokens) }}</div>
              </div>
            </div>

            <!-- 工具调用链（已按工具名合并） -->
            <div v-if="expandedTrace.spans?.length" class="spans-section">
              <h4>🔧 工具调用链 ({{ expandedTrace.spans.length }} 种工具)</h4>
              <div v-for="(s, i) in expandedTrace.spans" :key="i" class="span-item">
                <span class="span-name">{{ i + 1 }}. {{ s.tool_name }}</span>
                <span class="span-calls" v-if="(s.calls || 0) > 1">×{{ s.calls }}</span>
                <span class="span-duration">{{ formatMs(s.total_duration_ms || 0) }}</span>
                <span class="span-time" v-if="s.first_at">{{ (s.first_at || '').slice(5, 16) }}</span>
                <span :class="s.status === 1 ? 'success' : 'error'">{{ s.status === 1 ? '✅' : '❌' }}</span>
              </div>
            </div>

            <!-- 会话全部问答轮次（默认折叠，点击展开） -->
            <div v-if="expandedTrace.qna_list?.length" class="text-section">
              <h4>💬 会话问答 ({{ expandedTrace.qna_list.length }})</h4>
              <div v-for="(qa, qi) in expandedTrace.qna_list" :key="qi" class="qna-round">
                <details>
                  <summary>
                    <span class="qna-summary-text">Q{{ qi + 1 }}: {{ qa.question?.slice(0, 60) }}{{ (qa.question || '').length > 60 ? '…' : '' }}</span>
                    <span v-if="qa.created_at" class="qna-summary-time">{{ (qa.created_at || '').slice(5, 16) }}</span>
                  </summary>
                  <div class="text-content markdown-body qa-question" v-html="renderMd(qa.question)"></div>
                  <div class="text-content markdown-body" v-html="renderMd(qa.reply)"></div>
                </details>
              </div>
            </div>

            <!-- 子 trace 列表 -->
            <div v-if="expandedTrace.traces?.length" class="sub-traces">
              <h4>📋 调用详情 ({{ expandedTrace.traces.length }})</h4>
              <div v-for="st in expandedTrace.traces" :key="st.id" class="sub-trace-item">
                <div class="sub-trace-header">
                  <span class="sub-trace-index">#{{ st.turn_index || st.api_call_count }}</span>
                  <span class="sub-trace-time">{{ (st.created_at || '').slice(5, 16) }}</span>
                  <span>{{ st.model }}</span>
                  <span class="sub-trace-tokens">
                    入 {{ formatTokens((st.input_tokens || 0) + (st.cache_read_tokens || 0) + (st.cache_write_tokens || 0)) }} / 出 {{ formatTokens(st.output_tokens || 0) }} / 总 {{ formatTokens(st.total_tokens || 0) }}
                  </span>
                  <span>{{ formatMs(st.latency_ms) }}</span>
                  <span :class="st.status === 1 ? 'success' : 'error'">{{ st.status === 1 ? '✅' : '❌' }}</span>
                </div>
                <div v-if="st.prompt_text || st.completion_text" class="sub-trace-body">
                  <details v-if="st.prompt_text">
                    <summary>💬 提问</summary>
                    <div class="text-content markdown-body" v-html="renderMd(st.prompt_text)" />
                  </details>
                  <details v-if="st.completion_text">
                    <summary>🤖 回复</summary>
                    <div class="text-content markdown-body" v-html="renderMd(st.completion_text)" />
                  </details>
                </div>
              </div>
            </div>

            <!-- 最终问答（无 qna_list 且无子 trace 时显示） -->
            <template v-if="!expandedTrace.qna_list?.length && !expandedTrace.traces?.length">
              <div v-if="expandedTrace.prompt_text" class="text-section">
                <details><summary>💬 用户提问</summary>
                  <div class="text-content markdown-body" v-html="renderMd(expandedTrace.prompt_text)"></div>
                </details>
              </div>
              <div v-if="expandedTrace.completion_text" class="text-section">
                <details><summary>🤖 AI 回复</summary>
                  <div class="text-content markdown-body" v-html="renderMd(expandedTrace.completion_text)"></div>
                </details>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="empty-state">
        <p>暂无调用记录。发送一条消息开始追踪。</p>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="traceTotal > pageSize">
        <button :disabled="currentPage <= 1" @click="currentPage--; loadTraces()">← 上一页</button>
        <span>{{ currentPage }} / {{ totalPages }}</span>
        <button :disabled="currentPage >= totalPages" @click="currentPage++; loadTraces()">下一页 →</button>
      </div>
    </div>
    </template>

    <!-- ========== 排行榜 Tab ========== -->
    <template v-if="activeTab === 'ranking' && auth.hasPerm('trace.view')">
      <div class="time-selector">
        <button :class="{ active: rankingDays === 1 }" @click="rankingDays = 1">今天</button>
        <button :class="{ active: rankingDays === 7 }" @click="rankingDays = 7">7天</button>
        <button :class="{ active: rankingDays === 30 }" @click="rankingDays = 30">30天</button>
        <button :class="{ active: rankingDays === 0 }" @click="rankingDays = 0">全部</button>
      </div>
      <div class="ranking-list" v-if="ranking.length">
        <div v-for="u in ranking" :key="u.user_id" class="ranking-card">
          <div class="ranking-top">
            <span class="rank-badge" :class="{ top3: u.rank <= 3 }">
              {{ u.rank <= 3 ? ['🥇','🥈','🥉'][u.rank-1] : '#' + u.rank }}
            </span>
            <span class="rank-name">{{ u.username }}</span>
            <span class="rank-tokens">{{ formatTokens(u.total_tokens) }} tokens</span>
          </div>
          <div class="ranking-bottom">
            <span>{{ u.api_calls }} 次调用</span>
            <span>活跃 {{ u.active_days }} 天</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">暂无排名数据</div>
    </template>

    <!-- ========== 用户 Tab ========== -->
    <template v-if="activeTab === 'users' && auth.hasPerm('trace.manage')">
      <!-- 用户选择 -->
      <div class="filter-bar">
        <input
          v-model="userSearchQuery"
          placeholder="🔍 搜索用户名..."
          class="search-input"
          @input="debounceSearchUsers"
        />
        <select v-model="selectedUserId" @change="onUserSelected">
          <option :value="0">选择用户...</option>
          <option v-for="u in searchResults" :key="u.id" :value="u.id">{{ u.username }}</option>
        </select>
        <select v-model="filterSource">
          <option value="">全部来源</option>
          <option value="web">🌐 Web</option>
          <option value="wechat">💬 微信</option>
        </select>
        <select v-model="filterStatus">
          <option :value="-1">全部状态</option>
          <option :value="1">✅ 成功</option>
          <option :value="0">❌ 失败</option>
        </select>
        <span class="total-count">共 {{ traceTotal }} 条</span>
      </div>

      <!-- 选中用户后显示记录 -->
      <template v-if="selectedUserId > 0">
        <div class="trace-table" v-if="traces.length">
          <div v-for="(t, idx) in traces" :key="t.session_id || idx" class="trace-row">
            <div class="trace-summary" @click="toggleTraceDetail(t, idx)">
              <span class="expand-icon">{{ expandedRow === idx ? '▼' : '▶' }}</span>
              <span class="col-time">{{ t.created_at?.slice(5, 16) }}</span>
              <span class="col-source">{{ sourceLabel(t.source) }}</span>
              <span class="col-model">{{ t.model }}</span>
              <span class="col-tokens">{{ formatTokens(t.total_tokens) }}</span>
              <span class="col-latency">{{ formatMs(t.latency_ms) }}</span>
              <span class="col-api-calls" v-if="(t.api_calls || 0) > 1" :title="(t.api_calls || 0) + ' 次 LLM 调用'">{{ t.api_calls }}x</span>
              <span class="col-status" :class="t.status === 1 ? 'success' : 'error'">
                {{ t.status === 1 ? '✅' : '❌' }}
              </span>
              <span class="col-spans" v-if="t.span_count">🔧{{ t.span_count }}</span>
            </div>

            <!-- trace 详情展开 -->
            <div v-if="expandedRow === idx && expandedTrace" class="trace-detail">
              <div class="detail-meta">
                <span>模型: {{ expandedTrace.model }}</span>
                <span>来源: {{ sourceLabel(expandedTrace.source || '') }}</span>
                <span>API 调用: {{ expandedTrace.api_calls }} 次</span>
                <span>总延迟: {{ formatMs(expandedTrace.total_latency_ms || 0) }}</span>
              </div>
              <div class="token-breakdown">
                <h4>Token 统计</h4>
                <div class="token-grid">
                  <div><strong>总计: {{ formatTokens(expandedTrace.total_tokens || 0) }}</strong></div>
                  <div>输入: {{ formatTokens((expandedTrace.input_tokens || 0) + (expandedTrace.cache_read_tokens || 0) + (expandedTrace.cache_write_tokens || 0)) }}</div>
                  <div>输出: {{ formatTokens(expandedTrace.output_tokens || 0) }}</div>
                </div>
              </div>

              <!-- 会话全部问答轮次（默认折叠，点击展开） -->
              <div v-if="expandedTrace.qna_list?.length" class="text-section">
                <h4>💬 会话问答 ({{ expandedTrace.qna_list.length }})</h4>
                <div v-for="(qa, qi) in expandedTrace.qna_list" :key="qi" class="qna-round">
                  <details>
                    <summary>
                      <span class="qna-summary-text">Q{{ qi + 1 }}: {{ qa.question?.slice(0, 60) }}{{ (qa.question || '').length > 60 ? '…' : '' }}</span>
                      <span v-if="qa.created_at" class="qna-summary-time">{{ (qa.created_at || '').slice(5, 16) }}</span>
                    </summary>
                    <div class="text-content markdown-body qa-question" v-html="renderMd(qa.question)"></div>
                    <div class="text-content markdown-body" v-html="renderMd(qa.reply)"></div>
                  </details>
                </div>
              </div>
              <!-- 回退：无 conversations 轮次时显示单条问答 -->
              <template v-else>
                <div v-if="t.user_question || expandedTrace.prompt_text" class="text-section">
                  <details><summary>💬 用户提问</summary>
                    <div class="text-content markdown-body" v-html="renderMd(t.user_question || expandedTrace.prompt_text || '')"></div>
                  </details>
                </div>
                <div v-if="t.ai_reply || expandedTrace.completion_text" class="text-section">
                  <details><summary>🤖 AI 回复</summary>
                    <div class="text-content markdown-body" v-html="renderMd(t.ai_reply || expandedTrace.completion_text || '')"></div>
                  </details>
                </div>
              </template>

              <!-- 工具调用链（已按工具名合并） -->
              <div v-if="expandedTrace.spans?.length" class="spans-section">
                <h4>🔧 工具调用链 ({{ expandedTrace.spans.length }} 种工具)</h4>
                <div v-for="(s, i) in expandedTrace.spans" :key="i" class="span-item">
                  <span class="span-name">{{ i + 1 }}. {{ s.tool_name }}</span>
                  <span class="span-calls" v-if="(s.calls || 0) > 1">×{{ s.calls }}</span>
                  <span class="span-duration">{{ formatMs(s.total_duration_ms || 0) }}</span>
                  <span :class="s.status === 1 ? 'success' : 'error'">{{ s.status === 1 ? '✅' : '❌' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="!loading" class="empty-state"><p>该用户暂无记录</p></div>
        <div class="pagination" v-if="traceTotal > pageSize">
          <button :disabled="currentPage <= 1" @click="currentPage--; loadUserTraces()">← 上一页</button>
          <span>{{ currentPage }} / {{ totalPages }}</span>
          <button :disabled="currentPage >= totalPages" @click="currentPage++; loadUserTraces()">下一页 →</button>
        </div>
      </template>
      <div v-else class="empty-state"><p>请先搜索并选择一个用户</p></div>
    </template>

    <!-- 采集设置弹窗 -->
    <div v-if="showConfig" class="modal-overlay" @click.self="showConfig = false">
      <div class="modal-content">
        <h3>⚙️ 采集设置</h3>
        <label class="config-item">
          <span>全量采集模式</span>
          <input type="checkbox" v-model="config.trace_detail_enabled" />
        </label>
        <p class="config-hint">开启后将保存用户提问和 AI 最终回复</p>
        <label class="config-item">
          <span>文本截断长度</span>
          <input type="number" v-model.number="config.trace_max_text_chars" min="1000" max="100000" />
          <span>字符</span>
        </label>
        <label class="config-item">
          <span>数据保留天数</span>
          <input type="number" v-model.number="config.trace_retention_days" min="1" max="365" />
          <span>天</span>
        </label>
        <div class="modal-actions">
          <button @click="showConfig = false">取消</button>
          <button class="primary" @click="saveConfig" :disabled="configSaving">
            {{ configSaving ? '保存中...' : '保存' }}
          </button>
        </div>
        <p v-if="configSaved" class="save-success">✅ 保存成功</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}
.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.trace-header h2 { margin: 0; font-size: 20px; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.tab-bar {
  display: flex;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  overflow: hidden;
}
.tab-bar button {
  padding: 5px 14px;
  border: none;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-size: 13px;
  border-right: 1px solid var(--border-color, #e0e0e0);
}
.tab-bar button:last-child { border-right: none; }
.tab-bar button.active {
  background: var(--primary-color, #409eff);
  color: white;
}
.btn-config {
  padding: 6px 14px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-size: 13px;
}
.btn-config:hover { background: var(--bg-hover, #f5f5f5); }

.time-selector {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.time-selector button {
  padding: 4px 14px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-size: 13px;
}
.time-selector button.active {
  background: var(--primary-color, #409eff);
  color: white;
  border-color: var(--primary-color, #409eff);
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-label { font-size: 12px; color: #888; margin-bottom: 6px; }
.stat-value { font-size: 22px; font-weight: 600; }

.section { margin-bottom: 20px; }
.section h3 { font-size: 15px; margin-bottom: 10px; }

.three-col {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.col-section {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 14px;
}
.col-section h3 { font-size: 14px; margin-bottom: 8px; }

.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.item-name { min-width: 80px; }
.item-bar { flex: 1; height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.item-bar .bar-fill { height: 100%; background: var(--primary-color, #409eff); border-radius: 3px; }
.item-value { font-size: 12px; color: #666; white-space: nowrap; }

.bar-chart { display: flex; flex-direction: column; gap: 4px; }
.bar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.bar-label { min-width: 44px; text-align: right; color: #888; }
.bar-track { flex: 1; height: 16px; background: #f5f5f5; border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--primary-color, #409eff); border-radius: 4px; transition: width 0.3s; }
.bar-value { min-width: 50px; color: #666; }

.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.filter-bar select {
  padding: 4px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  font-size: 13px;
}
.total-count { font-size: 12px; color: #888; margin-left: auto; }

.trace-table { border: 1px solid var(--border-color, #e0e0e0); border-radius: 8px; overflow: hidden; }
.trace-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid #f0f0f0;
}
.trace-summary:hover { background: var(--bg-hover, #f9f9f9); }
.expand-icon { font-size: 10px; color: #999; min-width: 12px; }
.col-time { min-width: 90px; color: #666; }
.col-source { min-width: 70px; }
.col-model { min-width: 80px; font-family: monospace; font-size: 12px; }
.col-tokens { min-width: 50px; text-align: right; }
.col-latency { min-width: 50px; text-align: right; }
.col-api-calls { min-width: 28px; text-align: center; font-size: 11px; color: #409eff; font-weight: 600; }
.col-status { min-width: 24px; text-align: center; }
.col-spans { min-width: 36px; font-size: 12px; color: #888; }
.success { color: #67c23a; }
.error { color: #f56c6c; }

/* 会话多轮问答（默认折叠） */
.qna-round { border: 1px solid #eee; border-radius: 6px; margin-bottom: 6px; overflow: hidden; }
.qna-round details > summary {
  cursor: pointer;
  list-style: none;
  padding: 6px 10px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-detail, #fafafa);
}
.qna-round details > summary::-webkit-details-marker { display: none; }
.qna-round details > summary::before { content: '▶'; font-size: 10px; color: #999; }
.qna-round details[open] > summary::before { content: '▼'; }
.qna-round details[open] > summary { background: var(--brand-light, #eef2ff); }
.qna-summary-text { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-secondary, #444); }
.qna-summary-time { font-size: 11px; color: #999; flex-shrink: 0; }
.qna-round .text-content { padding: 8px 12px; }
.qa-question { color: var(--text-primary); }

.trace-detail {
  padding: 12px 16px;
  background: var(--bg-detail, #fafafa);
  border-bottom: 1px solid #e8e8e8;
  font-size: 13px;
}
.detail-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #666;
}
.token-breakdown h4, .spans-section h4 { font-size: 13px; margin: 8px 0 6px; }
.token-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 16px;
  font-size: 12px;
}
.token-sub { grid-column: 1 / -1; font-size: 11px; color: #888; }
.span-item {
  display: flex;
  gap: 12px;
  padding: 3px 0;
  font-size: 12px;
}
.span-name { min-width: 140px; font-family: monospace; }
.span-calls { min-width: 32px; color: #409eff; font-weight: 600; }
.span-duration { min-width: 60px; text-align: right; }
.span-time { min-width: 80px; color: #888; }
.text-section { margin-top: 8px; }
.text-section details summary { cursor: pointer; font-size: 12px; color: #666; }
.text-content {
  max-height: 400px;
  overflow: auto;
  font-size: 13px;
  background: var(--bg-detail, #fafafa);
  padding: 12px;
  border-radius: 6px;
  line-height: 1.6;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { margin: 8px 0 4px; font-size: 15px; }
.markdown-body :deep(p) { margin: 4px 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 20px; margin: 4px 0; }
.markdown-body :deep(code) { background: #e8e8e8; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.markdown-body :deep(pre) { background: #282c34; color: #abb2bf; padding: 10px; border-radius: 6px; overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; color: inherit; padding: 0; }
.markdown-body :deep(blockquote) { border-left: 3px solid #409eff; margin: 4px 0; padding: 2px 10px; color: #666; }
.markdown-body :deep(a) { color: #409eff; }
.markdown-body :deep(table) { border-collapse: collapse; margin: 6px 0; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid #ddd; padding: 4px 8px; font-size: 12px; }

.empty-state {
  text-align: center;
  padding: 40px;
  color: #999;
  font-size: 14px;
  border: 1px dashed #e0e0e0;
  border-radius: 8px;
}

/* 排名（竖排卡片） */
.ranking-list { display: flex; flex-direction: column; gap: 8px; }
.ranking-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 10px 14px;
}
.ranking-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}
.ranking-bottom {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #888;
  padding-left: 38px;
}
.rank-badge { min-width: 28px; text-align: center; font-weight: 600; font-size: 14px; }
.rank-badge.top3 { font-size: 18px; }
.rank-name { flex: 1; font-weight: 500; font-size: 14px; }
.rank-tokens { font-weight: 600; color: var(--primary-color, #409eff); font-size: 14px; }

/* 搜索 */
.search-input {
  padding: 4px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  font-size: 13px;
  width: 160px;
}

/* 配置弹窗 */
.save-success { font-size: 13px; color: #67c23a; text-align: center; margin-top: 8px; }

/* 子 trace */
.sub-traces { margin-top: 12px; }
.sub-traces h4 { font-size: 13px; margin-bottom: 6px; }
.sub-trace-item {
  background: var(--bg-card, #fff);
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}
.sub-trace-header {
  display: flex;
  gap: 12px;
  font-size: 12px;
  align-items: center;
}
.sub-trace-index { color: #409eff; font-weight: 600; min-width: 20px; }
.sub-trace-time { min-width: 80px; color: #888; }
.sub-trace-tokens { color: #666; }
.sub-trace-body { margin-top: 6px; }
.sub-trace-body details { margin: 3px 0; }
.sub-trace-body details summary { font-size: 12px; cursor: pointer; color: #666; }

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  font-size: 13px;
}
.pagination button {
  padding: 4px 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  cursor: pointer;
}
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: var(--bg-card, #fff);
  border-radius: 10px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
}
.modal-content h3 { margin: 0 0 16px; font-size: 16px; }
.config-item {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  font-size: 14px;
}
.config-item input[type="number"] {
  width: 80px;
  padding: 4px 8px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
}
.config-hint { font-size: 12px; color: #999; margin: -8px 0 12px 0; }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.modal-actions button {
  padding: 6px 18px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.modal-actions button.primary {
  background: var(--primary-color, #409eff);
  color: white;
  border-color: var(--primary-color, #409eff);
}

@media (max-width: 768px) {
  .stat-cards { grid-template-columns: repeat(3, 1fr); }
  .three-col { grid-template-columns: 1fr; }
  .token-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
