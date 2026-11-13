<template>
  <div class="modal-overlay" @click.self="$emit('close')" @keydown.esc="onKeydown">
    <div class="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="role-dialog-title">
      <div class="modal-header">
        <h2 id="role-dialog-title">{{ role ? '编辑角色' : '创建角色' }}</h2>
        <button @click="$emit('close')" class="btn-close">✕</button>
      </div>
      <div class="modal-body">
        <form @submit.prevent="save">
          <div class="form-row">
            <div class="form-group grow">
              <label class="form-label">角色标识 *</label>
              <input v-model="form.name" class="input" placeholder="如 ops_engineer" required :disabled="!!role" />
            </div>
            <div class="form-group grow">
              <label class="form-label">显示名称 *</label>
              <input v-model="form.display_name" class="input" placeholder="如 运维工程师" required />
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <input v-model="form.description" class="input" placeholder="角色描述（可选）" />
          </div>

          <!-- 系统拥有者：只读展示 -->
          <div v-if="isOwnerRole" class="notice-banner">
            系统拥有者（super_admin）拥有全部已启用权限，业务权限区只读。
          </div>

          <!-- P6：主编辑区 = 按分组的原子权限复选框（多选、逐项、历史保留） -->
          <h3 class="sub-title">功能权限</h3>
          <p class="muted-hint">
            逐项勾选原子授权；带文件依赖的动作（账单导入/导出）勾选时自动附带所需文件授权，
            取消动作不会撤销共享的文件授权。当前角色已有的授权（含历史自定义项）原样回显。
          </p>
          <p v-if="defsLoadFailed" class="muted-hint note">
            权限定义加载失败：以下按现有授权键回显并可编辑；直接保存不会丢失或扩大权限字段。
          </p>
          <div class="perm-groups" :class="{ readonly: isOwnerRole }">
            <section v-for="group in permGroups" :key="group.group_name" class="perm-group">
              <h4 class="tool-group-label">{{ group.group_label }}</h4>
              <label v-for="perm in group.permissions" :key="perm.key" class="perm-checkbox">
                <input
                  type="checkbox"
                  :checked="form.permissions.includes(perm.key)"
                  :disabled="isOwnerRole"
                  @change="onPermToggle(perm.key, $event)"
                />
                <span>{{ perm.label }}</span>
                <span class="tool-desc">— {{ perm.description }}</span>
                <span v-if="perm.risk === 'high'" class="badge badge-danger">高风险</span>
                <span v-else-if="perm.risk === 'medium'" class="badge badge-warning">中风险</span>
                <span v-if="dependencyHint(perm.key, permDefs).length" class="tool-desc">
                  （附带：{{ dependencyHint(perm.key, permDefs).join('、') }}）
                </span>
              </label>
            </section>

            <!-- 文件依赖内部项：随动作自动附带，也支持显式取消（历史独立配置可见） -->
            <section v-if="internalGroups.length > 0" class="perm-group">
              <h4 class="tool-group-label">文件依赖（内部授权）</h4>
              <label v-for="perm in internalGroups" :key="perm.key" class="perm-checkbox">
                <input
                  type="checkbox"
                  :checked="form.permissions.includes(perm.key)"
                  :disabled="isOwnerRole"
                  @change="onPermToggle(perm.key, $event)"
                />
                <span>{{ perm.label }}</span>
                <span class="tool-desc">— {{ perm.description }}</span>
              </label>
            </section>

            <!-- 定义之外的历史权限：原样保留、可显式取消；退役键按后端口径处理 -->
            <section v-if="orphanPerms.length > 0" class="perm-group">
              <h4 class="tool-group-label">历史自定义授权（不在当前定义列表）</h4>
              <label v-for="key in orphanPerms" :key="key" class="perm-checkbox">
                <input
                  type="checkbox"
                  checked
                  :disabled="isOwnerRole"
                  @change="onPermToggle(key, $event)"
                />
                <span class="mono">{{ key }}</span>
                <span class="tool-desc">— 保留历史配置；如后端已退役该键，保存时按后端口径处理</span>
              </label>
            </section>
          </div>

          <!-- 高级设置（默认收起）：功能预设 + 工具组 -->
          <div class="advanced">
            <button type="button" class="advanced-toggle" @click="showAdvanced = !showAdvanced">
              {{ showAdvanced ? '▾' : '▸' }} 高级设置
              <span v-if="customCount" class="muted-hint">（{{ customCount }} 项原子授权/工具）</span>
            </button>
            <div v-show="showAdvanced" class="advanced-body">
              <h4 class="tool-group-label">功能预设（快捷批量，结果同步到上方复选框）</h4>
              <div class="module-rows" :class="{ readonly: isOwnerRole }">
                <div v-for="row in moduleRows" :key="row.module" class="module-row">
                  <div class="module-info">
                    <span class="module-label">{{ row.label }}</span>
                    <span class="module-desc">{{ row.desc }}</span>
                  </div>
                  <select
                    v-model="form.moduleModes[row.module]"
                    class="select mode-select"
                    :disabled="isOwnerRole"
                    @change="onModeChange(row.module)"
                  >
                    <option v-for="m in row.modes" :key="m.mode" :value="m.mode">{{ m.label }}</option>
                    <option v-if="isCustomMode(row.module)" value="custom">自定义</option>
                  </select>
                </div>
              </div>
              <p v-if="modeChangeNote" class="muted-hint note">{{ modeChangeNote }}</p>

              <h4 class="tool-group-label">AI 对话工具组</h4>
              <template v-if="toolOptions.length > 0">
                <div class="hermes-tools">
                  <label v-for="tool in toolOptions" :key="tool.key" class="perm-checkbox hermes-tool">
                    <input type="checkbox" v-model="form.hermes_tools" :value="tool.key" :disabled="isOwnerRole" />
                    <span class="tool-name">{{ tool.label }}</span>
                    <span class="tool-desc">— {{ tool.desc }}<template v-if="tool.risk === 'high'">（高风险）</template></span>
                  </label>
                </div>
              </template>
              <p v-else class="muted-hint">工具组定义加载失败；为避免显示已退役项，暂不可编辑（保存不影响工具组）。</p>

              <h4 class="tool-group-label">数据范围</h4>
              <p class="muted-hint">
                带「全局」标注的授权允许跨用户访问该模块数据（如管理全部技能、全局用量、跨用户编码任务）。
                未标注的授权严格按本人数据范围。
              </p>
            </div>
          </div>

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
import {
  groupPermissions,
  visiblePermissions,
  internalPermissionDefs,
  permsAfterCheck,
  permsAfterUncheck,
  dependencyHint,
  type PermissionDef,
} from '@/utils/permissionGroups'

