<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>{{ role ? '编辑角色' : '创建角色' }}</h2>
        <button @click="$emit('close')" class="btn-close">✕</button>
      </div>
      <div class="modal-body">
        <form @submit.prevent="save">
          <div class="form-group">
            <label class="form-label">角色标识 *</label>
            <input v-model="form.name" class="input" placeholder="如 ops_engineer" required :disabled="!!role" />
          </div>
          <div class="form-group">
            <label class="form-label">显示名称 *</label>
            <input v-model="form.display_name" class="input" placeholder="如 运维工程师" required />
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <input v-model="form.description" class="input" placeholder="角色描述（可选）" />
          </div>

          <h3 class="sub-title">功能权限</h3>
          <div v-if="permissionTree.length === 0 && treeLoading" class="loading-state">
            <div class="spinner small"></div>
            <span>加载权限...</span>
          </div>
          <div v-else class="permission-groups">
            <div v-for="section in groupedTree" :key="section.label" class="perm-group">
              <div class="perm-group-header" @click="toggleGroup(section.label)">
                <span class="group-arrow">{{ openGroups[section.label] ? '▼' : '▶' }}</span>
                <span class="group-label">{{ section.label }}</span>
                <span class="group-count">
                  {{ countSelected(section.permissions) }}/{{ section.permissions.length }}
                </span>
              </div>
              <div v-show="openGroups[section.label]" class="perm-group-body">
                <label v-for="perm in section.permissions" :key="perm.key" class="perm-checkbox">
                  <input type="checkbox" v-model="form.permissions" :value="perm.key" />
                  <span>{{ perm.label }}</span>
                </label>
              </div>
            </div>
          </div>

          <h3 class="sub-title">AI 对话工具</h3>
          <template v-for="(tools, groupKey) in hermesToolsByGroup" :key="groupKey">
            <h4 class="tool-group-label">{{ groupLabels[groupKey] || groupKey }}</h4>
            <div class="hermes-tools">
              <label v-for="tool in tools" :key="tool.key" class="perm-checkbox hermes-tool">
                <input type="checkbox" v-model="form.hermes_tools" :value="tool.key" />
                <span class="tool-name">{{ tool.label }}</span>
                <span class="tool-desc">— {{ tool.desc }}</span>
              </label>
            </div>
          </template>

          <div class="modal-actions">
            <button type="button" @click="$emit('close')" class="btn btn-secondary">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import * as AdminAPI from '@/api/admin'

const props = defineProps<{ role?: any }>()
const emit = defineEmits<{
  close: []
  saved: []
}>()

interface PermItem { key: string; label: string }
interface PermGroup { group_name: string; group_label: string; permissions: PermItem[] }

const permissionTree = ref<PermGroup[]>([])
const openGroups = reactive<Record<string, boolean>>({})
const treeLoading = ref(false)
const saving = ref(false)

// 功能权限分组（与侧边栏菜单分组一致）：对话与观测 / 技能与记忆 / 知识库 / 系统
const PERM_SECTION_RULES: { label: string; groupNames: string[] }[] = [
  { label: '对话与观测', groupNames: ['chat', 'trace', 'cron'] },
  { label: '技能与记忆', groupNames: ['skill'] },
  { label: '知识库', groupNames: ['kb'] },
  { label: '系统', groupNames: ['admin', 'config', 'terminal'] },
]

const groupedTree = computed(() => {
  const sections = PERM_SECTION_RULES.map(s => ({
    label: s.label,
    permissions: permissionTree.value
      .filter(g => s.groupNames.includes(g.group_name))
      .flatMap(g => g.permissions),
  }))
  const known = new Set(PERM_SECTION_RULES.flatMap(s => s.groupNames))
  const rest = permissionTree.value
    .filter(g => !known.has(g.group_name))
    .flatMap(g => g.permissions)
  if (rest.length) sections.push({ label: '其他', permissions: rest })
  return sections.filter(s => s.permissions.length > 0)
})

