<template>
  <div class="schedules-page">
    <header class="page-header">
      <div>
        <h2>定时任务</h2>
        <p class="hint">按计划推送提醒或 AI 前沿日报；只保留最新一次错过实例。</p>
      </div>
      <button class="btn btn-primary" @click="showCreate = !showCreate">新建任务</button>
    </header>

    <form v-if="showCreate" class="card create-card" @submit.prevent="create">
      <div class="row">
        <select v-model="draft.content" class="select" @change="onContentChange">
          <option value="text">提醒文本</option>
          <option value="ai_news">AI 前沿日报（最多 10 条）</option>
        </select>
        <input v-model="draft.title" class="input" :placeholder="draft.content === 'ai_news' ? '标题（默认：AI 前沿日报）' : '标题（可选）'" />
        <select v-if="draft.content === 'text'" v-model="draft.kind" class="select">
          <option value="once">一次</option>
          <option value="daily">每天</option>
          <option value="interval">间隔</option>
        </select>
        <input v-if="draft.content === 'ai_news'" v-model="draft.dailyAt" class="input" type="time" required />
        <input v-else-if="draft.kind === 'once'" v-model="draft.at" class="input" type="datetime-local" required />
        <input v-else-if="draft.kind === 'daily'" v-model="draft.dailyAt" class="input" type="time" required />
        <input v-else v-model.number="draft.everySeconds" class="input" type="number" min="60" placeholder="间隔秒数" required />
      </div>
      <p v-if="draft.content === 'ai_news'" class="muted">
        每天抓取 OpenAI、DeepMind、TechCrunch、The Verge、MIT、arXiv 的 AI 资讯，排序后最多取 10 条，并用已配置模型生成中文摘要；模型不可用时保留原始标题。
      </p>
      <textarea v-else v-model="draft.text" class="textarea" rows="3" placeholder="提醒内容" required></textarea>
      <div class="row">
        <select v-model="draft.targetKind" class="select">
          <option value="">默认微信</option>
          <option value="email">邮箱</option>
        </select>
        <input v-if="draft.targetKind === 'email'" v-model="draft.targetRef" class="input" type="email" placeholder="收件邮箱" required />
        <span class="muted">默认使用你已绑定的微信；没有绑定时请选邮箱。</span>
      </div>
      <div class="actions">
        <button class="btn btn-secondary" type="button" @click="showCreate = false">取消</button>
        <button class="btn btn-primary" type="submit" :disabled="saving">创建</button>
      </div>
    </form>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="schedules.length === 0" class="empty">暂无提醒。</div>

    <div v-else class="list">
      <article v-for="s in schedules" :key="s.schedule_id" class="card item">
        <div class="item-head">
          <strong>{{ s.title || (isAiNews(s) ? 'AI 前沿日报' : '提醒') }}</strong>
          <span v-if="isAiNews(s)" class="tag ai">AI 日报</span>
          <span class="tag" :class="{ off: !s.enabled }">{{ s.enabled ? '启用' : '暂停' }}</span>
          <button class="btn btn-sm btn-secondary" @click="toggle(s)">{{ s.enabled ? '暂停' : '启用' }}</button>
          <button class="btn btn-sm btn-danger" @click="remove(s)">删除</button>
        </div>
        <p class="content">{{ isAiNews(s) ? '每天抓取并排序最新 AI 资讯（最多 10 条），发送到指定目标。' : s.text }}</p>
        <p class="muted">
          {{ kindText(s) }} · 目标 {{ s.target.kind }}:{{ s.target.ref }}
          · 下次 {{ s.next_run_at || '—' }}
        </p>
        <button class="link-btn" @click="loadOccurrences(s)">查看实例</button>
        <div v-if="expanded === s.schedule_id" class="occurrences">
          <div v-if="occurrences.length === 0" class="muted">暂无实例</div>
          <div v-for="o in occurrences" :key="o.occurrence_id" class="occurrence">
            <span>{{ o.scheduled_at }}</span>
            <span class="muted">{{ o.state }}{{ o.missed ? ' · 已错过' : '' }}</span>
            <span class="muted">{{ o.delivery_id || '—' }}</span>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import request from '@/api/request'

interface Schedule {
  schedule_id: string
  title: string
  text: string
  kind: string
  interval_seconds: number
  at_time: string
  enabled: boolean
  next_run_at: string
  target: { kind: string; ref: string }
  content_kind?: string
  briefing_kind?: string
}
interface Occurrence {
  occurrence_id: string
  scheduled_at: string
  state: string
  missed: boolean
  delivery_id: string | null
}