const props = defineProps<{ role?: any }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const saving = ref(false)
const showAdvanced = ref(false)
const toolOptions = ref<{ key: string; label: string; desc: string; risk?: string }[]>([])
const modeChangeNote = ref('')
const defsLoadFailed = ref(false)

const form = reactive({
  name: '',
  display_name: '',
  description: '',
  permissions: [] as string[],
  hermes_tools: [] as string[],
  moduleModes: {} as Record<string, string>,
})

const isOwnerRole = computed(() => props.role?.name === 'super_admin')

// ---- 9 功能项模式定义（原子映射唯一来源；与后端 permission_catalog 对齐） --------
interface ModeDef { mode: string; label: string; perms: string[] }
interface ModuleRow { module: string; label: string; desc: string; modes: ModeDef[]; governed: string[] }

const MODULE_ROWS: ModuleRow[] = [
  {
    module: 'chat', label: '智能对话', desc: '对话、微信入站、收藏与基础偏好',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'use', label: '使用', perms: ['chat.use'] },
    ],
    governed: ['chat.use'],
  },
  {
    module: 'memory', label: '记忆与情绪', desc: '情绪记录始终需要本人开启',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'read', label: '只读', perms: ['memory.view'] },
      { mode: 'use', label: '使用', perms: ['memory.view', 'memory.edit'] },
    ],
    governed: ['memory.view', 'memory.edit'],
  },
  {
    module: 'skills', label: '个人技能', desc: '本人技能；跨用户管理与经验在高级设置',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'use', label: '使用', perms: ['skill.create'] },
    ],
    governed: ['skill.create'],
  },
  {
    module: 'schedule', label: '提醒与简报', desc: '本人提醒/定时任务与日报',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'use', label: '使用', perms: ['cron.create'] },
    ],
    governed: ['cron.create'],
  },
  {
    module: 'ledger', label: '账单', desc: '只读可看；使用含导入/修正/报告（自动包含文件依赖）',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'read', label: '只读', perms: ['ledger.view'] },
      {
        mode: 'use', label: '使用',
        perms: ['ledger.view', 'ledger.import', 'ledger.edit', 'ledger.export', 'file.upload', 'file.read'],
      },
    ],
    governed: ['ledger.view', 'ledger.import', 'ledger.edit', 'ledger.export'],
  },
  {
    module: 'superagent', label: '编码代理', desc: '只读可查；执行会消耗模型用量并创建远端 Draft PR',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'read', label: '只读', perms: ['superagent.view'] },
      { mode: 'execute', label: '执行', perms: ['superagent.view', 'superagent.create'] },
    ],
    governed: ['superagent.view', 'superagent.create'],
  },
  {
    module: 'trace', label: '用量统计', desc: '查看本人用量与排行；管理范围可查看全部用户调用明细',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'read', label: '查看本人', perms: ['trace.view'] },
      { mode: 'manage', label: '管理（含全部用户明细）', perms: ['trace.view', 'trace.manage'] },
    ],
    governed: ['trace.view', 'trace.manage'],
  },
  {
    module: 'identity', label: '用户与角色管理', desc: '跨用户身份管理；不可管理拥有者身份',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'manage', label: '管理', perms: ['system.manage'] },
    ],
    governed: ['system.manage'],
  },
  {
    module: 'config', label: '系统配置', desc: '模型、SMTP 等平台配置与凭证',
    modes: [
      { mode: 'off', label: '关闭', perms: [] },
      { mode: 'manage', label: '配置', perms: ['system.config'] },
    ],
    governed: ['system.config'],
  },
]

