<template>
  <div class="dag-panel">
    <VueFlow
      v-model:nodes="nodes"
      v-model:edges="edges"
      :default-viewport="{ zoom: 1 }"
      :min-zoom="0.2"
      :max-zoom="4"
      fit-view-on-init
      @node-click="handleNodeClick"
    >
      <!-- 自定义任务节点 -->
      <template #node-taskNode="nodeProps">
        <TaskNode :data="nodeProps.data" />
      </template>

      <!-- 背景 -->
      <Background />

      <!-- 控制面板 -->
      <Controls />

      <!-- 小地图 -->
      <MiniMap />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import TaskNode from './TaskNode.vue'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

interface TaskNodeData {
  label: string
  status: string
}

const props = defineProps<{
  nodes: any[]
  edges: any[]
  taskStatus: Record<string, string>
}>()

const emit = defineEmits<{
  nodeClick: [nodeId: string]
}>()

const { onNodeClick } = useVueFlow()

// 本地节点和边
const nodes = ref<any[]>([])
const edges = ref<any[]>([])

// 监听 props 变化
watch(
  () => props.nodes,
  (newNodes) => {
    nodes.value = newNodes.map(node => ({
      ...node,
      type: 'taskNode',
      data: {
        ...node.data,
        status: props.taskStatus[node.id] || 'pending'
      }
    }))
  },
  { immediate: true, deep: true }
)

watch(
  () => props.edges,
  (newEdges) => {
    edges.value = newEdges.map(edge => ({
      ...edge,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#409eff', strokeWidth: 2 }
    }))
  },
  { immediate: true }
)

// 监听任务状态变化
watch(
  () => props.taskStatus,
  (newStatus) => {
    nodes.value = nodes.value.map(node => ({
      ...node,
      data: {
        ...node.data,
        status: newStatus[node.id] || 'pending'
      }
    }))
  },
  { deep: true }
)

// 处理节点点击
function handleNodeClick(event: any) {
  const nodeId = event.node.id
  emit('nodeClick', nodeId)
}

// VueFlow 事件
onNodeClick((event) => {
  handleNodeClick(event)
})
</script>

<style scoped>
.dag-panel {
  width: 100%;
  height: 100%;
  background: white;
  border-radius: 8px;
}

/* Vue Flow 自定义样式 */
:deep(.vue-flow) {
  background: #f5f7fa;
}

:deep(.vue-flow__edge-path) {
  stroke: #409eff;
  stroke-width: 2;
}

:deep(.vue-flow__edge.animated path) {
  stroke-dasharray: 5;
  animation: flowDash 1s linear infinite;
}

@keyframes flowDash {
  to {
    stroke-dashoffset: -10;
  }
}
</style>