<template>
  <dialog ref="dialog" class="card persona-dialog" aria-labelledby="persona-dialog-title" @cancel.prevent="close">
    <header>
      <h2 id="persona-dialog-title">对话角色</h2>
      <button class="btn btn-secondary btn-sm" type="button" :disabled="busy" @click="close">关闭</button>
    </header>

    <p v-if="error" class="persona-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载角色…</p>

    <form v-if="personas.length" class="new-session" @submit.prevent="startSession">
      <label>新会话角色
        <select v-model="selected" class="select" :disabled="busy">
          <option v-for="role in activePersonas" :key="role.id ?? 'default'" :value="role.id ?? ''">
            {{ role.name }}
          </option>
        </select>
      </label>
      <button class="btn btn-primary" type="submit" :disabled="busy || loading">开始新会话</button>
    </form>

    <div class="role-heading">
      <h3>角色设置</h3>
      <button class="btn btn-secondary btn-sm" type="button" :disabled="busy || loading" @click="openEditor()">新增角色</button>
    </div>

    <form v-if="showEditor" class="role-editor" @submit.prevent="saveRole">
      <label>角色名称
        <input v-model="name" class="input" maxlength="30" required :disabled="busy" />
      </label>
      <label>回复设定
        <textarea v-model="instruction" class="textarea" rows="4" maxlength="500" required :disabled="busy"></textarea>
      </label>
      <div class="role-actions">
        <button class="btn btn-secondary btn-sm" type="button" :disabled="busy" @click="showEditor = false">取消</button>
        <button class="btn btn-primary btn-sm" type="submit" :disabled="busy || !name.trim() || !instruction.trim()">保存角色</button>
      </div>
    </form>

    <ul class="roles">
      <li v-for="role in personas" :key="role.id ?? 'default'">
        <div>
          <strong>{{ role.name }}</strong>
          <span class="muted"> · v{{ role.version }}{{ role.active ? '' : ' · 已归档' }}</span>
          <p v-if="role.instruction" class="instruction">{{ role.instruction }}</p>
        </div>
        <div v-if="role.id && role.active" class="role-actions">
          <button class="btn btn-secondary btn-sm" type="button" :disabled="busy || loading" @click="openEditor(role)">编辑</button>
          <button class="btn btn-danger btn-sm" type="button" :disabled="busy || loading" @click="archiveRole(role)">归档</button>
        </div>
      </li>
    </ul>
  </dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createPersona, listPersonas, updatePersona, type Persona } from '@/api/personas'
import { createPersonaSession } from '@/api/session'
import { extractErrorMessage } from '@/utils/errorMessage'

const emit = defineEmits<{
  loaded: [personas: Persona[]]
  created: [id: string, personaId: string | null]
}>()
const dialog = ref<HTMLDialogElement>()
const personas = ref<Persona[]>([])
const activePersonas = computed(() => personas.value.filter(role => role.active))
const selected = ref('')
const error = ref('')
const loading = ref(false)
const busy = ref(false)
const showEditor = ref(false)
const editing = ref<string>()
const name = ref('')
const instruction = ref('')

function syncRoles(roles: Persona[]) {
  personas.value = roles
  emit('loaded', roles)
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    syncRoles(await listPersonas())
  } catch (cause) {
    error.value = extractErrorMessage(cause)
  } finally {
    loading.value = false
  }
}

function open() {
  dialog.value?.showModal()
  void load()
}

function close() {
  if (busy.value) return
  showEditor.value = false
  dialog.value?.close()
}

function openEditor(role?: Persona) {
  editing.value = role?.id ?? undefined
  name.value = role?.name ?? ''
  instruction.value = role?.instruction ?? ''
  error.value = ''
  showEditor.value = true
}

async function saveRole() {
  if (busy.value || !name.value.trim() || !instruction.value.trim()) return
  const target = editing.value
  const body = { name: name.value.trim(), instruction: instruction.value.trim() }
  busy.value = true
  error.value = ''
  try {
    if (target) {
      const saved = await updatePersona(target, body)
      syncRoles(personas.value.map(role => role.id === target ? saved : role))
    } else {
      const saved = await createPersona(body)
      syncRoles([...personas.value, saved])
    }
    showEditor.value = false
  } catch (cause) {
    error.value = extractErrorMessage(cause)
  } finally {
    busy.value = false
  }
}

async function archiveRole(role: Persona) {
  const id = role.id
  if (!id || busy.value || !window.confirm(`归档“${role.name}”？已有会话仍可查看。`)) return
  busy.value = true
  error.value = ''
  try {
    const archived = await updatePersona(id, { active: false })
    syncRoles(personas.value.map(item => item.id === id ? archived : item))
    if (selected.value === id) selected.value = ''
    if (editing.value === id) showEditor.value = false
  } catch (cause) {
    error.value = extractErrorMessage(cause)
  } finally {
    busy.value = false
  }
}

async function startSession() {
  if (busy.value || !activePersonas.value.some(role => (role.id ?? '') === selected.value)) return
  busy.value = true
  error.value = ''
  try {
    const session = await createPersonaSession(selected.value || null)
    emit('created', session.session_id, session.persona_id)
    busy.value = false
    dialog.value?.close()
    showEditor.value = false
  } catch (cause) {
    error.value = extractErrorMessage(cause)
  } finally {
    busy.value = false
  }
}

onMounted(load)
defineExpose({ open })
</script>

<style scoped>
.persona-dialog {
  width: min(540px, calc(100% - 24px));
  max-height: calc(100dvh - 32px);
  overflow: auto;
  margin: auto;
  padding: 18px;
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--border-secondary);
}
.persona-dialog::backdrop { background: rgb(0 0 0 / 45%); }
header, .role-heading, .role-actions, .new-session { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
header, .role-heading { justify-content: space-between; }
header h2, .role-heading h3 { margin: 0; font-size: 18px; }
.role-heading h3 { font-size: 15px; }
.role-heading, .new-session { border-top: 1px solid var(--border-secondary); padding: 12px 0; }
.new-session { margin-top: 12px; align-items: flex-end; }
.new-session label { flex: 1 1 180px; }
.new-session .select, .role-editor .input, .role-editor .textarea { width: 100%; }
.new-session label, .role-editor label { display: grid; gap: 4px; }
.role-editor label { font-size: 13px; }
.role-editor { display: grid; gap: 8px; margin-bottom: 12px; }
.role-editor .textarea { resize: vertical; }
.role-editor .role-actions { justify-content: flex-end; }
.roles { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
.roles li { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; padding: 9px; border: 1px solid var(--border-secondary); border-radius: 6px; }
.roles li > div:first-child { flex: 1; min-width: 145px; overflow-wrap: anywhere; }
.muted, .instruction { color: var(--text-secondary); font-size: 13px; }
.instruction { margin: 5px 0 0; white-space: pre-wrap; }
.persona-error { background: var(--bg-danger); border-left: 3px solid var(--text-danger); padding: 8px; }
</style>
