<template>
  <div class="review-panel">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span v-if="!loading && items.length > 0" class="count-badge">
          {{ items.length }} 项待审
        </span>
      </div>
      <button class="refresh-btn" @click="loadPoolItems" :disabled="loading">
        <svg class="icon" :class="{ spinning: loading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
        </svg>
        刷新
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <div class="loading-spinner"></div>
      <span class="loading-text">加载中...</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="items.length === 0" class="empty-container">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p class="empty-title">暂无待审核项目</p>
      <p class="empty-desc">所有提交的内容都已审核完毕</p>
    </div>

    <!-- 审核列表 -->
    <div v-else class="review-list">
      <div v-for="item in items" :key="item.id" class="review-card">
        <!-- 卡片头部 -->
        <div class="card-header">
          <div class="card-meta">
            <span class="type-tag">
              <svg class="tag-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              技能
            </span>
            <h3 class="item-name">{{ item.content_name }}</h3>
          </div>
          <div class="card-sub">
            <span class="submitter">
              <svg class="sub-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              {{ item.owner_name || `用户 ${item.owner_id}` }}
            </span>
            <span class="submit-time">
              <svg class="time-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
              {{ formatTime(item.created_at) }}
            </span>
          </div>
        </div>

        <!-- 详情区域 -->
        <div class="card-body">
          <button class="detail-toggle" @click="viewDetail(item)">
            <svg class="toggle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            {{ detailItem === item ? '收起详情' : '查看详情' }}
          </button>
          
          <Transition name="slide">
            <div v-if="detailItem === item" class="detail-wrapper">
              <div v-if="detailLoading" class="detail-loading">
                <div class="loading-spinner small"></div>
              </div>
              <pre v-else-if="detailContent" class="detail-content">{{ detailContent }}</pre>
              <div v-else class="detail-error">无法加载详情</div>
            </div>
          </Transition>
        </div>

        <!-- 操作按钮 -->
        <div class="card-actions">
          <button 
            @click="approveItem(item.id)" 
            class="action-btn approve"
            :disabled="actionLoading === item.id"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M5 13l4 4L19 7" />
            </svg>
            通过
          </button>
          <button 
            @click="rejectItem(item.id)" 
            class="action-btn reject"
            :disabled="actionLoading === item.id"
          >
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
            拒绝
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as AdminAPI from '@/api/admin'

interface PoolItem {
  id: number
  content_type: string
  content_name: string
  owner_id: number
  owner_name?: string
  submitted_by?: string
  definition?: any
  status: string
  created_at: string
}

const items = ref<PoolItem[]>([])
const loading = ref(false)
const actionLoading = ref<number | null>(null)
const detailItem = ref<PoolItem | null>(null)
const detailLoading = ref(false)
const detailContent = ref<string | null>(null)

function formatTime(time: string): string {
  if (!time) return '-'
  const d = new Date(time)
  if (isNaN(d.getTime())) return time
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function loadPoolItems() {
  loading.value = true
  try {
    items.value = await AdminAPI.getPendingPoolItems()
    detailItem.value = null
    detailContent.value = null
  } catch (e) {
    console.error('加载技能池审核列表失败:', e)
  } finally {
    loading.value = false
  }
}

import request from '@/api/request'

async function viewDetail(item: PoolItem) {
  if (detailItem.value === item) {
    detailItem.value = null
    return
  }
  detailItem.value = item
  detailLoading.value = true
  detailContent.value = null
  
  // 尝试加载技能内容
  try {
    const resp = await request.get(`/api/skills/${encodeURIComponent(item.content_name)}`)
    detailContent.value = resp.data.content || resp.data.body || JSON.stringify(resp.data, null, 2)
  } catch {
    detailContent.value = null
  } finally {
    detailLoading.value = false
  }
}

async function approveItem(id: number) {
  if (!confirm('确定通过审核？')) return
  actionLoading.value = id
  try {
    await AdminAPI.approvePoolItem(id)
    await loadPoolItems()
    alert('已通过审核')
  } catch (e) {
    console.error('审批失败:', e)
    alert('审批失败：' + (e as Error).message)
  } finally {
    actionLoading.value = null
  }
}

async function rejectItem(id: number) {
  const comment = prompt('拒绝原因（必填）:')
  if (!comment) return
  if (!confirm('确定拒绝此内容？')) return
  actionLoading.value = id
  try {
    await AdminAPI.rejectPoolItem(id, comment)
    await loadPoolItems()
    alert('已拒绝，原因已记录')
  } catch (e) {
    console.error('拒绝失败:', e)
    alert('拒绝失败：' + (e as Error).message)
  } finally {
    actionLoading.value = null
  }
}

onMounted(() => {
  loadPoolItems()
})
</script>

<style scoped>
.review-panel {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

/* ─── 工具栏 ─── */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-primary);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.count-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--brand);
  background: var(--brand-light);
  padding: 5px 12px;
  border-radius: var(--radius-md);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--brand);
  color: var(--brand);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-btn .icon {
  width: 14px;
  height: 14px;
}

