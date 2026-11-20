<template>
  <div class="schedules-page">
    <header class="page-header">
      <div>
        <h2>定时任务</h2>
        <p class="hint">管理提醒、简报和执行记录。</p>
      </div>
      <button type="button" class="btn btn-primary" @click="openEditor()">
        <Plus :size="16" aria-hidden="true" />
        新建任务
      </button>
    </header>

    <div v-if="error" class="error-banner" role="alert">{{ error }}</div>
    <div v-if="loading" class="card empty" role="status">正在加载定时任务…</div>
    <div v-else-if="schedules.length === 0 && !error" class="card empty">
      <CalendarClock :size="28" aria-hidden="true" />
      <p>暂无定时任务</p>
    </div>

    <div v-else class="list">
      <article v-for="s in schedules" :key="s.schedule_id" class="card item">
        <header class="item-header">
          <div class="item-heading">
            <div class="item-title">
              <h3>{{ s.title || briefingLabel(s) || '提醒' }}</h3>
              <span class="status" :class="{ active: s.enabled }">{{ statusText(s) }}</span>
            </div>
            <p v-if="s.text || s.briefing_kind === 'ai_news'" class="content">
              {{ s.text || '汇总最新 AI 资讯，每次最多 10 条。' }}
            </p>
          </div>
          <div class="actions">
            <button type="button" class="btn btn-sm btn-secondary" :disabled="actionId === s.schedule_id" @click="openEditor(s)">
              <Pencil :size="13" aria-hidden="true" /> 编辑
            </button>
            <button v-if="!isCompleted(s)" type="button" class="btn btn-sm btn-secondary" :disabled="actionId === s.schedule_id" @click="toggle(s)">
              {{ s.enabled ? '暂停' : '启用' }}
            </button>
            <button type="button" class="btn btn-sm btn-danger" :disabled="actionId === s.schedule_id" @click="remove(s)">删除</button>
          </div>
        </header>

        <dl class="item-meta">
          <div><dt>执行频率</dt><dd>{{ recurrence(s) }}</dd></div>
          <div>
            <dt>{{ isCompleted(s) ? '触发时间' : !s.enabled && s.kind === 'once' ? '计划时间' : '下次执行' }}</dt>
            <dd>
              <time v-if="s.enabled || s.kind === 'once'"
                :datetime="dateValue(isCompleted(s) ? s.last_run_at : s.next_run_at)?.toISOString()"
              >
                {{ formatDate(isCompleted(s) ? s.last_run_at : s.next_run_at, s.timezone) }}
              </time>
              <template v-else>暂停期间无安排</template>
              <span class="timezone">{{ s.timezone }}</span>
            </dd>
          </div>
          <div><dt>发送至</dt><dd>{{ destination(s) }}</dd></div>
        </dl>

        <button type="button" class="history-button" :aria-expanded="expanded === s.schedule_id" @click="loadOccurrences(s)">
          <ChevronDown :size="15" aria-hidden="true" />
          执行记录
        </button>
        <div v-if="expanded === s.schedule_id" class="occurrences">
          <p v-if="historyLoading" class="hint" role="status">正在读取执行记录…</p>
          <p v-else-if="historyError" class="hint" role="alert">{{ historyError }}</p>
          <p v-else-if="occurrences.length === 0" class="hint">暂无执行记录</p>
          <ul v-else>
            <li v-for="o in occurrences" :key="o.occurrence_id">
              <time :datetime="o.scheduled_at">{{ formatDate(o.scheduled_at, s.timezone) }}</time>
              <span>{{ occurrenceState[o.state] || o.state }}<template v-if="o.missed"> · 跳过 {{ o.missed }} 次</template></span>
            </li>
          </ul>
        </div>
      </article>
    </div>

    <dialog ref="editor" class="editor" aria-labelledby="schedule-editor-title" @cancel="cancelEditor">
      <form @submit.prevent="save">
        <header class="editor-header">
          <h3 id="schedule-editor-title">{{ editing ? '编辑定时任务' : '新建定时任务' }}</h3>
        </header>
        <fieldset :disabled="saving">
          <div class="form-grid">
            <label v-if="!editing">
              任务内容
              <select v-model="draft.content" class="select" @change="onContentChange">
                <option value="text">提醒文本</option>
                <option value="ai_news">AI 前沿日报</option>
              </select>
            </label>
            <label>
              标题
              <input v-model="draft.title" class="input" placeholder="可选" maxlength="120" autofocus />
            </label>
            <label v-if="editing ? editing.content_kind !== 'briefing' : draft.content === 'text'" class="wide">
              提醒内容
              <textarea v-model="draft.text" class="textarea" rows="3" required></textarea>
            </label>
            <label v-if="editing || draft.content === 'text'">
              执行频率
              <select v-model="draft.kind" class="select">
                <option value="once">仅一次</option>
                <option value="daily">每天</option>
                <option value="weekly">每周</option>
                <option value="interval">固定间隔</option>
              </select>
            </label>
            <label v-if="draft.kind === 'once'">
              执行时间
              <input v-model="draft.at" class="input" type="datetime-local" step="1" required />
            </label>
            <label v-if="draft.kind === 'weekly'">
              星期
              <select v-model.number="draft.weekday" class="select">
                <option v-for="(day, index) in weekdays" :key="day" :value="index">{{ day }}</option>
              </select>
            </label>
            <label v-if="draft.kind === 'daily' || draft.kind === 'weekly'">
              执行时间
              <input v-model="draft.time" class="input" type="time" required />
            </label>
            <label v-if="draft.kind === 'interval'">
              间隔秒数
              <input v-model.number="draft.everySeconds" class="input" type="number" min="60" step="1" required />
            </label>
            <label>
              时区
              <input v-model.trim="draft.timezone" class="input" list="schedule-timezones" required spellcheck="false" />
              <datalist id="schedule-timezones">
                <option value="Asia/Shanghai" />
                <option value="UTC" />
                <option value="Asia/Tokyo" />
                <option value="America/Los_Angeles" />
                <option value="Europe/London" />
              </datalist>
            </label>
            <label>
              发送至
              <select v-model="draft.targetKind" class="select">
                <option v-if="editing" value="keep">当前目标（{{ destination(editing) }}）</option>
                <option value="wechat">已绑定的微信</option>
                <option value="email">邮箱</option>
              </select>
            </label>
            <label v-if="draft.targetKind === 'email'">
              收件邮箱
              <input v-model.trim="draft.targetRef" class="input" type="email" required />
            </label>
          </div>
        </fieldset>
        <p v-if="formError" class="error-banner form-error" role="alert">{{ formError }}</p>
        <div class="actions editor-actions">
          <button type="button" class="btn btn-secondary" :disabled="saving" @click="editor?.close()">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? '正在保存…' : editing ? '保存修改' : '创建任务' }}
          </button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { CalendarClock, ChevronDown, Pencil, Plus } from '@lucide/vue'
