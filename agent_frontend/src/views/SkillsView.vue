<template>
  <div class="skills-page">
    <header class="page-header">
      <h2>技能管理</h2>
      <button v-if="canUseSkills" type="button" class="btn btn-primary" :disabled="saving" @click="startCreate">新建技能</button>
    </header>

    <div class="layout">
      <aside class="card library-panel" aria-label="技能目录">
        <div class="library-header">
          <div class="library-switch" role="group" aria-label="技能分类">
            <button type="button" :aria-pressed="category === 'personal'" @click="setCategory('personal')">个人技能</button>
            <button type="button" :aria-pressed="category === 'templates'" @click="setCategory('templates')">内置技能</button>
          </div>
          <label v-if="category === 'personal' && canManageSkills" class="scope-picker">
            技能归属
            <select :value="allOwners ? 'all' : 'self'" class="input" @change="changeScope">
              <option value="self">仅本人</option>
              <option value="all">全部用户</option>
            </select>
          </label>
        </div>
        <section class="list-panel" :aria-label="category === 'personal' ? '个人技能列表' : '内置技能列表'" tabindex="0">
          <template v-if="category === 'personal'">
            <div v-if="permissionRefreshError" class="list-status">
              <p role="alert" class="muted">技能权限刷新失败</p>
              <button type="button" class="btn btn-sm btn-secondary" @click="refreshPermissions">重试</button>
            </div>
            <p v-else-if="permissionsStale" role="status" class="muted list-status">正在刷新技能权限…</p>
            <p v-else-if="!auth.ready || loading" role="status" class="muted list-status">正在加载技能…</p>
            <p v-else-if="!canUseSkills" class="muted list-status">当前账号无权查看个人技能</p>
            <div v-else-if="listError" class="list-status">
              <p role="alert" class="muted">{{ listError }}</p>
              <button type="button" class="btn btn-sm btn-secondary" @click="load">重试</button>
            </div>
            <p v-else-if="!skills.length" class="muted list-status">暂无个人技能</p>
            <button
              v-for="skill in skills"
              :key="skill.skill_id"
              type="button"
              class="skill-row"
              :aria-current="selectedKey === skill.skill_id ? 'true' : undefined"
              @click="openSkill(skill.skill_id, true)"
            >
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
              <span v-if="allOwners || skill.pinned || skill.archived || !skill.active_version_id" class="badges">
                <span v-if="allOwners" class="tag">{{ ownerLabel(skill.owner_id) }}</span>
                <span v-if="skill.pinned" class="tag">固定</span>
                <span v-if="skill.archived" class="tag">归档</span>
                <span v-if="!skill.active_version_id" class="tag">草稿</span>
              </span>
            </button>
          </template>
          <template v-else>
            <p v-if="catalogLoading" role="status" class="muted list-status">正在加载内置技能…</p>
            <div v-else-if="catalogError" class="list-status">
              <p role="alert" class="muted">内置技能加载失败</p>
              <button type="button" class="btn btn-sm btn-secondary" @click="loadTemplates">重试</button>
            </div>
            <p v-else-if="!templates.length" class="muted list-status">暂无内置技能</p>
            <button
              v-for="template in templates"
              :key="template.key"
              type="button"
              class="skill-row"
              :aria-current="selectedKey === templateKey(template.key) ? 'true' : undefined"
              @click="openTemplate(template.key)"
            >
              <span class="skill-name">{{ template.title }}</span>
              <span class="skill-desc">{{ template.purpose }}</span>
            </button>
          </template>
        </section>
      </aside>

      <section ref="detailPanel" class="card detail-panel" aria-label="技能详情" tabindex="0">
        <p v-if="error" role="alert" class="error-banner">{{ error }}</p>
        <p v-if="detailLoading" role="status" class="empty">正在加载内容…</p>
        <template v-else-if="selectedTemplate">
          <header class="detail-header">
            <div>
              <p class="detail-kind">内置技能</p>
              <h3>{{ selectedTemplate.title }}</h3>
              <p class="description">{{ selectedTemplate.purpose }}</p>
            </div>
            <button v-if="existingPersonalSkill" type="button" class="btn btn-sm btn-secondary" @click="showPersonalSkill(existingPersonalSkill.skill_id)">
              查看同名个人技能
            </button>
            <button v-else-if="canUseSkills" type="button" class="btn btn-sm btn-primary" :disabled="saving || loading || !skillsLoaded" @click="enableTemplate">
              {{ saving ? '正在启用…' : '启用技能' }}
            </button>
          </header>
          <dl class="metadata">
            <div><dt>作者</dt><dd>{{ selectedTemplate.author }}</dd></div>
            <div><dt>来源日期</dt><dd><time :datetime="selectedTemplate.source_published_at">{{ formatTime(selectedTemplate.source_published_at) }}</time></dd></div>
            <div>
              <dt>来源</dt>
              <dd>
                <a :href="selectedTemplate.source_url" target="_blank" rel="noopener noreferrer">{{ selectedTemplate.origin }}</a>
                <span> · 修订 {{ selectedTemplate.commit }} · {{ selectedTemplate.license }}</span>
              </dd>
            </div>
            <div v-if="selectedTemplate.dependencies.length"><dt>依赖</dt><dd>{{ selectedTemplate.dependencies.join('、') }}</dd></div>
            <div><dt>资源</dt><dd>{{ selectedTemplate.resources }}</dd></div>
          </dl>
          <div class="skill-markdown markdown-body" v-html="templatePreview"></div>
        </template>
        <template v-else-if="selected">
          <header class="detail-header">
            <div>
              <p class="detail-kind">个人技能</p>
              <h3>{{ selected.name }}</h3>
              <p v-if="selected.description" class="description">{{ selected.description }}</p>
            </div>
            <div v-if="canModifySelected" class="detail-actions">
              <button type="button" class="btn btn-sm btn-secondary" :disabled="saving" @click="patch({ pinned: !selected.pinned })">
                {{ selected.pinned ? '取消固定' : '固定' }}
              </button>
              <button type="button" class="btn btn-sm btn-secondary" :disabled="saving" @click="toggleArchive">
                {{ selected.archived ? '取消归档' : '归档' }}
              </button>
            </div>
          </header>
          <dl class="metadata">
            <div><dt>所有者</dt><dd>{{ ownerLabel(selected.owner_id) }}</dd></div>
            <div><dt>作者</dt><dd>{{ personalAuthor }}</dd></div>
            <div>
              <dt>{{ activeVersion ? '版本时间' : '创建时间' }}</dt>
              <dd><time :datetime="activeVersion?.created_at || selected.created_at">{{ formatTime(activeVersion?.created_at || selected.created_at) }}</time></dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd v-if="personalTemplateProvenance">
                <a :href="personalTemplateProvenance.source_url" target="_blank" rel="noopener noreferrer">{{ personalTemplateProvenance.origin }}</a>
                <span> · 修订 {{ personalTemplateProvenance.commit }}</span>
              </dd>
              <dd v-else>{{ personalSource }}</dd>
            </div>
          </dl>
          <div class="content-toolbar">
            <span class="muted">{{ activeVersion ? '当前 v' + activeVersion.version_seq : '未激活' }}</span>
            <div class="detail-actions">
              <button type="button" class="btn btn-sm btn-secondary" :disabled="!versions.length || saving" @click="openHistory">版本历史</button>
              <button v-if="canEditSelected && !editing" type="button" class="btn btn-sm btn-secondary" :disabled="saving" @click="startEditing">编辑内容</button>
            </div>
          </div>
          <div v-if="editing" class="editor">
            <label class="field-label" for="skill-content">Markdown 正文</label>
            <textarea id="skill-content" v-model="content" class="textarea" rows="12" placeholder="# 技能指令"></textarea>
            <div class="detail-actions end">
              <button type="button" class="btn btn-secondary" :disabled="saving" @click="editing = false">取消</button>
              <button type="button" class="btn btn-primary" :disabled="saving || !content.trim()" @click="saveVersion">保存为新版本</button>
            </div>
          </div>
          <div v-else-if="activeVersion" class="skill-markdown markdown-body" v-html="personalPreview"></div>
          <p v-else class="empty">当前没有激活版本</p>
        </template>
        <p v-else-if="!error" class="empty">{{ category === 'templates' ? '选择一个内置技能查看正文' : '选择一个个人技能查看详情' }}</p>
      </section>
    </div>

    <dialog ref="historyDialog" class="history-dialog" aria-labelledby="skill-history-title" @close="clearComparison">
      <header class="detail-header">
        <div>
          <h3 id="skill-history-title">版本历史</h3>
          <p class="description">{{ selected?.name }}</p>
        </div>
        <form method="dialog"><button class="btn btn-sm btn-secondary">关闭</button></form>
      </header>

      <label class="history-picker" for="comparison-version">
        <span>对比版本</span>
        <select id="comparison-version" v-model="comparisonId" class="input" autofocus :disabled="!historyVersions.length" @change="loadComparison">
          <option v-if="!historyVersions.length" value="">暂无其他版本</option>
          <option v-for="version in historyVersions" :key="version.version_id" :value="version.version_id">
            v{{ version.version_seq }} · {{ formatTime(version.created_at) }}
          </option>
        </select>
      </label>
      <div class="comparison">
        <section class="compare-column" aria-labelledby="historical-content-title">
          <h4 id="historical-content-title">历史版本<span v-if="comparisonVersion"> v{{ comparisonVersion.version_seq }}</span></h4>
          <p v-if="comparisonLoading" role="status" class="muted">正在加载版本…</p>
          <p v-else-if="comparisonError" role="alert" class="error-banner">{{ comparisonError }}</p>
          <pre v-else-if="comparisonContent !== null" tabindex="0" aria-labelledby="historical-content-title">{{ comparisonContent }}</pre>
          <p v-else class="muted">暂无可对比的历史版本</p>
        </section>
        <section class="compare-column" aria-labelledby="active-content-title">
          <h4 id="active-content-title">当前版本<span v-if="activeVersion"> v{{ activeVersion.version_seq }}</span></h4>
          <pre v-if="activeVersion" tabindex="0" aria-labelledby="active-content-title">{{ persistedContent }}</pre>
          <p v-else class="muted">当前没有激活版本</p>
        </section>
      </div>
      <div v-if="canModifySelected && comparisonVersion && comparisonContent !== null && comparisonVersion.status !== 'rejected'" class="detail-actions end">
        <button type="button" class="btn btn-sm btn-secondary" :disabled="saving" @click="activate(comparisonVersion.version_id)">
          激活 v{{ comparisonVersion.version_seq }}
        </button>
      </div>
    </dialog>

    <dialog ref="createDialog" class="create-dialog" aria-labelledby="create-skill-title" @cancel="cancelCreate">
      <form @submit.prevent="createSkill">
        <h3 id="create-skill-title">新建技能</h3>
        <p v-if="createError" role="alert" class="error-banner">{{ createError }}</p>
        <label for="new-skill-name" class="field-label">名称（字母、数字、点、下划线、连字符）</label>
        <input id="new-skill-name" v-model="newName" class="input" required maxlength="64" pattern="[a-zA-Z0-9._\-]+" autofocus />
        <label for="new-skill-content" class="field-label">Markdown 正文</label>
        <textarea id="new-skill-content" v-model="newContent" class="textarea" rows="10" placeholder="# 技能指令" required></textarea>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" :disabled="saving" @click="createDialog?.close()">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">创建</button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import DOMPurify from 'dompurify'
