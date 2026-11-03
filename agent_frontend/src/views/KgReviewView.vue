<template>
  <div class="review-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h2>⏳ 知识图谱审核</h2>
        <span class="header-desc">LLM 提取后自动标记的可疑项，请逐项审核处理</span>
      </div>
      <div class="header-right">
        <select v-model="filterType" @change="loadCandidates" class="filter-select">
          <option value="">全部类型</option>
          <option value="duplicate">疑似重复</option>
          <option value="name_collision">同名消歧</option>
          <option value="low_confidence">低置信度</option>
          <option value="relation_direction">方向可疑</option>
        </select>
        <select v-model="filterStatus" @change="loadCandidates" class="filter-select">
          <option value="pending">待审核</option>
          <option value="">全部状态</option>
          <option value="merged">已合并</option>
          <option value="confirmed">已确认</option>
          <option value="ignored">已忽略</option>
        </select>
        <button @click="loadCandidates" class="refresh-btn" :disabled="loading">
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
      </div>
    </div>

    <!-- 统计栏 -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-num">{{ pendingCount }}</span>
        <span class="stat-label">待审核</span>
      </div>
      <div class="stat-item total">
        <span class="stat-num">{{ total }}</span>
        <span class="stat-label">总计</span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && candidates.length === 0" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="candidates.length === 0" class="empty-state">
      <div class="empty-icon">✅</div>
      <h3>暂无{{ filterStatus === 'pending' ? '待审核' : '' }}候选项</h3>
      <p>所有实体和关系都清晰明确，无需人工审核</p>
    </div>

    <!-- 候选列表 -->
    <div v-else class="candidate-list">
      <div v-for="c in candidates" :key="c.id" class="candidate-card" :class="[`type-${c.candidate_type}`, `status-${c.status}`]">
        <div class="card-header">
          <span class="type-tag" :class="c.candidate_type">{{ typeTagLabel(c.candidate_type) }}</span>
          <span v-if="c.score !== null" class="score-tag">{{ c.score }}</span>
          <span class="status-tag" :class="c.status">{{ statusLabel(c.status) }}</span>
          <span class="time-tag">{{ formatTime(c.created_at) }}</span>
        </div>

        <div class="card-body">
          <!-- duplicate / name_collision: 两个实体对比 -->
          <template v-if="c.candidate_type === 'duplicate' || c.candidate_type === 'name_collision'">
            <div class="entity-pair">
              <div class="entity-box" @click="focusEntity(c.entity_a_id)">
                <div class="entity-name">{{ c.entity_a_name }}</div>
                <div class="entity-id">{{ c.entity_a_id }}</div>
              </div>
              <div class="pair-symbol">{{ c.candidate_type === 'duplicate' ? '~' : '≠' }}</div>
              <div class="entity-box" @click="focusEntity(c.entity_b_id)">
                <div class="entity-name">{{ c.entity_b_name }}</div>
                <div class="entity-id">{{ c.entity_b_id }}</div>
              </div>
            </div>
          </template>

          <!-- low_confidence: 单个实体 -->
          <template v-else-if="c.candidate_type === 'low_confidence'">
            <div class="entity-single" @click="focusEntity(c.entity_a_id)">
              <div class="entity-name">{{ c.entity_a_name }}</div>
              <div class="entity-id">{{ c.entity_a_id }}</div>
            </div>
          </template>

          <!-- relation_direction: 关系 -->
          <template v-else-if="c.candidate_type === 'relation_direction'">
            <div class="entity-pair">
              <div class="entity-box">
                <div class="entity-name">{{ c.entity_a_name }}</div>
              </div>
              <div class="pair-symbol">→</div>
              <div class="entity-box">
                <div class="entity-name">{{ c.entity_b_name }}</div>
              </div>
            </div>
          </template>

          <div v-if="c.reason" class="reason-text">{{ c.reason }}</div>

          <!-- 内联编辑表单 -->
          <div v-if="editingId === c.id" class="inline-edit">
            <input v-model="editForm.name" placeholder="名称" class="edit-input" />
            <textarea v-model="editForm.description" placeholder="描述" class="edit-textarea" rows="2"></textarea>
            <input v-model="editForm.aliasesStr" placeholder="别名（逗号分隔）" class="edit-input" />
            <div class="edit-btns">
              <button class="action-btn confirm" @click="saveEdit(c)">💾 保存</button>
              <button class="action-btn" @click="editingId = null">取消</button>
            </div>
          </div>
        </div>

        <!-- 操作栏 -->
        <div v-if="c.status === 'pending'" class="card-actions">
          <template v-if="c.candidate_type === 'duplicate'">
            <button class="action-btn merge" @click="mergeCandidate(c)">🔗 合并到 A</button>
            <button class="action-btn ignore" @click="ignoreCandidate(c)">忽略</button>
          </template>
          <template v-else-if="c.candidate_type === 'name_collision'">
            <button class="action-btn confirm" @click="confirmCandidate(c)">✅ 确认不同</button>
            <button class="action-btn merge" @click="mergeCandidate(c)">🔗 合并</button>
            <button class="action-btn ignore" @click="ignoreCandidate(c)">忽略</button>
          </template>
          <template v-else-if="c.candidate_type === 'low_confidence'">
            <button class="action-btn confirm" @click="confirmCandidate(c)">✅ 确认</button>
            <button class="action-btn edit" @click="startEdit(c)">✏️ 编辑</button>
            <button class="action-btn ignore" @click="ignoreCandidate(c)">忽略</button>
          </template>
          <template v-else-if="c.candidate_type === 'relation_direction'">
            <button class="action-btn merge" @click="flipRelation(c)">🔄 翻转方向</button>
            <button class="action-btn ignore" @click="ignoreCandidate(c)">忽略</button>
          </template>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination">
      <button @click="page--; loadCandidates()" :disabled="page <= 1">← 上一页</button>
      <span class="page-info">{{ page }} / {{ totalPages }}</span>
      <button @click="page++; loadCandidates()" :disabled="page >= totalPages">下一页 →</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'

