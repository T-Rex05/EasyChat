<template>
  <div class="page-container memory-page">
    <!-- Header -->
    <header class="page-header">
      <div>
        <h2 class="page-title">智能记忆系统</h2>
        <p class="page-subtitle">两层架构：近期记忆（30 天 TTL） / 永久知识（图谱关联）</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="runConsolidation" :disabled="consolidating">
          <RefreshCw :size="14" :class="{ spinning: consolidating }" />
          {{ consolidating ? '合并中...' : '执行合并' }}
        </button>
        <button class="btn btn-primary" @click="openCreate">
          <Plus :size="14" />
          新建记忆
        </button>
      </div>
    </header>

    <!-- Layer Tabs -->
    <section class="layer-section">
      <div class="layer-tabs">
        <button
          class="layer-tab"
          :class="{ active: activeLayer === 'episodic' }"
          @click="switchLayer('episodic')"
        >
          <Clock :size="16" />
          <span>近期记忆</span>
          <span class="layer-count">{{ episodicStats.total || 0 }}</span>
        </button>
        <button
          class="layer-tab"
          :class="{ active: activeLayer === 'semantic' }"
          @click="switchLayer('semantic')"
        >
          <Gem :size="16" />
          <span>永久知识</span>
          <span class="layer-count">{{ semanticStats.total || 0 }}</span>
        </button>
      </div>
      <div class="layer-hint">
        <template v-if="activeLayer === 'episodic'">
          对话中自动提取，30 天后自动清理。重要的记忆可晋升为永久知识。
        </template>
        <template v-else>
          长期保存的核心知识，写入知识图谱，支持关联检索。
        </template>
      </div>
    </section>

    <!-- Type Filter -->
    <section class="type-filter">
      <button
        v-for="t in typeFilters"
        :key="t.value"
        class="type-chip"
        :class="{ active: activeType === t.value, ['type-' + t.value]: t.value }"
        @click="setActiveType(t.value)"
      >
        <component :is="t.icon" :size="14" />
        <span>{{ t.label }}</span>
        <span class="type-chip-count">{{ getTypeCount(t.value) }}</span>
      </button>
    </section>

    <!-- Search -->
    <section class="search-section">
      <div class="search-box">
        <Search :size="15" class="search-icon" />
        <input
          v-model="searchQuery"
          class="input search-input"
          placeholder="搜索记忆..."
          @keyup.enter="doSearch"
        />
        <button v-if="searchQuery" class="btn-icon search-clear" @click="clearSearch">
          <X :size="14" />
        </button>
        <button v-if="searchQuery || isSearchMode" class="btn btn-primary btn-sm search-btn" @click="doSearch">搜索</button>
      </div>
      <label v-if="activeLayer === 'episodic'" class="checkbox-label">
        <input type="checkbox" v-model="includeExpired" @change="loadMemories" />
        显示已过期
      </label>
    </section>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Search Results -->
    <section v-else-if="isSearchMode" class="results-section">
      <p class="results-info">找到 {{ searchResults.count }} 条相关记忆</p>
      <div class="memory-grid">
        <div
          v-for="item in searchResults.results"
          :key="item.memory.id"
          class="memory-card"
        >
          <div class="card-top">
            <span class="type-badge" :class="'type-' + item.memory.memory_type">
              <component :is="TYPE_ICONS[item.memory.memory_type]" :size="12" />
              {{ MEMORY_TYPE_LABELS[item.memory.memory_type] }}
            </span>
            <div class="card-scores">
              <span class="score-pill">{{ (item.memory.importance_score * 100).toFixed(0) }}%</span>
              <span class="score-pill match">{{ (item.score * 100).toFixed(0) }}% 匹配</span>
            </div>
          </div>
          <p class="card-content">{{ item.memory.content }}</p>
          <div class="card-bottom">
            <span class="card-date">{{ formatDate(item.memory.created_at) }}</span>
            <button class="btn btn-sm btn-secondary" @click="viewDetail(item.memory)">详情</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Empty -->
    <section v-else-if="memories.length === 0" class="empty-state">
      <component :is="activeLayer === 'episodic' ? Clock : Gem" :size="40" />
      <h3>{{ activeLayer === 'episodic' ? '暂无近期记忆' : '暂无永久知识' }}</h3>
      <p>{{ activeLayer === 'episodic' ? '对话中会自动提取记忆，或点击「新建记忆」手动添加' : '从近期记忆中晋升重要信息，或点击「新建记忆」直接创建' }}</p>
    </section>

    <!-- Memory List -->
    <section v-else class="results-section">
      <div class="memory-grid">
        <div
          v-for="item in memories"
          :key="item.id"
          class="memory-card"
        >
          <div class="card-top">
            <span class="type-badge" :class="'type-' + item.memory_type">
              <component :is="TYPE_ICONS[item.memory_type]" :size="12" />
              {{ MEMORY_TYPE_LABELS[item.memory_type] }}
            </span>
            <div class="card-scores">
              <span
                v-if="activeLayer === 'episodic' && (item as EpisodicMemory).expires_at"
                class="expiry-pill"
                :class="{ expiring: isExpiringSoon((item as EpisodicMemory).expires_at) }"
              >
                <Timer :size="11" />
                {{ formatExpiresAt((item as EpisodicMemory).expires_at) }}
              </span>
              <span class="score-pill">{{ (item.importance_score * 100).toFixed(0) }}%</span>
            </div>
          </div>
          <div class="card-body-area">
            <p class="card-content">{{ item.content }}</p>
            <div v-if="activeLayer === 'semantic' && (item as SemanticMemory).source_episodic_id" class="promotion-tag">
              <ArrowUp :size="11" /> 从近期记忆晋升
            </div>
          </div>
          <div class="card-bottom">
            <span class="card-date">{{ formatDate(item.created_at) }}</span>
            <div class="card-actions">
              <button
                v-if="activeLayer === 'episodic'"
                class="btn btn-sm btn-promote"
                @click="openPromote(item as EpisodicMemory)"
              >
                <ArrowUp :size="12" /> 晋升
              </button>
              <button class="btn btn-sm btn-secondary" @click="viewDetail(item)">
                <Pencil :size="12" /> 编辑
              </button>
              <div class="more-wrap">
                <button class="btn-icon more-btn" @click="toggleMore(item.id)" title="更多操作">
                  <MoreHorizontal :size="15" />
                </button>
                <div v-if="moreOpenId === item.id" class="more-menu" @click.stop>
                  <button class="more-item" @click="openVersions(item.id); closeMore()">
                    <History :size="13" /> 版本历史
                  </button>
                  <button v-if="activeLayer === 'semantic'" class="more-item" @click="openGraph(item.id); closeMore()">
                    <GitBranch :size="13" /> 图关联
                  </button>
                  <div class="more-divider"></div>
                  <button class="more-item danger" @click="confirmDelete(item); closeMore()">
                    <Trash2 :size="13" /> 删除
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer bar -->
      <div class="footer-bar">
        <span>当前显示 {{ memories.length }} 条{{ activeLayer === 'episodic' ? '近期记忆' : '永久知识' }}</span>
        <button class="footer-help" @click="openDrawer('help')">
          <HelpCircle :size="13" /> 合并说明
        </button>
      </div>
    </section>

    <!-- ===== Right-side Drawer ===== -->
    <Teleport to="body">
      <Transition name="drawer-fade">
        <div v-if="drawerOpen" class="drawer-overlay" @click.self="closeDrawer"></div>
      </Transition>
      <Transition name="drawer-slide">
        <div v-if="drawerOpen" class="drawer">
          <!-- Create / Edit -->
          <template v-if="drawerMode === 'create' || drawerMode === 'edit'">
            <div class="drawer-header">
              <h3>{{ drawerMode === 'edit' ? '编辑记忆' : '新建记忆' }}</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body">
              <div class="form-group">
                <label class="form-label">记忆类型</label>
                <div class="type-selector">
                  <button
                    v-for="mt in memoryTypes"
                    :key="mt"
                    class="type-option"
                    :class="{ selected: editForm.memory_type === mt, ['type-' + mt]: true }"
                    @click="editForm.memory_type = mt"
                  >
                    <component :is="TYPE_ICONS[mt]" :size="14" />
                    {{ MEMORY_TYPE_LABELS[mt] }}
                  </button>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">记忆内容</label>
                <textarea
                  v-model="editForm.content"
                  class="textarea"
                  placeholder="输入需要记住的内容..."
                  rows="5"
                ></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">
                  重要性：{{ (editForm.importance * 100).toFixed(0) }}%
                </label>
                <input
                  type="range"
                  v-model="editForm.importance"
                  min="0" max="1" step="0.1"
                  class="importance-slider"
                />
                <div class="slider-labels">
                  <span>低</span><span>中</span><span>高</span>
                </div>
              </div>
            </div>
            <div class="drawer-footer">
              <button class="btn btn-secondary" @click="closeDrawer">取消</button>
              <button class="btn btn-primary" @click="saveMemory" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>
          </template>

          <!-- Promote -->
          <template v-else-if="drawerMode === 'promote'">
            <div class="drawer-header">
              <h3>晋升为永久知识</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body">
              <p class="drawer-hint">将此近期记忆晋升为永久知识。晋升后可以编辑内容使其更精炼。</p>
              <div class="form-group">
                <label class="form-label">记忆内容</label>
                <textarea v-model="promoteForm.content" class="textarea" rows="5"></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">
                  重要性：{{ (promoteForm.importance * 100).toFixed(0) }}%
                </label>
                <input
                  type="range"
                  v-model="promoteForm.importance"
                  min="0" max="1" step="0.1"
                  class="importance-slider"
                />
              </div>
            </div>
            <div class="drawer-footer">
              <button class="btn btn-secondary" @click="closeDrawer">取消</button>
              <button class="btn btn-primary" @click="doPromote" :disabled="promoting">
                {{ promoting ? '晋升中...' : '确认晋升' }}
              </button>
            </div>
          </template>

          <!-- Version History -->
          <template v-else-if="drawerMode === 'versions'">
            <div class="drawer-header">
              <h3>版本历史</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body">
              <div v-if="versionsLoading" class="loading-state sm">
                <div class="loading-spinner"></div>
              </div>
              <div v-else-if="!versionsData" class="empty-state sm">
                <p>加载失败</p>
              </div>
              <div v-else-if="versionsData.versions.length === 0" class="empty-state sm">
                <Inbox :size="32" />
                <p>暂无历史版本</p>
                <p class="hint">记忆合并或编辑后会产生版本记录</p>
              </div>
              <template v-else>
                <!-- Current version -->
                <div class="version-card current">
                  <div class="version-head">
                    <span class="badge badge-info">当前</span>
                    <span class="version-time">至今</span>
                  </div>
                  <p class="version-text">{{ versionsData.current_content }}</p>
                  <div class="version-meta">
                    重要性 {{ (versionsData.current_importance * 100).toFixed(0) }}%
                  </div>
                </div>
                <!-- History -->
                <div class="version-timeline">
                  <div
                    v-for="ver in versionsData.versions"
                    :key="ver.id"
                    class="version-card"
                  >
                    <div class="version-head">
                      <span class="badge">v{{ ver.version }}</span>
                      <span class="version-reason" :style="{ color: getChangeReasonColor(ver.change_reason) }">
                        {{ getChangeReasonLabel(ver.change_reason) }}
                      </span>
                      <span class="version-time">{{ formatDateTime(ver.created_at) }}</span>
                    </div>
                    <p class="version-text">{{ ver.content }}</p>
                    <div class="version-meta">
                      重要性 {{ (ver.importance_score * 100).toFixed(0) }}%
                      <span v-if="ver.memory_type"> / {{ MEMORY_TYPE_LABELS[ver.memory_type] || ver.memory_type }}</span>
                    </div>
                    <button
                      class="btn btn-sm btn-secondary restore-btn"
                      @click="doRestore(versionsData!.memory_id, ver.version)"
                      :disabled="restoring"
                    >
                      <RotateCcw :size="12" /> 恢复此版本
                    </button>
                  </div>
                </div>
                <p class="versions-footer-text">共 {{ versionsData.total_versions }} 个历史版本</p>
              </template>
            </div>
          </template>

          <!-- Graph Relations -->
          <template v-else-if="drawerMode === 'graph'">
            <div class="drawer-header">
              <h3>图关联</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body">
              <div v-if="graphLoading" class="loading-state sm">
                <div class="loading-spinner"></div>
              </div>
              <div v-else-if="!graphData.graph_available" class="empty-state sm">
                <GitBranch :size="32" />
                <p>图数据库未启用</p>
                <p class="hint">请配置 NEO4J_URI 环境变量</p>
              </div>
              <div v-else-if="graphData.related_count === 0" class="empty-state sm">
                <p>暂无关联记忆</p>
              </div>
              <template v-else>
                <p class="graph-info">找到 {{ graphData.related_count }} 条关联记忆</p>
                <div class="graph-list">
                  <div v-for="item in graphData.related" :key="item.id" class="graph-item">
                    <span class="type-badge" :class="'type-' + item.memory_type">
                      <component :is="TYPE_ICONS[item.memory_type]" :size="12" />
                      {{ MEMORY_TYPE_LABELS[item.memory_type] }}
                    </span>
                    <p class="graph-content">{{ item.content }}</p>
                  </div>
                </div>
              </template>
            </div>
          </template>

          <!-- Consolidation Result -->
          <template v-else-if="drawerMode === 'consolidation'">
            <div class="drawer-header">
              <h3>记忆合并完成</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body">
              <div v-if="consolidationResult" class="cons-stats">
                <div class="cons-cell">
                  <span class="cons-num">{{ consolidationResult.deduped }}</span>
                  <span class="cons-label">去重</span>
                </div>
                <div class="cons-cell">
                  <span class="cons-num">{{ consolidationResult.merged }}</span>
                  <span class="cons-label">合并</span>
                </div>
                <div class="cons-cell">
                  <span class="cons-num">{{ consolidationResult.expired }}</span>
                  <span class="cons-label">淘汰</span>
                </div>
                <div class="cons-cell highlight">
                  <span class="cons-num">{{ consolidationResult.remaining }}</span>
                  <span class="cons-label">剩余</span>
                </div>
              </div>
              <p class="cons-note">三阶段合并：衰减 → 去重/合并 → 双条件淘汰</p>
            </div>
          </template>

          <!-- Help -->
          <template v-else-if="drawerMode === 'help'">
            <div class="drawer-header">
              <h3>记忆系统说明</h3>
              <button class="btn-icon" @click="closeDrawer"><X :size="18" /></button>
            </div>
            <div class="drawer-body help-body">
              <div class="help-block">
                <h4>两层记忆架构</h4>
                <div class="help-layers">
                  <div class="help-layer">
                    <span class="badge badge-warning">近期</span>
                    <div>
                      <strong>近期记忆（Episodic）</strong>
                      <p>对话中自动提取，30 天 TTL，用于短期上下文。</p>
                    </div>
                  </div>
                  <div class="help-layer">
                    <span class="badge badge-success">永久</span>
                    <div>
                      <strong>永久知识（Semantic）</strong>
                      <p>长期保存，写入知识图谱，支持关联检索。</p>
                    </div>
                  </div>
                </div>
              </div>
              <div class="help-block">
                <h4>晋升机制</h4>
                <ul>
                  <li>点击记忆卡片上的「晋升」按钮</li>
                  <li>可以编辑内容使其更精炼</li>
                  <li>晋升后会自动写入知识图谱</li>
                </ul>
              </div>
              <div class="help-block">
                <h4>三阶段合并</h4>
                <div class="help-steps">
                  <div class="help-step">
                    <span class="step-num">1</span>
                    <div><strong>衰减</strong><p>根据时间降低旧记忆的重要性分数</p></div>
                  </div>
                  <div class="help-step">
                    <span class="step-num">2</span>
                    <div><strong>去重 & 合并</strong><p>合并语义相似的重复记忆</p></div>
                  </div>
                  <div class="help-step">
                    <span class="step-num">3</span>
                    <div><strong>淘汰</strong><p>删除过期且低重要性的记忆</p></div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed, onBeforeUnmount, markRaw, type Component } from 'vue'