import request from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { renderMarkdown } from '@/utils/markdown'

interface Skill {
  skill_id: string
  owner_id: number
  name: string
  description: string
  origin: string
  pinned: boolean
  archived: boolean
  active_version_id: string | null
  created_at: string
}

interface Version {
  version_id: string
  version_seq: number
  source: string
  created_at: string
  status: string
}

interface TemplateInfo {
  key: string
  name: string
  title: string
  purpose: string
}

interface TemplateProvenance {
  author: string
  source_published_at: string
  source_url: string
  origin: string
  commit: string
}

interface TemplateDetail extends TemplateInfo, TemplateProvenance {
  license: string
  dependencies: string[]
  resources: string
  content: string
}

const auth = useAuthStore()
const permissionsStale = ref(false)
const permissionRefreshError = ref(false)
const currentUserId = computed(() => auth.user?.id ?? Number(auth.userId))
const canManageSkills = computed(() => auth.ready && !permissionsStale.value && auth.permissions.includes('skill.manage'))
const canUseSkills = computed(() => auth.ready && !permissionsStale.value &&
  (canManageSkills.value || auth.permissions.includes('skill.create')))
const category = ref<'personal' | 'templates'>('personal')
const allOwners = ref(false)
const skills = ref<Skill[]>([])
const templates = ref<TemplateInfo[]>([])
const detailPanel = ref<HTMLElement | null>(null)
const selectedKey = ref('')
const selected = ref<Skill | null>(null)
const selectedTemplate = ref<TemplateDetail | null>(null)
const personalTemplateProvenance = ref<TemplateProvenance | null>(null)
const versions = ref<Version[]>([])
const persistedContent = ref('')
const content = ref('')
const skillsLoaded = ref(false)
const loading = ref(false)
const listError = ref('')
let listRequest = 0
const detailLoading = ref(false)
const saving = ref(false)
const error = ref('')
const catalogError = ref(false)
const catalogLoading = ref(false)
const editing = ref(false)
const createDialog = ref<HTMLDialogElement | null>(null)
const createError = ref('')
const newName = ref('')
const newContent = ref('')
let detailRequest = 0

