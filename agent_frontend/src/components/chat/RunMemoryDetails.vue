<template>
  <details class="run-memory" @toggle="onToggle">
    <summary>本轮记忆</summary>
    <p v-if="loading" role="status">正在核实本轮记忆…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else-if="result && !result.recorded">本轮没有可核实的记录。</p>
    <p v-else-if="result && !result.items.length">本轮没有可展示的记忆。</p>
    <ul v-else-if="result">
      <li v-for="item in result.items" :key="item.memory_id">
        <RouterLink :to="{ name: 'Memory', query: { memory: item.memory_id, version: String(item.version) } }">
          {{ item.summary }}
        </RouterLink>
        <span>{{ memoryKindLabel(item.kind) }} · 本轮 v{{ item.version }}<template v-if="item.current_version !== item.version"> · 当前 v{{ item.current_version }}</template></span>
      </li>
    </ul>
  </details>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { getRunMemory, type RunMemory } from '@/api/memoryManagement'
import { extractErrorMessage } from '@/utils/errorMessage'
import { memoryKindLabel } from '@/utils/memoryView'

const props = defineProps<{ runId: string }>()
const result = ref<RunMemory>()
const loading = ref(false)
const error = ref('')
let generation = 0
watch(() => props.runId, () => {
  generation++
  result.value = undefined
  error.value = ''
  loading.value = false
})

async function onToggle(event: Event) {
  if (!(event.currentTarget instanceof HTMLDetailsElement) || !event.currentTarget.open || loading.value) return
  const current = ++generation
  result.value = undefined
  error.value = ''
  loading.value = true
  try {
    const data = await getRunMemory(props.runId)
    if (current === generation) result.value = data
  } catch (cause) {
    if (current === generation) error.value = extractErrorMessage(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
</script>

<style scoped>
.run-memory {
  margin-top: 10px;
  padding: 7px 10px;
  border: 1px solid var(--border-secondary);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}
.run-memory summary { cursor: pointer; }
.run-memory p { margin: 7px 0 0; }
.run-memory ul { list-style: none; padding: 0; margin: 7px 0 0; display: grid; gap: 6px; }
.run-memory li { display: grid; overflow-wrap: anywhere; }
.run-memory a { color: var(--brand); text-decoration: underline; }
</style>