import { errMsg } from '@/utils/err'
import {
  Clock, Gem, Search, X, Plus, RefreshCw, MoreHorizontal,
  Pencil, Trash2, History, GitBranch, ArrowUp, Timer,
  HelpCircle, RotateCcw, Inbox, Target, Pin, Calendar, Zap
} from '@lucide/vue'
import {
  createMemory, updateMemory, deleteMemory,
  searchMemories, getMemoryGraph, triggerConsolidation,
  getEpisodicMemories, getSemanticMemories, promoteMemory,
  getEpisodicStats, getSemanticStats,
  getMemoryVersions, restoreMemoryVersion,
  MEMORY_TYPE_LABELS,
  type MemoryItem, type EpisodicMemory, type SemanticMemory,
  type EpisodicStats, type SemanticStats,
  type SearchResponse, type GraphRelation, type ConsolidationResult,
  type VersionHistory
} from '@/api/memoryItems'

const memoryTypes = ['preference', 'fact', 'event', 'skill'] as const

const TYPE_ICONS: Record<string, Component> = {
  preference: markRaw(Target),
  fact: markRaw(Pin),
  event: markRaw(Calendar),
  skill: markRaw(Zap)
}

// ========== Type filter config ==========
const typeFilters = [
  { value: '', label: '全部', icon: markRaw(Search) },
  { value: 'preference', label: '偏好', icon: markRaw(Target) },
  { value: 'fact', label: '事实', icon: markRaw(Pin) },
  { value: 'event', label: '事件', icon: markRaw(Calendar) },
  { value: 'skill', label: '技能', icon: markRaw(Zap) }
]