// 高级原子授权 = active 且不被功能行管辖
const moduleRows = MODULE_ROWS

// ---- P6 主区：后端权限定义（含 depends/internal/lifecycle）驱动分组复选框 ----
const permDefs = ref<PermissionDef[]>([])

const permGroups = computed(() => groupPermissions(visiblePermissions(permDefs.value)))
const internalGroups = computed(() => internalPermissionDefs(permDefs.value))
// 当前持有但不在定义列表中的键（历史自定义/定义加载失败的兜底）——原样可编辑
const orphanPerms = computed(() => {
  const known = new Set(permDefs.value.map((d) => d.key))
  return form.permissions.filter((k) => !known.has(k))
})

const customCount = computed(() => form.permissions.length + form.hermes_tools.length)

function onPermToggle(key: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  form.permissions = checked
    ? permsAfterCheck(form.permissions, key, permDefs.value)
    : permsAfterUncheck(form.permissions, key)
  // 预设下拉与逐项真值保持同步（可能因此进入 custom）
  syncModesFromPermissions()
}

function governedPerms(row: ModuleRow): string[] {
  return row.governed
}

function detectMode(row: ModuleRow): string {
  const governed = governedPerms(row)
  const current = governed.filter(k => form.permissions.includes(k))
  for (const m of row.modes) {
    const expected = m.perms.filter(k => governed.includes(k))
    if (expected.length === current.length && m.perms.every(k => form.permissions.includes(k))) return m.mode
  }
  return 'custom'
}

function isCustomMode(module: string): boolean {
  const row = MODULE_ROWS.find(r => r.module === module)
  return !!row && detectMode(row) === 'custom'
}

function syncModesFromPermissions() {
  for (const row of MODULE_ROWS) {
    form.moduleModes[row.module] = detectMode(row)
  }
}

