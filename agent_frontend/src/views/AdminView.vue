<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">系统管理</h1>
        <p class="page-desc">管理用户与角色</p>
      </div>
    </header>

    <AdminLayout v-model="activeTab" :tabs="visibleTabs" />

    <UserListPanel v-if="activeTab === 'users'" />
    <RoleListPanel v-else-if="activeTab === 'roles'" ref="roleListRef" @edit="openRoleEdit" />
    <DepartmentPanel v-else-if="activeTab === 'departments'" />
    <HostWhitelistPanel v-else-if="activeTab === 'hosts'" />
    <CommandBlacklistPanel v-else-if="activeTab === 'blacklist'" />

    <RoleEditDialog
      v-if="showRoleEdit"
      :role="editingRole"
      @close="closeRoleEdit"
      @saved="onRoleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AdminLayout from './admin/AdminLayout.vue'
import UserListPanel from './admin/UserListPanel.vue'
import RoleListPanel from './admin/RoleListPanel.vue'
import RoleEditDialog from './admin/RoleEditDialog.vue'
import HostWhitelistPanel from './admin/HostWhitelistPanel.vue'
import CommandBlacklistPanel from './admin/CommandBlacklistPanel.vue'
import DepartmentPanel from './admin/DepartmentPanel.vue'
import type { Role } from '@/api/admin'

const auth = useAuthStore()
const activeTab = ref('users')
const roleListRef = ref<InstanceType<typeof RoleListPanel> | null>(null)

const visibleTabs = computed(() => {
  const tabs: { key: string; label: string; perm: string }[] = [
    { key: 'users', label: '用户管理', perm: 'system.manage' },
    { key: 'roles', label: '角色管理', perm: 'system.manage' },
    { key: 'departments', label: '部门管理', perm: 'system.manage' },
    { key: 'hosts', label: '主机白名单', perm: 'system.manage' },
    { key: 'blacklist', label: '命令黑名单', perm: 'system.manage' },
  ]
  return tabs.filter(t => auth.hasPerm(t.perm))
})

// 如果当前 activeTab 不在可见列表中，自动切到第一个可见 tab
watch(visibleTabs, (tabs) => {
  if (tabs.length && !tabs.some(t => t.key === activeTab.value)) {
    activeTab.value = tabs[0].key
  }
}, { immediate: true })

const showRoleEdit = ref(false)
const editingRole = ref<Role | null>(null)

function openRoleEdit(role?: Role) {
  editingRole.value = role || null
  showRoleEdit.value = true
}

function closeRoleEdit() {
  showRoleEdit.value = false
  editingRole.value = null
}

function onRoleSaved() {
  closeRoleEdit()
  // 刷新角色列表
  roleListRef.value?.loadRoles()
}
</script>

<style scoped>
.page-container {
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

.page-title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: var(--text-primary);
}

.page-desc {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}
</style>
