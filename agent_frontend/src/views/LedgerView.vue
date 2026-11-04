<template>
  <div class="ledger-page">
    <header class="page-header">
      <div>
        <h2>账单</h2>
        <p class="hint">
          原件长期保留；金额、去重与退款净额均由服务端计算，页面只展示结果。
        </p>
      </div>
      <div class="row">
        <input ref="fileInput" type="file" accept=".xlsx,.csv,image/*" class="input" @change="onPick" />
        <button class="btn btn-primary" :disabled="uploading" @click="upload">
          {{ uploading ? '上传中…' : '上传账单' }}
        </button>
      </div>
    </header>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="notice" class="notice-banner">{{ notice }}</div>

    <section class="card">
      <h3>导入记录</h3>
      <div v-if="imports.length === 0" class="empty">还没有导入记录。</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>导入</th><th>状态</th><th>行数</th><th>新增/更新/未变</th><th>覆盖</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in imports" :key="item.import_id">
            <td class="mono">{{ item.import_id }}</td>
            <td>{{ item.state }}</td>
            <td>{{ item.rows }}</td>
            <td>{{ item.inserted }} / {{ item.updated }} / {{ item.unchanged }}</td>
            <td>{{ item.coverage_kind || '—' }}</td>
            <td class="actions">
              <button class="btn btn-secondary" @click="parse(item.import_id)">解析</button>
              <button class="btn btn-secondary" @click="preview(item.import_id)">预览</button>
              <button class="btn btn-primary" @click="commit(item.import_id)">提交</button>
              <button class="btn btn-danger" @click="remove(item.import_id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="summary" class="card">
      <h3>导入核验</h3>
      <p>
        控制总额：<strong :class="summary.control.ok ? 'ok' : 'bad'">
          {{ summary.control.ok ? '一致' : '不一致' }}
        </strong>
        <span v-if="!summary.control.ok" class="muted">
          差异：{{ JSON.stringify(summary.control.differences || {}) }}；确认无误后可再次提交并允许差异。
        </span>
      </p>
      <p class="muted">行数 {{ summary.rows }}；提示：{{ summary.warnings.join('；') || '无' }}</p>
      <table class="table">
        <tbody>
          <tr v-for="(value, key) in summary.totals" :key="key">
            <td>{{ key }}</td><td class="mono">{{ (value / 100).toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h3>统计</h3>
      <div class="row">
        <select v-model="basis" class="select">
          <option value="consumption_net">消费净额（默认）</option>
          <option value="statement_flow">账单流水</option>
          <option value="period_cash_outflow">本期现金流出</option>
        </select>
        <input v-model="start" class="input" type="date" />
        <input v-model="end" class="input" type="date" />
        <button class="btn btn-primary" :disabled="analyzing" @click="runAnalyze">统计</button>
        <button class="btn btn-secondary" @click="report('markdown')">Markdown</button>
        <button class="btn btn-secondary" @click="report('csv')">CSV</button>
        <button class="btn btn-secondary" @click="report('pdf')">PDF</button>
      </div>
      <div v-if="analysis" class="result">
        <p class="muted">
          口径 {{ analysis.basis }}；区间 {{ analysis.coverage.start }} ~ {{ analysis.coverage.end_exclusive }}；
          覆盖 {{ analysis.coverage.coverage_kind }}；分析 {{ analysis.analysis_id }}
        </p>
        <table class="table">
          <thead><tr><th>指标</th><th>金额</th></tr></thead>
          <tbody>
            <tr v-for="metric in analysis.metrics" :key="metric.name">
              <td>{{ metric.name }}</td>
              <td class="mono">{{ money(metric.amount_minor) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="analysis.warnings.length" class="muted">{{ analysis.warnings.join('；') }}</p>
        <table v-if="analysis.groups.length" class="table">
          <thead><tr><th>分组</th><th>支出</th></tr></thead>
          <tbody>
            <tr v-for="(group, index) in analysis.groups" :key="index">
              <td>{{ group.bucket_label || group.bucket1 || '未分类' }}</td>
              <td class="mono">{{ money(group.expense_minor || 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card">
      <h3>最近交易</h3>
      <div class="row">
        <button class="btn btn-secondary" @click="refreshTransactions">刷新</button>
        <button class="btn btn-secondary" @click="newCategory">新建分类</button>
      </div>
      <table class="table">
        <thead>
          <tr><th>时间</th><th>商户</th><th>方向</th><th>金额</th><th>分类</th><th>备注</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="tx in transactions" :key="tx.transaction_id">
            <td>{{ tx.occurred_at.slice(0, 19) }}</td>
            <td>{{ tx.merchant || '—' }}</td>
            <td>{{ tx.direction }}</td>
            <td class="mono">{{ money(tx.amount_minor) }}</td>
            <td>
              <select v-model="drafts[tx.transaction_id].category_id" class="select">
                <option value="">未分类</option>
                <option v-for="category in categories" :key="category.id" :value="category.id">
                  {{ category.name }}
                </option>
              </select>
            </td>
            <td>
              <input v-model="drafts[tx.transaction_id].note" class="input" placeholder="备注" />
            </td>
            <td>
              <button class="btn btn-primary" @click="saveTransaction(tx.transaction_id)">保存</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h3>退款候选</h3>
      <p class="muted">只有确认关联后才影响净额；系统不会自动改账。</p>
      <div class="row">
        <button class="btn btn-secondary" @click="loadRefunds">刷新候选</button>
      </div>
      <div v-if="refunds.length === 0" class="empty">暂无待核对的退款。</div>
      <table v-else class="table">
        <thead><tr><th>退款交易</th><th>原支付</th><th>金额</th><th>置信度</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in refunds" :key="item.refund_transaction_id + item.original_transaction_id">
            <td class="mono">{{ item.refund_transaction_id }}</td>
            <td class="mono">{{ item.original_transaction_id }}</td>
            <td class="mono">{{ money(item.amount_minor) }}</td>
            <td>{{ (item.confidence * 100).toFixed(0) }}%</td>
            <td><button class="btn btn-primary" @click="linkRefund(item)">确认关联</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h3>图片账单候选</h3>
      <p class="muted">截图识别只生成候选；低置信字段必须人工确认后才写入交易。</p>
      <div class="row">
        <input ref="imageInput" type="file" accept="image/*" class="input" @change="onPickImage" />
        <button class="btn btn-secondary" :disabled="recognizing" @click="recognize">
          {{ recognizing ? '识别中…' : '识别截图' }}
        </button>
      </div>
      <div v-if="candidate" class="result">
        <p class="muted">候选 {{ candidate.candidate_id }}；整体置信度 {{ candidate.confidence }}</p>
        <table class="table">
          <thead><tr><th>字段</th><th>值</th><th>置信度</th><th>需要确认</th></tr></thead>
          <tbody>
            <tr v-for="field in candidate.fields" :key="field.name">
              <td>{{ field.name }}</td>
              <td><input v-model="field.value" class="input" /></td>
              <td>{{ field.confidence }}</td>
              <td>{{ field.needs_review ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
        <button class="btn btn-primary" @click="confirmCandidate">确认写入</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  analyze,
  commitImport,
  confirmRefund,
  createCategory,
  createReport,
  deleteImport,
  downloadUrl,
  importSummary,
  listCategories,
  listImports,
  listTransactions,
  parseImport,
  patchTransaction,
  refundSuggestions,
  registerImport,
  uploadFile,
  type AnalysisResult,
  type Category,
  type ImportSummary,
  type ImportView,
  type RefundSuggestion,
  type TransactionView,
} from '../api/ledger'
import request from '../api/request'

interface CandidateField {
  name: string
  value: string
  confidence: number
  needs_review: boolean
}

interface ImageCandidate {
  candidate_id: string
  confidence: number
  fields: CandidateField[]
}

const fileInput = ref<HTMLInputElement | null>(null)
const imageInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const recognizing = ref(false)
const analyzing = ref(false)
const error = ref('')
const notice = ref('')
const imports = ref<ImportView[]>([])
const transactions = ref<TransactionView[]>([])
const categories = ref<Category[]>([])
const refunds = ref<RefundSuggestion[]>([])
const analysis = ref<AnalysisResult | null>(null)
const summary = ref<ImportSummary | null>(null)
const candidate = ref<ImageCandidate | null>(null)
const drafts = reactive<Record<string, { category_id: string; note: string }>>({})

const basis = ref('consumption_net')
const start = ref('')
const end = ref('')

function money(amountMinor: number): string {
  return (Number(amountMinor) / 100).toFixed(2)
}

function fail(err: unknown) {
  const data = (err as { response?: { data?: { detail?: string } } }).response?.data
  error.value = data?.detail ? String(data.detail) : String(err)
}

async function refreshImports() {
  try {
    imports.value = await listImports()
  } catch (err) {
    fail(err)
  }
}

async function refreshTransactions() {
  try {
    transactions.value = await listTransactions()
    for (const tx of transactions.value) {
      if (!drafts[tx.transaction_id]) {
        drafts[tx.transaction_id] = { category_id: tx.category_id || '', note: tx.note || '' }
      }
    }
  } catch (err) {
    fail(err)
  }
}

async function loadCategories() {
  try {
    categories.value = await listCategories()
  } catch (err) {
    fail(err)
  }
}

function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) fileInput.value = target
}

async function upload() {
  const file = fileInput.value?.files?.[0]
  if (!file) {
    error.value = '请选择要上传的账单文件'
    return
  }
  uploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const record = await uploadFile(file)
    const view = await registerImport(record.file_id)
    notice.value = `已保存并登记导入：${view.import_id}（${view.state}）`
    if (fileInput.value) fileInput.value.value = ''
    await refreshImports()
    if (view.state === 'validated' || view.state === 'committed') {
      await preview(view.import_id)
    }
  } catch (err) {
    fail(err)
  } finally {
    uploading.value = false
  }
}

async function parse(importId: string) {
  try {
    await parseImport(importId)
    notice.value = '解析完成，请核对控制总额。'
    await refreshImports()
  } catch (err) {
    fail(err)
  }
}

async function preview(importId: string) {
  try {
    summary.value = await importSummary(importId)
    await refreshImports()
  } catch (err) {
    fail(err)
  }
}

async function commit(importId: string) {
  try {
    const result = await commitImport(importId)
    notice.value = `已提交：新增 ${result.inserted}，更新 ${result.updated}，未变 ${result.unchanged}`
    await refreshImports()
    await refreshTransactions()
    summary.value = null
  } catch (err) {
    fail(err)
  }
}

async function remove(importId: string) {
  if (!window.confirm('删除未提交的导入会解除其文件引用，确认继续？')) return
  try {
    await deleteImport(importId)
    notice.value = '已删除导入（原件仍保留在文件库）'
    await refreshImports()
  } catch (err) {
    fail(err)
  }
}

function plan() {
  const period = start.value && end.value
    ? { start: start.value, end_exclusive: end.value }
    : { start: '1970-01-01', end_exclusive: '2100-01-01' }
  return {
    version: 1,
    basis: basis.value,
    metrics: ['expense', 'income', 'refund_received', 'net'],
    period,
    group_by: ['category'],
    output: 'table',
  }
}

async function runAnalyze() {
  analyzing.value = true
  error.value = ''
  try {
    analysis.value = await analyze(plan())
  } catch (err) {
    fail(err)
  } finally {
    analyzing.value = false
  }
}

async function report(format: string) {
  try {
    const result = await createReport(plan(), format)
    notice.value = `报告已生成：${result.original_name}`
    window.open(downloadUrl(result.file_id), '_blank')
  } catch (err) {
    fail(err)
  }
}

async function saveTransaction(transactionId: string) {
  const draft = drafts[transactionId]
  try {
    await patchTransaction(transactionId, {
      category_id: draft.category_id || null,
      note: draft.note,
      reason: '前端修正',
    })
    notice.value = '已保存修正，并记录审计'
    await refreshTransactions()
  } catch (err) {
    fail(err)
  }
}

async function newCategory() {
  const name = window.prompt('新分类名称')
  if (!name) return
  try {
    await createCategory(name)
    await loadCategories()
  } catch (err) {
    fail(err)
  }
}

async function loadRefunds() {
  try {
    refunds.value = await refundSuggestions()
  } catch (err) {
    fail(err)
  }
}

async function linkRefund(item: RefundSuggestion) {
  try {
    await confirmRefund(item)
    notice.value = '退款关联已确认，净额将按确认结果计算'
    await loadRefunds()
  } catch (err) {
    fail(err)
  }
}

function onPickImage(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) imageInput.value = target
}

async function recognize() {
  const file = imageInput.value?.files?.[0]
  if (!file) {
    error.value = '请选择一张账单截图'
    return
  }
  recognizing.value = true
  error.value = ''
  try {
    const record = await uploadFile(file)
    const res = await request.post<ImageCandidate>(`/api/ledger/images/${record.file_id}/candidates`)
    candidate.value = res.data
  } catch (err) {
    fail(err)
  } finally {
    recognizing.value = false
  }
}

async function confirmCandidate() {
  if (!candidate.value) return
  const corrections: Record<string, string> = {}
  for (const field of candidate.value.fields) {
    corrections[field.name] = field.value
  }
  try {
    await request.post(`/api/ledger/candidates/${candidate.value.candidate_id}/confirm`, {
      corrections,
    })
    notice.value = '截图候选已写入，可在交易列表继续修正'
    candidate.value = null
    await refreshTransactions()
  } catch (err) {
    fail(err)
  }
}

onMounted(async () => {
  await refreshImports()
  await refreshTransactions()
  await loadCategories()
})
</script>

<style scoped>
.ledger-page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.card { background: var(--surface, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; padding: 16px; }
.table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
.table th, .table td { border-bottom: 1px solid var(--border, #eef0f3); padding: 6px 8px; text-align: left; vertical-align: middle; }
.table th { color: var(--muted, #6b7280); font-weight: 500; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: var(--muted, #6b7280); font-size: 12px; }
.empty { color: var(--muted, #6b7280); padding: 12px 0; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.error-banner { background: #fef2f2; color: #b91c1c; padding: 8px 12px; border-radius: 8px; }
.notice-banner { background: #f0fdf4; color: #15803d; padding: 8px 12px; border-radius: 8px; }
.ok { color: #15803d; }
.bad { color: #b91c1c; }
.result { margin-top: 12px; }
</style>