// ========== Layer ==========
const activeLayer = ref<'episodic' | 'semantic'>('episodic')
const includeExpired = ref(false)
const episodicStats = ref<EpisodicStats>({ total: 0, active: 0, expired: 0, by_type: {} })
const semanticStats = ref<SemanticStats>({ total: 0, by_type: {}, from_promotion: 0 })

const currentStats = computed(() =>
  activeLayer.value === 'episodic' ? episodicStats.value : semanticStats.value
)

function getTypeCount(type: string): number {
  if (!type) return currentStats.value.total
  return currentStats.value.by_type?.[type] || 0
}

// ========== State ==========
const loading = ref(false)
const saving = ref(false)
const consolidating = ref(false)
const activeType = ref('')
const memories = ref<(MemoryItem | EpisodicMemory | SemanticMemory)[]>([])

const searchQuery = ref('')
const isSearchMode = ref(false)
const searchResults = ref<SearchResponse>({ query: '', count: 0, results: [] })

// ========== Drawer ==========
type DrawerMode = 'create' | 'edit' | 'promote' | 'versions' | 'graph' | 'consolidation' | 'help'
const drawerOpen = ref(false)
const drawerMode = ref<DrawerMode>('create')

function openDrawer(mode: DrawerMode) {
  drawerMode.value = mode
  drawerOpen.value = true
}
function closeDrawer() {
  drawerOpen.value = false
}

