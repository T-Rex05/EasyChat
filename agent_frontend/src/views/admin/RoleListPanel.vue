<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">角色列表</h2>
      <button class="btn btn-primary" @click="$emit('edit')">+ 创建角色</button>
    </div>
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>
    <div v-else-if="roles.length === 0" class="empty-state">
      <p>暂无角色</p>
    </div>
    <div v-else class="role-grid">
      <div
        v-for="role in roles"
        :key="role.id"
        class="role-card"
        role="button"
        tabindex="0"
        @keydown.enter.self="$emit('edit', role)"
        @keydown.space.self.prevent="$emit('edit', role)"
        @click="$emit('edit', role)"
      >
        <div class="role-header">
          <h3>{{ role.display_name || role.name }}</h3>
          <button class="edit-btn" @click.stop="$emit('edit', role)">
            <Pencil :size="14" />
          </button>
        </div>
        <p v-if="role.description" class="role-desc">{{ role.description }}</p>
        <div class="role-stats">
          <span class="stat-item">
            <ShieldCheck :size="13" />
            {{ role.name === 'super_admin' ? '全部权限' : `${role.permissions?.length || 0} 个权限` }}
          </span>
          <span class="stat-item">
            <Wrench :size="13" />
            {{ role.hermes_tools?.length || 0 }} 个工具
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Pencil, ShieldCheck, Wrench } from '@lucide/vue'
import * as AdminAPI from '@/api/admin'
import type { Role } from '@/api/admin'

defineEmits<{
  edit: [role?: Role]
}>()

const roles = ref<Role[]>([])
const loading = ref(false)

async function loadRoles() {
  loading.value = true
  try {
    roles.value = await AdminAPI.getRoles()
  } catch (e) {
    console.error('加载角色失败:', e)
  } finally {
    loading.value = false
  }
}

defineExpose({ loadRoles })

onMounted(() => { loadRoles() })
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
  flex: 1;
}

.btn-primary {
  padding: 8px 16px;
  background: var(--brand-gradient);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.btn-primary:hover { opacity: 0.9; }

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

@keyframes spin { to { transform: rotate(360deg); } }

.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.role-card {
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  cursor: pointer;
  transition: var(--transition);
}

.role-card:hover {
  border-color: var(--brand);
  box-shadow: var(--shadow-sm);
}

.role-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.role-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.edit-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}

.edit-btn:hover {
  background: var(--bg-hover);
  color: var(--brand);
}

.role-desc {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.role-stats {
  display: flex;
  gap: 16px;
}

.stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}
</style>
