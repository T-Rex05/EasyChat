<template>
  <div class="mcp-panel">
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-header">🔌 远程 MCP 服务（StreamableHTTP）</div>
      <div class="card-body">
        <p class="section-tip">
          凭据加密存储且永不回显；能力默认关闭——新建后需显式"测试连接"再启用。
          受众"仅系统配置者"只授予持有 system.config 的角色；"所有用户"会注入每个对话。
        </p>
        <div v-if="error" class="error-banner">{{ error }}</div>

        <table v-if="servers.length" class="table">
          <thead>
            <tr>
              <th>名称</th><th>地址</th><th>凭据</th><th>受众</th><th>状态</th>
              <th>最近检查</th><th>目录</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in servers" :key="s.id">
              <td class="mono">{{ s.name }}</td>
              <td class="url">{{ s.url }}</td>
              <td>{{ s.credential_set ? '已设置' : '无' }}</td>
              <td>{{ s.audience === 'all' ? '所有用户' : '仅系统配置者' }}</td>
              <td>
                <span :class="['badge', s.enabled ? 'badge-info' : '']">
                  {{ s.enabled ? '已启用' : '停用' }}
                </span>
              </td>
              <td>
                <span v-if="s.last_check_state === 'ok'" class="ok">连接正常</span>
                <span v-else-if="s.last_check_state === 'empty'" class="warn">空目录</span>
                <span v-else-if="s.last_check_state" class="bad" :title="s.last_check_error">
                  {{ checkKindLabel(s) }}
                </span>
                <span v-else class="muted">未测试</span>
              </td>
              <td class="muted">{{ s.last_check_tools.length ? s.last_check_tools.length + ' 个工具' : '—' }}</td>
              <td class="actions">
                <button class="btn btn-sm btn-secondary" :disabled="busy === s.id" @click="test(s)">测试连接</button>
                <button class="btn btn-sm btn-secondary" :disabled="busy === s.id" @click="toggle(s)">
                  {{ s.enabled ? '停用' : '启用' }}
                </button>
                <button class="btn btn-sm btn-secondary" @click="edit(s)">编辑</button>
                <button class="btn btn-sm btn-secondary" @click="remove(s)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">尚未配置 MCP 服务。</p>
        <div v-if="lastTest" class="test-result" :class="lastTest.ok ? 'ok' : 'bad'">
          {{ lastTest.label }}
        </div>

        <button class="btn btn-primary" style="margin-top: 12px;" @click="startCreate">添加 MCP 服务</button>
      </div>
    </div>

    <div v-if="creating" class="modal-overlay" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="save">
        <h3>{{ form.id ? '编辑 MCP 服务' : '添加 MCP 服务' }}</h3>
        <label class="field-label">名称（小写字母/数字/-/_，2-41 位）</label>
        <input v-model="form.name" class="input" required pattern="[a-z0-9][a-z0-9_-]{1,40}" />
        <label class="field-label">StreamableHTTP 地址</label>
        <input v-model="form.url" class="input" required placeholder="https://host/path" />
        <label class="field-label">
          凭据（{{ form.id ? '留空=保留现有' : '可选 Bearer Token' }}）
        </label>
        <input v-model="form.credential" class="input" type="password" autocomplete="new-password" />
        <label v-if="form.id && form.credential_set" class="field-label checkbox-line">
          <input v-model="form.clear_credential" type="checkbox" /> 显式清除已存凭据
        </label>
        <label class="field-label">允许工具（glob，逗号分隔，留空=全部）</label>
        <input v-model="form.allowed" class="input" placeholder="search_*, ask" />
        <label class="field-label">受众</label>
        <select v-model="form.audience" class="input">
          <option value="config_admin">仅系统配置者</option>
          <option value="all">所有登录用户</option>
        </select>
        <div class="row-line">
          <div class="field grow">
            <label class="field-label">连接超时（秒）</label>
            <input v-model.number="form.connect_timeout_s" class="input" type="number" min="1" max="600" />
          </div>
          <div class="field grow">
            <label class="field-label">调用超时（秒）</label>
            <input v-model.number="form.call_timeout_s" class="input" type="number" min="1" max="600" />
          </div>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="creating = false">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="busy === 'form'">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
// MCP 配置面板（P4）：对应真实持久配置；凭据只写不读；测试与启用是分开的动作。
import { onMounted, reactive, ref } from 'vue'
import * as api from '@/api/mcp'
import type { McpServer, McpTestResult } from '@/api/mcp'

const servers = ref<McpServer[]>([])
const error = ref('')
const busy = ref('')
const creating = ref(false)
const lastTest = ref<{ label: string; ok: boolean } | null>(null)
const form = reactive({
  id: '',
  name: '',
  url: '',
  credential: '',
  credential_set: false,
  clear_credential: false,
  allowed: '',
  audience: 'config_admin' as 'config_admin' | 'all',
  connect_timeout_s: 60,
  call_timeout_s: 300,
})

