<template>
  <div class="paper-reproduction-view">
    <!-- 顶部标题栏 -->
    <header class="paper-header">
      <div class="header-left">
        <h1>论文复现系统</h1>
        <el-tag v-if="currentPaper" type="success" size="large">
          {{ currentPaper.title }}
        </el-tag>
      </div>
      <div class="header-right">
        <el-input
          v-model="paperUrl"
          placeholder="输入 arXiv URL 或上传 PDF"
          style="width: 300px"
          :disabled="isLoading"
        >
          <template #prepend>
            <el-icon><Document /></el-icon>
          </template>
        </el-input>
        <el-input
          v-model="localRepoPath"
          placeholder="本地仓库路径（可选，如 E:\repos\XGA）"
          style="width: 300px"
          :disabled="isLoading"
        >
          <template #prepend>
            <el-icon><Folder /></el-icon>
          </template>
        </el-input>
        <el-button
          type="primary"
          @click="startReproduction"
          :loading="isLoading"
          :disabled="!paperUrl"
        >
          开始复现
        </el-button>
      </div>
    </header>

    <!-- 主内容区 -->
    <div class="paper-main">
      <!-- 左侧：任务列表 -->
      <div class="task-sidebar">
        <TaskList
          :tasks="tasks"
          :current-task-id="currentTaskId"
          @select="selectTask"
        />
      </div>

      <!-- 右侧：主内容 -->
      <div class="content-area">
        <el-tabs v-model="activeTab" type="border-card">
          <!-- Tab 1: 执行流程 DAG -->
          <el-tab-pane label="执行流程" name="dag">
            <DAGPanel
              :nodes="dagNodes"
              :edges="dagEdges"
              :task-status="taskStatus"
              @node-click="handleNodeClick"
            />
          </el-tab-pane>

          <!-- Tab 2: 证据图谱 -->
          <el-tab-pane label="证据图谱" name="evidence">
            <EvidenceGraphPanel
              :graph="evidenceGraph?.graph"
              :confidence="confidence"
            />
          </el-tab-pane>

          <!-- Tab 3: 验证报告 -->
          <el-tab-pane label="验证报告" name="report">
            <ReportPanel
              :rubric="claimRubric"
              :graph="evidenceGraph?.graph"
              :confidence="confidence"
              @export-pdf="exportPDF"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 底部：日志面板 -->
    <div class="log-panel" v-if="logs.length > 0">
      <el-collapse>
        <el-collapse-item title="执行日志" name="logs">
          <div class="log-content">
            <div
              v-for="(log, index) in logs"
              :key="index"
              :class="['log-item', log.level]"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Folder } from '@element-plus/icons-vue'
import TaskList from './components/TaskList.vue'
import DAGPanel from './components/DAGPanel.vue'
import EvidenceGraphPanel from './components/EvidenceGraphPanel.vue'
import ReportPanel from './components/ReportPanel.vue'
import axios from 'axios'

// ==================== 响应式数据 ====================

const paperUrl = ref('')
const localRepoPath = ref('')  // 本地仓库路径
const isLoading = ref(false)
const activeTab = ref('dag')

// 论文数据
const currentPaper = ref<any>(null)
const claimRubric = ref<any>(null)
const repos = ref<any[]>([])
const containerId = ref<string | null>(null)  // 保存容器 ID
const executionResults = ref<any>(null)  // 保存代码执行结果
const evidenceGraph = ref<any>(null)
const confidence = ref<any>({
  overall: 0,
  verified: 0,
  failed: 0,
  inconclusive: 0,
  total: 0
})

// 任务列表
const tasks = ref<any[]>([
  { id: 'parse', name: '解析论文', status: 'pending' },
  { id: 'rubric', name: '提取主张', status: 'pending' },
  { id: 'repo', name: '发现仓库', status: 'pending' },
  { id: 'setup', name: '搭建环境', status: 'pending' },
  { id: 'debug', name: '调试代码', status: 'pending' },
  { id: 'verify', name: '构建证据图谱', status: 'pending' }
])
const currentTaskId = ref<string | null>(null)

// DAG 节点和边
const dagNodes = ref<any[]>([])
const dagEdges = ref<any[]>([])
const taskStatus = ref<Record<string, string>>({})

// 日志
const logs = ref<any[]>([])

// ==================== 计算属性 ====================

const sortedTasks = computed(() => {
  return tasks.value.sort((a, b) => {
    const order = ['parse', 'rubric', 'repo', 'setup', 'debug', 'verify']
    return order.indexOf(a.id) - order.indexOf(b.id)
  })
})