// ========== More menu ==========
const moreOpenId = ref<number | null>(null)

function toggleMore(id: number) {
  moreOpenId.value = moreOpenId.value === id ? null : id
}
function closeMore() {
  moreOpenId.value = null
}

// Close more-menu on outside click
function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.more-wrap')) {
    moreOpenId.value = null
  }
}
onMounted(() => document.addEventListener('click', onDocClick, true))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))

// ========== Editor form ==========
const editingItem = ref<MemoryItem | null>(null)
const editForm = reactive({ memory_type: 'fact' as string, content: '', importance: 0.5 })

// ========== Promote form ==========
const promoting = ref(false)
const promoteTarget = ref<EpisodicMemory | null>(null)
const promoteForm = reactive({ content: '', importance: 0.5 })

// ========== Consolidation ==========
const consolidationResult = ref<ConsolidationResult | null>(null)

// ========== Graph ==========
const graphLoading = ref(false)
const graphData = ref<GraphRelation>({ memory_id: 0, graph_available: false, related_count: 0, related: [] })

// ========== Versions ==========
const versionsLoading = ref(false)
const versionsData = ref<VersionHistory | null>(null)
const restoring = ref(false)

// ========== Layer switch ==========
function switchLayer(layer: 'episodic' | 'semantic') {
  activeLayer.value = layer
  isSearchMode.value = false
  loadMemories()
  loadStats()
}

