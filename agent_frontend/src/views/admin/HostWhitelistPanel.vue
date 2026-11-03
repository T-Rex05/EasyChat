<template>
  <div class="section">
    <div class="section-header">
      <div>
        <h2 class="section-title">主机白名单</h2>
        <p class="section-desc">白名单内的主机允许持有「主机白名单」权限的角色 Agent 免密登录；每条远程命令仍需人工审批。</p>
      </div>
      <button class="btn btn-primary" @click="openEdit()">+ 添加主机</button>
    </div>

    <div v-if="loading" class="loading-state"><div class="spinner"></div><p>加载中...</p></div>
    <div v-else-if="hosts.length === 0" class="empty-state"><p>白名单为空 — 此时所有 ssh/scp 远程执行都会被拦截（secure-by-default）</p></div>
    <table v-else class="host-table">
      <thead>
        <tr><th>主机</th><th>登录用户</th><th>端口</th><th>认证方式</th><th>凭据</th><th>备注</th><th>状态</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="h in hosts" :key="h.id">
          <td><code>{{ h.host_identifier }}</code></td>
          <td>{{ h.access_user || "-" }}</td>
          <td>{{ h.access_port }}</td>
          <td>{{ authLabel(h.auth_method) }}</td>
          <td>{{ h.auth_configured ? '已配置' : '未配置' }}</td>
          <td>{{ h.remark || "-" }}</td>
          <td>
            <span class="status-tag" :class="h.status === 1 ? 'on' : 'off'">{{ h.status === 1 ? '启用' : '禁用' }}</span>
          </td>
          <td class="actions">
            <button class="btn btn-sm btn-test" @click="testHost(h)" :disabled="testingId === h.id">
              <span v-if="testingId === h.id" class="spinner-tiny"></span>
              <span v-else>🔌 测试</span>
            </button>
            <button class="btn btn-sm btn-secondary" @click="openEdit(h)">编辑</button>
            <button class="btn btn-sm btn-secondary" @click="toggleStatus(h)">{{ h.status === 1 ? '禁用' : '启用' }}</button>
            <button class="btn btn-sm btn-danger" @click="removeHost(h)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 测试结果提示 -->
    <div v-if="testResult" class="test-result-toast" :class="testResult.ok ? 'success' : 'error'">
      <span>{{ testResult.ok ? '✅' : '❌' }} {{ testResult.message }}</span>
      <button class="btn-close-toast" @click="testResult = null">✕</button>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="showEditor" class="modal-overlay" @click.self="showEditor = false">
      <div class="modal">
        <div class="modal-header"><h2>{{ editing?.id ? '编辑主机' : '添加主机' }}</h2><button class="btn-close" @click="showEditor = false">✕</button></div>
        <div class="modal-body">
          <div class="form-group"><label class="form-label">主机 IP/主机名 *</label><input v-model="form.host_identifier" class="input" placeholder="192.168.1.10" /></div>
          <div class="form-group"><label class="form-label">登录用户名</label><input v-model="form.access_user" class="input" placeholder="root" /></div>
          <div class="form-row">
            <div class="form-group"><label class="form-label">端口</label><input v-model.number="form.access_port" type="number" class="input" /></div>
            <div class="form-group">
              <label class="form-label">认证方式</label>
              <select v-model="form.auth_method" class="input">
                <option value="none">无（密钥已配置在服务器）</option>
                <option value="password">密码（需主机安装 sshpass）</option>
                <option value="key">私钥文件路径</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">{{ form.auth_method === 'key' ? '私钥文件路径' : 'SSH 密码' }}</label>
            <input v-model="form.auth_secret" type="password" class="input"
              :placeholder="editing?.id ? '已配置，留空保持不变' : '输入后 AES 加密存储'" />
          </div>
          <div class="form-group"><label class="form-label">备注</label><input v-model="form.remark" class="input" /></div>
          <div class="modal-actions">
            <button class="btn btn-test" @click="testFromForm" :disabled="testingFromForm">
              <span v-if="testingFromForm" class="spinner-tiny"></span>
              <span v-else>🔌 测试连接</span>
            </button>
            <div class="modal-actions-right">
              <button class="btn btn-secondary" @click="showEditor = false">取消</button>
              <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button>
            </div>
          </div>
          <!-- 弹窗内测试结果 -->
          <div v-if="formTestResult" class="form-test-result" :class="formTestResult.ok ? 'success' : 'error'">
            {{ formTestResult.ok ? '✅' : '❌' }} {{ formTestResult.message }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import request from '@/api/request'
import { errMsg } from '@/utils/err'

const hosts = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const showEditor = ref(false)
const editing = ref<any>(null)
const form = ref({ host_identifier: '', access_user: '', access_port: 22, auth_method: 'none', auth_secret: '', remark: '' })

// 测试相关
const testingId = ref<number | null>(null)
const testResult = ref<{ ok: boolean; message: string } | null>(null)
const testingFromForm = ref(false)
const formTestResult = ref<{ ok: boolean; message: string } | null>(null)

function authLabel(m?: string) {
  const map: Record<string, string> = { password: '密码', key: '私钥', none: '免密(密钥已配置)' }
  return map[m || 'none'] || m || '-'
}

async function loadHosts() {
  loading.value = true
  try {
    hosts.value = (await request.get('/api/admin/host-whitelist')).data
  } catch (e: any) {
    alert('加载失败: ' + errMsg(e))
  } finally {
    loading.value = false
  }
}

function openEdit(h?: any) {
  editing.value = h || null
  form.value = h ? {
    host_identifier: h.host_identifier, access_user: h.access_user || '',
    access_port: h.access_port || 22, auth_method: h.auth_method || 'none',
    auth_secret: '', remark: h.remark || '',
  } : { host_identifier: '', access_user: '', access_port: 22, auth_method: 'none', auth_secret: '', remark: '' }
  formTestResult.value = null
  showEditor.value = true
}

async function save() {
  if (!form.value.host_identifier) { alert('主机标识不能为空'); return }
  saving.value = true
  try {
    const payload = { ...form.value }
    if (editing.value?.id) {
      await request.put(`/api/admin/host-whitelist/${editing.value.id}`, payload)
    } else {
      await request.post('/api/admin/host-whitelist', payload)
    }
    showEditor.value = false
    await loadHosts()
  } catch (e: any) {
    alert('保存失败: ' + errMsg(e))
  } finally {
    saving.value = false
  }
}

async function toggleStatus(h: any) {
  try {
    await request.put(`/api/admin/host-whitelist/${h.id}`, {
      host_identifier: h.host_identifier, access_user: h.access_user, access_port: h.access_port,
      auth_method: h.auth_method || 'none', auth_secret: '', remark: h.remark, status: h.status === 1 ? 0 : 1,
    })
    await loadHosts()
  } catch (e: any) {
    alert('操作失败: ' + errMsg(e))
  }
}

async function removeHost(h: any) {
  if (!confirm(`确定删除主机 "${h.host_identifier}"？`)) return
  try {
    await request.delete(`/api/admin/host-whitelist/${h.id}`)
    await loadHosts()
  } catch (e: any) {
    alert('删除失败: ' + errMsg(e))
  }
}

// ── 测试连通性 ──
async function testHost(h: any) {
  testingId.value = h.id
  testResult.value = null
  try {
    const res = await request.post('/api/admin/host-whitelist/test', {
      host_identifier: h.host_identifier,
      access_user: h.access_user || '',
      access_port: h.access_port || 22,
      auth_method: h.auth_method || 'none',
      auth_secret: '',  // 不传密码，后端从 DB 取已保存的凭据
      timeout: 10,
    })
    testResult.value = res.data
  } catch (e: any) {
    testResult.value = { ok: false, message: '测试请求失败: ' + errMsg(e) }
  } finally {
    testingId.value = null
    // 5 秒后自动隐藏
    setTimeout(() => { testResult.value = null }, 8000)
  }
}

async function testFromForm() {
  if (!form.value.host_identifier) { alert('请先填写主机 IP/主机名'); return }
  testingFromForm.value = true
  formTestResult.value = null
  try {
    const res = await request.post('/api/admin/host-whitelist/test', {
      host_identifier: form.value.host_identifier,
      access_user: form.value.access_user || '',
      access_port: form.value.access_port || 22,
      auth_method: form.value.auth_method || 'none',
      auth_secret: form.value.auth_secret || '',
      timeout: 10,
    })
    formTestResult.value = res.data
  } catch (e: any) {
    formTestResult.value = { ok: false, message: '测试请求失败: ' + errMsg(e) }
  } finally {
    testingFromForm.value = false
  }
}

onMounted(loadHosts)
</script>

<style scoped>
.section { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.section-title { font-size: 18px; margin: 0 0 4px 0; }
.section-desc { margin: 0; color: var(--text-secondary); font-size: 13px; }
.host-table { width: 100%; border-collapse: collapse; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 10px; overflow: hidden; }
.host-table th, .host-table td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--border-primary); }
.host-table th { background: var(--bg-secondary); font-weight: 600; }
.status-tag { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.status-tag.on { background: #e8f5e9; color: #2e7d32; }
.status-tag.off { background: #ffebee; color: #c62828; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.btn { padding: 8px 16px; border-radius: 8px; font-size: 13px; cursor: pointer; border: 1px solid var(--border-primary); }
.btn-primary { background: var(--brand-gradient); color: white; border: none; }
.btn-secondary { background: var(--bg-secondary); color: var(--text-primary); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { background: #ffebee; color: #c62828; border-color: #ffcdd2; }
.btn-test { background: #e3f2fd; color: #1565c0; border-color: #bbdefb; }
.btn-test:hover { background: #bbdefb; }
.btn-test:disabled { opacity: 0.6; cursor: not-allowed; }
.loading-state, .empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary); }
.spinner { width: 32px; height: 32px; border: 3px solid var(--border-primary); border-top-color: var(--brand); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px; }
.spinner-tiny { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border-primary); border-top-color: #1565c0; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-primary); border-radius: 12px; width: 90%; max-width: 520px; max-height: 90vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-primary); }
.modal-header h2 { margin: 0; font-size: 18px; }
.btn-close { background: none; border: none; font-size: 18px; cursor: pointer; color: var(--text-tertiary); }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.form-label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.input { width: 100%; padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 18px; }
.modal-actions-right { display: flex; gap: 10px; }
.form-test-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.form-test-result.success { background: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
.form-test-result.error { background: #ffebee; color: #c62828; border: 1px solid #ffcdd2; }
.test-result-toast { position: fixed; bottom: 24px; right: 24px; padding: 14px 20px; border-radius: 10px; font-size: 13px; display: flex; align-items: center; gap: 12px; z-index: 2000; box-shadow: 0 4px 12px rgba(0,0,0,0.15); max-width: 480px; animation: slideIn 0.3s ease; }
.test-result-toast.success { background: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
.test-result-toast.error { background: #ffebee; color: #c62828; border: 1px solid #ffcdd2; }
.btn-close-toast { background: none; border: none; font-size: 14px; cursor: pointer; opacity: 0.6; color: inherit; }
.btn-close-toast:hover { opacity: 1; }
@keyframes slideIn { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
</style>
