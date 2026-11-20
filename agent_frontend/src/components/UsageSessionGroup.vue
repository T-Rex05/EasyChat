<template>
  <details class="session-group" @toggle="onToggle">
    <summary>
      <span class="group-meta">
        <UsageOwnerBadge :label="group.username || (group.owner_id === 0 ? '系统任务' : global ? `#${group.owner_id}` : '本人')" />
        <SessionChannelBadge :channel="group.channel" />
        <span :title="String(group.call_count)">{{ formatUsageCount(group.call_count) }} 次调用</span>
        <time :datetime="group.last_message_at || group.last_call_at">{{ formatDateTime(group.last_message_at || group.last_call_at) }}</time>
        <span :title="String(group.total_tokens)">合计 {{ formatUsageCount(group.total_tokens) }} Token</span>
      </span>
      <strong class="group-title" :title="group.title || undefined">
        {{ group.preview || group.title || (group.session_id ? '未命名会话' : '未关联会话的调用') }}
      </strong>
    </summary>
    <div class="group-body">
      <div class="stats totals">
        <span :title="String(group.input_tokens)">输入 {{ formatUsageCount(group.input_tokens) }}</span>
        <span :title="String(group.output_tokens)">输出 {{ formatUsageCount(group.output_tokens) }}</span>
      </div>
      <article v-for="call in calls" :key="call.call_id" class="call">
        <div class="stats">
          <SessionChannelBadge v-if="call.source === 'chat'" :channel="call.channel" />
          <span v-else>{{ otherSources[call.source] || call.source }}</span>
          <time>{{ formatDateTime(call.created_at) }}</time>
          <strong>{{ call.model || '未知模型' }}</strong>
          <span :title="String(call.input_tokens)">输入 {{ formatUsageCount(call.input_tokens) }}</span>
          <span :title="String(call.output_tokens)">输出 {{ formatUsageCount(call.output_tokens) }}</span>
          <span>{{ call.status === 'ok' ? '成功' : call.status === 'error' ? '失败' : call.status }}</span>
        </div>
        <UsageCallDetail :call-id="call.call_id" @forbidden="emit('forbidden')" />
      </article>
      <p v-if="error" role="alert">{{ error }}</p>
      <button v-if="hasMore" type="button" class="btn btn-secondary" :disabled="loading" @click="load">
        {{ loading ? '加载中…' : error ? '重试' : '加载更多调用' }}
      </button>
    </div>
  </details>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { isAxiosError } from 'axios'
import request from '@/api/request'
import { formatDateTime } from '@/utils/dateTime'
import { formatUsageCount } from '@/utils/usageNumbers'
import UsageCallDetail from './UsageCallDetail.vue'
import SessionChannelBadge from './SessionChannelBadge.vue'
import UsageOwnerBadge from './UsageOwnerBadge.vue'

export interface CallGroup {
  owner_id: number
  username: string | null
  session_id: string | null
  channel: string | null
  title: string | null
  preview?: string | null
  last_message_at: string | null
  last_call_at: string
  call_count: number
  total_tokens: number
  input_tokens: number
  output_tokens: number
}
interface Call {
  call_id: string
  source: string
  channel: string | null
  created_at: string
  model: string
  input_tokens: number
  output_tokens: number
  status: string
}

const props = defineProps<{ group: CallGroup; global?: boolean }>()
const emit = defineEmits<{ forbidden: [] }>()
const calls = ref<Call[]>([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(true)
const pageSize = 20
const otherSources: Record<string, string> = { memory: '记忆', evolution: '进化', schedule: '定时任务' }
const controller = new AbortController()
let offset = 0
onBeforeUnmount(() => controller.abort())

async function load() {
  if (loading.value || !hasMore.value) return
  loading.value = true
  error.value = ''
  try {
    const params = {
      owner_id: props.global ? props.group.owner_id : undefined,
      session_id: props.group.session_id,
      limit: pageSize,
      offset,
    }
    const url = props.global ? '/api/usage/group-calls' : '/api/usage/me/group-calls'
    const { data } = await request.get<Call[]>(url, { params, signal: controller.signal })
    if (controller.signal.aborted) return
    const seen = new Set(calls.value.map(c => c.call_id))
    calls.value.push(...data.filter(c => !seen.has(c.call_id)))
    offset += data.length
    hasMore.value = data.length === pageSize && offset < props.group.call_count
  } catch (e) {
    if (controller.signal.aborted) return
    if (props.global && isAxiosError(e) && e.response?.status === 403) emit('forbidden')
    error.value = '调用记录加载失败。'
  } finally {
    loading.value = false
  }
}

function onToggle(event: Event) {
  if ((event.currentTarget as HTMLDetailsElement).open && !calls.value.length) load()
}
</script>

<style scoped>
.session-group { border-top: 1px solid var(--border-primary); }
summary { padding: 12px 0; cursor: pointer; }
.group-meta { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 5px 12px; max-width: calc(100% - 20px); vertical-align: top; color: var(--text-secondary); font-size: 13px; }
.group-meta time { white-space: nowrap; }
.group-title { display: block; margin: 6px 0 0 17px; color: var(--text-primary); overflow-wrap: anywhere; }
.stats { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; font-size: 13px; color: var(--text-secondary); }
.group-body { border-left: 2px solid var(--border-primary); margin: 0 0 12px 5px; padding-left: 12px; }
.call { padding: 8px 0; }
.call .stats { margin-bottom: 4px; }
.totals { padding-bottom: 6px; }
</style>