// ========== Data loading ==========
async function loadMemories() {
  loading.value = true
  try {
    memories.value = activeLayer.value === 'episodic'
      ? await getEpisodicMemories(activeType.value || undefined, includeExpired.value, 50)
      : await getSemanticMemories(activeType.value || undefined, 50)
  } catch (e: any) {
    alert('加载失败: ' + errMsg(e))
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const [e, s] = await Promise.all([getEpisodicStats(), getSemanticStats()])
    episodicStats.value = e
    semanticStats.value = s
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

function setActiveType(type: string) {
  activeType.value = type
  isSearchMode.value = false
  loadMemories()
}

// ========== Search ==========
async function doSearch() {
  if (!searchQuery.value.trim()) return
  loading.value = true
  try {
    searchResults.value = await searchMemories(searchQuery.value.trim(), activeType.value || undefined)
    isSearchMode.value = true
  } catch (e: any) {
    alert('搜索失败: ' + errMsg(e))
  } finally {
    loading.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  isSearchMode.value = false
  searchResults.value = { query: '', count: 0, results: [] }
  loadMemories()
}

// ========== Editor ==========
function openCreate() {
  editingItem.value = null
  editForm.memory_type = activeType.value || 'fact'
  editForm.content = ''
  editForm.importance = 0.5
  openDrawer('create')
}

function viewDetail(item: MemoryItem | EpisodicMemory | SemanticMemory) {
  editingItem.value = item as MemoryItem
  editForm.memory_type = item.memory_type
  editForm.content = item.content
  editForm.importance = item.importance_score
  openDrawer('edit')
}

async function saveMemory() {
  if (!editForm.content.trim()) {
    alert('请输入记忆内容')
    return
  }
  saving.value = true
  try {
    if (editingItem.value) {
      await updateMemory(editingItem.value.id, editForm.content, editForm.importance)
    } else {
      await createMemory(editForm.memory_type, editForm.content, editForm.importance)
    }
    closeDrawer()
    await Promise.all([loadMemories(), loadStats()])
  } catch (e: any) {
    alert('保存失败: ' + errMsg(e))
  } finally {
    saving.value = false
  }
}

// ========== Promote ==========
function openPromote(item: EpisodicMemory) {
  promoteTarget.value = item
  promoteForm.content = item.content
  promoteForm.importance = item.importance_score
  openDrawer('promote')
}

async function doPromote() {
  if (!promoteTarget.value) return
  promoting.value = true
  try {
    await promoteMemory(promoteTarget.value.id, promoteForm.content, promoteForm.importance)
    closeDrawer()
    await Promise.all([loadMemories(), loadStats()])
  } catch (e: any) {
    alert('晋升失败: ' + errMsg(e))
  } finally {
    promoting.value = false
  }
}

// ========== Delete ==========
async function confirmDelete(item: MemoryItem | EpisodicMemory | SemanticMemory) {
  if (!confirm(`确定删除这条${MEMORY_TYPE_LABELS[item.memory_type]}记忆吗？\n\n${item.content.slice(0, 100)}...`)) return
  try {
    await deleteMemory(item.id)
    await Promise.all([loadMemories(), loadStats()])
  } catch (e: any) {
    alert('删除失败: ' + errMsg(e))
  }
}

// ========== Consolidation ==========
async function runConsolidation() {
  if (!confirm('确定执行记忆合并吗？')) return
  consolidating.value = true
  try {
    const resp = await triggerConsolidation()
    if (resp.result) {
      consolidationResult.value = resp.result
      openDrawer('consolidation')
      await Promise.all([loadMemories(), loadStats()])
    } else {
      alert(resp.message)
    }
  } catch (e: any) {
    alert('合并失败: ' + errMsg(e))
  } finally {
    consolidating.value = false
  }
}

// ========== Graph ==========
async function openGraph(memoryId: number) {
  openDrawer('graph')
  graphLoading.value = true
  try {
    graphData.value = await getMemoryGraph(memoryId)
  } catch (e: any) {
    alert('加载图关联失败: ' + errMsg(e))
    closeDrawer()
  } finally {
    graphLoading.value = false
  }
}

// ========== Versions ==========
async function openVersions(memoryId: number) {
  openDrawer('versions')
  versionsLoading.value = true
  versionsData.value = null
  try {
    versionsData.value = await getMemoryVersions(memoryId)
  } catch (e: any) {
    alert('加载版本历史失败: ' + errMsg(e))
    closeDrawer()
  } finally {
    versionsLoading.value = false
  }
}

async function doRestore(memoryId: number, version: number) {
  if (!confirm(`确定要恢复到版本 ${version} 吗？\n当前内容会被保存为新版本。`)) return
  restoring.value = true
  try {
    await restoreMemoryVersion(memoryId, version)
    await Promise.all([loadMemories(), loadStats()])
    versionsData.value = await getMemoryVersions(memoryId)
  } catch (e: any) {
    alert('恢复失败: ' + errMsg(e))
  } finally {
    restoring.value = false
  }
}

// ========== Utils ==========
function formatDate(date?: string): string {
  if (!date) return ''
  return new Date(date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function formatDateTime(date?: string): string {
  if (!date) return ''
  return new Date(date).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatExpiresAt(date?: string): string {
  if (!date) return ''
  const expires = new Date(date)
  const now = new Date()
  const diffDays = Math.ceil((expires.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays < 0) return '已过期'
  if (diffDays === 0) return '今天过期'
  if (diffDays <= 7) return `${diffDays}天后`
  return formatDate(date)
}

function isExpiringSoon(date?: string): boolean {
  if (!date) return false
  const diffDays = (new Date(date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  return diffDays <= 7
}

function getChangeReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    consolidation: '合并', dedup: '去重', merge: '融合',
    contradiction: '矛盾解决', conflict_resolution: '冲突解决',
    user_edit: '用户编辑', llm_merge: 'LLM融合',
    restore: '恢复备份', restore_backup: '恢复前备份'
  }
  return labels[reason] || reason
}

function getChangeReasonColor(reason: string): string {
  const colors: Record<string, string> = {
    consolidation: 'var(--brand)', dedup: 'var(--text-success)',
    merge: '#9c27b0', contradiction: 'var(--text-danger)',
    conflict_resolution: 'var(--text-warning)', user_edit: 'var(--brand)',
    llm_merge: '#9c27b0', restore: 'var(--text-warning)', restore_backup: 'var(--text-warning)'
  }
  return colors[reason] || 'var(--text-tertiary)'
}

onMounted(() => { loadMemories(); loadStats() })
</script>

<style scoped>
/* ─── Page ─── */
.memory-page { padding-top: 24px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.page-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ─── Layer Tabs ─── */
.layer-section { margin-bottom: 20px; }

.layer-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.layer-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-secondary);
  background: var(--bg-card);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: var(--transition);
}

.layer-tab:hover {
  border-color: var(--brand);
  color: var(--text-primary);
}

.layer-tab.active {
  background: var(--brand-light);
  border-color: var(--brand);
  color: var(--brand);
}

.layer-count {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.layer-tab.active .layer-count {
  background: var(--brand);
  color: var(--text-inverse);
}

.layer-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 0 4px;
}

/* ─── Type Filter ─── */
.type-filter {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.type-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius-bubble);
  border: 1px solid var(--border-secondary);
  background: var(--bg-card);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: var(--transition);
}

.type-chip:hover { border-color: var(--brand); }

.type-chip.active {
  border-color: var(--brand);
  background: var(--brand-light);
  color: var(--brand);
}

.type-chip.active.type-preference { border-color: #9c27b0; background: rgba(156, 39, 176, 0.08); color: #9c27b0; }
.type-chip.active.type-fact { border-color: var(--brand); background: var(--brand-light); color: var(--brand); }
.type-chip.active.type-event { border-color: var(--text-warning); background: var(--bg-warning); color: var(--text-warning); }
.type-chip.active.type-skill { border-color: var(--text-success); background: var(--bg-success); color: var(--text-success); }

.type-chip-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

/* ─── Search ─── */
.search-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 200px;
  max-width: 420px;
  background: var(--bg-card);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg);
  padding: 0 12px;
  transition: var(--transition);
}

.search-box:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--brand-shadow);
}

.search-icon { color: var(--text-tertiary); flex-shrink: 0; }

.search-input {
  flex: 1;
  border: none !important;
  box-shadow: none !important;
  padding: 10px 4px;
  background: transparent;
  min-width: 0;
}

.search-input:focus { outline: none; }

.search-clear {
  flex-shrink: 0;
}

.search-btn {
  flex-shrink: 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

/* ─── Memory Grid ─── */
.memory-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.memory-card {
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s, transform 0.2s;
}

.memory-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-primary);
  gap: 8px;
}

.card-scores {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.type-badge.type-preference { background: rgba(156, 39, 176, 0.1); color: #9c27b0; }
.type-badge.type-fact { background: var(--brand-light); color: var(--brand); }
.type-badge.type-event { background: var(--bg-warning); color: var(--text-warning); }
.type-badge.type-skill { background: var(--bg-success); color: var(--text-success); }

.score-pill {
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.score-pill.match {
  background: var(--brand-light);
  color: var(--brand);
}

.expiry-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-success);
  color: var(--text-success);
}

.expiry-pill.expiring {
  background: var(--bg-warning);
  color: var(--text-warning);
}

.card-body-area {
  padding: 14px 16px;
  flex: 1;
}

.card-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 140px;
  overflow-y: auto;
}

.promotion-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 3px 8px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.card-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-top: 1px solid var(--border-primary);
  gap: 8px;
}