const historyDialog = ref<HTMLDialogElement | null>(null)
const comparisonId = ref('')
const comparisonContent = ref<string | null>(null)
const comparisonLoading = ref(false)
const comparisonError = ref('')
let comparisonRequest = 0

const sourceLabels: Record<string, string> = {
  user: '用户提交',
  web: 'Web',
  background: '后台任务',
  evolution: '技能演化',
}
const timeFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
const activeVersion = computed(() => versions.value.find(v => v.version_id === selected.value?.active_version_id))
const historyVersions = computed(() => versions.value.filter(v => v.version_id !== activeVersion.value?.version_id).reverse())
const comparisonVersion = computed(() => historyVersions.value.find(v => v.version_id === comparisonId.value))
const canEditSelected = computed(() => canUseSkills.value && selected.value?.owner_id === currentUserId.value)
const canModifySelected = computed(() => selected.value !== null && (canEditSelected.value || canManageSkills.value))
const existingPersonalSkill = computed(() => skills.value.find(skill =>
  skill.owner_id === currentUserId.value && skill.active_version_id && skill.name === selectedTemplate.value?.name,
))
const personalAuthor = computed(() => {
  if (personalTemplateProvenance.value) return personalTemplateProvenance.value.author
  const ownerId = selected.value?.owner_id
  return ownerId === undefined ? '' : ownerLabel(ownerId)
})
const personalSource = computed(() => {
  const source = activeVersion.value?.source || selected.value?.origin || ''
  return sourceLabels[source] || source
})
const personalPreview = computed(() => renderSkill(persistedContent.value, personalTemplateProvenance.value !== null))
const templatePreview = computed(() => renderSkill(selectedTemplate.value?.content || '', true))

