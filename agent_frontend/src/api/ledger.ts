// 文件与账本 API（F10：前端只展示服务端算出的结果，不自行计算金额）
import request from './request'

export interface FileRecord {
  file_id: string
  original_name: string
  size_bytes: number
  kind: string
  status: string
  source: string
  created_at: string
}

export interface ImportView {
  import_id: string
  file_id: string
  state: string
  rows: number
  inserted: number
  updated: number
  unchanged: number
  failed: number
  control_totals?: Record<string, number>
  coverage_kind?: string
  quality?: { commit?: { inserted?: number; updated?: number; unchanged?: number } }
  created_at?: string
}

type ImportPayload = Omit<ImportView, 'rows' | 'inserted' | 'updated' | 'unchanged' | 'failed'> & {
  row_counts?: { rows?: number; errors?: number }
}

function normalizeImport(view: ImportPayload): ImportView {
  return {
    ...view,
    rows: view.row_counts?.rows ?? 0,
    failed: view.row_counts?.errors ?? 0,
    inserted: view.quality?.commit?.inserted ?? 0,
    updated: view.quality?.commit?.updated ?? 0,
    unchanged: view.quality?.commit?.unchanged ?? 0,
  }
}

export interface ImportSummary {
  totals: Record<string, number>
  control: { ok: boolean; differences?: Record<string, number> }
  warnings: string[]
  rows: number
}

export interface TransactionView {
  transaction_id: string
  occurred_at: string
  merchant: string
  product?: string
  direction: string
  amount_minor: number
  currency: string
  status: string
  category_id?: string
  note?: string
  revision: number
}

export interface Category {
  id: string
  name: string
  kind: string
}

export interface RefundSuggestion {
  refund_transaction_id: string
  original_transaction_id: string
  amount_minor: number
  match_method: string
  reason: string
}

export interface AnalysisResult {
  analysis_id: string
  basis: string
  currency: string
  metrics: { name: string; amount_minor: number }[]
  groups: { bucket_label?: string; bucket1?: string; expense_minor?: number }[]
  coverage: { coverage_kind: string; start: string; end_exclusive: string; notes: string[] }
  warnings: string[]
  transactions: TransactionView[]
}

export async function uploadFile(file: File): Promise<FileRecord> {
  const form = new FormData()
  form.append('file', file)
  form.append('request_id', `web-${file.name}-${file.size}-${file.lastModified}`)
  const res = await request.post<{ file: FileRecord }>('/api/files', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return res.data.file
}

export async function registerImport(fileId: string): Promise<ImportView> {
  const res = await request.post<{ import: ImportPayload }>('/api/ledger/imports', { file_id: fileId })
  return normalizeImport(res.data.import)
}

export async function listImports(): Promise<ImportView[]> {
  const res = await request.get<{ imports: ImportPayload[] }>('/api/ledger/imports')
  return (res.data.imports || []).map(normalizeImport)
}

export async function parseImport(importId: string): Promise<ImportView> {
  const res = await request.post<{ import: ImportPayload }>(`/api/ledger/imports/${importId}/parse`)
  return normalizeImport(res.data.import)
}

export async function importSummary(importId: string): Promise<ImportSummary> {
  const res = await request.get<ImportSummary>(`/api/ledger/imports/${importId}/summary`)
  return res.data
}

export async function commitImport(importId: string, confirmMismatch = false) {
  const res = await request.post(`/api/ledger/imports/${importId}/commit`, {
    request_id: `commit-${importId}-${Date.now()}`,
    confirm_mismatch: confirmMismatch,
  })
  return res.data
}

export async function deleteImport(importId: string) {
  await request.delete(`/api/ledger/imports/${importId}`)
}

export async function listTransactions(limit = 100): Promise<TransactionView[]> {
  const res = await request.get<{ transactions: TransactionView[] }>('/api/ledger/transactions', {
    params: { limit },
  })
  return res.data.transactions || []
}

export async function listCategories(): Promise<Category[]> {
  const res = await request.get<{ categories: Category[] }>('/api/ledger/categories')
  return res.data.categories || []
}

export async function createCategory(name: string): Promise<Category> {
  const res = await request.post<Category>('/api/ledger/categories', { name })
  return res.data
}

export async function patchTransaction(transactionId: string, patch: Record<string, unknown>) {
  const res = await request.patch(`/api/ledger/transactions/${transactionId}`, patch)
  return res.data
}

export async function analyze(plan: Record<string, unknown>): Promise<AnalysisResult> {
  const res = await request.post<AnalysisResult>('/api/ledger/analyze', { plan })
  return res.data
}

export async function refundSuggestions(): Promise<RefundSuggestion[]> {
  const res = await request.get<{ suggestions: RefundSuggestion[] }>('/api/ledger/refunds/suggestions')
  return res.data.suggestions || []
}

export async function confirmRefund(suggestion: RefundSuggestion) {
  const res = await request.post('/api/ledger/refunds/links', {
    refund_transaction_id: suggestion.refund_transaction_id,
    original_transaction_id: suggestion.original_transaction_id,
    amount_minor: suggestion.amount_minor,
  })
  return res.data
}

export async function createReport(plan: Record<string, unknown>, format: string) {
  const res = await request.post<{ file_id: string; original_name: string }>('/api/ledger/reports', {
    plan,
    format,
  })
  return res.data
}

export function downloadUrl(fileId: string): string {
  return `/api/files/${fileId}/content`
}