.card-date {
  font-size: 11px;
  color: var(--text-tertiary);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-promote {
  background: rgba(156, 39, 176, 0.08);
  color: #9c27b0;
  border: 1px solid rgba(156, 39, 176, 0.25);
}

.btn-promote:hover {
  background: #9c27b0;
  color: var(--text-inverse);
}

/* ─── More menu ─── */
.more-wrap { position: relative; }

.more-btn {
  width: 28px;
  height: 28px;
}

.more-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 4px);
  background: var(--bg-card);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  min-width: 140px;
  padding: 4px;
  z-index: 100;
  animation: menuIn 0.15s ease;
}

@keyframes menuIn {
  from { opacity: 0; transform: translateY(4px); }
}

.more-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: var(--transition);
  text-align: left;
}

.more-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.more-item.danger:hover {
  background: var(--bg-danger);
  color: var(--text-danger);
}

.more-divider {
  height: 1px;
  background: var(--border-primary);
  margin: 4px 0;
}

/* ─── Footer bar ─── */
.footer-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  background: var(--brand);
  border-radius: var(--radius-lg);
  color: var(--text-inverse);
  font-size: 13px;
}

.footer-help {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  font-size: 12px;
  transition: var(--transition);
}

.footer-help:hover { color: white; }

/* ─── Results info ─── */
.results-info {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

/* ─── Loading / Empty ─── */
.loading-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-tertiary);
}

