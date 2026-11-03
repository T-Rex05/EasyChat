<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">部门管理</h2>
      <button class="btn btn-primary btn-sm" @click="openCreate">+ 新建部门</button>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="layers.length === 0" class="empty-state">
      <p>暂无部门</p>
    </div>

    <div v-else class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>部门名称</th>
            <th>描述</th>
            <th>关联知识库</th>
            <th>关联用户</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="layer in layers" :key="layer.id">
            <td>{{ layer.id }}</td>
            <td>
              <span>{{ layer.name }}</span>
              <span v-if="layer.is_system" class="badge-system">系统</span>
            </td>
            <td>{{ layer.description || '-' }}</td>
            <td>{{ layer.kb_count || 0 }} 个</td>
            <td>{{ layer.user_count || 0 }} 人</td>
            <td>
              <button v-if="!layer.is_system" @click="openEdit(layer)" class="btn-link">编辑</button>
              <button v-if="!layer.is_system" @click="confirmDelete(layer)" class="btn-link btn-danger">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建/编辑对话框 -->
    <div v-if="showDialog" class="dialog-overlay" @click="closeDialog">
      <div class="dialog" @click.stop>
        <div class="dialog-header">
          <h3>{{ editingLayer ? '编辑部门' : '新建部门' }}</h3>
          <button class="btn-close" @click="closeDialog">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>部门名称 *</label>
            <input v-model="form.name" type="text" placeholder="例如：技术部" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="form.description" placeholder="部门说明"></textarea>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn" @click="closeDialog">取消</button>
          <button class="btn btn-primary" @click="submitForm" :disabled="submitting">
            {{ submitting ? '提交中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as AdminAPI from '@/api/admin'
import type { DataLayer } from '@/api/admin'

const layers = ref<DataLayer[]>([])
const loading = ref(false)
const showDialog = ref(false)
const editingLayer = ref<DataLayer | null>(null)
const submitting = ref(false)

const form = ref({
  name: '',
  description: ''
})

async function loadLayers() {
  loading.value = true
  try {
    layers.value = await AdminAPI.getDataLayers()
  } catch (e) {
    console.error('加载部门失败:', e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingLayer.value = null
  form.value = { name: '', description: '' }
  showDialog.value = true
}

function openEdit(layer: DataLayer) {
  editingLayer.value = layer
  form.value = { name: layer.name, description: layer.description || '' }
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
  editingLayer.value = null
}

async function submitForm() {
  if (!form.value.name.trim()) {
    alert('请输入部门名称')
    return
  }

  submitting.value = true
  try {
    if (editingLayer.value) {
      await AdminAPI.updateDataLayer(editingLayer.value.id, form.value)
    } else {
      await AdminAPI.createDataLayer(form.value)
    }
    closeDialog()
    await loadLayers()
  } catch (e: any) {
    console.error('提交失败:', e)
    alert(e.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function confirmDelete(layer: DataLayer) {
  const msg = `确定要删除部门"${layer.name}"吗？\n\n` +
    `该部门关联 ${(layer.kb_count || 0)} 个知识库、${(layer.user_count || 0)} 个用户。\n` +
    `如有引用，将无法删除。`
  if (!confirm(msg)) return

  try {
    await AdminAPI.deleteDataLayer(layer.id)
    await loadLayers()
  } catch (e: any) {
    console.error('删除失败:', e)
    alert(e.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
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

.badge-system {
  margin-left: 8px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.btn-link {
  background: none;
  border: none;
  color: var(--brand);
  cursor: pointer;
  font-size: 13px;
  text-decoration: underline;
  margin-right: 12px;
}

.btn-link:hover {
  color: var(--brand-hover);
}

.btn-link.btn-danger {
  color: #ff4d4f;
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

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
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
  max-width: 480px;
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
  font-size: 18px;
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

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-primary);
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border-primary);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
