<template>
  <div class="memory-page">
    <header class="page-header">
      <div>
        <h2>记忆管理</h2>
        <p class="hint">只展示有来源的事实/事件/偏好/经验；删除为墓碑，不保留原文。</p>
      </div>
      <div class="header-actions">
        <input v-model="query" class="input" placeholder="检索记忆..." @keyup.enter="recall" />
        <button class="btn btn-secondary" :disabled="loading" @click="recall">检索</button>
        <button class="btn btn-primary" @click="showAdd = !showAdd">新增记忆</button>
      </div>
    </header>

    <form v-if="showAdd" class="card add-card" @submit.prevent="remember">
      <div class="form-row">
        <select v-model="draft.kind" class="select">
          <option value="fact">事实</option>
          <option value="event">事件</option>
          <option value="preference">偏好</option>
          <option value="experience">经验</option>
        </select>
        <input v-model="draft.source" class="input" placeholder="来源 ref（如 chat:42）" required />
        <input v-model="draft.quote" class="input" placeholder="来源引文（可选）" />
      </div>
      <textarea v-model="draft.content" class="textarea" rows="3" placeholder="要记住的内容" required></textarea>
      <div class="form-actions">
        <label class="checkbox"><input v-model="draft.pinned" type="checkbox" /> 固定</label>
        <button class="btn btn-primary" type="submit">保存</button>
      </div>
    </form>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="items.length === 0" class="empty">暂无记忆。聊天中明确说“记住…”或在这里新增。</div>

    <div v-else class="memory-list">
      <article v-for="item in items" :key="item.memory_id" class="card memory-card">
        <div class="memory-meta">
          <span class="tag">{{ kindLabel(item.kind) }}</span>
          <span class="muted">v{{ item.version }}</span>
          <span v-if="item.pinned" class="tag pin">固定</span>
          <span v-if="item.status !== 'active'" class="tag archived">{{ item.status }}</span>
          <span class="muted">{{ item.recorded_at }}</span>
        </div>
        <p class="content">{{ item.content }}</p>
        <p class="source">来源：{{ item.source_refs.map((r: any) => `${r.kind}:${r.ref}`).join('、') || '—' }}</p>
        <div class="card-actions">
          <button class="btn btn-sm btn-secondary" @click="startEdit(item)">修订</button>
          <button class="btn btn-sm btn-danger" @click="forget(item)">遗忘</button>
        </div>
        <form v-if="editing === item.memory_id" class="edit-form" @submit.prevent="saveEdit(item)">
          <textarea v-model="editContent" class="textarea" rows="3"></textarea>
          <div class="form-actions">
            <button class="btn btn-sm btn-secondary" type="button" @click="editing = ''">取消</button>
            <button class="btn btn-sm btn-primary" type="submit">提交修订</button>
          </div>
        </form>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import request from '@/api/request'

interface MemoryItem {
  memory_id: string
  kind: string
  content: string
  source_refs: { kind: string; ref: string; quote: string }[]
  status: string
  version: number
  pinned: boolean
  recorded_at: string
}

const items = ref<MemoryItem[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const showAdd = ref(false)
const editing = ref('')
const editContent = ref('')
const draft = reactive({ kind: 'fact', content: '', source: '', quote: '', pinned: false })

const KIND: Record<string, string> = {
  fact: '事实', event: '事件', preference: '偏好', experience: '经验',
}
const kindLabel = (kind: string) => KIND[kind] || kind

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await request.get<{ memories: MemoryItem[] }>('/api/memory')
    items.value = res.data.memories
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function recall() {
  if (!query.value.trim()) return load()
  loading.value = true
  error.value = ''
  try {
    const res = await request.post<{ items: { memory: MemoryItem }[] }>('/api/memory/recall', {
      query: query.value.trim(), top_k: 20, budget: 2000,
    })
    items.value = res.data.items.map((i) => i.memory)
  } catch (e: any) {
    error.value = e?.message || '检索失败'
  } finally {
    loading.value = false
  }
}

async function remember() {
  error.value = ''
  try {
    await request.post('/api/memory/remember', {
      kind: draft.kind,
      content: draft.content,
      source_refs: [{ kind: 'manual', ref: draft.source, quote: draft.quote }],
      source_type: 'user_explicit',
      pinned: draft.pinned,
    })
    draft.content = ''
    draft.quote = ''
    showAdd.value = false
    await load()
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  }
}

function startEdit(item: MemoryItem) {
  editing.value = item.memory_id
  editContent.value = item.content
}

async function saveEdit(item: MemoryItem) {
  try {
    await request.put(`/api/memory/${item.memory_id}`, {
      expected_version: item.version, content: editContent.value, reason: 'user revision',
    })
    editing.value = ''
    await load()
  } catch (e: any) {
    error.value = e?.message || '修订失败'
  }
}

async function forget(item: MemoryItem) {
  if (!confirm('确认遗忘这条记忆？原文将被墓碑替代。')) return
  try {
    await request.post('/api/memory/forget', { memory_id: item.memory_id, reason: 'user forget' })
    await load()
  } catch (e: any) {
    error.value = e?.message || '遗忘失败'
  }
}

onMounted(load)
</script>

<style scoped>
.memory-page { max-width: 980px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.add-card { padding: 14px; margin-bottom: 16px; display: grid; gap: 10px; }
.form-row { display: flex; gap: 8px; flex-wrap: wrap; }
.form-row .input { flex: 1; min-width: 160px; }
.textarea { width: 100%; resize: vertical; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; align-items: center; }
.checkbox { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.memory-list { display: grid; gap: 12px; }
.memory-card { padding: 14px; }
.memory-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.tag { background: var(--bg-tertiary); color: var(--text-secondary); border-radius: 999px; padding: 2px 8px; font-size: 12px; }
.tag.pin { color: #d98a00; }
.tag.archived { color: #999; }
.muted { color: var(--text-tertiary); font-size: 12px; }
.content { margin: 0 0 8px; white-space: pre-wrap; line-height: 1.55; }
.source { margin: 0; color: var(--text-tertiary); font-size: 12px; }
.card-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
.edit-form { margin-top: 10px; display: grid; gap: 8px; }
.empty { text-align: center; color: var(--text-tertiary); padding: 40px 0; }
.error-banner { background: rgba(220, 53, 69, 0.12); color: #c82333; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
</style>