async function load() {
  error.value = ''
  try {
    servers.value = await api.listServers()
  } catch (e: any) {
    error.value = e?.message || 'MCP 配置加载失败'
  }
}

function checkKindLabel(s: McpServer): string {
  const kind = s.last_check_error || ''
  if (kind.includes('401') || kind.includes('403') || /auth/i.test(kind)) return '认证失败'
  if (/超时|timeout/i.test(kind)) return '连接超时'
  if (kind) return '连接失败'
  return s.last_check_state
}

async function test(s: McpServer) {
  busy.value = s.id
  error.value = ''
  try {
    const r: McpTestResult = await api.testServer(s.id)
    lastTest.value = r.ok
      ? { ok: true, label: `「${s.name}」连接正常：${r.tools.length} 个工具${r.truncated ? '（目录过大已截断显示）' : ''}` }
      : { ok: false, label: `「${s.name}」${r.state === 'empty' ? '目录为空' : '连接失败'}：${r.error_message || r.error_kind}` }
    await load()
  } catch (e: any) {
    error.value = e?.message || '测试失败'
  } finally {
    busy.value = ''
  }
}

async function toggle(s: McpServer) {
  busy.value = s.id
  error.value = ''
  try {
    if (!s.enabled) {
      // fail-closed：启用前先验证连接与目录
      const r = await api.testServer(s.id)
      if (!r.ok) {
        error.value = `「${s.name}」未通过连接测试（${r.error_message || r.error_kind || '空目录'}），保持停用`
        await load()
        return
      }
    }
    await api.setEnabled(s.id, !s.enabled)
    await load()
  } catch (e: any) {
    error.value = e?.message || '状态更新失败'
  } finally {
    busy.value = ''
  }
}

function startCreate() {
  Object.assign(form, {
    id: '', name: '', url: '', credential: '', credential_set: false,
    clear_credential: false, allowed: '', audience: 'config_admin',
    connect_timeout_s: 60, call_timeout_s: 300,
  })
  creating.value = true
}

function edit(s: McpServer) {
  Object.assign(form, {
    id: s.id, name: s.name, url: s.url, credential: '',
    credential_set: s.credential_set, clear_credential: false,
    allowed: s.allowed_tools.join(', '), audience: s.audience,
    connect_timeout_s: s.connect_timeout_s, call_timeout_s: s.call_timeout_s,
  })
  creating.value = true
}

async function save() {
  busy.value = 'form'
  error.value = ''
  try {
    const draft: api.McpDraft = {
      name: form.name,
      url: form.url,
      audience: form.audience,
      allowed_tools: form.allowed.split(',').map(x => x.trim()).filter(Boolean),
      connect_timeout_s: form.connect_timeout_s,
      call_timeout_s: form.call_timeout_s,
    }
    if (form.credential.trim()) draft.credential = form.credential.trim()
    if (form.id && form.clear_credential) draft.clear_credential = true
    if (form.id) await api.updateServer(form.id, draft)
    else await api.createServer(draft)
    creating.value = false
    await load()
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  } finally {
    busy.value = ''
  }
}

async function remove(s: McpServer) {
  if (!confirm(`删除「${s.name}」？凭据将一并销毁；如已注册需重启回收连接资源。`)) return
  try {
    await api.deleteServer(s.id)
    await load()
  } catch (e: any) {
    error.value = e?.message || '删除失败'
  }
}

onMounted(load)
</script>

<style scoped>
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border-primary); }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; }
.url { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ok { color: #1d7f3c; }
.warn { color: #b58900; }
.bad { color: #b42318; }
.muted { color: var(--text-tertiary); }
.error-banner { background: rgba(220,53,69,.12); color: #c82333; padding: 8px 10px; border-radius: 6px; margin-bottom: 10px; font-size: 13px; }
.test-result { margin-top: 10px; padding: 8px 10px; border-radius: 6px; font-size: 13px; }
.test-result.ok { background: rgba(29,127,60,.1); color: #1d7f3c; }
.test-result.bad { background: rgba(180,35,24,.08); color: #b42318; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 60; }
.modal-card { width: min(560px, 92vw); max-height: 88vh; overflow: auto; background: var(--bg-primary); border-radius: 10px; padding: 20px; display: grid; gap: 8px; }
.modal-card h3 { margin: 0 0 8px; }
.field-label { font-size: 13px; color: var(--text-secondary); }
.checkbox-line { display: flex; gap: 6px; align-items: center; }
.row-line { display: flex; gap: 12px; }
.field { display: grid; gap: 4px; }
.field.grow { flex: 1; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.section-tip { font-size: 12px; color: var(--text-tertiary); }
.empty-state { color: var(--text-tertiary); padding: 16px 0; }
</style>
