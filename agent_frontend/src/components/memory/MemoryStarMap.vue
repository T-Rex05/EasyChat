<template>
  <div class="star-map" aria-label="记忆星图">
    <section v-for="group in groups" :key="group.label" class="constellation" :style="{ minHeight: group.height + 'px' }">
      <svg class="edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <line
          v-for="node in group.nodes" :key="node.item.memory_id"
          x1="50" y1="14" :x2="node.x" :y2="node.y"
        />
        <line
          v-for="edge in group.replacements" :key="edge.node.item.memory_id"
          class="replacement-edge"
          :x1="edge.node.x" :y1="edge.node.y" :x2="edge.previous.x" :y2="edge.previous.y"
        />
      </svg>
      <h3 class="center">{{ group.label }}</h3>
      <button
        v-for="node in group.nodes" :key="node.item.memory_id" type="button"
        class="node" :class="{ selected: node.item.memory_id === selected }"
        :aria-label="`${node.item.content}，版本 ${node.item.version}`"
        :aria-pressed="node.item.memory_id === selected"
        :title="node.item.content"
        :style="{ left: node.x + '%', top: node.y + '%' }"
        @click="emit('select', node.item.memory_id)"
      >
        <span class="point" aria-hidden="true"></span>
        <span class="node-label">{{ node.item.content }}</span>
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MemoryRecord } from '@/api/memoryManagement'
import { groupMemories } from '@/utils/memoryView'

const props = defineProps<{
  items: MemoryRecord[]
  grouping: 'kind' | 'tag'
  selected?: string
}>()
const emit = defineEmits<{ select: [id: string] }>()

const groups = computed(() => groupMemories(props.items, props.grouping).map(({ label, items }) => {
  const columns = Math.min(3, items.length)
  const rows = Math.ceil(items.length / columns)
  const nodes = items.map((item, i) => ({
    item,
    x: (i % columns + 0.5) * (100 / columns),
    y: 29 + (Math.floor(i / columns) + 0.5) * (60 / rows),
  }))
  const byId = new Map(nodes.map(node => [node.item.memory_id, node]))
  const replacements = nodes.flatMap(node => {
    const previous = byId.get(node.item.supersedes ?? '')
    return previous ? [{ node, previous }] : []
  })
  return { label, nodes, replacements, height: Math.max(168, 70 + rows * 60) }
}))
</script>

<style scoped>
.star-map {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 286px), 1fr));
  gap: 12px;
}
.constellation {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-secondary);
  border-radius: 12px;
  background-color: var(--bg-card);
  background-image: radial-gradient(var(--border-secondary) 1px, transparent 1px);
  background-size: 14px 14px;
}
.edges { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.edges line { stroke: var(--brand); stroke-opacity: .38; vector-effect: non-scaling-stroke; }
.edges .replacement-edge { stroke: var(--text-secondary); stroke-dasharray: 3 4; }
.center {
  position: absolute;
  top: 14%;
  left: 50%;
  transform: translate(-50%, -50%);
  max-width: 80%;
  overflow-wrap: anywhere;
  margin: 0;
  padding: 5px 12px;
  border: 1px solid var(--brand);
  border-radius: 16px;
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
}
.node {
  position: absolute;
  display: grid;
  justify-items: center;
  gap: 5px;
  width: 29%;
  min-height: 36px;
  transform: translate(-50%, -10px);
  border-radius: 6px;
  border: 1px solid transparent;
  padding: 4px 2px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.node:hover, .node.selected { background: var(--bg-active); border-color: var(--brand); color: var(--text-primary); }
.node:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.point { width: 10px; height: 10px; background: var(--brand); border: 2px solid var(--bg-card); border-radius: 50%; outline: 1px solid var(--brand); }
.node-label { display: block; width: 100%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 12px; background: var(--bg-card); border-radius: 4px; }
</style>
