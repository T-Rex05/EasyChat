<template>
  <div :class="['task-node', data.status]">
    <div class="node-header">
      <el-icon v-if="data.status === 'completed'" color="#67c23a" :size="20">
        <CircleCheckFilled />
      </el-icon>
      <el-icon v-else-if="data.status === 'failed'" color="#f56c6c" :size="20">
        <CircleCloseFilled />
      </el-icon>
      <el-icon v-else-if="data.status === 'in_progress'" :size="20" class="is-loading">
        <Loading />
      </el-icon>
      <div v-else class="node-number">{{ nodeNumber }}</div>
    </div>

    <div class="node-content">
      <div class="node-label">{{ data.label }}</div>
      <div class="node-status">{{ getStatusText(data.status) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled, CircleCloseFilled, Loading } from '@element-plus/icons-vue'

interface TaskNodeData {
  label: string
  status: string
}

const props = defineProps<{
  data: TaskNodeData
}>()

const nodeNumber = computed(() => {
  const labels: Record<string, string> = {
    '解析论文': '1',
    '提取主张': '2',
    '发现仓库': '3',
    '搭建环境': '4',
    '调试代码': '5',
    '构建证据图谱': '6'
  }
  return labels[props.data.label] || '?'
})

function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    pending: '等待执行',
    in_progress: '执行中...',
    completed: '已完成',
    failed: '执行失败'
  }
  return statusMap[status] || status
}
</script>

<style scoped>
.task-node {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: white;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  min-width: 180px;
  transition: all 0.3s;
}

.task-node:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.task-node.pending {
  border-color: #dcdfe6;
  background: #fafafa;
}

.task-node.in_progress {
  border-color: #409eff;
  background: #ecf5ff;
}

.task-node.completed {
  border-color: #67c23a;
  background: #f0f9eb;
}

.task-node.failed {
  border-color: #f56c6c;
  background: #fef0f0;
}

.node-header {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f5f7fa;
  font-weight: bold;
}

.node-number {
  color: #606266;
  font-size: 14px;
}

.node-content {
  flex: 1;
}

.node-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.node-status {
  font-size: 12px;
  color: #909399;
}

.is-loading {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>