// 兜底列表（API 不可用时的旧定义）
const FALLBACK_TOOL_OPTIONS = [
  { key: 'terminal',       label: '终端执行',   desc: '执行 Shell 命令',        group: 'hermes' },
  { key: 'file',           label: '文件读写',   desc: '读写文件',             group: 'hermes' },
  { key: 'web',            label: '网络搜索',   desc: '搜索网页和抓取 URL',      group: 'hermes' },
  { key: 'data',           label: '知识库检索', desc: 'RAG 知识库检索',          group: 'project' },
  { key: 'schedule',       label: '定时任务',   desc: '定时任务管理',           group: 'project' },
]

const hermesToolOptions = ref<any[]>(FALLBACK_TOOL_OPTIONS)

const groupLabels: Record<string, string> = {
  hermes: '内置',
  project: '扩展',
}

const hermesToolsByGroup = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const t of hermesToolOptions.value) {
    if (!groups[t.group]) groups[t.group] = []
    groups[t.group].push(t)
  }
  return groups
})

const form = reactive({
  name: '',
  display_name: '',
  description: '',
  permissions: [] as string[],
  hermes_tools: [] as string[],
})

onMounted(async () => {
  treeLoading.value = true
  try {
    permissionTree.value = await AdminAPI.getPermissionTree()
    // 默认展开所有分区
    groupedTree.value.forEach(s => { openGroups[s.label] = true })
  } catch (e) {
    console.error('加载权限树失败:', e)
  } finally {
    treeLoading.value = false
  }

  // toolset 选项从后端拉取（单一数据源）
  try {
    const defs = await AdminAPI.getToolsetDefinitions()
    if (Array.isArray(defs) && defs.length > 0) {
      hermesToolOptions.value = defs
    }
  } catch (e) {
    console.warn('加载 toolset 定义失败，使用内置兜底列表:', e)
  }

  if (props.role) {
    form.name = props.role.name
    form.display_name = props.role.display_name || ''
    form.description = props.role.description || ''
    form.permissions = [...(props.role.permissions || [])]
    form.hermes_tools = [...(props.role.hermes_tools || [])]
  }
})

function toggleGroup(name: string) {
  openGroups[name] = !openGroups[name]
}

function countSelected(perms: PermItem[]): number {
  return perms.filter(p => form.permissions.includes(p.key)).length
}

async function save() {
  if (!form.name || !form.display_name) {
    alert('请填写角色标识和显示名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      display_name: form.display_name,
      description: form.description,
      permissions: form.permissions,
      hermes_tools: form.hermes_tools,
    }
    if (props.role?.id) {
      await AdminAPI.updateRole(props.role.id, payload)
      alert(`✅ 角色「${form.display_name}」已更新`)
    } else {
      await AdminAPI.createRole(payload)
      alert(`✅ 角色「${form.display_name}」已创建`)
    }
    emit('saved')
  } catch (e) {
    console.error('保存角色失败:', e)
    alert('保存失败：' + (e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
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

.modal {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-tertiary);
  cursor: pointer;
}

.modal-body {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 8px;
  font-weight: 500;
}

.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 14px;
  box-sizing: border-box;
}

.input:focus {
  outline: none;
  border-color: var(--brand);
}

.input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sub-title {
  font-size: 15px;
  color: var(--text-primary);
  margin: 24px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-primary);
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-primary);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner.small {
  width: 16px;
  height: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.permission-groups {
  display: flex;
  flex-direction: column;
  gap: 4px;
}


.perm-group {
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  overflow: hidden;
}

.perm-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
}

.perm-group-header:hover {
  background: var(--bg-hover);
}

.group-arrow {
  font-size: 10px;
  color: var(--text-tertiary);
  width: 12px;
}

.group-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  flex: 1;
}

.group-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

.perm-group-body {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 12px;
}

.perm-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
}

.perm-checkbox input {
  cursor: pointer;
}

.hermes-tools {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tool-group-label {
  font-size: 12px;
  color: #888;
  margin: 8px 0 4px;
  font-weight: 500;
}

.hermes-tool {
  padding: 8px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.hermes-tool:hover {
  border-color: var(--brand);
}

.tool-name {
  font-weight: 500;
  color: var(--text-primary);
}

.tool-desc {
  color: var(--text-tertiary);
  font-size: 12px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-primary);
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border-primary);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-secondary:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.btn-primary {
  background: var(--brand-gradient);
  color: white;
  border: none;
}

.btn-primary:hover {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