function ownerLabel(ownerId: number) {
  if (ownerId === currentUserId.value) return auth.username || '本人'
  return '用户 #' + ownerId
}

function formatTime(timestamp: string) {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? timestamp : timeFormat.format(date)
}

function renderSkill(markdown: string, builtIn = false) {
  const content = builtIn
    ? markdown.replace(/^\s*<!--[\s\S]*?-->\s*---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, '').trimStart()
    : markdown
  return DOMPurify.sanitize(renderMarkdown(content), { FORBID_TAGS: ['iframe', 'img'] })
}

function templateKey(key: string) {
  return 'template:' + key
}

function message(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback
}

async function refreshPermissions() {
  permissionsStale.value = true
  permissionRefreshError.value = false
  try {
    await auth.verify()
    permissionsStale.value = false
  } catch {
    permissionRefreshError.value = true
  }
}

function privateFailure(err: unknown, fallback: string) {
  if (isAxiosError(err) && err.response?.status === 403 && !permissionsStale.value) {
    void refreshPermissions()
  }
  return message(err, fallback)
}

async function loadTemplates() {
  catalogLoading.value = true
  catalogError.value = false
  try {
    const res = await request.get<{ templates: TemplateInfo[] }>('/api/skills/templates')
    templates.value = res.data.templates
  } catch {
    catalogError.value = true
  } finally {
    catalogLoading.value = false
  }
}

