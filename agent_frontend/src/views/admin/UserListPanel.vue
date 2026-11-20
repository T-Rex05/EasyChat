<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">用户列表</h2>
      <button v-if="auth.hasPerm('system.manage')" type="button" class="btn btn-primary" @click="openCreateDialog">
        添加用户
      </button>
    </div>
    <p class="status-feedback" role="status">{{ statusFeedback }}</p>
    <p class="status-error" role="alert">{{ statusError }}</p>
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
              <span :class="['status-badge', user.status === 1 ? 'status-active' : 'status-inactive']">
                {{ user.status === 1 ? '正常' : '已禁用' }}
              </span>
            </td>
            <td>{{ formatTime(user.created_at) }}</td>
            <td>
              <button
                type="button"
                class="btn btn-sm user-status-action"
                :class="user.status === 1 ? 'btn-danger' : 'btn-secondary'"
                :disabled="!!statusRestriction(user) || updatingStatus.has(user.id)"
                :aria-label="`${user.status === 1 ? '禁用' : '启用'} ${user.username}`"
                :title="statusRestriction(user) || undefined"
                @click="toggleUserStatus(user)"
              >
                {{ updatingStatus.has(user.id) ? '更新中…' : user.status === 1 ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <dialog
      ref="createDialog"
      class="create-dialog"
      :aria-labelledby="`${createId}-title`"
      @cancel="onCreateCancel"
      @close="resetCreateDialog"
    >
      <h3 :id="`${createId}-title`">添加用户</h3>
      <form @submit.prevent="submitNewUser" @input="createError = ''">
        <div class="form-group">
          <label class="form-label" :for="`${createId}-username`">用户名</label>
          <input
            :id="`${createId}-username`"
            v-model.trim="newUsername"
            class="input"
            name="username"
            autocomplete="username"
            autocorrect="off"
            autocapitalize="none"
            spellcheck="false"
            :aria-describedby="`${createId}-username-help`"
            minlength="2"
            required
            autofocus
          />
          <small :id="`${createId}-username-help`">至少 2 个字符</small>
        </div>
        <div class="form-group">
          <label class="form-label" :for="`${createId}-password`">密码</label>
          <input
            :id="`${createId}-password`"
            v-model="newPassword"
            class="input"
            name="password"
            type="password"
            autocomplete="new-password"
            :aria-describedby="`${createId}-password-help`"
            minlength="6"
            required
          />
          <small :id="`${createId}-password-help`">至少 6 个字符</small>
        </div>
        <p class="create-error" role="alert">{{ createError }}</p>
        <div class="dialog-footer">
          <button type="button" class="btn btn-secondary" :disabled="creating" @click="createDialog?.close()">
            取消
          </button>
          <button type="submit" class="btn btn-primary" :disabled="creating">
            {{ creating ? '创建中…' : '创建用户' }}
          </button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, useId } from 'vue'
import * as AdminAPI from '@/api/admin'
import type { User, Role } from '@/api/admin'

import { useAuthStore } from '@/stores/auth'
import { extractErrorMessage } from '@/utils/errorMessage'

const auth = useAuthStore()
const users = ref<User[]>([])
const roles = ref<Role[]>([])
const loading = ref(false)
const updatingStatus = ref(new Set<number>())
const statusFeedback = ref('')
const statusError = ref('')
const createId = useId()
const createDialog = ref<HTMLDialogElement | null>(null)
const newUsername = ref('')
const newPassword = ref('')
const creating = ref(false)
const createError = ref('')

function openCreateDialog() {
  statusFeedback.value = ''
  statusError.value = ''
  createDialog.value?.showModal()
}

function onCreateCancel(event: Event) {
  if (creating.value) event.preventDefault()
}

function resetCreateDialog() {
  newUsername.value = ''
  newPassword.value = ''
  createError.value = ''
}

async function submitNewUser() {
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    await AdminAPI.createUser({ username: newUsername.value, password: newPassword.value })
    statusFeedback.value = `已创建用户 ${newUsername.value}`
    createDialog.value?.close()
    await loadUsers()
  } catch (error) {
    createError.value = extractErrorMessage(error) || '创建用户失败，请重试'
  } finally {
    creating.value = false
  }
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await AdminAPI.getUsers()
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

function statusRestriction(user: User): string {
  if (!auth.hasPerm('system.manage')) return '需要系统管理权限'
  if (user.id === (auth.user?.id ?? Number(auth.userId))) return '无法禁用当前登录账号'
  if (user.role === 'super_admin' && auth.userRole !== 'super_admin') return '拥有者身份只能由超级管理员管理'
  return ''
}

async function toggleUserStatus(user: User) {
  if (statusRestriction(user) || updatingStatus.value.has(user.id)) return
  const newStatus = user.status === 1 ? 0 : 1
  const action = newStatus === 1 ? '启用' : '禁用'
  statusFeedback.value = ''
  statusError.value = ''
  updatingStatus.value.add(user.id)
  try {
    await AdminAPI.updateUserStatus(user.id, newStatus)
    user.status = newStatus
    statusFeedback.value = `已${action}用户 ${user.username}`
  } catch (error) {
    statusError.value = `${action}用户 ${user.username} 失败。${extractErrorMessage(error)}`
  } finally {
    updatingStatus.value.delete(user.id)
  }
}

function formatTime(time?: string): string {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

onMounted(() => {
  loadUsers()
  loadRoles()
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
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-primary);
}

.section-title {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0;
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

.user-status-action:disabled {
  cursor: default;
  opacity: .55;
}

.create-dialog {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  width: min(420px, calc(100% - 32px));
  margin: auto;
  padding: 20px;
}

.create-dialog::backdrop {
  background: rgb(0 0 0 / 50%);
}

.create-dialog h3 {
  margin: 0 0 16px;
  font-size: 18px;
}

.create-dialog small {
  color: var(--text-secondary);
}

.status-feedback {
  color: var(--text-secondary);
}

.create-error,
.status-error {
  color: var(--text-danger);
}

.status-feedback:empty,
.create-error:empty,
.status-error:empty {
  margin: 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

</style>
