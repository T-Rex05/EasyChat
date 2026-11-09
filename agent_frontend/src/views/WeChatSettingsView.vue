<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>微信偏好</h1>
        <p class="muted">人格、安静时段、情绪记录与稍后读。所有数据只对当前账号可见。</p>
      </div>
      <router-link class="button ghost" to="/schedules">管理提醒与简报</router-link>
    </header>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="notice" class="alert success">{{ notice }}</p>

    <section class="card">
      <h2>说话方式</h2>
      <div class="form-grid">
        <label>
          人设
          <select v-model="form.persona_preset">
            <option v-for="item in presets" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          称呼
          <input v-model.trim="form.address_form" maxlength="12" />
        </label>
        <label>
          微信最多字数
          <input v-model.number="form.max_chars" type="number" min="40" max="500" />
        </label>
        <label>
          表情
          <select v-model="form.emoji_level">
            <option value="none">不用</option>
            <option value="sparse">少量</option>
            <option value="rich">多一点</option>
          </select>
        </label>
        <label>
          主动程度
          <select v-model="form.proactivity">
            <option value="low">少打扰</option>
            <option value="normal">正常</option>
            <option value="high">多提醒</option>
          </select>
        </label>
        <label>
          时区
          <input v-model.trim="form.timezone" placeholder="Asia/Shanghai" />
        </label>
        <label>
          安静开始
          <input v-model="form.quiet_start" type="time" />
        </label>
        <label>
          安静结束
          <input v-model="form.quiet_end" type="time" />
        </label>
      </div>
      <label class="full">
        自定义指令（仅人设为「自定义」时生效，最多 500 字）
        <textarea v-model="form.custom_instruction" rows="3" maxlength="500"></textarea>
      </label>
      <button class="button" :disabled="saving" @click="saveProfile">
        {{ saving ? '保存中…' : '保存偏好' }}
      </button>
    </section>

    <section class="card">
      <div class="section-head">
        <div>
          <h2>情绪记录</h2>
          <p class="muted">
            默认关闭。开启后会分析你发给我的文字，按天记录分数和标签，不做诊断；
            可随时关闭或删除。
          </p>
        </div>
        <label class="switch">
          <input type="checkbox" :checked="form.mood_opt_in" @change="toggleMood" />
          <span>{{ form.mood_opt_in ? '已开启' : '已关闭' }}</span>
        </label>
      </div>
      <div v-if="mood.length" class="mood-list">
        <div v-for="entry in mood" :key="entry.id" class="mood-row">
          <span>{{ entry.entry_date }}</span>
          <strong :class="entry.score >= 0 ? 'score-up' : 'score-down'">
            {{ entry.score > 0 ? '+' : '' }}{{ entry.score }} 分
          </strong>
          <span class="muted">{{ entry.labels.join('、') || '未标注' }}</span>
        </div>
      </div>
      <p v-else class="muted">最近 7 天没有记录。</p>
      <button class="button danger" :disabled="!mood.length" @click="removeMood">删除全部情绪记录</button>
    </section>

    <section class="card">
      <div class="section-head">
        <div>
          <h2>稍后读</h2>
          <p class="muted">链接只做轻量摘要，不抓图片；同一链接会更新备注。</p>
        </div>
        <div class="inline">
          <input v-model="searchQuery" placeholder="搜索标题/备注/标签" @keyup.enter="search" />
          <button class="button ghost" @click="search">搜索</button>
        </div>
      </div>
      <div class="inline">
        <input v-model.trim="newUrl" placeholder="https://…" />
        <input v-model.trim="newNote" placeholder="备注（可选）" />
        <button class="button" :disabled="!newUrl" @click="saveLink">存链接</button>
      </div>
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.value" class="tab" :class="{ active: tabValue === tab.value }" @click="loadInbox(tab.value)">
          {{ tab.label }}
        </button>
      </div>
      <div v-if="items.length" class="inbox-list">
        <article v-for="item in items" :key="item.id" class="inbox-item">
          <div>
            <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title || item.url }}</a>
            <strong v-else>{{ item.title || item.note || '未命名' }}</strong>
            <p class="muted">{{ item.summary || item.note || item.url }}</p>
            <small>{{ item.enrich_state }} · {{ item.tags.join('、') }}</small>
          </div>
          <div class="inline">
            <button v-if="item.status !== 'archived'" class="button ghost" @click="archive(item.id)">归档</button>
            <button class="button danger" @click="removeItem(item.id)">删除</button>
          </div>
        </article>
      </div>
      <p v-else class="muted">这里还是空的。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  archiveInbox, deleteInbox, deleteMood, getProfile, listInbox, listMood,
  saveInbox, searchInbox, updateProfile, type AssistantProfile, type InboxItem, type MoodEntry,
} from '@/api/wechat'

const presets = [
  { value: 'warm', label: '温柔' },
  { value: 'concise', label: '干练' },
  { value: 'playful', label: '俏皮' },
  { value: 'direct', label: '直给' },
  { value: 'custom', label: '自定义' },
]
const tabs = [
  { value: 'unread', label: '未读' },
  { value: 'archived', label: '已归档' },
  { value: '', label: '全部' },
]

