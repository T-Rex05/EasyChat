<template>
  <div class="community-page">
    <!-- 顶部操作栏 -->
    <div class="page-header">
      <div class="header-left">
        <h1>社区管理</h1>
        <span class="subtitle">GraphRAG 社区检测与报告浏览</span>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="refreshData" :disabled="loading && !generating">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          刷新
        </button>
        <button class="btn btn-primary" @click="showDetectDialog = true" :disabled="loading || !hasGraphManage">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/><circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/></svg>
          社区检测
        </button>
        <button v-if="!generating" class="btn btn-accent" @click="generateReports" :disabled="loading || !hasGraphManage || communities.length === 0">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          生成报告
        </button>
        <button v-else class="btn btn-accent" @click="cancelGeneration" title="停止轮询（后台任务继续运行）">
          停止轮询
        </button>
      </div>
    </div>

    <!-- 生成进度条 -->
    <div v-if="generating" class="gen-progress">
      <div class="gen-progress-header">
        <span class="gen-progress-label">
          <span class="gen-spinner"></span>
          正在生成报告…
        </span>
        <span class="gen-progress-stats">
          {{ genProgress.generated }} 成功 / {{ genProgress.failed }} 失败 / {{ genProgress.total }} 总计
        </span>
      </div>
      <div class="gen-progress-bar">
        <div
          class="gen-progress-fill"
          :style="{ width: (genProgress.total ? (genProgress.current / genProgress.total * 100) : 0) + '%' }"
        ></div>
      </div>
      <div class="gen-progress-detail">
        已处理 {{ genProgress.current }} / {{ genProgress.total }}
        <span v-if="genProgress.total > 0">({{ Math.round(genProgress.current / genProgress.total * 100) }}%)</span>
      </div>
    </div>

    <!-- 智能搜索 -->
    <div class="search-section">
      <div class="search-bar">
        <input
          v-model="searchQuery"
          placeholder="输入问题，测试 GraphRAG 智能检索（如：三国演义的核心主题？）"
          @keyup.enter="doSmartSearch"
          class="search-input"
        />
        <select v-model="searchMode" class="search-mode">
          <option value="smart">智能路由</option>
          <option value="local">Local 局部</option>
          <option value="global">Global 全局</option>
          <option value="drift">DRIFT 混合</option>
        </select>
        <button class="btn btn-primary" @click="doSmartSearch" :disabled="!searchQuery.trim() || searching">
          {{ searching ? '搜索中...' : '搜索' }}
        </button>
      </div>
      <!-- 搜索结果 -->
      <div v-if="searchResult" class="search-result">
        <div class="result-header">
          <span class="result-type" :class="searchResult.query_type">
            {{ modeLabel(searchResult.query_type) }}
          </span>
          <span v-if="searchResult.reports_used" class="result-meta">
            使用 {{ searchResult.reports_used }} 个社区报告
          </span>
        </div>
        <div class="result-answer" v-if="searchResult.answer">
          {{ searchResult.answer }}
        </div>
        <div v-if="searchResult.sources && searchResult.sources.length" class="result-sources">
          来源：{{ searchResult.sources.join('、') }}
        </div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="tabs">
      <button :class="{ active: activeTab === 'reports' }" @click="activeTab = 'reports'">
        社区报告 ({{ reports.length }})
      </button>
      <button :class="{ active: activeTab === 'communities' }" @click="activeTab = 'communities'">
        社区列表 ({{ communities.length }})
      </button>
    </div>

    <!-- 层级筛选 -->
    <div class="level-filter">
      <label>层级：</label>
      <select v-model="levelFilter" @change="refreshData">
        <option :value="null">全部</option>
        <option v-for="l in levels" :key="l" :value="l">Level {{ l }}</option>
      </select>
    </div>

    <!-- 报告列表 -->
    <div v-if="activeTab === 'reports'" class="report-grid">
      <div v-for="report in reports" :key="report.community_id" class="report-card" @click="showReportDetail(report)">
        <div class="card-header">
          <span class="card-title">{{ report.title }}</span>
          <span class="card-rating" :class="'rating-' + Math.min(report.rating, 10)">
            {{ report.rating }}
          </span>
        </div>
        <div class="card-level">Level {{ report.level }}</div>
        <div class="card-summary">{{ report.summary }}</div>
        <div class="card-findings" v-if="report.findings && report.findings.length">
          <div v-for="(f, i) in report.findings.slice(0, 3)" :key="i" class="finding-item">
            {{ f }}
          </div>
        </div>
        <div class="card-entities">
          <span v-for="e in report.top_entities.slice(0, 5)" :key="e" class="entity-tag">{{ e }}</span>
        </div>
      </div>
      <div v-if="reports.length === 0" class="empty-state">
        <p>暂无社区报告</p>
        <p class="hint">请先运行「社区检测」，再点击「生成报告」</p>
      </div>
    </div>

    <!-- 社区列表 -->
    <div v-if="activeTab === 'communities'" class="community-list">
      <table class="data-table">
        <thead>
          <tr>
            <th>社区 ID</th>
            <th>层级</th>
            <th>实体数</th>
            <th>关系数</th>
            <th>父社区</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in communities" :key="c.id">
            <td><code>{{ c.id }}</code></td>
            <td><span class="level-badge">L{{ c.level }}</span></td>
            <td>{{ c.entity_count }}</td>
            <td>{{ c.relationship_count }}</td>
            <td>{{ c.parent_id || '-' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="communities.length === 0" class="empty-state">
        <p>暂无社区数据</p>
      </div>
    </div>

    <!-- 报告详情弹窗 -->
    <div v-if="detailReport" class="modal-overlay" @click.self="detailReport = null">
      <div class="modal-content report-detail">
        <div class="modal-header">
          <h2>{{ detailReport.title }}</h2>
          <button class="close-btn" @click="detailReport = null">&times;</button>
        </div>
        <div class="modal-body">
          <div class="detail-meta">
            <span class="level-badge">Level {{ detailReport.level }}</span>
            <span class="card-rating" :class="'rating-' + Math.min(detailReport.rating, 10)">
              评分 {{ detailReport.rating }}
            </span>
            <span>{{ detailReport.entity_count }} 实体 / {{ detailReport.relationship_count }} 关系</span>
          </div>
          <div class="detail-section">
            <h3>摘要</h3>
            <p>{{ detailReport.summary }}</p>
          </div>
          <div class="detail-section" v-if="detailReport.full_content">
            <h3>完整报告</h3>
            <p class="full-content">{{ detailReport.full_content }}</p>
          </div>
          <div class="detail-section" v-if="detailReport.findings && detailReport.findings.length">
            <h3>关键发现</h3>
            <ul>
              <li v-for="(f, i) in detailReport.findings" :key="i">{{ f }}</li>
            </ul>
          </div>
          <div class="detail-section" v-if="detailReport.top_entities && detailReport.top_entities.length">
            <h3>核心实体</h3>
            <div class="entity-tags">
              <span v-for="e in detailReport.top_entities" :key="e" class="entity-tag">{{ e }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 社区检测弹窗 -->
    <div v-if="showDetectDialog" class="modal-overlay" @click.self="showDetectDialog = false">
      <div class="modal-content detect-dialog">
        <div class="modal-header">
          <h2>社区检测</h2>
          <button class="close-btn" @click="showDetectDialog = false">&times;</button>
        </div>
        <div class="modal-body">
          <p>从 Neo4j 读取全部节点和关系，使用 Louvain 算法进行社区划分。</p>
          <p class="hint">检测完成后，需要再点击「生成报告」来生成 LLM 摘要。</p>
          <div v-if="detectResult" class="detect-result">
            <p>检测到 <strong>{{ detectResult.communities }}</strong> 个社区，
              <strong>{{ detectResult.levels }}</strong> 个层级，
              覆盖 <strong>{{ detectResult.entities_covered }}</strong> 个实体</p>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-secondary" @click="showDetectDialog = false">关闭</button>
            <button class="btn btn-primary" @click="runDetect" :disabled="detecting">
              {{ detecting ? '检测中...' : '开始检测' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  detectCommunities,
  generateReports as apiGenerateReports,
  getReportProgress,
  listCommunities,
  listReports,
  getReportDetail,
  smartSearch,
  type Community,
  type CommunityReport,
  type CommunityReportDetail,
  type SmartSearchResult,
} from '@/api/graphrag'

const authStore = useAuthStore()

const loading = ref(false)
const searching = ref(false)
const detecting = ref(false)
const activeTab = ref<'reports' | 'communities'>('reports')
const levelFilter = ref<number | null>(null)

const communities = ref<Community[]>([])
const reports = ref<CommunityReport[]>([])
const searchQuery = ref('')
const searchMode = ref('smart')
const searchResult = ref<SmartSearchResult | null>(null)

const showDetectDialog = ref(false)
const detectResult = ref<any>(null)
const detailReport = ref<CommunityReportDetail | null>(null)

// ── 报告生成进度 ──
const generating = ref(false)
const genProgress = ref({ status: '', total: 0, generated: 0, failed: 0, current: 0 })
let pollTimer: ReturnType<typeof setInterval> | null = null

const hasGraphManage = computed(() => {
  const perms = authStore.permissions
  const role = authStore.userRole
  return role === 'super_admin' || role === 'admin'
    || perms.includes('graph.manage')
})

const levels = computed(() => {
  const set = new Set(communities.value.map(c => c.level))
  return Array.from(set).sort()
})

function modeLabel(type: string) {
  const map: Record<string, string> = {
    local: 'Local 局部检索',
    global: 'Global 全局汇总',
    drift: 'DRIFT 混合检索',
  }
  return map[type] || type
}

async function refreshData() {
  loading.value = true
  try {
    const [commRes, repRes] = await Promise.all([
      listCommunities(levelFilter.value),
      listReports(levelFilter.value),
    ])
    communities.value = commRes.data.communities || []
    reports.value = repRes.data.reports || []
  } catch (e) {
    console.error('Failed to load community data:', e)
  } finally {
    loading.value = false
  }
}

async function runDetect() {
  detecting.value = true
  detectResult.value = null
  try {
    const res = await detectCommunities()
    detectResult.value = res.data
    await refreshData()
  } catch (e) {
    console.error('Community detection failed:', e)
    alert('社区检测失败: ' + ((e as any).response?.data?.detail || (e instanceof Error ? e.message : '未知错误')))
  } finally {
    detecting.value = false
  }
}

async function doGenerateReports() {
  generating.value = true
  genProgress.value = { status: 'starting', total: 0, generated: 0, failed: 0, current: 0 }

  try {
    const res = await apiGenerateReports()
    const taskId = res.data?.task_id
    if (!taskId) {
      alert('报告生成启动失败: 未返回任务 ID')
      generating.value = false
      return
    }

    // 持久化 taskId，切换页面后可恢复
    localStorage.setItem('community_report_task_id', taskId)
    startPolling(taskId)
  } catch (e) {
    console.error('Report generation failed:', e)
    const detail = (e as any).response?.data?.detail
    alert('报告生成失败: ' + (detail || (e instanceof Error ? e.message : '未知错误')))
    generating.value = false
  }
}

function startPolling(taskId: string) {
  // 清除已有轮询
  if (pollTimer) clearInterval(pollTimer)
  generating.value = true

  pollTimer = setInterval(async () => {
    try {
      const prog = await getReportProgress(taskId)
      genProgress.value = prog.data

      // 刷新报告列表（每轮更新）
      await refreshDataSilent()

      if (prog.data.status === 'completed' || prog.data.status === 'failed') {
        stopPolling()
        if (prog.data.status === 'failed') {
          alert('报告生成失败: ' + (prog.data.error || '未知错误'))
        }
      }
    } catch (e) {
      // 任务可能已过期（完成一段时间后自动清除）
      console.error('Progress query failed:', e)
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  generating.value = false
  localStorage.removeItem('community_report_task_id')
}

/** 仅暂停定时器，不清 localStorage（用于组件卸载，刷新后可恢复） */
function pausePolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  generating.value = false
}

/** 恢复之前未完成的轮询 */
function restorePolling() {
  const savedTaskId = localStorage.getItem('community_report_task_id')
  if (!savedTaskId) return

  // 尝试查询进度，如果任务还在运行则恢复轮询
  getReportProgress(savedTaskId).then(prog => {
    if (prog.data.status === 'running' || prog.data.status === 'starting') {
      genProgress.value = prog.data
      startPolling(savedTaskId)
    } else {
      // 已完成或失败，清除
      localStorage.removeItem('community_report_task_id')
    }
  }).catch(() => {
    // 任务不存在，清除
    localStorage.removeItem('community_report_task_id')
  })
}

async function refreshDataSilent() {
  // 静默刷新（不设置 loading，避免进度条闪烁）
  try {
    const [commRes, repRes] = await Promise.all([
      listCommunities(levelFilter.value),
      listReports(levelFilter.value),
    ])
    communities.value = commRes.data.communities || []
    reports.value = repRes.data.reports || []
  } catch (e) {
    // ignore
  }
}

async function generateReports() {
  if (confirm('将为所有社区生成 LLM 摘要报告，可能需要几分钟。生成过程中可以刷新页面查看已完成的报告。确定？')) {
    await doGenerateReports()
  }
}

async function cancelGeneration() {
  stopPolling()
  await refreshData()
}

async function doSmartSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searchResult.value = null
  try {
    const res = await smartSearch(searchQuery.value, searchMode.value)
    searchResult.value = res.data
  } catch (e) {
    console.error('Smart search failed:', e)
    alert('搜索失败: ' + ((e as any).response?.data?.detail || (e instanceof Error ? e.message : '未知错误')))
  } finally {
    searching.value = false
  }
}

async function showReportDetail(report: CommunityReport) {
  try {
    const res = await getReportDetail(report.community_id)
    detailReport.value = res.data
  } catch (e) {
    console.error('Failed to load report detail:', e)
  }
}

onMounted(() => {
  refreshData()
  restorePolling()
})

onUnmounted(() => {
  pausePolling()  // 仅停定时器，保留 localStorage 中的 task_id 以便刷新后恢复
})
</script>

<style scoped>
.community-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ── 生成进度条 ── */
.gen-progress {
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 20px;
}

.gen-progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.gen-progress-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--brand);
}

.gen-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--brand);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.gen-progress-stats {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.gen-progress-bar {
  height: 6px;
  background: var(--bg-hover);
  border-radius: 3px;
  overflow: hidden;
}

.gen-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--brand), #6b83f5);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.gen-progress-detail {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn svg {
  width: 16px;
  height: 16px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-primary {
  background: var(--brand);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-accent {
  background: #10b981;
  color: #fff;
}

.btn-accent:hover:not(:disabled) {
  opacity: 0.9;
}

/* Search section */
.search-section {
  margin-bottom: 24px;
}

.search-bar {
  display: flex;
  gap: 8px;
}

.search-input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.search-input:focus {
  outline: none;
  border-color: var(--brand);
}

.search-mode {
  padding: 10px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-width: 120px;
}

.search-result {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.result-type {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.result-type.local { background: #dbeafe; color: #1d4ed8; }
.result-type.global { background: #fef3c7; color: #92400e; }
.result-type.drift { background: #ede9fe; color: #5b21b6; }

.result-meta {
  font-size: 12px;
  color: var(--text-tertiary);
}

.result-answer {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}

.result-sources {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Tabs */
.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-primary);
}

.tabs button {
  padding: 10px 20px;
  border: none;
  background: none;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tabs button.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 500;
}

.level-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.level-filter select {
  padding: 6px 10px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Report grid */
.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.report-card {
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.report-card:hover {
  border-color: var(--brand);
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-rating {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}

.card-rating.rating-9, .card-rating.rating-10 { background: #fef3c7; color: #92400e; }
.card-rating.rating-7, .card-rating.rating-8 { background: #dbeafe; color: #1d4ed8; }
.card-rating.rating-5, .card-rating.rating-6 { background: #e5e7eb; color: #374151; }

.card-level {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.card-summary {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.card-findings {
  margin-bottom: 10px;
}

.finding-item {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 3px 0;
  padding-left: 12px;
  position: relative;
}

.finding-item::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--brand);
}

.card-entities {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.entity-tag {
  padding: 2px 8px;
  background: var(--bg-hover);
  border-radius: 10px;
  font-size: 11px;
  color: var(--text-secondary);
}

/* Community table */
.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th, .data-table td {
  padding: 10px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-primary);
  font-size: 13px;
}

.data-table th {
  font-weight: 600;
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.data-table td {
  color: var(--text-secondary);
}

.level-badge {
  padding: 2px 8px;
  background: var(--brand-light);
  color: var(--brand);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-tertiary);
}

.empty-state .hint {
  font-size: 13px;
  margin-top: 8px;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border-radius: 12px;
  max-width: 720px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 4px 8px;
}

.modal-body {
  padding: 20px 24px;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.detail-section p {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.detail-section ul {
  padding-left: 20px;
}

.detail-section li {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.full-content {
  white-space: pre-wrap;
}

.entity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detect-dialog .modal-content {
  max-width: 480px;
}

.detect-result {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
</style>