async function load() {
  if (!canUseSkills.value) return
  const sequence = ++listRequest
  loading.value = true
  listError.value = ''
  try {
    const res = await request.get<{ skills: Skill[] }>('/api/skills', {
      params: { include_archived: true, all_owners: allOwners.value && canManageSkills.value },
    })
    if (sequence !== listRequest) return
    skills.value = res.data.skills
    skillsLoaded.value = true
  } catch (err) {
    if (sequence !== listRequest) return
    skills.value = []
    skillsLoaded.value = false
    listError.value = privateFailure(err, '加载技能失败')
  } finally {
    if (sequence === listRequest) loading.value = false
  }
}

function clearSkills() {
  listRequest++
  skills.value = []
  skillsLoaded.value = false
  loading.value = false
  listError.value = ''
}

function clearDetail() {
  detailRequest++
  selectedKey.value = ''
  selected.value = null
  selectedTemplate.value = null
  versions.value = []
  persistedContent.value = ''
  personalTemplateProvenance.value = null
  editing.value = false
  detailLoading.value = false
  error.value = ''
  historyDialog.value?.close()
  clearComparison()
  if (detailPanel.value) detailPanel.value.scrollTop = 0
}

function setCategory(next: typeof category.value) {
  if (category.value === next) return
  category.value = next
  clearDetail()
}

function changeScope(event: Event) {
  if (!canManageSkills.value) return
  allOwners.value = (event.target as HTMLSelectElement).value === 'all'
  clearSkills()
  clearDetail()
  void load()
}

function startDetail(key: string) {
  clearDetail()
  selectedKey.value = key
  detailLoading.value = true
  return detailRequest
}

async function showPersonalSkill(skillId: string) {
  setCategory('personal')
  await openSkill(skillId, true)
}

async function openSkill(skillId: string, focus = false) {
  if (!canUseSkills.value) return
  const sequence = startDetail(skillId)
  try {
    const res = await request.get<{
      skill: Skill
      versions: Version[]
      content: string | null
      template_provenance?: TemplateProvenance | null
    }>('/api/skills/' + skillId)
    if (sequence !== detailRequest) return
    selected.value = res.data.skill
    versions.value = res.data.versions
    persistedContent.value = res.data.content ?? ''
    personalTemplateProvenance.value = res.data.template_provenance ?? null
  } catch (err) {
    if (sequence === detailRequest) error.value = privateFailure(err, '读取技能失败')
  } finally {
    if (sequence === detailRequest) {
      detailLoading.value = false
      if (focus) detailPanel.value?.focus({ preventScroll: true })
    }
  }
}

async function openTemplate(key: string) {
  const sequence = startDetail(templateKey(key))
  try {
    const res = await request.get<{ template: TemplateDetail }>(`/api/skills/templates/${key}`)
    if (sequence === detailRequest) selectedTemplate.value = res.data.template
  } catch (err) {
    if (sequence === detailRequest) error.value = message(err, '读取内置技能失败')
  } finally {
    if (sequence === detailRequest) {
      detailLoading.value = false
      detailPanel.value?.focus({ preventScroll: true })
    }
  }
}

async function enableTemplate() {
  const template = selectedTemplate.value
  if (!canUseSkills.value || !template || existingPersonalSkill.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await request.post<{ version: { skill_id: string } }>(`/api/skills/templates/${template.key}/import`, {
      activate: true,
      only_if_inactive: true,
    })
    await load()
    if (selectedKey.value === templateKey(template.key)) await showPersonalSkill(res.data.version.skill_id)
  } catch (err) {
    error.value = privateFailure(err, '启用技能失败')
  } finally {
    saving.value = false
  }
}

function startEditing() {
  if (!canEditSelected.value) return
  content.value = persistedContent.value
  editing.value = true
}

async function saveVersion() {
  const skill = selected.value
  if (!skill || !canEditSelected.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await request.post<{ version: Version }>('/api/skills/' + skill.name + '/versions', {
      content: content.value,
      source: 'web',
      parent_version_id: skill.active_version_id,
    })
    await setActive(skill, res.data.version.version_id)
    await refreshSkill(skill.skill_id)
  } catch (err) {
    error.value = privateFailure(err, '保存失败')
  } finally {
    saving.value = false
  }
}

function setActive(skill: Skill, versionId: string) {
  return request.post('/api/skills/' + skill.skill_id + '/activate', {
    version_id: versionId,
    expected_active_version_id: skill.active_version_id,
  })
}

async function refreshSkill(skillId: string) {
  await load()
  if (selectedKey.value === skillId) await openSkill(skillId)
}