.loading-state.sm { padding: 32px 20px; }

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-secondary);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}

.empty-state {
  text-align: center;
  padding: 64px 20px;
  color: var(--text-tertiary);
}

.empty-state.sm { padding: 32px 20px; }

.empty-state h3 {
  margin: 12px 0 4px;
  font-size: 16px;
  color: var(--text-secondary);
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 4px;
}

/* ═══════════════════════════════════════
   Drawer
   ═══════════════════════════════════════ */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  z-index: 900;
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 480px;
  max-width: 90vw;
  background: var(--bg-card);
  box-shadow: var(--shadow-lg);
  z-index: 910;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.drawer-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 24px;
  border-top: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.drawer-hint {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

/* Drawer transitions */
.drawer-fade-enter-active,
.drawer-fade-leave-active { transition: opacity 0.2s; }
.drawer-fade-enter-from,
.drawer-fade-leave-to { opacity: 0; }

.drawer-slide-enter-active,
.drawer-slide-leave-active { transition: transform 0.25s ease; }
.drawer-slide-enter-from,
.drawer-slide-leave-to { transform: translateX(100%); }

/* ─── Type selector (editor) ─── */
.type-selector {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.type-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-secondary);
  background: var(--bg-card);
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: var(--transition);
}

.type-option:hover { border-color: var(--brand); }

