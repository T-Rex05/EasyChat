<template>
  <div class="report-panel">
    <!-- 报告预览 -->
    <div class="report-preview" ref="reportRef">
      <div class="report-header">
        <h1>论文复现验证报告</h1>
        <div class="report-meta">
          <p><strong>论文标题:</strong> {{ rubric?.paper_title || 'N/A' }}</p>
          <p><strong>生成时间:</strong> {{ new Date().toLocaleString() }}</p>
          <p><strong>置信度:</strong> {{ (confidence?.overall * 100).toFixed(0) }}% ({{ getGrade(confidence?.overall) }})</p>
        </div>
      </div>

      <el-divider />

      <!-- 摘要 -->
      <div class="report-summary">
        <h2>验证摘要</h2>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="总主张数">
            {{ summary.total_claims }}
          </el-descriptions-item>
          <el-descriptions-item label="完全验证">
            <el-tag type="success">{{ summary.fully_verified }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="部分验证">
            <el-tag type="warning">{{ summary.partially_verified }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="待验证">
            <el-tag type="info">{{ summary.pending }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="验证失败">
            <el-tag type="danger">{{ summary.failed }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <el-divider />

      <!-- 主张详情 -->
      <div class="report-claims">
        <h2>主张验证详情</h2>
        <el-table :data="claimsTable" border stripe>
          <el-table-column prop="id" label="ID" width="120" />
          <el-table-column prop="title" label="主张标题" min-width="200" />
          <el-table-column prop="type" label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="row.type === 'quantitative' ? 'primary' : 'success'">
                {{ row.type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="criteria_count" label="准则数" width="80" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-divider />

      <!-- 证据图谱可视化 -->
      <div class="report-graph">
        <h2>证据图谱</h2>
        <div class="graph-visualization">
          <p v-if="!graph">暂无证据图谱数据</p>
          <div v-else class="graph-stats">
            <p><strong>节点总数:</strong> {{ graph.nodes?.length || 0 }}</p>
            <p><strong>边总数:</strong> {{ graph.edges?.length || 0 }}</p>
            <p><strong>层级:</strong> Claims → Criteria → Evidence → Judgment</p>
          </div>
        </div>
      </div>

      <el-divider />

      <!-- 建议 -->
      <div class="report-recommendation">
        <h2>建议</h2>
        <el-alert
          :title="summary.recommendation"
          :type="getAlertType(confidence?.overall)"
          :closable="false"
          show-icon
        />
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="report-actions">
      <el-button type="primary" @click="exportPDF" :loading="isExporting">
        <el-icon><Download /></el-icon>
        导出 PDF
      </el-button>
      <el-button @click="copyReport">
        <el-icon><CopyDocument /></el-icon>
        复制报告
      </el-button>
      <el-button @click="printReport">
        <el-icon><Printer /></el-icon>
        打印报告
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, CopyDocument, Printer } from '@element-plus/icons-vue'

const props = defineProps<{
  rubric: any
  graph: any
  confidence: any
}>()

const emit = defineEmits<{
  exportPdf: []
}>()

const reportRef = ref<HTMLElement>()
const isExporting = ref(false)

const summary = computed(() => {
  if (!props.graph) {
    return {
      total_claims: 0,
      fully_verified: 0,
      partially_verified: 0,
      pending: 0,
      failed: 0,
      recommendation: '暂无验证结果'
    }
  }

  const claims = props.graph.nodes?.filter((n: any) => n.type === 'claim') || []
  return {
    total_claims: claims.length,
    fully_verified: claims.filter((c: any) => c.status === 'fully_verified').length,
    partially_verified: claims.filter((c: any) => c.status === 'partially_verified').length,
    pending: claims.filter((c: any) => c.status === 'pending' || c.status === 'partially_pending').length,
    failed: claims.filter((c: any) => c.status === 'failed').length,
    recommendation: getRecommendation(props.confidence?.overall || 0)
  }
})

const claimsTable = computed(() => {
  if (!props.graph) return []

  const claims = props.graph.nodes?.filter((n: any) => n.type === 'claim') || []
  return claims.map((claim: any) => ({
    id: claim.id,
    title: claim.title,
    type: claim.claim_type,
    criteria_count: claim.criteria?.length || 0,
    status: claim.status
  }))
})

function getGrade(confidence: number): string {
  if (!confidence) return 'N/A'
  if (confidence >= 0.9) return 'A+'
  if (confidence >= 0.8) return 'A'
  if (confidence >= 0.7) return 'B'
  if (confidence >= 0.6) return 'C'
  return 'D'
}

function getRecommendation(confidence: number): string {
  if (confidence >= 0.9) return '论文复现成功，结果高度可信'
  if (confidence >= 0.8) return '论文复现基本成功，建议关注少数未验证项'
  if (confidence >= 0.7) return '论文复现部分成功，需要进一步调试'
  if (confidence >= 0.6) return '论文复现存在较多问题，建议重新审查'
  return '论文复现失败，建议从其他来源寻找代码'
}

function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    fully_verified: '完全验证',
    partially_verified: '部分验证',
    failed: '验证失败',
    pending: '待验证'
  }
  return statusMap[status] || status
}

function getStatusType(status: string): string {
  const typeMap: Record<string, string> = {
    fully_verified: 'success',
    partially_verified: 'warning',
    failed: 'danger',
    pending: 'info'
  }
  return typeMap[status] || 'info'
}

function getAlertType(confidence: number): string {
  if (confidence >= 0.8) return 'success'
  if (confidence >= 0.6) return 'warning'
  return 'error'
}

async function exportPDF() {
  isExporting.value = true

  try {
    // 调用后端生成 PDF
    emit('exportPdf')
    ElMessage.success('PDF 导出成功')
  } catch (error: any) {
    ElMessage.error(`PDF 导出失败: ${error.message}`)
  } finally {
    isExporting.value = false
  }
}

function copyReport() {
  if (!reportRef.value) return

  const text = reportRef.value.innerText
  navigator.clipboard.writeText(text)
    .then(() => ElMessage.success('报告已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

function printReport() {
  window.print()
}
</script>

<style scoped>
.report-panel {
  padding: 20px;
  background: white;
  border-radius: 8px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.report-preview {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}

.report-header {
  text-align: center;
  margin-bottom: 20px;
}

.report-header h1 {
  font-size: 24px;
  color: #303133;
  margin-bottom: 12px;
}

.report-meta p {
  font-size: 14px;
  color: #606266;
  margin: 4px 0;
}

.report-summary,
.report-claims,
.report-graph,
.report-recommendation {
  margin-bottom: 20px;
}

.report-summary h2,
.report-claims h2,
.report-graph h2,
.report-recommendation h2 {
  font-size: 18px;
  color: #303133;
  margin-bottom: 12px;
}

.graph-visualization {
  padding: 20px;
  background: white;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}

.graph-stats p {
  font-size: 14px;
  color: #606266;
  margin: 8px 0;
}

.report-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}

/* 打印样式 */
@media print {
  .report-actions {
    display: none;
  }
}
</style>