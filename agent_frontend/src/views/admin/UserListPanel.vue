<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">用户列表</h2>
    </div>
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>
    <div v-else-if="users.length === 0" class="empty-state">
      <p>暂无用户</p>
    </div>
    <div v-else class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>部门</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td>
              <select v-model="user.role" @change="updateUserRole(user)" class="select-sm">
                <option v-for="role in roles" :key="role.id" :value="role.name">
                  {{ role.display_name || role.name }}
                </option>
              </select>
            </td>
            <td>
              <button class="btn-link" @click="openLayerEdit(user)">
                {{ getUserLayerNames(user) }}
              </button>
            </td>
            <td>
              <span :class="['status-badge', user.status === 1 ? 'status-active' : 'status-inactive']">
                {{ user.status === 1 ? '正常' : '已禁用' }}
              </span>
            </td>
            <td>{{ formatTime(user.created_at) }}</td>
            <td>
              <button @click="toggleUserStatus(user)" class="btn-link">
                {{ user.status === 1 ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 部门编辑对话框 -->
    <div v-if="showLayerDialog" class="dialog-overlay" @click="closeLayerDialog">
      <div class="dialog" @click.stop>
        <div class="dialog-header">
          <h3>编辑用户部门</h3>
          <button class="btn-close" @click="closeLayerDialog">×</button>
        </div>
        <div class="dialog-body">
          <p class="dialog-user">用户：<b>{{ editingUser?.username }}</b></p>
          <div class="layer-checkboxes">
            <label v-for="layer in layers" :key="layer.id" class="layer-checkbox">
              <input type="checkbox" :value="layer.id" v-model="editingLayerIds" />
              <span>{{ layer.name }}</span>
            </label>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn" @click="closeLayerDialog">取消</button>
          <button class="btn btn-primary" @click="saveUserLayers" :disabled="savingLayers">
            {{ savingLayers ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as AdminAPI from '@/api/admin'
import type { User, Role, DataLayer } from '@/api/admin'

const users = ref<(User & { layer_ids?: number[] })[]>([])
const roles = ref<Role[]>([])
const layers = ref<DataLayer[]>([])
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  try {
    users.value = await AdminAPI.getUsers()
    // 加载每个用户的部门
    for (const user of users.value) {
      try {
        user.layer_ids = await AdminAPI.getUserDataLayers(user.id)
      } catch {
        user.layer_ids = [0]
      }
    }
  } catch (e) {
    console.error('加载用户失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  try {
    roles.value = await AdminAPI.getRoles()
  } catch (e) {
    console.error('加载角色失败:', e)
  }
}

async function loadLayers() {
  try {
    layers.value = await AdminAPI.getDataLayers()
  } catch (e) {
    console.error('加载部门失败:', e)
  }
}

async function updateUserRole(user: User) {
  try {
    await AdminAPI.updateUserRole(user.id, user.role)
    alert(`✅ 用户 ${user.username} 的角色已更新为 ${user.role}`)
  } catch (e) {
    console.error('更新用户角色失败:', e)
    alert('❌ 更新角色失败')
    await loadUsers()
  }
}

// ── 部门编辑对话框 ──
const showLayerDialog = ref(false)
const editingUser = ref<(User & { layer_ids?: number[] }) | null>(null)
const editingLayerIds = ref<number[]>([])
const savingLayers = ref(false)

function getUserLayerNames(user: User & { layer_ids?: number[] }): string {
  if (!user.layer_ids || user.layer_ids.length === 0) return '全员'
  const names = user.layer_ids.map(id => {
    const layer = layers.value.find(l => l.id === id)
    return layer ? layer.name : `层级${id}`
  })
  return names.join(', ')
}

function openLayerEdit(user: User & { layer_ids?: number[] }) {
  editingUser.value = user
  editingLayerIds.value = [...(user.layer_ids || [0])]
  showLayerDialog.value = true
}

function closeLayerDialog() {
  showLayerDialog.value = false
  editingUser.value = null
  editingLayerIds.value = []
}

async function saveUserLayers() {
  if (!editingUser.value) return
  const userName = editingUser.value.username
  savingLayers.value = true
  try {
    const layerIds = editingLayerIds.value.length > 0 ? editingLayerIds.value : [0]
    await AdminAPI.setUserDataLayers(editingUser.value.id, layerIds)
    editingUser.value.layer_ids = layerIds
    closeLayerDialog()
    alert(`✅ 用户 ${userName} 的部门已更新`)
  } catch (e) {
    console.error('更新用户部门失败:', e)
    alert('❌ 更新部门失败')
  } finally {
    savingLayers.value = false
  }
}

async function toggleUserStatus(user: User) {
  const newStatus = user.status === 1 ? 0 : 1
  try {
    await AdminAPI.updateUserStatus(user.id, newStatus)
    user.status = newStatus
    alert(`✅ 用户 ${user.username} 已${newStatus === 1 ? '启用' : '禁用'}`)
  } catch (e) {
    console.error('更新用户状态失败:', e)
    alert('❌ 操作失败')
  }
}

function formatTime(time?: string): string {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

onMounted(() => {
  loadUsers()
  loadRoles()
  loadLayers()
})
</script>

<style scoped>
.section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-primary);
  width: 100%;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px 20px;
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

.table-container {
  overflow-x: auto;
  background: var(--bg-primary);
  border-radius: 12px;
  border: 1px solid var(--border-primary);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-primary);
}

.data-table th {
  background: var(--bg-secondary);
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
}

.data-table td {
  font-size: 14px;
  color: var(--text-primary);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.select-sm {
  padding: 4px 8px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
}

.status-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-active {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-inactive {
  background: #ffebee;
  color: #c62828;
}

.btn-link {
  background: none;
  border: none;
  color: var(--brand);
  cursor: pointer;
  font-size: 13px;
  text-decoration: underline;
}

.btn-link:hover {
  color: var(--brand-hover);
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 420px;
}

.dialog-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
}

.dialog-body {
  padding: 20px;
}

.dialog-user {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.layer-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.layer-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  cursor: pointer;
  padding: 6px 10px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  transition: all 0.15s;
}

.layer-checkbox:hover {
  background: var(--bg-hover);
}

.layer-checkbox input {
  width: auto;
  margin: 0;
}

.dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border-primary);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn {
  padding: 8px 16px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: var(--bg-primary);
  cursor: pointer;
  font-size: 14px;
}

.btn-primary {
  background: var(--brand);
  color: white;
  border-color: var(--brand);
}

.btn-primary:hover {
  background: var(--brand-hover);
}
</style>
