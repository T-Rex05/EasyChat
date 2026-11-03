<template>
  <div v-if="tasks.length" class="subagent-panel">
    <details :open="isExpanded" @toggle="onToggle">
      <summary class="subagent-summary">
        🔀 子 Agent 委派（{{ tasks.length }} 个任务）
        <span v-if="runningCount > 0" class="subagent-running-badge">
          {{ runningCount }} 执行中
        </span>
      </summary>

      <div class="subagent-list">
        <div
          v-for="task in tasks"
          :key="task.subagent_id"
          :class="['subagent-item', `status-${task.status}`]"
        >
          <!-- 头部：状态 + 目标 -->
          <div class="subagent-item-header">
            <span class="subagent-status-icon">{{ statusIcon(task.status) }}</span>
            <span class="subagent-goal">{{ task.goal || '未命名任务' }}</span>
            <span v-if="task.depth > 0" class="subagent-depth">L{{ task.depth }}</span>
          </div>

          <!-- 元信息 -->
          <div class="subagent-meta">
            <span v-if="task.model" class="subagent-model">{{ task.model }}</span>
            <span v-if="task.duration_seconds != null" class="subagent-duration">
              {{ task.duration_seconds.toFixed(1) }}s
            </span>
            <span v-if="task.tokens" class="subagent-tokens">
              {{ formatTokens(task.tokens) }}
            </span>
            <span v-if="task.tools.length > 0" class="subagent-tools-count">
              🔧 {{ task.tools.length }}
            </span>
          </div>

          <!-- 工具调用记录（可折叠） -->
          <details v-if="task.tools.length > 0" class="subagent-tools-details">
            <summary class="subagent-tools-summary">
              工具调用（{{ task.tools.length }}）
            </summary>
            <div class="subagent-tools-list">
              <div
                v-for="(tool, ti) in task.tools"
                :key="ti"
                class="subagent-tool-item"
              >
                <span class="tool-name">{{ tool.tool_name }}</span>
                <span v-if="tool.preview" class="tool-preview">{{ tool.preview }}</span>
              </div>
            </div>
          </details>

          <!-- 流式输出（可折叠） -->
          <details v-if="task.output" class="subagent-output-details">
            <summary class="subagent-output-summary">
              输出（{{ formatOutputLength(task.output.length) }}）
            </summary>
            <div class="subagent-output-content">{{ task.output }}</div>
          </details>

          <!-- 完成摘要 -->
          <div v-if="task.summary && task.status !== 'running'" class="subagent-summary-text">
            {{ task.summary }}
          </div>
        </div>
      </div>

      <div class="subagent-collapse-bar" @click.stop="collapse">
        ▲ 收起委派面板
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { SubagentTask } from '@/types/chat'

const props = defineProps<{
  tasks: SubagentTask[]
}>()

const isExpanded = ref(true)

const runningCount = computed(() => props.tasks.filter(t => t.status === 'running').length)

function statusIcon(status: string): string {
  switch (status) {
    case 'running': return '⏳'
    case 'completed': return '✅'
    case 'failed': return '❌'
    default: return '⚪'
  }
}

function formatTokens(tokens: { input: number; output: number }): string {
  const total = tokens.input + tokens.output
  if (total >= 1000) {
    return `${(total / 1000).toFixed(1)}k tokens`
  }
  return `${total} tokens`
}

function formatOutputLength(len: number): string {
  if (len >= 10000) return `${(len / 1000).toFixed(1)}k 字符`
  return `${len} 字符`
}

function onToggle(e: Event) {
  const details = e.target as HTMLDetailsElement
  isExpanded.value = details.open
}

function collapse() {
  isExpanded.value = false
}
</script>

<style scoped>
.subagent-panel {
  margin-bottom: 12px;
  position: relative;
}

/* 委派面板和回答之间的分隔 */
.subagent-panel::after {
  content: '';
  display: block;
  margin-top: 10px;
  border-bottom: 1px dashed var(--border-secondary, #e5e6eb);
}

.subagent-panel details {
  border: 1px solid var(--border-primary, #f2f3f5);
  border-radius: 8px;
  overflow: hidden;
}

.subagent-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary, #606266);
  background: var(--bg-secondary, #f7f8fa);
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
}

.subagent-summary::-webkit-details-marker {
  display: none;
}

.subagent-summary:hover {
  background: var(--bg-hover, #e8e9ec);
}

.subagent-running-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--brand, #4e6ef2);
  color: #fff;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.subagent-list {
  padding: 0;
}

.subagent-item {
  padding: 10px 12px;
  border-top: 1px solid var(--border-primary, #f2f3f5);
}

.subagent-item.status-running {
  border-left: 3px solid var(--brand, #4e6ef2);
}

.subagent-item.status-completed {
  border-left: 3px solid #00b42a;
}

.subagent-item.status-failed {
  border-left: 3px solid #f53f3f;
}

.subagent-item-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.subagent-status-icon {
  font-size: 14px;
}

.subagent-goal {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1d2129);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subagent-depth {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--bg-secondary, #f7f8fa);
  color: var(--text-tertiary, #86909c);
}

.subagent-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-tertiary, #86909c);
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.subagent-model {
  padding: 0 4px;
  background: var(--bg-secondary, #f7f8fa);
  border-radius: 3px;
}

/* 子工具调用折叠 */
.subagent-tools-details,
.subagent-output-details {
  margin-top: 6px;
  border: 1px solid var(--border-primary, #f2f3f5);
  border-radius: 6px;
  overflow: hidden;
}

.subagent-tools-summary,
.subagent-output-summary {
  padding: 4px 8px;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-tertiary, #86909c);
  background: var(--bg-secondary, #f7f8fa);
  user-select: none;
  list-style: none;
}

.subagent-tools-summary::-webkit-details-marker,
.subagent-output-summary::-webkit-details-marker {
  display: none;
}

.subagent-tools-summary:hover,
.subagent-output-summary:hover {
  background: var(--bg-hover, #e8e9ec);
}

.subagent-tools-list {
  padding: 4px 8px;
  max-height: 150px;
  overflow-y: auto;
}

.subagent-tool-item {
  padding: 2px 0;
  font-size: 12px;
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.subagent-tool-item .tool-name {
  font-weight: 500;
  color: var(--text-primary, #1d2129);
}

.subagent-tool-item .tool-preview {
  color: var(--text-tertiary, #86909c);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.subagent-output-content {
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
  color: var(--text-secondary, #606266);
  white-space: pre-wrap;
  word-break: break-word;
}

.subagent-summary-text {
  margin-top: 6px;
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, #606266);
  background: var(--bg-secondary, #f7f8fa);
  border-radius: 4px;
  max-height: 100px;
  overflow-y: auto;
}

.subagent-collapse-bar {
  padding: 6px 12px;
  text-align: center;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-tertiary, #86909c);
  border-top: 1px solid var(--border-primary, #f2f3f5);
}

.subagent-collapse-bar:hover {
  background: var(--bg-hover, #e8e9ec);
}
</style>