import request from '@/api/request'
import { DEFAULT_TIMEZONE, formatDateTime } from '@/utils/dateTime'

type Kind = 'once' | 'daily' | 'weekly' | 'interval'

interface Schedule {
  schedule_id: string
  title: string
  text: string
  kind: Kind
  interval_seconds: number
  at_time: string
  weekday: number
  timezone: string
  enabled: boolean
  next_run_at: number
  last_run_at: string | null
  target: { kind: string; ref: string }
  content_kind: string
  briefing_kind: string
}

interface Occurrence {
  occurrence_id: string
  scheduled_at: string
  state: string
  missed: number
}

interface Draft {
  title: string
  text: string
  kind: Kind
  at: string
  time: string
  weekday: number
  everySeconds: number
  timezone: string
  targetKind: 'keep' | 'wechat' | 'email'
  targetRef: string
  content: 'text' | 'ai_news'
}

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const briefingNames: Record<string, string> = {
  ai_news: 'AI 前沿日报', morning: '晨间简报', evening: '晚间简报', weekly: '每周简报', mood_weekly: '情绪周报',
}
const occurrenceState: Record<string, string> = { pending: '等待处理', queued: '已入队', missed: '已错过' }
const schedules = ref<Schedule[]>([])
const occurrences = ref<Occurrence[]>([])
const expanded = ref('')
const historyLoading = ref(false)
const historyError = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
const actionId = ref('')
const editor = ref<HTMLDialogElement>()
const editing = ref<Schedule>()
let initialDraft: Draft
let historyRequest = 0

function newDraft(): Draft {
  return {
    title: '', text: '', kind: 'daily', at: '', time: '08:00', weekday: 0,
    everySeconds: 3600, timezone: DEFAULT_TIMEZONE, targetKind: 'wechat', targetRef: '', content: 'text',
  }
}

const draft = reactive(newDraft())

function briefingLabel(s: Schedule) {
  return s.content_kind === 'briefing' ? briefingNames[s.briefing_kind] || '简报' : ''
}

function destination(s: Schedule) {
  if (s.target.kind === 'email') return s.target.ref
  if (s.target.kind === 'wechat') return '微信'
  return s.target.kind
}

