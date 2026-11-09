<template>
  <div class="card upgrade-panel">
    <div class="panel-head" @click="open = !open">
      <strong>权限模板升级（{{ preview?.current_template_version || '…' }}）</strong>
      <span v-if="pendingCount" class="badge badge-warning">{{ pendingCount }} 个角色待确认升级</span>
      <span class="arrow">{{ open ? '▾' : '▸' }}</span>
    </div>
    <div v-show="open" class="panel-body">
      <p class="hint">
        已有角色的授权不会被自动补种（包括新增的编码代理权限）。升级由系统拥有者在此显式确认；
        应用前会留存当前授权快照。
      </p>
      <div v-if="loading" class="hint">加载中…</div>
      <div v-else-if="preview" class="role-cards">
        <div v-for="r in preview.roles" :key="r.role" class="role-card">
          <div class="role-head">
            <strong>{{ r.role }}</strong>
            <span class="badge" :class="r.pending ? 'badge-warning' : 'badge-success'">
              {{ r.pending ? `模板 ${r.template_version} → 待升级` : '已是当前模板' }}
            </span>
          </div>
          <div v-if="r.missing_from_role.length" class="diff">
            <span class="diff-label">模板新增（未授予）：</span>
            <span v-for="k in r.missing_from_role" :key="k" class="diff-item"
                  :class="{ high: r.high_risk_missing.includes(k) }">{{ k }}</span>
          </div>
          <div v-if="r.not_in_template.length" class="diff">
            <span class="diff-label">角色自定义（模板外，保留）：</span>
            <span v-for="k in r.not_in_template" :key="k" class="diff-item custom">{{ k }}</span>
          </div>
          <div v-if="toolsetDiff(r)" class="diff">
            <span class="diff-label">工具组差异：</span>
            <span class="diff-item custom">库 {{ r.toolsets_in_db.join('/') || '无' }} → 模板 {{ r.toolsets_in_template.join('/') || '无' }}</span>
          </div>
          <button
            v-if="r.pending && canApply"
            class="btn btn-sm btn-primary"
            :disabled="applying === r.role"
            @click="apply(r.role)"
          >{{ applying === r.role ? '应用中…' : `应用 ${preview.current_template_version} 模板` }}</button>
          <p v-if="!canApply" class="hint">升级应用需要超级管理员确认。</p>
        </div>
      </div>
      <p v-if="message" class="hint">{{ message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  applyRoleTemplate,
  getPermissionUpgradePreview,
  type UpgradePreview,
} from '@/api/permissions'

const auth = useAuthStore()
const open = ref(false)
const loading = ref(false)
const preview = ref<UpgradePreview | null>(null)
const applying = ref('')
const message = ref('')

const canApply = computed(() => auth.userRole === 'super_admin')
const pendingCount = computed(() => preview.value?.roles.filter(r => r.pending).length || 0)

function toolsetDiff(r: { toolsets_in_db: string[]; toolsets_in_template: string[] }): boolean {
  const a = [...r.toolsets_in_db].sort().join(',')
  const b = [...r.toolsets_in_template].sort().join(',')
  return a !== b
}

async function load() {
  loading.value = true
  try {
    preview.value = await getPermissionUpgradePreview()
  } catch (e) {
    message.value = '加载升级预览失败：' + (e as Error).message
  } finally {
    loading.value = false
  }
}

async function apply(roleName: string) {
  if (!confirm(`确认把「${roleName}」升级到 ${preview.value?.current_template_version} 模板？\n模板新增权限将生效；模板外自定义授权与工具组保留（合并语义）。\n当前授权已留存快照，可回滚。`)) return
  applying.value = roleName
  message.value = ''
  try {
    const result = await applyRoleTemplate(roleName)
    message.value = `✅ ${roleName} 已升级；升级前授权（${result.previous_permissions.length} 项）已留存快照。`
    await load()
  } catch (e) {
    message.value = '应用失败：' + (e as Error).message
  } finally {
    applying.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.upgrade-panel {
  margin-top: 16px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.arrow {
  color: var(--text-tertiary);
}

.panel-body {
  margin-top: 10px;
}

.hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.role-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.role-card {
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 10px 12px;
}

.role-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.diff {
  font-size: 12px;
  margin: 4px 0;
}

.diff-label {
  color: var(--text-tertiary);
  margin-right: 6px;
}

.diff-item {
  display: inline-block;
  background: var(--bg-hover);
  border-radius: 4px;
  padding: 1px 6px;
  margin: 2px 4px 2px 0;
}

.diff-item.high {
  background: rgba(217, 83, 79, 0.12);
  color: #d9534f;
}

.diff-item.custom {
  background: rgba(240, 173, 78, 0.12);
}
</style>
