<template>
  <div class="skills-page">
    <header class="page-header">
      <div>
        <h2>技能管理</h2>
        <p class="hint">技能内容不可变：每次保存生成新版本，激活/回滚只切换指针。</p>
      </div>
      <button class="btn btn-primary" @click="startCreate">新建技能</button>
    </header>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- P3：内置示例技能模板（来源与固定版本可查；导入≠默认激活） -->
    <section class="card templates-panel">
      <button type="button" class="btn-link" @click="showTemplates = !showTemplates">
        {{ showTemplates ? '▾' : '▸' }} 示例技能模板（PDF 处理 / 表格处理 / 技能编写）
      </button>
      <div v-show="showTemplates" class="template-grid">
        <p v-if="templates.length === 0" class="empty">模板目录加载失败或为空</p>
        <div v-for="tpl in templates" :key="tpl.key" class="template-card">
          <h4>{{ tpl.title }}</h4>
          <p class="muted">{{ tpl.purpose }}</p>
          <p class="muted small">来源：{{ tpl.origin }} · 固定版本 {{ tpl.commit }} · {{ tpl.license }}</p>
          <p class="muted small">依赖：{{ tpl.dependencies.length ? tpl.dependencies.join('、') : '无第三方依赖' }}</p>
          <p class="muted small">{{ tpl.resources }}</p>
          <div class="template-actions">
            <button class="btn btn-sm btn-secondary" :disabled="importing === tpl.key" @click="importTemplate(tpl, false)">
              导入为候选
            </button>
            <button class="btn btn-sm btn-primary" :disabled="importing === tpl.key" @click="importTemplate(tpl, true)">
              导入并激活
            </button>
          </div>
        </div>
      </div>
      <p v-if="templateNotice" class="muted notice-line">{{ templateNotice }}</p>
    </section>

    <div class="layout">
      <aside class="card list-panel">
        <div v-if="loading" class="empty">加载中...</div>
        <div v-else-if="skills.length === 0" class="empty">暂无技能</div>
        <button
          v-for="skill in skills"
          :key="skill.skill_id"
          class="skill-row"
          :class="{ active: selected?.skill_id === skill.skill_id }"
          @click="openSkill(skill.skill_id)"
        >
          <span class="skill-name">{{ skill.name }}</span>
          <span class="skill-desc">{{ skill.description || '无描述' }}</span>
          <span class="badges">
            <span v-if="skill.pinned" class="tag pin">固定</span>
            <span v-if="skill.archived" class="tag archived">归档</span>
            <span v-if="!skill.active_version_id" class="tag">草稿</span>
          </span>
        </button>
      </aside>

      <main class="card detail-panel">
        <div v-if="!selected" class="empty">选择或新建一个技能</div>
        <template v-else>
          <header class="detail-header">
            <div>
              <h3>{{ selected.name }}</h3>
              <p class="muted">owner {{ selected.owner_id }} · {{ selected.origin }} · 更新 {{ selected.updated_at }}</p>
            </div>
            <div class="detail-actions">
              <button class="btn btn-sm btn-secondary" @click="togglePin">
                {{ selected.pinned ? '取消固定' : '固定' }}
              </button>
              <button class="btn btn-sm btn-secondary" @click="toggleArchive">
                {{ selected.archived ? '取消归档' : '归档' }}
              </button>
            </div>
          </header>

          <label class="field-label">当前内容（保存后生成新版本）</label>
          <textarea v-model="content" class="textarea" rows="14" placeholder="# 技能指令&#10;..."></textarea>
          <div class="detail-actions end">
            <span v-if="activeVersion" class="muted">当前 v{{ activeVersion.version_seq }} · {{ activeVersion.content_hash.slice(0, 8) }}</span>
            <button class="btn btn-primary" :disabled="saving || !content.trim()" @click="saveVersion">保存为新版本</button>
          </div>

          <h4 class="section-title">版本历史</h4>
          <div class="version-list">
            <div v-for="v in versions" :key="v.version_id" class="version-row">
              <span>v{{ v.version_seq }}</span>
              <span class="muted">{{ v.source }} · {{ v.created_at }}</span>
              <span class="muted">{{ v.content_hash.slice(0, 10) }}</span>
              <span class="version-actions">
                <button v-if="v.version_id !== selected.active_version_id" class="btn btn-sm btn-secondary" @click="activate(v.version_id)">激活</button>
                <span v-else class="tag active">当前</span>
              </span>
            </div>
          </div>
        </template>
      </main>
    </div>

    <div v-if="creating" class="modal-overlay" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="createSkill">
        <h3>新建技能</h3>
        <label class="field-label">名称（小写字母/数字/-）</label>
        <input v-model="newName" class="input" required pattern="[a-z0-9][a-z0-9-]*" />
        <label class="field-label">内容</label>
        <textarea v-model="newContent" class="textarea" rows="10" placeholder="# 技能指令&#10;..." required></textarea>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="creating = false">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">创建</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import request from '@/api/request'