function recurrence(s: Schedule) {
  if (s.kind === 'once') return '仅一次'
  if (s.kind === 'daily') return `每天 ${s.at_time}`
  if (s.kind === 'weekly') return `每周 · ${weekdays[s.weekday]} ${s.at_time}`
  const seconds = s.interval_seconds
  if (seconds % 3600 === 0) return `每 ${seconds / 3600} 小时`
  if (seconds % 60 === 0) return `每 ${seconds / 60} 分钟`
  return `每 ${seconds} 秒`
}

function isCompleted(s: Schedule) {
  const lastRun = dateValue(s.last_run_at)
  return !s.enabled && s.kind === 'once' && lastRun !== undefined && lastRun.getTime() >= Math.floor(s.next_run_at * 1000)
}

function statusText(s: Schedule) {
  return s.enabled ? '已启用' : isCompleted(s) ? '已触发' : '已暂停'
}

function dateValue(value: number | string | null) {
  if (value === null) return undefined
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  return Number.isNaN(date.getTime()) ? undefined : date
}

function formatDate(value: number | string | null, timeZone: string) {
  return formatDateTime(typeof value === 'number' ? dateValue(value)?.toISOString() : value, timeZone)
}

function localInput(value: number, timeZone: string) {
  const date = dateValue(value)
  if (!date) return ''
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).map(({ type, value }) => [type, value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}${parts.second === '00' ? '' : `:${parts.second}`}`
}

async function openEditor(s?: Schedule) {
  editing.value = s
  formError.value = ''
  const values = newDraft()
  if (s) {
    Object.assign(values, {
      title: s.title, text: s.text, kind: s.kind, timezone: s.timezone,
      targetKind: 'keep', targetRef: s.target.kind === 'email' ? s.target.ref : '',
      at: s.kind === 'once' ? localInput(s.next_run_at, s.timezone) : '',
      time: s.at_time || values.time, weekday: s.weekday,
      everySeconds: s.interval_seconds || values.everySeconds,
    })
  }
  initialDraft = values
  Object.assign(draft, values)
  await nextTick()
  editor.value?.showModal()
}

function cancelEditor(event: Event) {
  if (saving.value) event.preventDefault()
}

function onContentChange() {
  if (draft.content !== 'ai_news') return
  draft.kind = 'daily'
  if (!draft.title.trim()) draft.title = 'AI 前沿日报'
}

function timing(values: Draft) {
  if (values.kind === 'once') return { timezone: values.timezone, at: values.at }
  if (values.kind === 'weekly') return { timezone: values.timezone, weekly_at: values.time, weekday: values.weekday }
  if (values.kind === 'daily') return { timezone: values.timezone, daily_at: values.time }
  return { timezone: values.timezone, every_seconds: values.everySeconds }
}

function replaceSchedule(schedule: Schedule) {
  schedules.value = schedules.value.map(item => item.schedule_id === schedule.schedule_id ? schedule : item)
}

function errorText(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await request.get<{ schedules: Schedule[] }>('/api/schedules')
    schedules.value = res.data.schedules
  } catch (cause) {
    error.value = errorText(cause, '加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  saving.value = true
  formError.value = ''
  try {
    const schedule = editing.value
    const body: Record<string, unknown> = {}
    if (!schedule || draft.title !== initialDraft.title) body.title = draft.title
    const textTask = schedule ? schedule.content_kind !== 'briefing' : draft.content === 'text'
    if (textTask && (!schedule || draft.text !== initialDraft.text)) body.text = draft.text
    const scheduleTiming = timing(draft)
    if (!schedule || JSON.stringify(scheduleTiming) !== JSON.stringify(timing(initialDraft))) Object.assign(body, scheduleTiming)
    if (draft.targetKind !== 'keep') {
      body.target_kind = draft.targetKind
      body.target_ref = draft.targetKind === 'email' ? draft.targetRef : ''
    }
    if (schedule) {
      if (Object.keys(body).length) {
        const res = await request.patch<{ schedule: Schedule }>(`/api/schedules/${schedule.schedule_id}`, body)
        replaceSchedule(res.data.schedule)
      }
    } else {
      body.content_kind = draft.content === 'ai_news' ? 'briefing' : 'text'
      body.briefing_kind = draft.content === 'ai_news' ? 'ai_news' : ''
      await request.post('/api/schedules', body)
      await load()
    }
    editor.value?.close()
  } catch (cause) {
    formError.value = errorText(cause, editing.value ? '保存失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function toggle(s: Schedule) {
  if (actionId.value) return
  actionId.value = s.schedule_id
  error.value = ''
  try {
    const res = await request.patch<{ schedule: Schedule }>(`/api/schedules/${s.schedule_id}`, { enabled: !s.enabled })
    replaceSchedule(res.data.schedule)
  } catch (cause) {
    error.value = errorText(cause, '更新失败')
  } finally {
    actionId.value = ''
  }
}

async function remove(s: Schedule) {
  if (actionId.value || !confirm('删除这项定时任务？已入队的提醒会继续处理。')) return
  actionId.value = s.schedule_id
  error.value = ''
  try {
    await request.delete(`/api/schedules/${s.schedule_id}`)
    schedules.value = schedules.value.filter(item => item.schedule_id !== s.schedule_id)
  } catch (cause) {
    error.value = errorText(cause, '删除失败')
  } finally {
    actionId.value = ''
  }
}

async function loadOccurrences(s: Schedule) {
  const requestId = ++historyRequest
  if (expanded.value === s.schedule_id) {
    expanded.value = ''
    return
  }
  expanded.value = s.schedule_id
  historyLoading.value = true
  historyError.value = ''
  try {
    const res = await request.get<{ occurrences: Occurrence[] }>(`/api/schedules/${s.schedule_id}/occurrences`)
    if (requestId === historyRequest) occurrences.value = res.data.occurrences
  } catch (cause) {
    if (requestId === historyRequest) historyError.value = errorText(cause, '读取执行记录失败')
  } finally {
    if (requestId === historyRequest) historyLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.schedules-page { max-width: 1000px; margin: 0 auto; padding: clamp(16px, 4vw, 40px); }
.page-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 22px; }
.page-header h2, h3, .empty p { margin: 0; }
.page-header h2 { margin-bottom: 5px; font-size: 24px; }
.hint, .item-meta dt, .timezone { margin: 0; color: var(--text-secondary); font-size: 13px; }
.list { display: grid; gap: 14px; }
.item { min-width: 0; padding: clamp(14px, 3vw, 22px); }
.item-header, .item-title, .actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.item-header { justify-content: space-between; align-items: flex-start; gap: 12px; }
.item-heading { min-width: 0; flex: 1 1 230px; }
.item-title h3 { font-size: 16px; overflow-wrap: anywhere; }
.content { color: var(--text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; margin: 6px 0 0; }
.status { background: var(--bg-tertiary); color: var(--text-secondary); border-radius: 999px; padding: 3px 9px; font-size: 12px; white-space: nowrap; }
.status.active { background: var(--bg-success); color: var(--text-primary); }
.status.active::before { content: ''; display: inline-block; width: 6px; height: 6px; margin-inline-end: 5px; border-radius: 50%; background: var(--text-success); vertical-align: 2px; }
.item-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 175px), 1fr)); gap: 12px 18px; margin: 16px 0 10px; padding: 13px; border-radius: var(--radius-md); background: var(--bg-secondary); }
.item-meta dd { margin: 3px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.timezone { display: block; font-size: 12px; }
.history-button { display: inline-flex; align-items: center; gap: 4px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); cursor: pointer; padding: 6px; font: inherit; font-size: 13px; }
.history-button:hover { color: var(--text-primary); background: var(--bg-hover); }
.history-button[aria-expanded="true"] svg { transform: rotate(180deg); }
.occurrences { border-top: 1px solid var(--border-primary); margin-top: 7px; padding: 10px 0 0; }
.occurrences ul { list-style: none; margin: 0; padding: 0; }
.occurrences li { display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 5px; color: var(--text-secondary); font-size: 13px; }
.empty { display: grid; justify-items: center; gap: 10px; color: var(--text-secondary); padding: 44px 16px; text-align: center; }
.error-banner { margin: 0 0 12px; background: var(--bg-danger); color: var(--text-primary); border: 1px solid var(--border-danger); padding: 10px; border-radius: var(--radius-sm); }
.editor { width: min(560px, calc(100% - 24px)); max-height: calc(100% - 24px); margin: auto; padding: 0; border: 1px solid var(--border-secondary); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); background: var(--bg-card); color: var(--text-primary); }
.editor:modal { overscroll-behavior: contain; }
.editor::backdrop { background: var(--bg-overlay); touch-action: none; }
.editor form { padding: clamp(15px, 4vw, 24px); }
.editor-header { margin-bottom: 16px; }
.editor fieldset { margin: 0; padding: 0; border: 0; min-width: 0; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 14px; }
.form-grid label { display: grid; min-width: 0; align-content: start; gap: 5px; color: var(--text-secondary); font-size: 13px; }
.form-grid :is(.input, .select, .textarea) { width: 100%; min-width: 0; color: var(--text-primary); }
.form-grid .textarea { resize: vertical; }
.wide { grid-column: 1 / -1; }
.editor-actions { justify-content: flex-end; margin-top: 18px; }
.form-error { margin: 12px 0 0; }
@media (max-width: 480px) {
  .form-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