.refresh-btn .icon.spinning {
  animation: spin 1s linear infinite;
}

/* ─── 加载状态 ─── */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 16px;
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border-primary);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-spinner.small {
  width: 18px;
  height: 18px;
  border-width: 2px;
}

.loading-text {
  color: var(--text-secondary);
  font-size: 14px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── 空状态 ─── */
.empty-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-light);
  border-radius: 50%;
  margin-bottom: 16px;
}

.empty-icon svg {
  width: 28px;
  height: 28px;
  color: var(--brand);
}

.empty-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.empty-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* ─── 审核列表 ─── */
.review-list {
  padding: 12px;
}

.review-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  margin-bottom: 12px;
  transition: var(--transition);
}

.review-card:hover {
  border-color: var(--border-secondary);
  box-shadow: var(--shadow-sm);
}

.review-card:last-child {
  margin-bottom: 0;
}

/* ─── 卡片头部 ─── */
.card-header {
  padding: 16px 18px 12px;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.type-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
  background: var(--brand-light);
  color: var(--brand);
}

.tag-icon {
  width: 12px;
  height: 12px;
}

.item-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-sub {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.submitter,
.submit-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sub-icon,
.time-icon {
  width: 12px;
  height: 12px;
  opacity: 0.7;
}

/* ─── 卡片主体 ─── */
.card-body {
  padding: 12px 18px;
}

.detail-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}

.detail-toggle:hover {
  background: var(--brand-light);
  border-color: var(--brand);
  color: var(--brand);
}

.toggle-icon {
  width: 13px;
  height: 13px;
}

.detail-wrapper {
  margin-top: 12px;
}

.detail-loading {
  display: flex;
  justify-content: center;
  padding: 16px;
}

.detail-content {
  background: var(--bg-code);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 14px;
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  overflow-x: auto;
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-error {
  color: var(--text-tertiary);
  font-size: 12px;
  text-align: center;
  padding: 16px;
}

/* ─── 操作按钮 ─── */
.card-actions {
  display: flex;
  gap: 10px;
  padding: 12px 18px 16px;
  border-top: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 18px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
  border: none;
}

.action-btn .btn-icon {
  width: 14px;
  height: 14px;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.approve {
  background: var(--brand-gradient);
  color: #fff;
  box-shadow: var(--brand-shadow);
}

.action-btn.approve:hover:not(:disabled) {
  box-shadow: var(--brand-shadow-lg);
}

.action-btn.reject {
  background: var(--bg-primary);
  color: var(--text-danger);
  border: 1px solid var(--border-danger);
}

.action-btn.reject:hover:not(:disabled) {
  background: var(--bg-danger);
}

/* ─── 动画 ─── */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ─── 响应式 ─── */
@media (max-width: 640px) {
  .toolbar {
    flex-direction: column;
    gap: 10px;
    align-items: stretch;
  }
  
  .card-meta {
    flex-wrap: wrap;
  }
  
  .card-sub {
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .card-actions {
    flex-direction: column;
  }
}
</style>