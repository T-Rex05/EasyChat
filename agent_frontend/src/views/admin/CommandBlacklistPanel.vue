<template>
  <div class="section">
    <div class="section-header">
      <div>
        <h2 class="section-title">命令黑名单</h2>
        <p class="section-desc">管理自定义的危险命令正则规则。命中黑名单的命令会被拦截，需要管理员审批后才能执行。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="showAiDialog = true; aiResult = null; aiError = ''">🤖 AI 生成</button>
        <button class="btn btn-primary" @click="openAddDialog">+ 添加规则</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state"><div class="spinner"></div><p>加载中...</p></div>
    <div v-else-if="rules.length === 0" class="empty-state"><p>暂无黑名单规则</p></div>
    <table v-else class="rules-table">
      <thead>
        <tr>
          <th>正则表达式</th>
          <th>描述</th>
          <th>状态</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="rule in rules" :key="rule.id">
          <td><code class="pattern-code">{{ rule.pattern }}</code></td>
          <td>{{ rule.description || '-' }}</td>
          <td>
            <span class="status-tag" :class="rule.enabled ? 'on' : 'off'">
              {{ rule.enabled ? '启用' : '禁用' }}
            </span>
          </td>
          <td class="time-col">{{ formatTime(rule.created_at) }}</td>
          <td class="actions">
            <button class="btn btn-sm btn-secondary" @click="openEditDialog(rule)">编辑</button>
            <button class="btn btn-sm btn-secondary" @click="toggleRule(rule)">
              {{ rule.enabled ? '禁用' : '启用' }}
            </button>
            <button class="btn btn-sm btn-danger" @click="deleteRule(rule)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 添加/编辑弹窗 -->
    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h2>{{ editingRule ? '编辑规则' : '添加规则' }}</h2>
          <button class="btn-close" @click="showDialog = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">正则表达式 *</label>
            <input v-model="form.pattern" class="input" placeholder="例如：\brm\s+-rf\s+/" />
            <p class="form-hint">使用 Python re 语法的正则表达式，不区分大小写</p>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <input v-model="form.description" class="input" placeholder="例如：递归删除根目录" />
          </div>
          <div class="form-group">
            <label class="form-checkbox">
              <input type="checkbox" v-model="form.enabled" />
              <span>启用</span>
            </label>
          </div>
          <div v-if="testResult" class="test-result" :class="testResult.ok ? 'success' : 'error'">
            {{ testResult.message }}
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="testPattern" :disabled="testing">
            {{ testing ? '测试中...' : '测试正则' }}
          </button>
          <div class="modal-actions-right">
            <button class="btn btn-secondary" @click="showDialog = false">取消</button>
            <button class="btn btn-primary" @click="saveRule" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 生成弹窗 -->
    <div v-if="showAiDialog" class="modal-overlay" @click.self="showAiDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h2>AI 辅助生成正则</h2>
          <button class="btn-close" @click="showAiDialog = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">用中文描述想拦截的命令行为 *</label>
            <textarea v-model="aiDescription" class="input textarea" rows="3" 
              placeholder="例如：禁止删除 /data 目录下的所有文件"></textarea>
            <p class="form-hint">AI 会根据描述生成正则表达式和正反例</p>
          </div>
          
          <div v-if="aiResult" class="ai-result">
            <div class="ai-result-header">
              <span>生成结果</span>
              <button class="btn btn-sm btn-secondary" @click="applyAiResult">应用到表单</button>
            </div>
            <div class="ai-result-item">
              <label>正则表达式：</label>
              <code class="pattern-code">{{ aiResult.pattern }}</code>
            </div>
            <div class="ai-result-item">
              <label>应该命中的示例：</label>
              <ul class="example-list">
                <li v-for="(ex, i) in aiResult.should_match" :key="'m'+i">{{ ex }}</li>
              </ul>
            </div>
            <div class="ai-result-item">
              <label>不应该命中的示例：</label>
              <ul class="example-list">
                <li v-for="(ex, i) in aiResult.should_not_match" :key="'n'+i">{{ ex }}</li>
              </ul>
            </div>
          </div>
          
          <div v-if="aiError" class="test-result error">{{ aiError }}</div>
        </div>
        <div class="modal-actions">
          <div></div>
          <div class="modal-actions-right">
            <button class="btn btn-secondary" @click="showAiDialog = false">关闭</button>
            <button class="btn btn-primary" @click="generateAiPattern" :disabled="generating">
              {{ generating ? '生成中...' : '生成正则' }}
            </button>
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

const rules = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const showDialog = ref(false)
const editingRule = ref<any>(null)
const form = ref({ pattern: '', description: '', enabled: true })
const testResult = ref<{ ok: boolean; message: string } | null>(null)

// AI 生成相关
const showAiDialog = ref(false)
const aiDescription = ref('')
const aiResult = ref<any>(null)
const aiError = ref('')
const generating = ref(false)

