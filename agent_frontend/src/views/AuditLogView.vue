<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">操作审计日志</h1>
        <p class="page-desc">AI 在对话中执行的服务器命令、SQL 查询、审批记录全留痕</p>
      </div>
      <button class="btn btn-secondary" @click="loadData">🔄 刷新</button>
    </header>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'operations' }" @click="switchTab('operations')">🖥️ AI 操作</button>
      <button class="tab-btn" :class="{ active: activeTab === 'sql' }" @click="switchTab('sql')">🗄️ SQL 操作</button>
      <button class="tab-btn" :class="{ active: activeTab === 'memory' }" @click="switchTab('memory')">🧠 记忆操作</button>
      <button class="tab-btn" :class="{ active: activeTab === 'approvals' }" @click="switchTab('approvals')">🔐 审批记录</button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>用户筛选：</label>
        <select v-model="filterUserId" class="input" @change="loadData">
          <option :value="null">全部用户</option>
          <option v-for="u in whitelistUsers" :key="u.id" :value="u.id">
            {{ u.username }} ({{ u.role === 'super_admin' ? '超管' : u.role === 'admin' ? '管理员' : '用户' }})
          </option>
        </select>
      </div>
      <div v-if="activeTab === 'operations'" class="filter-group">
        <label>目标主机：</label>
        <input v-model="filterHost" class="input" placeholder="输入主机名/IP" @keyup.enter="loadData" />
      </div>
      <div v-if="activeTab === 'operations'" class="filter-group">
        <label>操作类型：</label>
        <select v-model="filterOpType" class="input" @change="loadData">
          <option value="">全部</option>
          <option value="ssh_remote">远程执行</option>
          <option value="blocked">已拦截</option>
        </select>
      </div>
      <div v-if="activeTab === 'sql'" class="filter-group">
        <label>执行状态：</label>
        <select v-model="filterSqlStatus" class="input" @change="loadData">
          <option :value="null">全部</option>
          <option :value="1">成功</option>
          <option :value="0">失败</option>
        </select>
      </div>
      <div v-if="activeTab === 'memory'" class="filter-group">
        <label>操作类型：</label>
        <select v-model="filterMemAction" class="input" @change="loadData">
          <option value="">全部</option>
          <option value="create">创建</option>
          <option value="update">更新</option>
          <option value="delete">删除</option>
          <option value="search">搜索</option>
          <option value="promote">晋升</option>
          <option value="restore">恢复</option>
          <option value="consolidate">合并</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading-state"><div class="spinner"></div><p>加载中...</p></div>

    <!-- ── AI 操作日志 ── -->
    <template v-else-if="activeTab === 'operations'">
      <div v-if="operations.length === 0" class="empty-state"><p>暂无操作记录</p></div>
      <table v-else class="audit-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>用户</th>
            <th>会话</th>
            <th>操作类型</th>
            <th>目标主机</th>
            <th>执行命令</th>
            <th>状态</th>
            <th>审核人</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="op in operations" :key="op.id" :class="'row-' + op.status">
            <td class="col-time">{{ formatTime(op.created_at) }}</td>
            <td>{{ op.username || `user_${op.user_id}` }}</td>
            <td><code class="thread-tag" :title="op.thread_id">{{ truncate(op.thread_id, 16) }}</code></td>
            <td><span class="op-type-tag" :class="op.operation_type">{{ opTypeLabel(op.operation_type) }}</span></td>
            <td><code class="host-tag">{{ op.target_host || '-' }}</code></td>
            <td class="col-cmd" :title="op.command">{{ truncate(op.command, 60) }}</td>
            <td><span class="status-dot" :class="statusClass(op.status)">{{ statusLabel(op.status) }}</span></td>
            <td>{{ getApprover(op) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- ── SQL 操作日志 ── -->
    <template v-else-if="activeTab === 'sql'">
      <div v-if="sqlOperations.length === 0" class="empty-state"><p>暂无 SQL 操作记录</p></div>
      <table v-else class="audit-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>用户</th>
            <th>会话</th>
            <th>SQL 语句</th>
            <th>状态</th>
            <th>错误信息</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="op in sqlOperations" :key="op.id" :class="'row-' + op.status">
            <td class="col-time">{{ formatTime(op.created_at) }}</td>
            <td>{{ op.username || `user_${op.user_id}` }}</td>
            <td><code class="thread-tag" :title="op.thread_id">{{ truncate(op.thread_id, 16) }}</code></td>
            <td class="col-sql" :title="op.query"><code>{{ truncate(op.query, 100) }}</code></td>
            <td><span class="status-dot" :class="op.status === 1 ? 'ok' : 'blocked'">{{ op.status === 1 ? '✓ 成功' : '⛔ 失败' }}</span></td>
            <td class="col-summary" :title="op.error_message">{{ truncate(op.error_message, 40) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- ── 记忆操作日志 ── -->
    <template v-else-if="activeTab === 'memory'">
      <div v-if="memoryOperations.length === 0" class="empty-state"><p>暂无记忆操作记录</p></div>
      <table v-else class="audit-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>用户</th>
            <th>操作</th>
            <th>记忆层</th>
            <th>记忆 ID</th>
            <th>详情</th>
            <th>IP</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="op in memoryOperations" :key="op.id" :class="'row-' + op.status">
            <td class="col-time">{{ formatTime(op.created_at) }}</td>
            <td>{{ op.username || `user_${op.user_id}` }}</td>
            <td><span class="mem-action-tag" :class="op.action">{{ memActionLabel(op.action) }}</span></td>
            <td><span class="layer-tag" :class="op.memory_layer">{{ layerLabel(op.memory_layer) }}</span></td>
            <td>{{ op.memory_id || '-' }}</td>
            <td class="col-detail" :title="op.detail">{{ truncate(op.detail, 60) }}</td>
            <td><code class="ip-tag">{{ op.ip_address || '-' }}</code></td>
            <td><span class="status-dot" :class="op.status === 1 ? 'ok' : 'blocked'">{{ op.status === 1 ? '✓ 成功' : '⛔ 失败' }}</span></td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- ── 审批记录 ── -->
    <template v-else>
      <div v-if="approvals.length === 0" class="empty-state"><p>暂无审批记录</p></div>
      <table v-else class="audit-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>会话</th>
            <th>命令</th>
            <th>决议</th>
            <th>审核人</th>
            <th>审核人ID</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in approvals" :key="a.id">
            <td class="col-time">{{ formatTime(a.created_at) }}</td>
            <td><code class="thread-tag" :title="a.thread_id">{{ truncate(a.thread_id, 20) }}</code></td>
            <td class="col-cmd" :title="a.command">{{ truncate(a.command, 80) }}</td>
            <td><span class="decision-tag" :class="a.decision">{{ decisionLabel(a.decision) }}</span></td>
            <td>{{ a.confirmed_by_name || '-' }}</td>
            <td>{{ a.confirmed_by_user_id || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import request from '@/api/request'
import { errMsg } from '@/utils/err'

const activeTab = ref('operations')
const loading = ref(false)
const operations = ref<any[]>([])
const approvals = ref<any[]>([])
const sqlOperations = ref<any[]>([])
const memoryOperations = ref<any[]>([])
const whitelistUsers = ref<any[]>([])
const filterUserId = ref<number | null>(null)
const filterHost = ref('')
const filterOpType = ref('')
const filterSqlStatus = ref<number | null>(null)
const filterMemAction = ref('')

function formatTime(dt: string) {
  if (!dt) return '-'
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

function truncate(s: string, max: number) {
  if (!s) return '-'
  return s.length > max ? s.slice(0, max) + '…' : s
}

function opTypeLabel(t: string) {
  const map: Record<string, string> = { ssh_remote: '远程执行', blocked: '已拦截' }
  return map[t] || t || '-'
}

function statusClass(s: number) {
  if (s === 0) return 'blocked'
  if (s === 2) return 'approved'
  return 'ok'
}

function statusLabel(s: number) {
  if (s === 0) return '⛔ 拦截'
  if (s === 2) return '✅ 已审批'
  return '✓ 成功'
}

function decisionLabel(d: string) {
  const map: Record<string, string> = { 'allow-once': '✓ 允许本次', 'allow-session': '✓ 本会话允许', 'allow-always': '✓ 永远允许', 'deny': '✗ 拒绝' }
  return map[d] || d || '-'
}

function memActionLabel(a: string) {
  const map: Record<string, string> = {
    create: '📝 创建', update: '✏️ 更新', delete: '🗑️ 删除',
    search: '🔍 搜索', promote: '⬆️ 晋升', restore: '↩️ 恢复',
    consolidate: '🔀 合并', read: '👁️ 查看'
  }
  return map[a] || a || '-'
}

function layerLabel(l: string) {
  const map: Record<string, string> = { legacy: '📦 Legacy', episodic: '📝 情景', semantic: '💎 语义' }
  return map[l] || l || '-'
}

function getApprover(op: any) {
  if (!op.thread_id) return '-'
  const approval = approvals.value.find(a => a.thread_id === op.thread_id)
  if (approval) {
    const name = approval.confirmed_by_name || '-'
    const decision = approval.decision || ''
    if (decision.startsWith('allow')) return `✓ ${name}`
    else if (decision === 'deny') return `✗ ${name}`
    return name
  }
  return op.status === 0 ? '-' : '待查'
}

function switchTab(tab: string) {
  activeTab.value = tab
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    if (activeTab.value === 'operations') {
      const params: any = { limit: 200 }
      if (filterUserId.value) params.user_id = filterUserId.value
      if (filterHost.value) params.target_host = filterHost.value
      if (filterOpType.value) params.operation_type = filterOpType.value
      const [opsRes, approvalsRes] = await Promise.all([
        request.get('/api/admin/agent-operations', { params }),
        request.get('/api/admin/exec-approvals', { params: { limit: 200 } })
      ])
      operations.value = opsRes.data
      approvals.value = approvalsRes.data
    } else if (activeTab.value === 'sql') {
      const params: any = { limit: 200 }
      if (filterUserId.value) params.user_id = filterUserId.value
      if (filterSqlStatus.value !== null) params.status = filterSqlStatus.value
      const res = await request.get('/api/admin/sql-operations', { params })
      sqlOperations.value = res.data
    } else if (activeTab.value === 'memory') {
      const params: any = { limit: 200 }
      if (filterUserId.value) params.user_id = filterUserId.value
      if (filterMemAction.value) params.action = filterMemAction.value
      const res = await request.get('/api/admin/memory-operations', { params })
      memoryOperations.value = res.data
    } else {
      const res = await request.get('/api/admin/exec-approvals', { params: { limit: 200 } })
      approvals.value = res.data
    }
  } catch (e: any) {
    alert('加载失败: ' + errMsg(e))
  } finally {
    loading.value = false
  }
}

async function loadWhitelistUsers() {
  try {
    const res = await request.get('/api/admin/users-with-whitelist-perm')
    whitelistUsers.value = res.data
  } catch (e: any) {
    console.error('加载用户列表失败:', e)
  }
}

onMounted(() => {
  loadWhitelistUsers()
  loadData()
})
</script>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Tab 栏 */
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-primary);
  padding-bottom: 8px;
}

.tab-btn {
  padding: 8px 20px;
  border-radius: 8px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.tab-btn.active {
  background: var(--brand-gradient);
  color: white;
  border-color: transparent;
  font-weight: 500;
}

.filter-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.input {
  padding: 6px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  min-width: 150px;
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--border-primary);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-primary);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  overflow: hidden;
}

.audit-table th, .audit-table td {
  padding: 10px 12px;
  text-align: left;
  font-size: 13px;
  border-bottom: 1px solid var(--border-primary);
}

.audit-table th {
  background: var(--bg-secondary);
  font-weight: 600;
  font-size: 12px;
}

.col-time {
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary);
}

.col-cmd {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.col-sql {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.col-summary {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-secondary);
}

.thread-tag {
  font-size: 11px;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.host-tag {
  font-size: 12px;
  background: #e3f2fd;
  color: #1565c0;
  padding: 2px 8px;
  border-radius: 4px;
}

.op-type-tag {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.op-type-tag.ssh_remote {
  background: #e8f5e9;
  color: #2e7d32;
}

.op-type-tag.blocked {
  background: #ffebee;
  color: #c62828;
}

.status-dot {
  font-size: 12px;
  font-weight: 500;
}

.status-dot.blocked {
  color: #c62828;
}

.status-dot.approved {
  color: #2e7d32;
}

.status-dot.ok {
  color: #1565c0;
}

.row-0 {
  background: rgba(198, 40, 40, 0.03);
}

.decision-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}

.decision-tag.allow-once, .decision-tag.allow-session, .decision-tag.allow-always {
  background: #e8f5e9;
  color: #2e7d32;
}

.decision-tag.deny {
  background: #ffebee;
  color: #c62828;
}

/* 记忆操作标签 */
.col-detail {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary);
}

.mem-action-tag {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.mem-action-tag.create { background: #e8f5e9; color: #2e7d32; }
.mem-action-tag.update { background: #fff3e0; color: #e65100; }
.mem-action-tag.delete { background: #ffebee; color: #c62828; }
.mem-action-tag.search { background: #e3f2fd; color: #1565c0; }
.mem-action-tag.promote { background: #ede7f6; color: #4527a0; }
.mem-action-tag.restore { background: #e0f7fa; color: #00695c; }
.mem-action-tag.consolidate { background: #fce4ec; color: #ad1457; }
.mem-action-tag.read { background: #f3e5f5; color: #6a1b9a; }

.layer-tag {
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 11px;
  white-space: nowrap;
}

.layer-tag.legacy { background: #efebe9; color: #4e342e; }
.layer-tag.episodic { background: #fff8e1; color: #f57f17; }
.layer-tag.semantic { background: #e8eaf6; color: #283593; }

.ip-tag {
  font-size: 11px;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
