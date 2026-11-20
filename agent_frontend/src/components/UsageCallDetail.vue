<template>
  <details @toggle="onToggle">
    <summary>查看问答</summary>
    <p v-if="loading" role="status">正在加载问答…</p>
    <p v-else-if="error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
    <dl v-else-if="detail">
      <dt>用户提问</dt>
      <dd>{{ detail.prompt_text || '没有保存提问文本' }}</dd>
      <dt>对应回复</dt>
      <dd>{{ detail.completion_text || '暂无已保存的回复' }}</dd>
    </dl>
  </details>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { isAxiosError } from 'axios'
import request from '@/api/request'

const props = defineProps<{ callId: string }>()
const emit = defineEmits<{ forbidden: [] }>()
const detail = ref<{ prompt_text?: string | null; completion_text?: string | null } | null>(null)
const loading = ref(false)
const error = ref('')
let pending: AbortController | null = null

function clearDetail() {
  pending?.abort()
  pending = null
  detail.value = null
  error.value = ''
  loading.value = false
}

onBeforeUnmount(clearDetail)

async function load() {
  clearDetail()
  const controller = new AbortController()
  pending = controller
  loading.value = true
  try {
    const res = await request.get('/api/usage/calls/' + encodeURIComponent(props.callId), { signal: controller.signal })
    if (!controller.signal.aborted) detail.value = res.data
  } catch (e) {
    if (controller.signal.aborted) return
    error.value = '问答加载失败。'
    if (isAxiosError(e) && e.response?.status === 403) emit('forbidden')
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

function onToggle(event: Event) {
  if ((event.currentTarget as HTMLDetailsElement).open) load()
  else clearDetail()
}
</script>

<style scoped>
summary { cursor: pointer; color: var(--accent-primary, var(--text-primary)); }
dl { padding: 12px; background: var(--bg-secondary); border-radius: 6px; }
dt { font-weight: 600; }
dd { margin: 4px 0 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
dd:last-child { margin-bottom: 0; }
</style>