const form = reactive<AssistantProfile>({
  owner_id: 0, persona_preset: 'warm', address_form: '你', max_chars: 120,
  emoji_level: 'sparse', proactivity: 'normal', quiet_start: '23:00',
  quiet_end: '07:30', timezone: 'Asia/Shanghai', custom_instruction: '',
  mood_opt_in: false, mood_retention_days: 90, persona_revision: 1,
})
const mood = ref<MoodEntry[]>([])
const items = ref<InboxItem[]>([])
const tabValue = ref('unread')
const newUrl = ref('')
const newNote = ref('')
const searchQuery = ref('')
const saving = ref(false)
const error = ref('')
const notice = ref('')

function flash(text: string) {
  notice.value = text
  window.setTimeout(() => { notice.value = '' }, 2500)
}

function fail(err: unknown) {
  error.value = err instanceof Error ? err.message : String(err)
  window.setTimeout(() => { error.value = '' }, 4000)
}

async function saveProfile() {
  saving.value = true
  try {
    const profile = await updateProfile({
      persona_preset: form.persona_preset,
      address_form: form.address_form,
      max_chars: form.max_chars,
      emoji_level: form.emoji_level,
      proactivity: form.proactivity,
      quiet_start: form.quiet_start,
      quiet_end: form.quiet_end,
      timezone: form.timezone,
      custom_instruction: form.custom_instruction,
    })
    Object.assign(form, profile)
    flash('偏好已保存')
  } catch (err) {
    fail(err)
  } finally {
    saving.value = false
  }
}

async function toggleMood(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked
  try {
    const profile = await updateProfile({ mood_opt_in: enabled })
    Object.assign(form, profile)
    flash(enabled ? '已开启情绪记录' : '已停止采样，历史记录保留')
    await loadMood()
  } catch (err) {
    fail(err)
  }
}

async function loadMood() {
  try {
    mood.value = await listMood()
  } catch (err) {
    fail(err)
  }
}

async function removeMood() {
  if (!window.confirm('删除全部情绪记录？此操作不可恢复。')) return
  try {
    const count = await deleteMood()
    mood.value = []
    flash(`已删除 ${count} 条记录`)
  } catch (err) {
    fail(err)
  }
}

async function loadInbox(status = tabValue.value) {
  tabValue.value = status
  try {
    items.value = await listInbox(status)
  } catch (err) {
    fail(err)
  }
}

async function search() {
  if (!searchQuery.value.trim()) {
    await loadInbox()
    return
  }
  try {
    items.value = await searchInbox(searchQuery.value.trim())
  } catch (err) {
    fail(err)
  }
}

async function saveLink() {
  try {
    await saveInbox(newUrl.value, newNote.value)
    newUrl.value = ''
    newNote.value = ''
    await loadInbox()
    flash('已存')
  } catch (err) {
    fail(err)
  }
}

async function archive(itemId: string) {
  try {
    await archiveInbox(itemId)
    await loadInbox()
  } catch (err) {
    fail(err)
  }
}

async function removeItem(itemId: string) {
  try {
    await deleteInbox(itemId)
    await loadInbox()
  } catch (err) {
    fail(err)
  }
}

onMounted(async () => {
  try {
    Object.assign(form, await getProfile())
    await Promise.all([loadMood(), loadInbox()])
  } catch (err) {
    fail(err)
  }
})
</script>

<style scoped>
.page { padding: 24px; max-width: 980px; display: grid; gap: 16px; }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
h1 { margin: 0 0 6px; font-size: 24px; }
h2 { margin: 0 0 10px; font-size: 17px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px; display: grid; gap: 12px; }
.muted { color: var(--text-muted); font-size: 13px; margin: 0; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
label { display: grid; gap: 6px; font-size: 13px; color: var(--text-muted); }
label.full { grid-column: 1 / -1; }
input, select, textarea { padding: 9px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--text); }
.button { padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--brand); color: #fff; cursor: pointer; width: fit-content; }
.button.ghost { background: transparent; color: var(--text); }
.button.danger { background: #b42318; }
.button:disabled { opacity: .5; cursor: not-allowed; }
.section-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; flex-wrap: wrap; }
.inline { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.switch { display: flex; gap: 8px; align-items: center; color: var(--text); }
.tabs { display: flex; gap: 6px; }
.tab { padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); background: transparent; color: var(--text); cursor: pointer; }
.tab.active { background: var(--brand); color: #fff; }
.mood-list, .inbox-list { display: grid; gap: 8px; }
.mood-row { display: grid; grid-template-columns: 120px 80px 1fr; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.score-up { color: #067647; }
.score-down { color: #b42318; }
.inbox-item { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.inbox-item p { margin: 4px 0; }
.inbox-item small { color: var(--text-muted); }
.alert { padding: 10px 12px; border-radius: 8px; }
.alert.error { background: #fef3f2; color: #b42318; }
.alert.success { background: #ecfdf3; color: #067647; }
</style>