interface Skill {
  skill_id: string
  owner_id: number
  name: string
  description: string
  origin: string
  pinned: boolean
  archived: boolean
  active_version_id: string | null
  updated_at: string
}
interface Version {
  version_id: string
  version_seq: number
  content_hash: string
  source: string
  created_at: string
}
interface TemplateInfo {
  key: string
  name: string
  title: string
  purpose: string
  origin: string
  commit: string
  license: string
  dependencies: string[]
  resources: string
}

const skills = ref<Skill[]>([])
const selected = ref<Skill | null>(null)
const versions = ref<Version[]>([])
const content = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const creating = ref(false)
const newName = ref('')
const newContent = ref('')

// P3 模板面板
const templates = ref<TemplateInfo[]>([])
const showTemplates = ref(false)
const importing = ref('')
const templateNotice = ref('')

async function loadTemplates() {
  try {
    const res = await request.get<{ templates: TemplateInfo[] }>('/api/skills/templates')
    templates.value = res.data.templates || []
  } catch {
    // 模板目录是可选能力：加载失败仅面板显示空态，不打断主流程
    templates.value = []
  }
}

async function importTemplate(tpl: TemplateInfo, activate: boolean) {
  importing.value = tpl.key
  templateNotice.value = ''
  error.value = ''
  try {
    const res = await request.post(`/api/skills/templates/${tpl.key}/import`, {
      activate,
    })
    const v = res.data.version
    templateNotice.value = activate
      ? `已导入并激活「${tpl.title}」来源版本 ${v.source} v${v.version_seq}（${tpl.origin}@${tpl.commit}）`
      : `已导入「${tpl.title}」为候选版本 v${v.version_seq}，可在技能详情中确认后激活`
    await load()
    if (v.skill_id) await openSkill(v.skill_id)
  } catch (e: any) {
    error.value = e?.message || '模板导入失败'
  } finally {
    importing.value = ''
  }
}