const schedules = ref<Schedule[]>([])
const occurrences = ref<Occurrence[]>([])
const expanded = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const showCreate = ref(false)
const draft = reactive({
  title: '', text: '', kind: 'daily', at: '', dailyAt: '08:00',
  everySeconds: 3600, targetKind: '', targetRef: '',
  content: 'text',
})

function onContentChange() {
  if (draft.content !== 'ai_news') return
  draft.kind = 'daily'
  if (!draft.title.trim()) draft.title = 'AI 前沿日报'
  if (!draft.dailyAt) draft.dailyAt = '08:00'
}

function toIso(local: string) {
  return local ? new Date(local).toISOString() : ''
}
function isAiNews(s: Schedule) {
  return s.content_kind === 'briefing' && s.briefing_kind === 'ai_news'
}
function kindText(s: Schedule) {
  if (isAiNews(s)) return `每天 ${s.at_time} · AI 前沿`
  if (s.kind === 'once') return `一次 ${s.at_time}`
  if (s.kind === 'daily') return `每天 ${s.at_time}`
  return `每 ${s.interval_seconds}s`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await request.get<{ schedules: Schedule[] }>('/api/schedules')
    schedules.value = res.data.schedules
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function create() {
  saving.value = true
  error.value = ''
  try {
    const body: Record<string, unknown> = {
      title: draft.title,
      text: draft.content === 'ai_news' ? '' : draft.text,
      target_kind: draft.targetKind,
      target_ref: draft.targetKind === 'email' ? draft.targetRef : '',
      content_kind: draft.content === 'ai_news' ? 'briefing' : 'text',
      briefing_kind: draft.content === 'ai_news' ? 'ai_news' : '',
    }
    if (draft.content === 'ai_news' || draft.kind === 'daily') body.daily_at = draft.dailyAt
    else if (draft.kind === 'once') body.at = toIso(draft.at)
    else body.every_seconds = draft.everySeconds
    await request.post('/api/schedules', body)
    draft.text = ''
    showCreate.value = false
    await load()
  } catch (e: any) {
    error.value = e?.message || '创建失败'
  } finally {
    saving.value = false
  }
}

async function toggle(s: Schedule) {
  try {
    await request.patch(`/api/schedules/${s.schedule_id}`, { enabled: !s.enabled })
    await load()
  } catch (e: any) {
    error.value = e?.message || '更新失败'
  }
}

async function remove(s: Schedule) {
  if (!confirm('删除这个提醒？已到达的实例不会撤回。')) return
  try {
    await request.delete(`/api/schedules/${s.schedule_id}`)
    await load()
  } catch (e: any) {
    error.value = e?.message || '删除失败'
  }
}

async function loadOccurrences(s: Schedule) {
  if (expanded.value === s.schedule_id) { expanded.value = ''; return }
  try {
    const res = await request.get<{ occurrences: Occurrence[] }>(`/api/schedules/${s.schedule_id}/occurrences`)
    occurrences.value = res.data.occurrences
    expanded.value = s.schedule_id
  } catch (e: any) {
    error.value = e?.message || '读取实例失败'
  }
}

onMounted(load)
</script>

<style scoped>
.schedules-page { max-width: 920px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.create-card { padding: 14px; display: grid; gap: 10px; margin-bottom: 16px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row .input { flex: 1; min-width: 160px; }
.textarea { width: 100%; resize: vertical; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.list { display: grid; gap: 10px; }
.item { padding: 14px; }
.item-head { display: flex; gap: 8px; align-items: center; }
.item-head strong { flex: 1; }
.content { margin: 8px 0; white-space: pre-wrap; }
.muted { color: var(--text-tertiary); font-size: 12px; }
.tag { background: var(--bg-tertiary); color: #2e7d32; border-radius: 999px; padding: 1px 8px; font-size: 12px; }
.tag.off { color: #999; }
.tag.ai { color: #6a4cff; background: rgba(106, 76, 255, 0.12); }
.link-btn { border: 0; background: transparent; color: var(--accent, #4a7cff); cursor: pointer; padding: 4px 0; }
.occurrences { border-top: 1px solid var(--border-primary); margin-top: 8px; padding-top: 8px; display: grid; gap: 4px; }
.occurrence { display: grid; grid-template-columns: 1.2fr 1fr 1fr; font-size: 12px; }
.empty { text-align: center; color: var(--text-tertiary); padding: 40px 0; }
.error-banner { background: rgba(220, 53, 69, 0.12); color: #c82333; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
</style>