// ==================== 方法定义 ====================

/**
 * 开始复现流程
 */
async function startReproduction() {
  if (!paperUrl.value) {
    ElMessage.warning('请输入论文 URL')
    return
  }

  isLoading.value = true
  logs.value = []
  addLog('info', `开始复现论文: ${paperUrl.value}`)

  try {
    // 重置任务状态
    tasks.value.forEach(t => t.status = 'pending')
    currentTaskId.value = 'parse'

    // 步骤 1: 解析论文
    await parsePaper()

    // 步骤 2: 提取主张
    await extractRubric()

    // 步骤 3: 发现仓库
    await discoverRepo()

    // 步骤 4-6: 环境搭建、调试、证据图谱（即使某步失败也继续）
    try {
      await setupEnvironment()
    } catch (error: any) {
      addLog('warning', `环境搭建失败，跳过后续步骤: ${error.message}`)
      // 设置空执行结果，让证据图谱能继续构建
      executionResults.value = {
        results: [],
        metrics: {},
        status: 'setup_failed',
        error: error.message
      }
    }

    // 只有环境搭建成功才尝试调试
    if (containerId.value) {
      try {
        await debugCode()
      } catch (error: any) {
        addLog('warning', `代码调试失败: ${error.message}`)
      }
    } else {
      // 没有容器，跳过调试
      updateTaskStatus('debug', 'skipped')
      if (!executionResults.value) {
        executionResults.value = {
          results: [],
          metrics: {},
          status: 'no_container',
          reason: '环境搭建未成功'
        }
      }
    }

    // 无论如何都构建证据图谱
    await buildEvidence()

    ElMessage.success('论文复现完成！')
    addLog('success', '论文复现完成')
  } catch (error: any) {
    ElMessage.error(`复现失败: ${error.message}`)
    addLog('error', `复现失败: ${error.message}`)
  } finally {
    isLoading.value = false
  }
}

/**
 * 解析论文
 */
async function parsePaper() {
  currentTaskId.value = 'parse'
  updateTaskStatus('parse', 'in_progress')
  addLog('info', '正在解析论文...')

  try {
    // 调用后端工具
    const response = await invokeTool('parse_paper', {
      paper_url: paperUrl.value
    })

    currentPaper.value = JSON.parse(response)

    // 检查是否解析成功
    if (currentPaper.value.error) {
      throw new Error(currentPaper.value.error)
    }

    updateTaskStatus('parse', 'completed')
    addLog('success', `论文解析完成: ${currentPaper.value.title || '未知标题'}`)

    // 更新 DAG
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('parse', 'failed')
    throw new Error(`论文解析失败: ${error.message}`)
  }
}

/**
 * 提取主张
 */
async function extractRubric() {
  currentTaskId.value = 'rubric'
  updateTaskStatus('rubric', 'in_progress')
  addLog('info', '正在提取主张...')

  try {
    const response = await invokeTool('extract_claim_rubric', {
      parsed_paper: currentPaper.value,
      max_claims: 5
    })

    claimRubric.value = JSON.parse(response)

    // 检查是否提取成功
    if (claimRubric.value.error) {
      throw new Error(claimRubric.value.error)
    }

    updateTaskStatus('rubric', 'completed')
    const claimsCount = claimRubric.value.claims?.length || 0
    addLog('success', `主张提取完成: ${claimsCount} 个主张`)

    // 更新 DAG
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('rubric', 'failed')
    throw new Error(`主张提取失败: ${error.message}`)
  }
}

/**
 * 发现仓库
 */
async function discoverRepo() {
  currentTaskId.value = 'repo'
  updateTaskStatus('repo', 'in_progress')
  addLog('info', '正在搜索 GitHub 仓库...')

  try {
    const response = await invokeTool('discover_repo', {
      parsed_paper: currentPaper.value,
      claim_rubric: claimRubric.value,
      max_repos: 3
    })

    const result = JSON.parse(response)
    repos.value = result.repos || []

    if (repos.value.length === 0) {
      // 没有找到仓库，提供选项
      updateTaskStatus('repo', 'warning')
      addLog('warning', '未找到匹配的仓库')
      addLog('info', '建议：在 GitHub 上搜索论文标题，或查看论文是否提供了代码链接')

      // 设置一个标志，允许用户手动输入仓库 URL
      ElMessage.warning('未找到匹配的仓库，您可以手动输入仓库 URL 或跳过此步骤')
    } else {
      updateTaskStatus('repo', 'completed')
      addLog('success', `找到 ${repos.value.length} 个仓库`)
    }

    // 更新 DAG
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('repo', 'failed')
    throw new Error(`仓库发现失败: ${error.message}`)
  }
}