const activeVersion = computed(() => versions.value.find(v => v.version_id === selected.value?.active_version_id) || null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await request.get<{ skills: Skill[] }>('/api/skills', { params: { include_archived: true } })
    skills.value = res.data.skills
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function openSkill(skillId: string) {
  try {
    const res = await request.get(`/api/skills/${skillId}`)
    selected.value = res.data.skill
    versions.value = res.data.versions
    content.value = res.data.content || ''
  } catch (e: any) {
    error.value = e?.message || '读取失败'
  }
}

async function saveVersion() {
  if (!selected.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await request.post(`/api/skills/${selected.value.name}/versions`, {
      content: content.value,
      source: 'web',
      parent_version_id: selected.value.active_version_id,
    })
    const versionId = res.data.version.version_id
    await request.post(`/api/skills/${selected.value.skill_id}/activate`, {
      version_id: versionId,
      expected_active_version_id: selected.value.active_version_id,
    })
    await openSkill(selected.value.skill_id)
    await load()
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function activate(versionId: string) {
  if (!selected.value) return
  try {
    await request.post(`/api/skills/${selected.value.skill_id}/activate`, {
      version_id: versionId,
      expected_active_version_id: selected.value.active_version_id,
    })
    await openSkill(selected.value.skill_id)
    await load()
  } catch (e: any) {
    error.value = e?.message || '激活失败'
  }
}

async function togglePin() {
  if (!selected.value) return
  await patch({ pinned: !selected.value.pinned })
}

async function toggleArchive() {
  if (!selected.value) return
  if (!selected.value.archived && !confirm('归档后默认列表不可见，确认？')) return
  await patch({ archived: !selected.value.archived })
}

async function patch(body: Record<string, boolean>) {
  if (!selected.value) return
  try {
    await request.patch(`/api/skills/${selected.value.skill_id}`, body)
    await openSkill(selected.value.skill_id)
    await load()
  } catch (e: any) {
    error.value = e?.message || '更新失败'
  }
}

function startCreate() {
  creating.value = true
  newName.value = ''
  newContent.value = ''
}

async function createSkill() {
  saving.value = true
  error.value = ''
  try {
    const res = await request.post(`/api/skills/${newName.value}/versions`, {
      content: newContent.value, source: 'web',
    })
    const { skill_id, version_id } = res.data.version
    await request.post(`/api/skills/${skill_id}/activate`, { version_id })
    creating.value = false
    await load()
    await openSkill(skill_id)
  } catch (e: any) {
    error.value = e?.message || '创建失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => { load(); loadTemplates() })
</script>

<style scoped>
.skills-page { max-width: 1100px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.hint { margin: 0; color: var(--text-tertiary); font-size: 13px; }
.layout { display: grid; grid-template-columns: 300px 1fr; gap: 16px; }
.list-panel { padding: 8px; max-height: 70vh; overflow: auto; }
.skill-row { display: grid; gap: 4px; width: 100%; text-align: left; padding: 10px; border: 0; border-radius: 6px; background: transparent; color: inherit; cursor: pointer; }
.skill-row:hover, .skill-row.active { background: var(--bg-tertiary); }
.skill-name { font-weight: 600; }
.skill-desc { font-size: 12px; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badges { display: flex; gap: 4px; }
.tag { background: var(--bg-tertiary); color: var(--text-secondary); border-radius: 999px; padding: 1px 7px; font-size: 11px; }
.tag.pin { color: #d98a00; }
.tag.archived { color: #999; }
.tag.active { color: #2e7d32; }
.detail-panel { padding: 16px; min-height: 320px; }
.detail-header { display: flex; justify-content: space-between; gap: 12px; }
.detail-header h3 { margin: 0 0 4px; }
.detail-actions { display: flex; gap: 8px; align-items: center; }
.detail-actions.end { justify-content: flex-end; margin: 8px 0 18px; }
.field-label { display: block; margin: 12px 0 6px; font-size: 13px; color: var(--text-secondary); }
.textarea { width: 100%; resize: vertical; font-family: ui-monospace, monospace; }
.section-title { margin: 10px 0; }
.version-list { display: grid; gap: 6px; }
.version-row { display: grid; grid-template-columns: 60px 1fr 120px 80px; gap: 8px; align-items: center; padding: 8px; border-radius: 6px; background: var(--bg-secondary); font-size: 13px; }
.version-actions { text-align: right; }
.muted { color: var(--text-tertiary); font-size: 12px; }
.empty { color: var(--text-tertiary); text-align: center; padding: 40px 0; }
.error-banner { background: rgba(220, 53, 69, 0.12); color: #c82333; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal-card { width: min(680px, 92vw); background: var(--bg-primary); border-radius: 10px; padding: 20px; display: grid; gap: 8px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.templates-panel { padding: 12px 16px; margin-bottom: 16px; }
.btn-link { background: none; border: none; color: var(--brand); cursor: pointer; font-size: 14px; padding: 0; }
.template-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 10px; }
.template-card { border: 1px solid var(--border-primary); border-radius: 8px; padding: 10px 12px; display: grid; gap: 4px; }
.template-card h4 { margin: 0 0 4px; font-size: 14px; }
.template-card .small { font-size: 12px; margin: 0; }
.template-actions { display: flex; gap: 8px; margin-top: 6px; }
.notice-line { margin-top: 8px; }
</style>