function formatTime(dt: string) {
  if (!dt) return '-'
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

async function loadRules() {
  loading.value = true
  try {
    const res = await request.get('/api/admin/command-blacklist')
    rules.value = res.data
  } catch (e: any) {
    alert('加载失败: ' + errMsg(e))
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  editingRule.value = null
  form.value = { pattern: '', description: '', enabled: true }
  testResult.value = null
  showDialog.value = true
}

function openEditDialog(rule: any) {
  editingRule.value = rule
  form.value = {
    pattern: rule.pattern,
    description: rule.description || '',
    enabled: rule.enabled
  }
  testResult.value = null
  showDialog.value = true
}

async function saveRule() {
  if (!form.value.pattern) {
    alert('正则表达式不能为空')
    return
  }
  saving.value = true
  try {
    if (editingRule.value) {
      await request.put(`/api/admin/command-blacklist/${editingRule.value.id}`, form.value)
    } else {
      await request.post('/api/admin/command-blacklist', form.value)
    }
    showDialog.value = false
    await loadRules()
  } catch (e: any) {
    alert('保存失败: ' + errMsg(e))
  } finally {
    saving.value = false
  }
}

async function toggleRule(rule: any) {
  try {
    await request.put(`/api/admin/command-blacklist/${rule.id}`, {
      pattern: rule.pattern,
      description: rule.description || '',
      enabled: !rule.enabled
    })
    await loadRules()
  } catch (e: any) {
    alert('操作失败: ' + errMsg(e))
  }
}

async function deleteRule(rule: any) {
  if (!confirm(`确定删除规则「${rule.pattern}」？`)) return
  try {
    await request.delete(`/api/admin/command-blacklist/${rule.id}`)
    await loadRules()
  } catch (e: any) {
    alert('删除失败: ' + errMsg(e))
  }
}

async function testPattern() {
  if (!form.value.pattern) {
    alert('请先填写正则表达式')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    const res = await request.post('/api/admin/command-blacklist/test', {
      pattern: form.value.pattern,
      description: form.value.description,
      enabled: form.value.enabled
    })
    testResult.value = res.data
  } catch (e: any) {
    testResult.value = { ok: false, message: '测试失败: ' + errMsg(e) }
  } finally {
    testing.value = false
  }
}

async function generateAiPattern() {
  if (!aiDescription.value) {
    aiError.value = '请先填写描述'
    return
  }
  generating.value = true
  aiError.value = ''
  aiResult.value = null
  try {
    const res = await request.post('/api/admin/command-blacklist/ai-suggest', {
      description: aiDescription.value
    })
    aiResult.value = res.data
  } catch (e: any) {
    aiError.value = '生成失败: ' + errMsg(e)
  } finally {
    generating.value = false
  }
}

function applyAiResult() {
  if (!aiResult.value) return
  form.value.pattern = aiResult.value.pattern
  form.value.description = aiDescription.value
  showAiDialog.value = false
  showDialog.value = true
  editingRule.value = null
}

onMounted(loadRules)
</script>

<style scoped>
.section { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.section-title { font-size: 18px; margin: 0 0 4px 0; }
.section-desc { margin: 0; color: var(--text-secondary); font-size: 13px; }
.header-actions { display: flex; gap: 10px; }
.rules-table { width: 100%; border-collapse: collapse; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 10px; overflow: hidden; }
.rules-table th, .rules-table td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--border-primary); }
.rules-table th { background: var(--bg-secondary); font-weight: 600; }
.pattern-code { background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; color: var(--brand); word-break: break-all; }
.time-col { white-space: nowrap; font-size: 12px; color: var(--text-secondary); }
.status-tag { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.status-tag.on { background: #e8f5e9; color: #2e7d32; }
.status-tag.off { background: #ffebee; color: #c62828; }
.actions { display: flex; gap: 6px; }
.btn { padding: 8px 16px; border-radius: 8px; font-size: 13px; cursor: pointer; border: 1px solid var(--border-primary); }
.btn-primary { background: var(--brand-gradient); color: white; border: none; }
.btn-secondary { background: var(--bg-secondary); color: var(--text-primary); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { background: #ffebee; color: #c62828; border-color: #ffcdd2; }
.loading-state, .empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary); }
.spinner { width: 32px; height: 32px; border: 3px solid var(--border-primary); border-top-color: var(--brand); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-primary); border-radius: 12px; width: 90%; max-width: 520px; max-height: 90vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-primary); }
.modal-header h2 { margin: 0; font-size: 18px; }
.btn-close { background: none; border: none; font-size: 18px; cursor: pointer; color: var(--text-tertiary); }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.form-hint { margin: 4px 0 0 0; font-size: 12px; color: var(--text-tertiary); }
.form-checkbox { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.input { width: 100%; padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; }
.textarea { resize: vertical; min-height: 60px; font-family: inherit; }
.modal-actions { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-top: 1px solid var(--border-primary); }
.modal-actions-right { display: flex; gap: 10px; }
.test-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.test-result.success { background: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
.test-result.error { background: #ffebee; color: #c62828; border: 1px solid #ffcdd2; }

/* AI 生成结果样式 */
.ai-result { margin-top: 16px; padding: 16px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-primary); }
.ai-result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-weight: 600; }
.ai-result-item { margin-bottom: 12px; }
.ai-result-item label { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.example-list { margin: 4px 0 0 0; padding-left: 20px; font-size: 12px; color: var(--text-primary); }
.example-list li { margin: 2px 0; }
</style>