/**
 * 搭建环境
 */
async function setupEnvironment() {
  currentTaskId.value = 'setup'
  updateTaskStatus('setup', 'in_progress')
  addLog('info', '正在搭建环境...')

  try {
    // 优先使用本地仓库路径
    if (localRepoPath.value) {
      addLog('info', `使用本地仓库: ${localRepoPath.value}`)

      const response = await invokeTool('debug_paper_code', {
        action: 'setup',
        repo_path: localRepoPath.value  // 使用本地路径
      })

      const setupResult = JSON.parse(response)

      if (setupResult.error) {
        throw new Error(setupResult.error)
      }

      if (setupResult.container_id) {
        containerId.value = setupResult.container_id
        addLog('success', `环境搭建完成，容器 ID: ${containerId.value.slice(0, 12)}`)
      }

      updateTaskStatus('setup', 'completed')
      updateDAG()
      return
    }

    // 没有本地路径，尝试从 GitHub 克隆
    if (repos.value.length === 0) {
      updateTaskStatus('setup', 'skipped')
      addLog('warning', '没有找到可用仓库，跳过环境搭建')
      addLog('info', '建议：输入本地仓库路径，或手动在 GitHub 搜索论文代码')
      return
    }

    const response = await invokeTool('debug_paper_code', {
      action: 'setup',
      repo_url: repos.value[0].html_url
    })

    const setupResult = JSON.parse(response)

    if (setupResult.error) {
      throw new Error(setupResult.error)
    }

    if (setupResult.container_id) {
      containerId.value = setupResult.container_id
      addLog('success', `环境搭建完成，容器 ID: ${containerId.value.slice(0, 12)}`)
    } else {
      addLog('warning', '环境搭建完成，但未返回容器 ID')
    }

    updateTaskStatus('setup', 'completed')
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('setup', 'failed')
    executionResults.value = {
      results: [],
      metrics: {},
      status: 'setup_failed',
      error: error.message
    }
    throw new Error(`环境搭建失败: ${error.message}`)
  }
}

/**
 * 调试代码
 */
async function debugCode() {
  currentTaskId.value = 'debug'
  updateTaskStatus('debug', 'in_progress')
  addLog('info', '正在调试代码...')

  try {
    // 检查是否有仓库或容器
    if (repos.value.length === 0 || !containerId.value) {
      updateTaskStatus('debug', 'skipped')
      addLog('warning', '没有可用环境，跳过代码调试')
      // 即使没有环境，也创建模拟执行结果
      executionResults.value = {
        results: [],
        metrics: {},
        status: 'skipped',
        reason: repos.value.length === 0 ? '没有找到可用仓库' : '环境搭建未完成'
      }
      return
    }

    const response = await invokeTool('debug_paper_code', {
      action: 'debug',
      container_id: containerId.value,  // 传递容器 ID
      rubric: claimRubric.value
    })

    // 保存执行结果
    executionResults.value = JSON.parse(response)

    // 检查是否有错误
    if (executionResults.value.error) {
      addLog('warning', `代码调试失败: ${executionResults.value.error}`)
    } else {
      addLog('success', `代码调试完成: ${executionResults.value.status || 'success'}`)
    }

    updateTaskStatus('debug', 'completed')

    // 更新 DAG
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('debug', 'failed')
    // 即使失败，也记录错误结果
    executionResults.value = {
      results: [],
      metrics: {},
      status: 'failed',
      error: error.message
    }
    addLog('error', `代码调试失败: ${error.message}`)
    // 不抛出异常，让流程继续到证据图谱构建
  }
}

/**
 * 构建证据图谱
 */
