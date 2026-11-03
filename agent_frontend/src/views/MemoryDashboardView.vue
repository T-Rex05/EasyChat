<template>
  <div class="page-container memory-dashboard">
    <!-- Header -->
    <header class="dashboard-header">
      <div>
        <h2 class="dashboard-title">记忆监控</h2>
        <p class="dashboard-subtitle">系统健康状态与数据覆盖率总览</p>
      </div>
      <button class="btn btn-secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="14" :class="{ spinning: loading }" />
        刷新
      </button>
    </header>

    <!-- Skeleton Loading -->
    <div v-if="loading && !data" class="skeleton-grid">
      <div v-for="i in 4" :key="i" class="skeleton-card">
        <div class="skeleton-line w60"></div>
        <div class="skeleton-line w40 tall"></div>
        <div class="skeleton-line w80"></div>
      </div>
    </div>

    <template v-else-if="data">
      <!-- KPI Row -->
      <section class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-icon total">
            <Database :size="18" />
          </div>
          <div class="kpi-body">
            <span class="kpi-label">活跃记忆总数</span>
            <span class="kpi-value">{{ data.memory_counts.grand_total }}</span>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon episodic">
            <Clock :size="18" />
          </div>
          <div class="kpi-body">
            <span class="kpi-label">情景记忆</span>
            <span class="kpi-value">{{ data.memory_counts.episodic.active }}</span>
            <span class="kpi-hint">30 天 TTL</span>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon semantic">
            <Gem :size="18" />
          </div>
          <div class="kpi-body">
            <span class="kpi-label">语义记忆</span>
            <span class="kpi-value">{{ data.memory_counts.semantic.active }}</span>
            <span class="kpi-hint">永久知识</span>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon outbox" :class="{ warn: (data.outbox_health.dead || data.outbox_health.failed || 0) > 0 }">
            <Inbox :size="18" />
          </div>
          <div class="kpi-body">
            <span class="kpi-label">Outbox 待处理</span>
            <span class="kpi-value">{{ data.outbox_health.pending }}</span>
            <span class="kpi-hint" v-if="(data.outbox_health.dead || data.outbox_health.failed || 0) > 0">
              {{ data.outbox_health.dead || data.outbox_health.failed }} 条死信
            </span>
          </div>
        </div>
      </section>

      <!-- Main Grid: 2 columns -->
      <section class="main-grid">
        <!-- 7-day trend chart -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <TrendingUp :size="15" /> 近 7 天版本写入
            </span>
          </div>
          <div class="card-body trend-body">
            <template v-if="data.version_stats.last_7_days_trend?.length">
              <svg class="trend-chart" viewBox="0 0 280 120" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="var(--brand)" stop-opacity="0.25" />
                    <stop offset="100%" stop-color="var(--brand)" stop-opacity="0.02" />
                  </linearGradient>
                </defs>
                <!-- area -->
                <path :d="trendAreaPath" fill="url(#trendGrad)" />
                <!-- line -->
                <path :d="trendLinePath" fill="none" stroke="var(--brand)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                <!-- dots -->
                <circle
                  v-for="(pt, i) in trendPoints"
                  :key="i"
                  :cx="pt.x" :cy="pt.y" r="3"
                  fill="var(--bg-card)" stroke="var(--brand)" stroke-width="2"
                >
                  <title>{{ formatTrendDate(data.version_stats.last_7_days_trend[i].date) }}: {{ data.version_stats.last_7_days_trend[i].count }} 次</title>
                </circle>
              </svg>
              <div class="trend-labels">
                <span
                  v-for="item in data.version_stats.last_7_days_trend"
                  :key="item.date"
                  class="trend-date"
                >{{ formatTrendDate(item.date) }}</span>
              </div>
            </template>
            <div v-else class="empty-state">
              <BarChart2 :size="24" />
              <span>暂无趋势数据</span>
            </div>
          </div>
        </div>

        <!-- Outbox status -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <Mail :size="15" /> Outbox 队列
            </span>
            <button
              v-if="(data.outbox_health.dead || 0) > 0"
              class="btn-retry-all"
              :disabled="retryingAll"
              @click="handleRetryAll"
            >
              {{ retryingAll ? '重试中...' : `重试全部死信 (${data.outbox_health.dead})` }}
            </button>
          </div>
          <div class="card-body">
            <div class="outbox-grid outbox-grid-5">
              <div class="outbox-cell">
                <div class="outbox-num pending">{{ data.outbox_health.pending }}</div>
                <div class="outbox-label">待处理</div>
              </div>
              <div class="outbox-cell">
                <div class="outbox-num processing">{{ data.outbox_health.processing }}</div>
                <div class="outbox-label">处理中</div>
              </div>
              <div class="outbox-cell">
                <div class="outbox-num processed">{{ data.outbox_health.processed || data.outbox_health.completed }}</div>
                <div class="outbox-label">已处理</div>
              </div>
              <div class="outbox-cell" :class="{ 'is-dead': (data.outbox_health.dead || 0) > 0 }">
                <div class="outbox-num dead">{{ data.outbox_health.dead || data.outbox_health.failed || 0 }}</div>
                <div class="outbox-label">死信</div>
              </div>
            </div>
            <!-- outbox mini bar -->
            <div class="outbox-bar">
              <div
                class="outbox-seg pending"
                :style="{ width: outboxPct('pending') + '%' }"
                title="待处理"
              ></div>
              <div
                class="outbox-seg processing"
                :style="{ width: outboxPct('processing') + '%' }"
                title="处理中"
              ></div>
              <div
                class="outbox-seg processed"
                :style="{ width: outboxPct('processed') + '%' }"
                title="已处理"
              ></div>
              <div
                class="outbox-seg dead"
                :style="{ width: outboxPct('dead') + '%' }"
                title="死信"
              ></div>
            </div>

            <!-- Dead letter detail panel -->
            <div v-if="(data.outbox_health.dead || 0) > 0" class="dead-letter-panel">
              <div class="dead-letter-header">
                <span class="dead-letter-title">🪦 死信队列详情</span>
                <button class="btn-show-all" @click="showAllDead = !showAllDead">
                  {{ showAllDead ? '收起' : '展开详情' }}
                </button>
              </div>
              <div v-if="showAllDead" class="dead-letter-list">
                <div v-if="deadEvents.length === 0" class="dead-letter-loading">
                  加载中...
                </div>
                <div
                  v-for="evt in deadEvents"
                  :key="evt.id"
                  class="dead-letter-item"
                >
                  <div class="dead-letter-main">
                    <span class="dead-letter-target" :class="evt.target">{{ evt.target }}</span>
                    <span class="dead-letter-type">{{ evt.event_type }}</span>
                    <span class="dead-letter-mem">mem#{{ evt.memory_id }}</span>
                    <span class="dead-letter-attempts">重试 {{ evt.attempts }} 次</span>
                    <span class="dead-letter-time">{{ formatTime(evt.created_at) }}</span>
                    <button
                      class="btn-retry-single"
                      :disabled="retryingIds.has(evt.id)"
                      @click="handleRetrySingle(evt.id)"
                    >
                      {{ retryingIds.has(evt.id) ? '...' : '重试' }}
                    </button>
                  </div>
                  <div v-if="evt.last_error" class="dead-letter-error">
                    {{ evt.last_error }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Second Grid: coverage + health -->
      <section class="main-grid">
        <!-- Coverage overview -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <Cpu :size="15" /> 覆盖率
            </span>
          </div>
          <div class="card-body">
            <div class="coverage-group" v-for="(entries, groupLabel) in coverageGroups" :key="groupLabel">
              <div class="coverage-group-label">{{ groupLabel }}</div>
              <div
                v-for="item in entries"
                :key="item.layer"
                class="coverage-row"
              >
                <span class="coverage-name">{{ item.label }}</span>
                <div class="coverage-bar-track">
                  <div
                    class="coverage-bar-fill"
                    :class="coverageColorClass(item.pct)"
                    :style="{ width: item.pct + '%' }"
                  ></div>
                </div>
                <span class="coverage-pct">{{ item.pct }}%</span>
                <span class="coverage-detail">{{ item.done }}/{{ item.total }}</span>
              </div>
            </div>
            <div v-if="Object.keys(coverageGroups).length === 0" class="empty-state">
              <BarChart2 :size="24" />
              <span>暂无覆盖率数据</span>
            </div>
          </div>
        </div>

        <!-- Health: TTL + conflicts -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <Activity :size="15" /> 健康监控
            </span>
          </div>
          <div class="card-body">
            <!-- TTL expiry -->
            <div class="health-section">
              <div class="health-section-title">
                <Timer :size="13" /> 情景记忆到期
              </div>
              <div class="ttl-grid">
                <div class="ttl-cell urgent">
                  <span class="ttl-num">{{ data.ttl_expiry.within_1_day }}</span>
                  <span class="ttl-label">24h 内</span>
                </div>
                <div class="ttl-cell warn">
                  <span class="ttl-num">{{ data.ttl_expiry.within_7_days }}</span>
                  <span class="ttl-label">7 天内</span>
                </div>
                <div class="ttl-cell info">
                  <span class="ttl-num">{{ data.ttl_expiry.within_30_days }}</span>
                  <span class="ttl-label">30 天内</span>
                </div>
                <div class="ttl-cell safe">
                  <span class="ttl-num">{{ data.ttl_expiry.after_30_days }}</span>
                  <span class="ttl-label">30 天后</span>
                </div>
              </div>
            </div>

            <!-- Conflicts -->
            <div class="health-section" v-if="data.kg_store_stats?.available">
              <div class="health-section-title">
                <AlertTriangle :size="13" /> 矛盾检测
              </div>
              <div v-if="data.kg_store_stats.conflicts?.length" class="conflict-list">
                <div
                  v-for="(c, i) in data.kg_store_stats.conflicts"
                  :key="i"
                  class="conflict-item"
                >
                  <span class="badge badge-warning">{{ conflictLabel(c.type) }}</span>
                  <span class="conflict-person">{{ c.person }}</span>
                  <span class="conflict-companies">{{ c.companies?.join(', ') }}</span>
                </div>
              </div>
              <div v-else class="health-ok">
                <CheckCircle2 :size="14" /> 未检测到矛盾
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Detail Grid: KGStore + encryption + versions + consolidation -->
      <section class="detail-grid">
        <!-- KGStore -->
        <div class="card" v-if="data.kg_store_stats?.available">
          <div class="card-header">
            <span class="card-title">
              <GitBranch :size="15" /> KGStore
            </span>
          </div>
          <div class="card-body">
            <div class="stat-list">
              <div class="stat-row">
                <span class="stat-label">实体</span>
                <span class="stat-val">{{ data.kg_store_stats.entity_count }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">关系</span>
                <span class="stat-val">{{ data.kg_store_stats.relation_count }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">平均置信度</span>
                <span class="stat-val">{{ data.kg_store_stats.quality?.avg_confidence ?? '-' }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">归档实体</span>
                <span class="stat-val">{{ data.kg_store_stats.archive?.archived_count ?? 0 }}</span>
              </div>
              <div class="stat-row" v-if="data.kg_store_stats.quality?.low_confidence_count">
                <span class="stat-label">低置信度</span>
                <span class="stat-val warn">{{ data.kg_store_stats.quality.low_confidence_count }}</span>
              </div>
              <div class="stat-row" v-if="data.kg_store_stats.quality?.orphan_entity_count">
                <span class="stat-label">孤立实体</span>
                <span class="stat-val warn">{{ data.kg_store_stats.quality.orphan_entity_count }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Encryption -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <Shield :size="15" /> 加密覆盖
            </span>
          </div>
          <div class="card-body">
            <div
              v-for="(stats, layer) in data.encryption_stats"
              :key="layer"
              class="mini-coverage-row"
            >
              <span class="mini-label">{{ layerLabel(layer as string) }}</span>
              <div class="mini-bar-track">
                <div
                  class="mini-bar-fill"
                  :class="coverageColorClass(stats.coverage)"
                  :style="{ width: stats.coverage + '%' }"
                ></div>
              </div>
              <span class="mini-pct">{{ stats.coverage }}%</span>
            </div>
            <div v-if="!data.encryption_stats || Object.keys(data.encryption_stats).length === 0" class="empty-state sm">
              <span>暂无数据</span>
            </div>
          </div>
        </div>

        <!-- Version stats -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <History :size="15" /> 版本历史
            </span>
          </div>
          <div class="card-body">
            <div class="stat-list">
              <div class="stat-row">
                <span class="stat-label">有版本的记忆</span>
                <span class="stat-val">{{ data.version_stats.memories_with_versions }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">平均版本数</span>
                <span class="stat-val">{{ data.version_stats.avg_versions_per_memory }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总快照数</span>
                <span class="stat-val">{{ data.consolidation_stats.total_versions }}</span>
              </div>
            </div>
            <!-- consolidation reasons -->
            <div v-if="data.consolidation_stats.by_change_reason && Object.keys(data.consolidation_stats.by_change_reason).length" class="tag-cloud">
              <span
                v-for="(count, reason) in data.consolidation_stats.by_change_reason"
                :key="reason"
                class="tag-item"
              >
                {{ changeReasonLabel(reason as string) }}
                <strong>{{ count }}</strong>
              </span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  RefreshCw, Database, Clock, Gem, Inbox, TrendingUp, Mail,
  Cpu, Activity, Timer, AlertTriangle, CheckCircle2,
  GitBranch, Shield, History, BarChart2
} from '@lucide/vue'
import { getMemoryDashboard, listOutboxEvents, retryOutboxEvents, type MemoryDashboard, type OutboxEvent } from '../api/memoryItems'

const loading = ref(false)
const data = ref<MemoryDashboard | null>(null)

async function refresh() {
  loading.value = true
  try {
    data.value = await getMemoryDashboard()
  } catch (e) {
    console.error('Failed to load dashboard:', e)
  } finally {
    loading.value = false
  }
}

// ========== Trend chart paths ==========
const trendPoints = computed(() => {
  const trend = data.value?.version_stats?.last_7_days_trend
  if (!trend?.length) return []
  const maxCount = Math.max(...trend.map(i => i.count), 1)
  const w = 280, h = 100, pad = 10
  return trend.map((item, i) => ({
    x: pad + (i / Math.max(trend.length - 1, 1)) * (w - pad * 2),
    y: h - pad - (item.count / maxCount) * (h - pad * 2)
  }))
})

const trendLinePath = computed(() => {
  const pts = trendPoints.value
  if (!pts.length) return ''
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
})

const trendAreaPath = computed(() => {
  const pts = trendPoints.value
  if (!pts.length) return ''
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  return `${line} L${pts[pts.length - 1].x},110 L${pts[0].x},110 Z`
})

// ========== Outbox ==========
function outboxPct(status: string): number {
  const oh = data.value?.outbox_health
  if (!oh) return 0
  // 兼容新旧字段名
  const processed = (oh as any).processed ?? oh.completed ?? 0
  const dead = (oh as any).dead ?? oh.failed ?? 0
  const total = (oh.pending || 0) + (oh.processing || 0) + processed + dead
  if (!total) return 0
  const val = status === 'processed' ? processed : status === 'dead' ? dead : ((oh as any)[status] || 0)
  return Math.round(val / total * 100)
}

// ========== Dead Letter Queue ==========
const showAllDead = ref(false)
const deadEvents = ref<OutboxEvent[]>([])
const retryingAll = ref(false)
const retryingIds = ref(new Set<number>())

async function loadDeadEvents() {
  try {
    const resp = await listOutboxEvents({ status: 'dead', limit: 20 })
    deadEvents.value = resp.events || []
  } catch (e) {
    console.warn('Failed to load dead events:', e)
  }
}

async function handleRetryAll() {
  if (retryingAll.value) return
  retryingAll.value = true
  try {
    const resp = await retryOutboxEvents({ retry_all: true })
    console.log(`Retried ${resp.retried} dead events`)
    // 刷新看板数据
    await refresh()
    deadEvents.value = []
  } catch (e) {
    console.error('Failed to retry all:', e)
  } finally {
    retryingAll.value = false
  }
}

async function handleRetrySingle(id: number) {
  if (retryingIds.value.has(id)) return
  retryingIds.value.add(id)
  try {
    await retryOutboxEvents({ event_ids: [id] })
    // 从列表中移除
    deadEvents.value = deadEvents.value.filter(e => e.id !== id)
    await refresh()
  } catch (e) {
    console.error('Failed to retry event:', e)
  } finally {
    retryingIds.value.delete(id)
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 监听展开状态，加载死信详情
watch(showAllDead, (val) => {
  if (val && deadEvents.value.length === 0) {
    loadDeadEvents()
  }
})

// ========== Coverage ==========
interface CoverageEntry { layer: string; label: string; pct: number; done: number; total: number }

const coverageGroups = computed<Record<string, CoverageEntry[]>>(() => {
  const groups: Record<string, CoverageEntry[]> = {}
  const vc = data.value?.vector_coverage
  const gc = data.value?.graph_coverage
  if (vc) {
    groups['向量化'] = Object.entries(vc).map(([layer, s]) => ({
      layer: `vec_${layer}`,
      label: layerLabel(layer),
      pct: Math.round(s.coverage),
      done: s.vectorized,
      total: s.total
    }))
  }
  if (gc) {
    groups['图谱'] = Object.entries(gc).map(([layer, s]) => ({
      layer: `graph_${layer}`,
      label: layerLabel(layer),
      pct: Math.round(s.coverage),
      done: s.graphed,
      total: s.total
    }))
  }
  return groups
})

function coverageColorClass(pct: number): string {
  if (pct >= 80) return 'good'
  if (pct >= 50) return 'warn'
  return 'bad'
}

// ========== Labels ==========
function layerLabel(layer: string): string {
  const labels: Record<string, string> = {
    legacy: 'Legacy',
    episodic: '情景记忆',
    semantic: '语义记忆',
    versions: '版本历史',
  }
  return labels[layer] || layer
}

function changeReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    dedup: '去重',
    merge: '融合',
    contradiction: '矛盾解决',
    consolidation: '合并',
    conflict_resolution: '冲突解决',
    user_edit: '用户编辑',
    llm_merge: 'LLM 融合',
    restore_backup: '恢复备份',
  }
  return labels[reason] || reason
}

function conflictLabel(type: string): string {
  if (type === 'multiple_workplaces') return '多重任职'
  return type
}

function formatTrendDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(() => { refresh() })
</script>

<style scoped>
/* ─── Header ─── */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.dashboard-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.dashboard-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.spinning {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── KPI Row ─── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.kpi-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  padding: 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  transition: box-shadow 0.2s;
}

.kpi-card:hover {
  box-shadow: var(--shadow-md);
}

.kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-icon.total { background: var(--brand-light); color: var(--brand); }
.kpi-icon.episodic { background: var(--bg-warning); color: var(--text-warning); }
.kpi-icon.semantic { background: var(--bg-success); color: var(--text-success); }
.kpi-icon.outbox { background: var(--bg-info); color: var(--text-brand); }
.kpi-icon.outbox.warn { background: var(--bg-danger); color: var(--text-danger); }

.kpi-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.kpi-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.kpi-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* ─── Main Grid ─── */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

/* ─── Trend Chart ─── */
.trend-body {
  padding-bottom: 12px !important;
}

.trend-chart {
  width: 100%;
  height: 120px;
  display: block;
}

.trend-labels {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px 0;
}

.trend-date {
  font-size: 11px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

/* ─── Outbox ─── */
.outbox-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.outbox-cell {
  text-align: center;
  padding: 12px 8px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.outbox-num {
  display: block;
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.outbox-num.pending { color: var(--text-warning); }
.outbox-num.processing { color: var(--text-brand); }
.outbox-num.failed { color: var(--text-danger); }
.outbox-num.completed { color: var(--text-success); }

.outbox-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.outbox-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--bg-tertiary);
}

.outbox-seg {
  height: 100%;
  transition: width 0.3s ease;
  min-width: 0;
}

.outbox-seg.pending { background: var(--text-warning); }
.outbox-seg.processing { background: var(--brand); }
.outbox-seg.failed { background: var(--text-danger); }
.outbox-seg.completed { background: var(--text-success); }

/* ─── Coverage ─── */
.coverage-group {
  margin-bottom: 16px;
}

.coverage-group:last-child {
  margin-bottom: 0;
}

.coverage-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.coverage-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.coverage-name {
  width: 64px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.coverage-bar-track {
  flex: 1;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.coverage-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.coverage-bar-fill.good { background: var(--text-success); }
.coverage-bar-fill.warn { background: var(--text-warning); }
.coverage-bar-fill.bad { background: var(--text-danger); }

.coverage-pct {
  width: 36px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.coverage-detail {
  width: 56px;
  font-size: 11px;
  color: var(--text-tertiary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ─── Health ─── */
.health-section {
  margin-bottom: 20px;
}

.health-section:last-child {
  margin-bottom: 0;
}

.health-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.health-ok {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-success);
  padding: 8px 12px;
  background: var(--bg-success);
  border-radius: var(--radius-md);
}

/* TTL */
.ttl-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.ttl-cell {
  text-align: center;
  padding: 10px 6px;
  border-radius: var(--radius-md);
}

.ttl-cell.urgent { background: var(--bg-danger); }
.ttl-cell.warn { background: var(--bg-warning); }
.ttl-cell.info { background: var(--bg-info); }
.ttl-cell.safe { background: var(--bg-success); }

.ttl-num {
  display: block;
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.ttl-cell.urgent .ttl-num { color: var(--text-danger); }
.ttl-cell.warn .ttl-num { color: var(--text-warning); }
.ttl-cell.info .ttl-num { color: var(--text-brand); }
.ttl-cell.safe .ttl-num { color: var(--text-success); }

.ttl-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* Conflicts */
.conflict-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conflict-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-warning);
  border-radius: var(--radius-md);
  font-size: 12px;
}

.conflict-person {
  font-weight: 600;
  color: var(--text-primary);
}

.conflict-companies {
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ─── Detail Grid ─── */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* ─── Stat list ─── */
.stat-list {
  display: flex;
  flex-direction: column;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-primary);
  font-size: 13px;
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-label {
  color: var(--text-secondary);
}

.stat-val {
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-val.warn {
  color: var(--text-warning);
}

/* ─── Tag cloud ─── */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-primary);
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: var(--bg-secondary);
  border-radius: 12px;
  font-size: 11px;
  color: var(--text-secondary);
}

.tag-item strong {
  color: var(--text-primary);
}

/* ─── Mini coverage (encryption) ─── */
.mini-coverage-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.mini-label {
  width: 64px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.mini-bar-track {
  flex: 1;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.mini-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.mini-bar-fill.good { background: var(--text-success); }
.mini-bar-fill.warn { background: var(--text-warning); }
.mini-bar-fill.bad { background: var(--text-danger); }

.mini-pct {
  width: 36px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ─── Card title with icon ─── */
.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* ─── Empty state ─── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.empty-state.sm {
  padding: 16px;
}

/* ─── Skeleton ─── */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.skeleton-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-secondary) 50%, var(--bg-tertiary) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-line.tall { height: 28px; }
.skeleton-line.w40 { width: 40%; }
.skeleton-line.w60 { width: 60%; }
.skeleton-line.w80 { width: 80%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ─── Responsive ─── */
@media (max-width: 1200px) {
  .detail-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 900px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .main-grid {
    grid-template-columns: 1fr;
  }
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .kpi-row {
    grid-template-columns: 1fr;
  }
}

/* ─── Dead Letter Panel ─── */
.dead-letter-panel {
  margin-top: 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.dead-letter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-secondary, #f5f5f5);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.dead-letter-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-danger, #e53e3e);
}

.btn-show-all,
.btn-retry-all,
.btn-retry-single {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  background: var(--bg-primary, #fff);
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-show-all:hover,
.btn-retry-all:hover,
.btn-retry-single:hover {
  background: var(--bg-hover, #f0f0f0);
  border-color: var(--brand, #6366f1);
  color: var(--brand, #6366f1);
}
.btn-retry-all {
  background: var(--bg-danger, #fee);
  color: var(--text-danger, #e53e3e);
  border-color: var(--text-danger, #e53e3e);
}
.btn-retry-all:hover {
  background: var(--text-danger, #e53e3e);
  color: #fff;
}
.btn-retry-all:disabled,
.btn-retry-single:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dead-letter-list {
  max-height: 300px;
  overflow-y: auto;
}

.dead-letter-loading {
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary, #999);
  font-size: 12px;
}

.dead-letter-item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color, #eee);
  font-size: 12px;
}
.dead-letter-item:last-child {
  border-bottom: none;
}

.dead-letter-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dead-letter-target {
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  text-transform: uppercase;
}
.dead-letter-target.milvus { background: #e3f2fd; color: #1565c0; }
.dead-letter-target.neo4j { background: #e8f5e9; color: #2e7d32; }
.dead-letter-target.redis { background: #fce4ec; color: #c62828; }

.dead-letter-type {
  color: var(--text-secondary, #666);
  font-family: monospace;
  font-size: 11px;
}

.dead-letter-mem {
  color: var(--text-tertiary, #999);
  font-size: 11px;
}

.dead-letter-attempts {
  color: var(--text-warning, #b45309);
  font-size: 11px;
  font-weight: 500;
}

.dead-letter-time {
  color: var(--text-tertiary, #999);
  font-size: 11px;
  margin-left: auto;
}

.dead-letter-error {
  margin-top: 4px;
  padding: 4px 8px;
  background: var(--bg-tertiary, #f8f8f8);
  border-radius: 3px;
  font-family: monospace;
  font-size: 11px;
  color: var(--text-danger, #e53e3e);
  word-break: break-all;
  max-height: 60px;
  overflow-y: auto;
}

/* Outbox grid 5-column (for future use) */
.outbox-grid-5 {
  grid-template-columns: repeat(4, 1fr);
}

/* Outbox cell dead state */
.outbox-cell.is-dead {
  background: var(--bg-danger, #fee);
  border: 1px solid var(--text-danger, #e53e3e);
}

/* Outbox num colors */
.outbox-num.processed { color: var(--text-success, #38a169); }
.outbox-num.dead { color: var(--text-danger, #e53e3e); }

.outbox-seg.processed { background: var(--text-success, #38a169); }
.outbox-seg.dead { background: var(--text-danger, #e53e3e); }

</style>