function openHistory() {
  comparisonId.value = historyVersions.value[0]?.version_id ?? ''
  historyDialog.value?.showModal()
  void loadComparison()
}

function clearComparison() {
  comparisonRequest++
  comparisonLoading.value = false
  comparisonError.value = ''
  comparisonContent.value = null
}

async function loadComparison() {
  clearComparison()
  const sequence = comparisonRequest
  const skillId = selected.value?.skill_id
  const versionId = comparisonId.value
  if (!skillId || !versionId) return
  comparisonLoading.value = true
  try {
    const res = await request.get<{ content: string }>(`/api/skills/${skillId}/versions/${versionId}`)
    if (sequence === comparisonRequest) comparisonContent.value = res.data.content
  } catch (err) {
    if (sequence === comparisonRequest) comparisonError.value = privateFailure(err, '读取历史版本失败')
  } finally {
    if (sequence === comparisonRequest) comparisonLoading.value = false
  }
}

async function activate(versionId: string) {
  const skill = selected.value
  if (!skill || !canModifySelected.value || saving.value) return
  saving.value = true
  comparisonError.value = ''
  try {
    await setActive(skill, versionId)
    historyDialog.value?.close()
    await refreshSkill(skill.skill_id)
  } catch (err) {
    const failure = privateFailure(err, '激活失败')
    if (historyDialog.value?.open) comparisonError.value = failure
    else error.value = failure
  } finally {
    saving.value = false
  }
}

function toggleArchive() {
  if (!selected.value) return
  if (!selected.value.archived && !confirm('归档后不会在会话中使用此技能，确认归档？')) return
  void patch({ archived: !selected.value.archived })
}

async function patch(body: { pinned?: boolean; archived?: boolean }) {
  const skill = selected.value
  if (!skill || !canModifySelected.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await request.patch('/api/skills/' + skill.skill_id, body)
    await refreshSkill(skill.skill_id)
  } catch (err) {
    error.value = privateFailure(err, '更新失败')
  } finally {
    saving.value = false
  }
}

function startCreate() {
  if (!canUseSkills.value) return
  newName.value = ''
  newContent.value = ''
  createError.value = ''
  createDialog.value?.showModal()
}

function cancelCreate(event: Event) {
  if (saving.value) event.preventDefault()
}

async function createSkill() {
  if (!canUseSkills.value || saving.value) return
  saving.value = true
  createError.value = ''
  try {
    const res = await request.post<{ version: { skill_id: string; version_id: string } }>('/api/skills/' + newName.value + '/versions', {
      content: newContent.value, source: 'web',
    })
    const { skill_id, version_id } = res.data.version
    await request.post('/api/skills/' + skill_id + '/activate', { version_id })
    createDialog.value?.close()
    await load()
    await showPersonalSkill(skill_id)
  } catch (err) {
    createError.value = privateFailure(err, '创建失败')
  } finally {
    saving.value = false
  }
}

watch([currentUserId, canUseSkills, canManageSkills], () => {
  allOwners.value = false
  clearSkills()
  if (category.value === 'personal') clearDetail()
  if (!canUseSkills.value) createDialog.value?.close()
  void load()
}, { immediate: true })

onMounted(() => {
  void loadTemplates()
})
</script>