async function buildEvidence() {
  currentTaskId.value = 'verify'
  updateTaskStatus('verify', 'in_progress')
  addLog('info', '正在构建证据图谱...')

  try {
    // 使用保存的执行结果，如果没有则使用空对象
    const execResults = executionResults.value || {
      results: [],
      metrics: {},
      status: 'no_execution'
    }

    // 调试日志
    console.log('=== 构建证据图谱参数 ===')
    console.log('claimRubric:', JSON.stringify(claimRubric.value, null, 2))
    console.log('execResults:', JSON.stringify(execResults, null, 2))

    const response = await invokeTool('build_evidence_graph', {
      rubric: claimRubric.value,
      execution_results: execResults
    })

    console.log('=== 证据图谱返回 ===')
    console.log('response:', response)

    evidenceGraph.value = JSON.parse(response)

    console.log('=== evidenceGraph ===')
    console.log('evidenceGraph:', JSON.stringify(evidenceGraph.value, null, 2))

    confidence.value = evidenceGraph.value.confidence || {
      overall: 0,
      verified: 0,
      failed: 0,
      inconclusive: 0,
      pending: 0,
      total: 0
    }

    // 检查是否有错误
    if (evidenceGraph.value.error) {
      updateTaskStatus('verify', 'warning')
      addLog('warning', `证据图谱构建警告: ${evidenceGraph.value.error}`)
    } else {
      updateTaskStatus('verify', 'completed')
      addLog('success', `证据图谱构建完成: 置信度 ${(confidence.value.overall * 100).toFixed(0)}%`)
    }

    // 切换到证据图谱 Tab
    activeTab.value = 'evidence'

    // 更新 DAG
    updateDAG()

  } catch (error: any) {
    updateTaskStatus('verify', 'failed')
    throw new Error(`证据图谱构建失败: ${error.message}`)
  }
}

/**
 * 调用后端工具
 */
async function invokeTool(toolName: string, params: any): Promise<string> {
  try {
    const response = await fetch(`/api/tools/${toolName}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()

    if (!data.success) {
      throw new Error(data.error || '工具调用失败')
    }

    return data.result
  } catch (error: any) {
    console.error('工具调用失败:', error)
    throw error
  }
}

/**
 * 更新任务状态
 */
function updateTaskStatus(taskId: string, status: string) {
  const task = tasks.value.find(t => t.id === taskId)
  if (task) {
    task.status = status
  }
  taskStatus.value[taskId] = status
}

/**
 * 添加日志
 */
function addLog(level: string, message: string) {
  logs.value.push({
    time: new Date().toLocaleTimeString(),
    level,
    message
  })
}

/**
 * 更新 DAG
 */
function updateDAG() {
  // 根据任务状态更新 DAG 节点和边
  const nodePositions = [
    { x: 100, y: 100 },
    { x: 300, y: 100 },
    { x: 500, y: 100 },
    { x: 200, y: 250 },
    { x: 400, y: 250 },
    { x: 300, y: 400 }
  ]

  dagNodes.value = tasks.value.map((task, index) => ({
    id: task.id,
    type: 'taskNode',
    position: nodePositions[index],
    data: {
      label: task.name,
      status: task.status
    }
  }))

  dagEdges.value = [
    { id: 'e1', source: 'parse', target: 'rubric' },
    { id: 'e2', source: 'rubric', target: 'repo' },
    { id: 'e3', source: 'repo', target: 'setup' },
    { id: 'e4', source: 'setup', target: 'debug' },
    { id: 'e5', source: 'debug', target: 'verify' }
  ]
}

/**
 * 选择任务
 */
function selectTask(taskId: string) {
  currentTaskId.value = taskId
  // 显示任务详情
}

/**
 * 处理节点点击
 */
function handleNodeClick(nodeId: string) {
  console.log('Node clicked:', nodeId)
  selectTask(nodeId)
}

/**
 * 导出 PDF
 */
function exportPDF() {
  ElMessage.success('PDF 导出功能开发中...')
}

// ==================== 生命周期 ====================

onMounted(() => {
  // 初始化 DAG
  updateDAG()
})
</script>

<style scoped>
.paper-reproduction-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
}

.paper-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: white;
  border-bottom: 1px solid #e4e7ed;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-left h1 {
  margin: 0;
  font-size: 24px;
  color: #303133;
}

.header-right {
  display: flex;
  gap: 12px;
}

.paper-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.task-sidebar {
  width: 280px;
  background: white;
  border-right: 1px solid #e4e7ed;
  overflow-y: auto;
}

.content-area {
  flex: 1;
  padding: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 确保 el-tabs 填满容器 */
:deep(.el-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}

:deep(.el-tab-pane) {
  height: 100%;
  overflow: auto;
}

.log-panel {
  background: white;
  border-top: 1px solid #e4e7ed;
  padding: 12px 20px;
}

.log-content {
  max-height: 200px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 12px;
}

.log-item {
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 4px;
}

.log-item.info {
  background: #f0f9ff;
  color: #1e88e5;
}

.log-item.success {
  background: #f1f8e9;
  color: #4caf50;
}

.log-item.error {
  background: #ffebee;
  color: #f44336;
}

.log-time {
  color: #909399;
  margin-right: 12px;
}

.log-message {
  color: inherit;
}
</style>