<template>
  <div class="knowledge-base-manager">
    <div class="header">
      <h2>知识库管理</h2>
      <button class="btn btn-primary" @click="showCreateDialog = true">
        <i class="icon-plus"></i> 创建知识库
      </button>
    </div>

    <div class="kb-list">
      <div v-for="kb in knowledgeBases" :key="kb.id" class="kb-card">
        <div class="kb-header">
          <h3>{{ kb.kb_name }}</h3>
          <span class="kb-dept-badge">{{ getLayerNames(kb) }}</span>
        </div>
        <div class="kb-body">
          <p class="kb-desc">{{ kb.description || '暂无描述' }}</p>
          <div class="kb-meta">
            <span>文档数: {{ kb.document_count || 0 }}</span>
            <span>创建时间: {{ formatDate(kb.created_at) }}</span>
          </div>
        </div>
        <div class="kb-footer">
          <button class="btn btn-sm" @click="editKb(kb)">编辑</button>
          <button class="btn btn-sm btn-danger" @click="deleteKb(kb)">删除</button>
        </div>
      </div>
    </div>

    <!-- 创建/编辑知识库对话框 -->
    <div v-if="showCreateDialog || showEditDialog" class="dialog-overlay" @click="closeDialogs">
      <div class="dialog" @click.stop>
        <div class="dialog-header">
          <h3>{{ showEditDialog ? '编辑知识库' : '创建知识库' }}</h3>
          <button class="btn-close" @click="closeDialogs">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>知识库名称 *</label>
            <input v-model="formData.kb_name" type="text" placeholder="例如：历史正确案例" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="formData.description" placeholder="描述知识库的用途和内容"></textarea>
          </div>
          <div class="form-group">
            <label>所属部门（可多选）</label>
            <div class="layer-checkboxes">
              <label v-for="layer in dataLayers" :key="layer.id" class="layer-checkbox">
                <input type="checkbox" :value="layer.id" v-model="formData.layer_ids" />
                <span>{{ layer.name }}</span>
              </label>
            </div>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn" @click="closeDialogs">取消</button>
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
import request from '@/api/request'

interface KnowledgeBase {
  id: number
  kb_name: string
  description: string
  document_count?: number
  created_at: string
  user_id: number
  layer_ids?: number[]
  layer_names?: string[]
}

interface DataLayer {
  id: number
  name: string
}

const knowledgeBases = ref<KnowledgeBase[]>([])
const dataLayers = ref<DataLayer[]>([])
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const editingKb = ref<KnowledgeBase | null>(null)
const submitting = ref(false)

const formData = ref({
  kb_name: '',
  description: '',
  layer_ids: [] as number[]
})

const getLayerNames = (kb: KnowledgeBase): string => {
  if (kb.layer_names && kb.layer_names.length > 0) {
    return kb.layer_names.join(', ')
  }
  return '全员'
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const loadKnowledgeBases = async () => {
  try {
    const res = await request.get('/api/kb/knowledge-bases')
    knowledgeBases.value = res.data.knowledge_bases || []
  } catch (error) {
    console.error('加载知识库列表失败:', error)
  }
}

const loadDataLayers = async () => {
  try {
    const res = await request.get('/api/data-layers')
    dataLayers.value = res.data.data || []
  } catch (error) {
    console.error('加载部门列表失败:', error)
  }
}

const editKb = (kb: KnowledgeBase) => {
  editingKb.value = kb
  formData.value = {
    kb_name: kb.kb_name,
    description: kb.description,
    layer_ids: kb.layer_ids || [0]
  }
  showEditDialog.value = true
}

const deleteKb = async (kb: KnowledgeBase) => {
  if (!confirm(`确定要删除知识库"${kb.kb_name}"吗？这将删除该知识库下的所有文档和分片。`)) {
    return
  }
  try {
    await request.delete(`/api/kb/knowledge-bases/${kb.id}`)
    await loadKnowledgeBases()
  } catch (error) {
    console.error('删除知识库失败:', error)
    alert('删除失败，请重试')
  }
}

const closeDialogs = () => {
  showCreateDialog.value = false
  showEditDialog.value = false
  editingKb.value = null
  formData.value = {
    kb_name: '',
    description: '',
    layer_ids: []
  }
}

const submitForm = async () => {
  if (!formData.value.kb_name.trim()) {
    alert('请输入知识库名称')
    return
  }

  submitting.value = true
  try {
    const payload = {
      kb_name: formData.value.kb_name,
      description: formData.value.description
    }
    if (showEditDialog.value && editingKb.value) {
      // 编辑模式
      await request.put(`/api/kb/knowledge-bases/${editingKb.value.id}`, payload)
      // 单独保存层级
      await request.put(`/api/data-layers/kb/${editingKb.value.id}`, { layer_ids: formData.value.layer_ids })
    } else {
      // 创建模式
      const res = await request.post('/api/kb/knowledge-bases', payload)
      const newKbId = res.data.knowledge_base?.id
      if (newKbId) {
        await request.put(`/api/data-layers/kb/${newKbId}`, { layer_ids: formData.value.layer_ids })
      }
    }
    closeDialogs()
    await loadKnowledgeBases()
  } catch (error) {
    console.error('提交失败:', error)
    alert('提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadKnowledgeBases()
  loadDataLayers()
})
</script>

<style scoped>
.knowledge-base-manager {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header h2 {
  margin: 0;
  font-size: 24px;
}

.btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn:hover {
  background: #f5f5f5;
}

.btn-primary {
  background: #1890ff;
  color: white;
  border-color: #1890ff;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-danger {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

.btn-danger:hover {
  background: #ff4d4f;
  color: white;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

.kb-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.kb-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: white;
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.kb-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.kb-header {
  padding: 16px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kb-header h3 {
  margin: 0;
  font-size: 18px;
}

.kb-dept-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: #e6f7ff;
  color: #1890ff;
}

.kb-body {
  padding: 16px;
}

.kb-desc {
  margin: 0 0 12px 0;
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.kb-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #999;
}

.kb-footer {
  padding: 12px 16px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

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
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow: auto;
}

.dialog-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
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
  color: #999;
  padding: 0;
  width: 24px;
  height: 24px;
  line-height: 1;
}

.btn-close:hover {
  color: #333;
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
  color: #333;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.icon-plus::before {
  content: '+';
  margin-right: 4px;
}
</style>