<style scoped>
.skills-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
  height: 100%;
  max-width: 1320px;
  margin-inline: auto;
  padding: 24px;
}
.page-header, .detail-header, .content-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.page-header { align-items: center; flex-wrap: wrap; }
.page-header h2, .detail-header h3, .compare-column h4, .create-dialog h3 { margin: 0; }
.layout { display: grid; grid-template-columns: minmax(170px, 280px) minmax(0, 1fr); gap: 16px; min-height: 0; }
.library-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; min-height: 0; }
.library-header { padding: 12px; border-bottom: 1px solid var(--border-primary); }
.library-switch { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px; padding: 4px; border-radius: 10px; background: var(--bg-secondary); }
.library-switch button {
  min-height: 36px;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--text-secondary);
  background: transparent;
  font: inherit;
  cursor: pointer;
}
.library-switch button[aria-pressed="true"] { border-color: var(--border-primary); background: var(--bg-primary); color: var(--text-primary); font-weight: 600; }
.scope-picker { display: flex; align-items: center; gap: 8px; margin-top: 8px; color: var(--text-secondary); font-size: 13px; }
.scope-picker select { flex: 1; min-width: 0; padding-block: 5px; }
.list-panel, .detail-panel {
  min-height: 0;
  min-width: 0;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.list-panel { padding: 8px; }
.list-status { margin: 8px; }
.skill-row {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  text-align: left;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.skill-row:hover { background: var(--bg-hover); }
.skill-row[aria-current="true"] { background: var(--brand-light); border-color: var(--border-secondary); }
.skill-name { font-weight: 600; overflow-wrap: anywhere; }
.skill-desc { font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badges { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { background: var(--bg-tertiary); color: var(--text-secondary); border-radius: 999px; padding: 1px 7px; font-size: 11px; font-weight: 500; }
.detail-panel { padding: clamp(16px, 3vw, 28px); }
.list-panel:focus-visible, .detail-panel:focus-visible { outline: 2px solid var(--brand); outline-offset: -2px; }
.detail-header { flex-wrap: wrap; }
.detail-header > div:first-child { min-width: 0; overflow-wrap: anywhere; }
.detail-header h3 { font-size: clamp(18px, 2.5vw, 25px); }
.detail-header > .btn { flex: none; }
.detail-kind { margin: 0 0 4px; color: var(--text-secondary); font-size: 12px; }
.description { margin: 4px 0 0; color: var(--text-secondary); font-size: 13px; }
.metadata { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 16px 0; padding: 12px; border-radius: 8px; background: var(--bg-secondary); font-size: 13px; }
.metadata div { display: flex; gap: 8px; min-width: 0; }
.metadata dt { flex: none; color: var(--text-secondary); }
.metadata dd { margin: 0; overflow-wrap: anywhere; }
.metadata a { color: var(--brand); text-decoration: underline; }
.content-toolbar { align-items: center; flex-wrap: wrap; border-bottom: 1px solid var(--border-primary); padding-bottom: 12px; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.detail-actions.end { justify-content: flex-end; margin-top: 12px; }
.field-label { display: block; margin: 10px 0 6px; font-size: 13px; color: var(--text-secondary); }
.textarea { display: block; width: 100%; resize: vertical; font-family: ui-monospace, monospace; }
.skill-markdown { max-width: 76ch; padding: 4px 0 8px; line-height: 1.7; overflow-wrap: anywhere; }
.skill-markdown :deep(pre) { padding: 12px; overflow-x: auto; border-radius: 8px; background: var(--bg-code); }
.skill-markdown :deep(.code-block-copy-btn) { display: none; }
.muted { color: var(--text-secondary); font-size: 13px; }
.empty { color: var(--text-secondary); text-align: center; padding: 40px 8px; }
.error-banner { background: var(--bg-danger); color: var(--text-danger); padding: 10px; border-radius: 6px; margin-bottom: 12px; }
.history-dialog, .create-dialog { width: min(960px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); padding: 20px; margin: auto; border: 1px solid var(--border-secondary); border-radius: 12px; color: var(--text-primary); background: var(--bg-primary); box-shadow: var(--shadow-lg); }
.history-dialog:modal, .create-dialog:modal { overscroll-behavior: contain; }
.history-dialog::backdrop, .create-dialog::backdrop { background: var(--bg-overlay); }
.create-dialog { width: min(680px, calc(100vw - 32px)); }
.history-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 16px 0; font-size: 13px; }
.history-picker select { width: auto; max-width: 100%; }
.comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.compare-column { min-width: 0; padding: 12px; border: 1px solid var(--border-secondary); border-radius: 8px; background: var(--bg-secondary); }
.compare-column pre { max-height: 52dvh; overflow: auto; overscroll-behavior: contain; margin: 12px 0 0; font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
@media (max-width: 700px) {
  .skills-page { padding: 12px; gap: 12px; }
  .layout, .comparison { grid-template-columns: minmax(0, 1fr); }
  .layout { grid-template-rows: minmax(0, 32%) minmax(0, 1fr); gap: 12px; }
  .library-header { padding: 8px; }
  .detail-panel, .history-dialog { padding: 14px; }
}
@media (max-width: 700px) and (max-height: 460px) and (orientation: landscape) {
  .layout { grid-template-columns: minmax(150px, 36%) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
}
</style>
