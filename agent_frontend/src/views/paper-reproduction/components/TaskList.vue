<template>
  <div class="task-list">
    <div class="task-list-header">
      <h3>任务列表</h3>
      <el-button text @click="resetTasks">
        <el-icon><RefreshRight /></el-icon>
        重置
      </el-button>
    </div>

    <el-scrollbar>
      <div class="task-items">
        <div
          v-for="task in sortedTasks"
          :key="task.id"
          :class="['task-item', task.status, { active: task.id === currentTaskId }]"
          @click="$emit('select', task.id)"
        >
          <div class="task-icon">
            <el-icon v-if="task.status === 'completed'" color="#67c23a">
              <CircleCheckFilled />
            </el-icon>
            <el-icon v-else-if="task.status === 'failed'" color="#f56c6c">
              <CircleCloseFilled />
            </el-icon>
            <el-icon v-else-if="task.status === 'in_progress'" class="is-loading">
              <Loading />
            </el-icon>
            <el-icon v-else color="#909399">
              <Document />
            </el-icon>
          </div>

          <div class="task-content">
            <div class="task-name">{{ task.name }}</div>
            <div class="task-status">{{ getStatusText(task.status) }}</div>
          </div>

          <el-progress
            v-if="task.status === 'in_progress'"
            :percentage="50"
            :stroke-width="2"
            :show-text="false"
          />
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  CircleCheckFilled,
  CircleCloseFilled,
  Loading,
  Document,
  RefreshRight
} from '@element-plus/icons-vue'

interface Task {
  id: string
  name: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
}

const props = defineProps<{
  tasks: Task[]
  currentTaskId: string | null
}>()

const emit = defineEmits<{
  select: [taskId: string]
}>()

const sortedTasks = computed(() => {
  const order = ['parse', 'rubric', 'repo', 'setup', 'debug', 'verify']
  return [...props.tasks].sort((a, b) => {
    return order.indexOf(a.id) - order.indexOf(b.id)
  })
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

function resetTasks() {
  // 重置任务状态
}
</script>

<style scoped>
.task-list {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.task-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.task-list-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.task-items {
  padding: 12px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid transparent;
}

.task-item:hover {
  background: #f5f7fa;
}

.task-item.active {
  background: #ecf5ff;
  border-color: #409eff;
}

.task-item.completed {
  background: #f0f9eb;
}

.task-item.failed {
  background: #fef0f0;
}

.task-icon {
  font-size: 24px;
}

.task-content {
  flex: 1;
}

.task-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}

.task-status {
  font-size: 12px;
  color: #909399;
}
</style>