function onModeChange(module: string) {
  const row = MODULE_ROWS.find(r => r.module === module)
  if (!row) return
  const mode = form.moduleModes[module]
  if (mode === 'custom') return
  const target = row.modes.find(m => m.mode === mode)
  if (!target) return
  // 应用模式：移除该模式未包含的管辖原子，加入目标原子
  for (const key of governedPerms(row)) {
    if (!target.perms.includes(key)) {
      form.permissions = form.permissions.filter(k => k !== key)
    }
  }
  for (const key of target.perms) {
    if (!form.permissions.includes(key)) form.permissions.push(key)
  }
  // 文件依赖也可由高级区显式授予；账单降档保留已有共享授权。
  if (module === 'ledger') {
    if (mode === 'use') {
      modeChangeNote.value = '已自动包含文件上传/读取依赖（账单导入与报告下载需要）。'
    } else {
      modeChangeNote.value = ''
    }
  } else {
    modeChangeNote.value = ''
  }
}

onMounted(async () => {
  // 权限定义（含 lifecycle/module/depends/internal/risk 元数据）——单一来源。
  // 加载失败时不清空、不改写现有授权：主区按历史键回显（orphan 组），
  // 保存原样提交，绝不因定义故障丢权限字段。
  try {
    const defs = await AdminAPI.getPermissionDefinitions()
    permDefs.value = Array.isArray(defs) ? defs as PermissionDef[] : []
    defsLoadFailed.value = permDefs.value.length === 0
  } catch (e) {
    console.warn('权限定义加载失败，按现有授权键回显:', e)
    permDefs.value = []
    defsLoadFailed.value = true
  }
  // 工具组：仅后端注册项；失败时禁用编辑（不再使用含废弃项的离线兜底）
  try {
    const defs = await AdminAPI.getToolsetDefinitions()
    if (Array.isArray(defs) && defs.length > 0) {
      toolOptions.value = defs
    }
  } catch (e) {
    console.warn('工具组定义加载失败，工具组不可编辑:', e)
    toolOptions.value = []
  }

  if (props.role) {
    form.name = props.role.name
    form.display_name = props.role.display_name || ''
    form.description = props.role.description || ''
    form.permissions = [...(props.role.permissions || [])]
    form.hermes_tools = [...(props.role.hermes_tools || [])]
    syncModesFromPermissions()
  }
})

// 标准模态键盘语义:Esc 关闭(模板 @keydown.esc 冒泡绑定,焦点在弹窗内任意元素均生效)。
// 同时接受当前规范值 'Escape' 与旧值 'Esc',兼容不同 WebView 实现。
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' || e.key === 'Esc') emit('close')
}

async function save() {
  if (!form.name || !form.display_name) {
    alert('请填写角色标识和显示名称')
    return
  }
  if (isOwnerRole.value) {
    emit('close')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      display_name: form.display_name,
      description: form.description,
      permissions: form.permissions,
      hermes_tools: toolOptions.value.length > 0 ? form.hermes_tools : undefined,
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
.modal-wide {
  max-width: 720px;
  width: 92vw;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .grow {
  flex: 1;
}

.module-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.module-rows.readonly {
  opacity: 0.85;
}

.module-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 8px 12px;
}

.module-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.module-label {
  font-weight: 600;
  font-size: 13px;
}

.module-desc {
  font-size: 12px;
  color: var(--text-tertiary);
}

.mode-select {
  min-width: 150px;
}

.sub-title {
  margin: 16px 0 8px;
  font-size: 14px;
}

.muted-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 8px;
}

.note {
  color: var(--brand);
}

.notice-banner {
  background: rgba(240, 173, 78, 0.12);
  border: 1px solid rgba(240, 173, 78, 0.4);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  margin-bottom: 8px;
}

.advanced {
  margin-top: 12px;
  border-top: 1px dashed var(--border-primary);
  padding-top: 8px;
}

.advanced-toggle {
  background: none;
  border: none;
  color: var(--brand);
  cursor: pointer;
  font-size: 13px;
  padding: 0;
}

.advanced-body {
  margin-top: 8px;
}

.tool-group-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 12px 0 6px;
}

.perm-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 3px 0;
}

.perm-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.perm-groups.readonly {
  opacity: 0.85;
}

.perm-group {
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 8px 12px;
}

.perm-group .tool-group-label {
  margin: 0 0 6px;
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
}

.tool-desc {
  color: var(--text-tertiary);
  font-size: 12px;
}

.modal-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