.type-option.selected.type-preference { border-color: #9c27b0; background: rgba(156, 39, 176, 0.08); color: #9c27b0; }
.type-option.selected.type-fact { border-color: var(--brand); background: var(--brand-light); color: var(--brand); }
.type-option.selected.type-event { border-color: var(--text-warning); background: var(--bg-warning); color: var(--text-warning); }
.type-option.selected.type-skill { border-color: var(--text-success); background: var(--bg-success); color: var(--text-success); }

/* ─── Importance slider ─── */
.importance-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  appearance: none;
  background: linear-gradient(90deg, var(--text-success), var(--text-warning), var(--text-danger));
  cursor: pointer;
  outline: none;
}

.importance-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 2px solid var(--brand);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* ─── Version cards ─── */
.version-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 14px;
  margin-bottom: 10px;
}

.version-card.current {
  background: var(--brand-light);
  border-color: rgba(78, 110, 242, 0.2);
}

.version-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.version-time {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: auto;
}

.version-reason {
  font-size: 12px;
  font-weight: 500;
}

.version-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  margin: 0 0 8px;
  padding: 8px 10px;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

.version-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.restore-btn {
  display: flex;
  align-items: center;
  gap: 4px;
}

.versions-footer-text {
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 8px 0;
  border-top: 1px solid var(--border-primary);
}

/* ─── Graph ─── */
.graph-info {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.graph-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.graph-item {
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
}

.graph-content {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}

/* ─── Consolidation result ─── */
.cons-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.cons-cell {
  text-align: center;
  padding: 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.cons-cell.highlight {
  background: var(--brand);
  color: var(--text-inverse);
}

.cons-num {
  display: block;
  font-size: 28px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.cons-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.cons-cell.highlight .cons-label {
  color: rgba(255, 255, 255, 0.8);
}

.cons-note {
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}

/* ─── Help ─── */
.help-body { padding-bottom: 32px; }

.help-block {
  margin-bottom: 24px;
}

.help-block:last-child { margin-bottom: 0; }

.help-block h4 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.help-block p {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.help-block ul {
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.help-layers {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.help-layer {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.help-layer strong {
  display: block;
  font-size: 13px;
  margin-bottom: 2px;
}

.help-layer p {
  margin: 0;
  font-size: 12px;
}

.help-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help-step {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--brand);
  color: var(--text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
  flex-shrink: 0;
}

.help-step strong {
  font-size: 13px;
}

.help-step p {
  margin: 2px 0 0;
  font-size: 12px;
}

/* ─── Responsive ─── */
@media (max-width: 768px) {
  .memory-grid {
    grid-template-columns: 1fr;
  }
  .drawer {
    width: 100%;
    max-width: 100vw;
  }
}
</style>
