<template>
  <div class="evidence-graph-panel">
    <!-- 顶部统计卡片 -->
    <div class="stats-cards">
      <el-card class="stat-card" shadow="hover">
        <div class="stat-content">
          <div class="stat-label">整体置信度</div>
          <div class="stat-value">
            <el-progress
              type="dashboard"
              :percentage="confidence.overall * 100"
              :color="getConfidenceColor(confidence.overall)"
              :width="80"
            >
              <template #default="{ percentage }">
                <span class="percentage-value">{{ percentage.toFixed(0) }}%</span>
              </template>
            </el-progress>
          </div>
          <div class="stat-grade">{{ getGrade(confidence.overall) }}</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-content">
          <div class="stat-label">已验证</div>
          <div class="stat-value success">{{ confidence.verified }}</div>
          <div class="stat-total">/ {{ confidence.total }}</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-content">
          <div class="stat-label">失败</div>
          <div class="stat-value danger">{{ confidence.failed }}</div>
          <div class="stat-total">/ {{ confidence.total }}</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-content">
          <div class="stat-label">待定</div>
          <div class="stat-value warning">{{ confidence.pending || confidence.inconclusive || 0 }}</div>
          <div class="stat-total">/ {{ confidence.total }}</div>
        </div>
      </el-card>
    </div>

    <!-- 三车道证据图谱 -->
    <div class="evidence-lanes">
      <!-- Lane 1: 主张 -->
      <div class="lane claims-lane">
        <div class="lane-header">
          <el-tag type="primary" effect="dark">Layer 1: 主张</el-tag>
        </div>
        <div class="lane-content">
          <div
            v-for="claim in claims"
            :key="claim.id"
            :class="['claim-node', claim.status]"
            @click="selectNode(claim)"
          >
            <div class="node-id">{{ claim.id }}</div>
            <div class="node-title">{{ claim.title }}</div>
            <div class="node-statement">{{ claim.statement }}</div>
            <div class="node-importance">
              <el-rate
                v-model="claim.importance"
                disabled
                :max="1"
                :allow-half="true"
                size="small"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Lane 2: 准则 -->
      <div class="lane criteria-lane">
        <div class="lane-header">
          <el-tag type="success" effect="dark">Layer 2: 准则</el-tag>
        </div>
        <div class="lane-content">
          <div
            v-for="criterion in criteria"
            :key="criterion.id"
            :class="['criterion-node', criterion.status]"
            @click="selectNode(criterion)"
          >
            <div class="node-id">{{ criterion.id }}</div>
            <div class="node-description">{{ criterion.description }}</div>
            <div v-if="criterion.expected_value" class="node-expected">
              期望值: {{ criterion.expected_value }} ± {{ criterion.tolerance }}
            </div>
          </div>
        </div>
      </div>

      <!-- Lane 3: 证据 + 判定 -->
      <div class="lane evidence-lane">
        <div class="lane-header">
          <el-tag type="warning" effect="dark">Layer 3-4: 证据 & 判定</el-tag>
        </div>
        <div class="lane-content">
          <div
            v-for="judgment in judgments"
            :key="judgment.id"
            :class="['judgment-node', judgment.status]"
            @click="selectNode(judgment)"
          >
            <div class="node-id">{{ judgment.id }}</div>
            <div class="node-status">
              <el-icon v-if="judgment.status === 'verified'" color="#67c23a">
                <CircleCheckFilled />
              </el-icon>
              <el-icon v-else-if="judgment.status === 'failed'" color="#f56c6c">
                <CircleCloseFilled />
              </el-icon>
              <el-icon v-else color="#e6a23c">
                <WarningFilled />
              </el-icon>
              <span>{{ getStatusText(judgment.status) }}</span>
            </div>
            <div v-if="judgment.actual_value" class="node-actual">
              实际值: {{ judgment.actual_value }}
            </div>
            <div class="node-reason">{{ judgment.reason }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled, CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  graph: any
  confidence: any
}>()

const emit = defineEmits<{
  selectNode: [node: any]
}>()

// 从图谱中提取各层节点
const claims = computed(() => {
  if (!props.graph?.nodes) return []
  return props.graph.nodes.filter((n: any) => n.type === 'claim')
})

const criteria = computed(() => {
  if (!props.graph?.nodes) return []
  return props.graph.nodes.filter((n: any) => n.type === 'criterion')
})

const judgments = computed(() => {
  if (!props.graph?.nodes) return []
  return props.graph.nodes.filter((n: any) => n.type === 'judgment')
})

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

function getGrade(confidence: number): string {
  if (confidence >= 0.9) return 'A+'
  if (confidence >= 0.8) return 'A'
  if (confidence >= 0.7) return 'B'
  if (confidence >= 0.6) return 'C'
  return 'D'
}

function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    verified: '已验证',
    failed: '未通过',
    inconclusive: '待定',
    manual_review_required: '需人工审查'
  }
  return statusMap[status] || status
}

function selectNode(node: any) {
  emit('selectNode', node)
}
</script>

<style scoped>
.evidence-graph-panel {
  padding: 20px;
  background: white;
  border-radius: 8px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  cursor: pointer;
  transition: transform 0.3s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-content {
  text-align: center;
  padding: 8px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 12px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 8px;
}

.stat-value.success {
  color: #67c23a;
}

.stat-value.danger {
  color: #f56c6c;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-total {
  font-size: 14px;
  color: #909399;
}

.stat-grade {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin-top: 8px;
}

.percentage-value {
  font-size: 16px;
  font-weight: bold;
}

.evidence-lanes {
  display: flex;
  gap: 16px;
  flex: 1;
  overflow: hidden;
}

.lane {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.lane-header {
  padding: 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.lane-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

.claim-node,
.criterion-node,
.judgment-node {
  padding: 12px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.claim-node:hover,
.criterion-node:hover,
.judgment-node:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.claim-node.fully_verified,
.judgment-node.verified {
  border-color: #67c23a;
  background: #f0f9eb;
}

.claim-node.failed,
.judgment-node.failed {
  border-color: #f56c6c;
  background: #fef0f0;
}

.claim-node.partially_verified,
.judgment-node.inconclusive {
  border-color: #e6a23c;
  background: #fdf6ec;
}

.node-id {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.node-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}

.node-statement {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}

.node-description {
  font-size: 13px;
  color: #303133;
  margin-bottom: 8px;
}

.node-expected,
.node-actual {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.node-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  margin-bottom: 8px;
}

.node-reason {
  font-size: 12px;
  color: #606266;
}
</style>