const router = useRouter()

const candidates = ref([])
const loading = ref(false)
const filterType = ref('')
const filterStatus = ref('pending')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const pendingCount = ref(0)
const editingId = ref(null)
const editForm = ref({ name: '', description: '', aliasesStr: '' })

const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)

function typeTagLabel(type) {
  const map = { duplicate: '疑似重复', name_collision: '同名消歧', low_confidence: '低置信度', relation_direction: '方向可疑' }
  return map[type] || type
}

function statusLabel(status) {
  const map = { pending: '待审核', merged: '已合并', confirmed: '已确认', ignored: '已忽略', edited: '已编辑' }
  return map[status] || status
}

function formatTime(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadCandidates() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filterType.value) params.candidate_type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value
    const resp = await request.get('/api/graph/candidates', { params })
    candidates.value = resp.data.candidates || []
    total.value = resp.data.pagination?.total || 0

    // 同时刷新待审核计数
    const countResp = await request.get('/api/graph/candidates/count')
    pendingCount.value = countResp.data.pending_count || 0
  } catch (e) {
    console.error('Failed to load candidates:', e)
  } finally {
    loading.value = false
  }
}

async function mergeCandidate(c) {
  if (!confirm(`确认将「${c.entity_b_name}」合并到「${c.entity_a_name}」？\n合并后 B 的名称和关系将全部归入 A。`)) return
  try {
    await request.post(`/api/graph/candidates/${c.id}/merge`)
    c.status = 'merged'
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  } catch (e) {
    alert('合并失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function confirmCandidate(c) {
  try {
    await request.post(`/api/graph/candidates/${c.id}/confirm`)
    c.status = 'confirmed'
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  } catch (e) {
    alert('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function ignoreCandidate(c) {
  try {
    await request.post(`/api/graph/candidates/${c.id}/ignore`)
    c.status = 'ignored'
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  } catch (e) {
    alert('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

function startEdit(c) {
  editingId.value = c.id
  editForm.value = { name: c.entity_a_name, description: '', aliasesStr: '' }
}

async function saveEdit(c) {
  try {
    const body = {}
    if (editForm.value.name) body.name = editForm.value.name
    if (editForm.value.description) body.description = editForm.value.description
    if (editForm.value.aliasesStr) {
      body.aliases = editForm.value.aliasesStr.split(/[,，]/).map(s => s.trim()).filter(Boolean)
    }
    await request.put(`/api/graph/entities/${c.entity_a_id}`, body)
    await request.post(`/api/graph/candidates/${c.id}/confirm`)
    c.status = 'edited'
    editingId.value = null
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  } catch (e) {
    alert('编辑失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function flipRelation(c) {
  if (!confirm(`确认翻转「${c.entity_a_name} → ${c.entity_b_name}」的方向？`)) return
  try {
    await request.post(`/api/graph/relations/${c.entity_a_id}/flip`)
    await request.post(`/api/graph/candidates/${c.id}/confirm`)
    c.status = 'confirmed'
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  } catch (e) {
    alert('翻转失败: ' + (e.response?.data?.detail || e.message))
  }
}

function focusEntity(entityId) {
  if (!entityId) return
  router.push({ path: '/graph', query: { focus: entityId } })
}

onMounted(() => {
  loadCandidates()
})
</script>

<style scoped>
.review-page {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
  min-height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
  flex-wrap: wrap;
}

.header-left h2 {
  margin: 0 0 4px 0;
  font-size: 20px;
  color: #111827;
}

.header-desc {
  font-size: 13px;
  color: #6b7280;
}

.header-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.filter-select {
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: white;
}

.refresh-btn {
  padding: 6px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 13px;
}
.refresh-btn:hover { background: #f3f4f6; }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.stat-item {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
}

.stat-item.pending { border-left: 3px solid #f59e0b; }
.stat-num { font-size: 24px; font-weight: 600; color: #111827; }
.stat-label { font-size: 12px; color: #6b7280; margin-top: 2px; }

.loading-state, .empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-state h3 { color: #374151; margin: 8px 0; }

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.candidate-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  border-left: 4px solid #d1d5db;
  overflow: hidden;
  transition: box-shadow 0.15s;
}

.candidate-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.candidate-card.type-duplicate { border-left-color: #f59e0b; }
.candidate-card.type-name_collision { border-left-color: #8b5cf6; }
.candidate-card.type-low_confidence { border-left-color: #3b82f6; }
.candidate-card.type-relation_direction { border-left-color: #ef4444; }
.candidate-card.status-merged, .candidate-card.status-confirmed, .candidate-card.status-ignored { opacity: 0.6; }

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f9fafb;
  border-bottom: 1px solid #f3f4f6;
}

.type-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.type-tag.duplicate { background: #fef3c7; color: #92400e; }
.type-tag.name_collision { background: #ede9fe; color: #5b21b6; }
.type-tag.low_confidence { background: #dbeafe; color: #1e40af; }
.type-tag.relation_direction { background: #fee2e2; color: #991b1b; }

.score-tag {
  font-size: 12px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
}

.status-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}
.status-tag.pending { background: #fef3c7; color: #92400e; }
.status-tag.merged { background: #d1fae5; color: #065f46; }
.status-tag.confirmed { background: #dbeafe; color: #1e40af; }
.status-tag.ignored { background: #f3f4f6; color: #6b7280; }

.time-tag {
  margin-left: auto;
  font-size: 12px;
  color: #9ca3af;
}

.card-body {
  padding: 12px 14px;
}

.entity-pair {
  display: flex;
  align-items: center;
  gap: 12px;
}

.entity-box {
  flex: 1;
  padding: 8px 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  cursor: pointer;
}
.entity-box:hover { background: #f3f4f6; }

.entity-single {
  padding: 8px 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  cursor: pointer;
  display: inline-block;
}
.entity-single:hover { background: #f3f4f6; }

.entity-name { font-size: 14px; font-weight: 500; color: #111827; }
.entity-id { font-size: 11px; color: #9ca3af; margin-top: 2px; font-family: monospace; }

.pair-symbol {
  font-size: 20px;
  font-weight: bold;
  color: #9ca3af;
  min-width: 24px;
  text-align: center;
}

.reason-text {
  font-size: 13px;
  color: #6b7280;
  margin-top: 8px;
  line-height: 1.5;
}

.inline-edit {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.edit-input, .edit-textarea {
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  font-size: 13px;
  font-family: inherit;
}
.edit-input:focus, .edit-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.edit-btns {
  display: flex;
  gap: 6px;
}

.card-actions {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  background: #f9fafb;
  border-top: 1px solid #f3f4f6;
}

.action-btn {
  padding: 5px 12px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  background: white;
  transition: all 0.15s;
}
.action-btn:hover { transform: translateY(-1px); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.action-btn.merge { border-color: #f59e0b; color: #92400e; }
.action-btn.merge:hover { background: #fef3c7; }
.action-btn.confirm { border-color: #10b981; color: #065f46; }
.action-btn.confirm:hover { background: #d1fae5; }
.action-btn.ignore { border-color: #9ca3af; color: #6b7280; }
.action-btn.ignore:hover { background: #f3f4f6; }
.action-btn.edit { border-color: #3b82f6; color: #1e40af; }
.action-btn.edit:hover { background: #dbeafe; }

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
  padding: 12px;
}

.pagination button {
  padding: 6px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 13px;
}
.pagination button:hover:not(:disabled) { background: #f3f4f6; }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: #6b7280; }

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
