// RAG 测评 API

import request from './request'

export interface KbEvalSet {
  id: number
  user_id: number
  name: string
  description: string
  item_count: number
  created_at: string
  updated_at: string
}

export interface KbEvalItem {
  id: number
  eval_set_id: number
  question: string
  ground_truth_chunk_ids: number[]
  ground_truth_answer: string
  sort_order: number
}

export interface KbEvalSetDetail extends KbEvalSet {
  items: KbEvalItem[]
}

export interface RetrievedChunk {
  chunk_id: number | null
  document_id: number | null
  content: string
  score: number
  is_gt: boolean
}

export interface KbEvalResult {
  id: number
  item_id: number
  question: string
  retrieved_chunks: RetrievedChunk[]
  metrics: Record<string, number>
  answer: string
  judge_metrics: Record<string, number | null>
  classification?: string
}

export interface KbEvalRun {
  id: number
  eval_set_id: number
  config: { top_k: number; generate_answer: boolean; judge_enabled: boolean; retriever: string }
  status: 'running' | 'done' | 'failed'
  progress: { done: number; total: number; stage?: string; message?: string }
  // 后端 _aggregate_run 返回异构结构：数值指标 + classifications 计数对象 + warnings 数组 + _count
  metrics: Record<string, any>
  error: string
  started_at: string
  finished_at: string
  created_at: string
}

export interface KbEvalRunDetail extends KbEvalRun {
  results: KbEvalResult[]
}

export interface RunEvalOptions {
  top_k?: number
  generate_answer?: boolean
  judge_enabled?: boolean
  retriever?: string
  chunk_kind?: string   // all | base | topic（切分策略对比）
}

// ── 向量化 / 试检索 / chunk 搜索 ──

export async function vectorizeDocument(id: number): Promise<{ id: number; vectorized_chunks: number }> {
  const response = await request.post(`/api/kb/documents/${id}/vectorize`, {}, { timeout: 10 * 60 * 1000 })
  return response.data
}

export async function tryRetrieve(query: string, topK = 5, mode = 'auto', kind = 'all'): Promise<{ retriever: string; kind: string; results: RetrievedChunk[]; warnings: string[] }> {
  const response = await request.get('/api/kb/retrieve', { params: { query, top_k: topK, mode, kind } })
  return response.data
}

export async function searchChunks(keyword: string, page = 1, pageSize = 20, documentId?: number): Promise<{
  total: number
  items: { 
    id: number
    document_id: number
    document_name: string
    chunk_index: number
    char_count: number
    content: string
    kind: 'parent' | 'child' | 'base' | 'topic'
    chunk_strategy: string
  }[]
}> {
  const response = await request.get('/api/kb/chunks/search', {
    params: { keyword, page, page_size: pageSize, document_id: documentId || undefined },
  })
  return response.data
}

// ── 测评集 CRUD ──

export async function listEvalSets(): Promise<{ total: number; items: KbEvalSet[] }> {
  const response = await request.get('/api/kb/eval-sets')
  return response.data
}

export async function getEvalSet(id: number): Promise<KbEvalSetDetail> {
  const response = await request.get(`/api/kb/eval-sets/${id}`)
  return response.data
}

export async function createEvalSet(name: string, description = ''): Promise<KbEvalSet> {
  const response = await request.post('/api/kb/eval-sets', { name, description })
  return response.data
}

export async function updateEvalSet(id: number, name: string, description = ''): Promise<{ id: number }> {
  const response = await request.put(`/api/kb/eval-sets/${id}`, { name, description })
  return response.data
}

export async function deleteEvalSet(id: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/eval-sets/${id}`)
  return response.data
}

// ── 题目 CRUD ──

export async function addEvalItem(
  setId: number,
  data: { question: string; ground_truth_chunk_ids: number[]; ground_truth_answer?: string },
): Promise<{ id: number }> {
  const response = await request.post(`/api/kb/eval-sets/${setId}/items`, data)
  return response.data
}

export async function updateEvalItem(
  setId: number,
  itemId: number,
  data: { question: string; ground_truth_chunk_ids?: number[]; ground_truth_answer?: string },
): Promise<{ id: number }> {
  const response = await request.put(`/api/kb/eval-sets/${setId}/items/${itemId}`, data)
  return response.data
}

export async function deleteEvalItem(setId: number, itemId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/eval-sets/${setId}/items/${itemId}`)
  return response.data
}

// ── 运行 ──

export async function runEval(setId: number, options: RunEvalOptions = {}): Promise<{ run_id: number; total: number }> {
  const response = await request.post(`/api/kb/eval-sets/${setId}/run`, {
    top_k: options.top_k ?? 5,
    generate_answer: options.generate_answer ?? true,
    judge_enabled: options.judge_enabled ?? true,
    retriever: options.retriever ?? 'auto',
    chunk_kind: options.chunk_kind ?? 'all',
  })
  return response.data
}

export async function listRuns(setId: number): Promise<{ items: KbEvalRun[] }> {
  const response = await request.get(`/api/kb/eval-sets/${setId}/runs`)
  return response.data
}

export async function getRun(runId: number): Promise<KbEvalRunDetail> {
  const response = await request.get(`/api/kb/eval-runs/${runId}`)
  return response.data
}

export async function deleteRun(runId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/eval-runs/${runId}`)
  return response.data
}

// ── RAG 评测闭环：优化建议 ──

export interface KbSuggestion {
  id: number
  user_id: number
  eval_set_id: number | null
  source: 'eval' | 'feedback' | 'manual'
  kind: string
  summary: string
  evidence: Record<string, any>
  status: 'pending' | 'verifying' | 'verified' | 'failed' | 'dismissed' | 'approved' | 'executed'
  before_metrics: Record<string, number>
  after_metrics: Record<string, number>
  linked_run_ids: number[]
  attempts: number
  created_at: string
  updated_at: string
  resolved_at: string
  // ★ 前端临时状态
  _selectedActions?: number[]
  _collapsed?: boolean
  _actions?: { chunkId: number; note: string; itemId?: number; location?: string; supplement?: string; reason?: string }[]
}

export async function generateSuggestionsForRun(runId: number): Promise<{ created: number; suggestion_ids: number[] }> {
  // LLM 分析耗时较长，设置 3 分钟超时
  const response = await request.post(`/api/kb/eval-runs/${runId}/suggestions`, {}, { timeout: 3 * 60 * 1000 })
  return response.data
}

export async function listSuggestions(status = '', page = 1, pageSize = 30, evalSetId?: number, source?: string): Promise<{
  total: number
  items: KbSuggestion[]
}> {
  const response = await request.get('/api/kb/suggestions', {
    params: { status: status || undefined, page, page_size: pageSize, eval_set_id: evalSetId || undefined, source: source || undefined },
  })
  return response.data
}

export async function runSuggestion(id: number): Promise<{ run_id: number; suggestion_id: number }> {
  const response = await request.post(`/api/kb/suggestions/${id}/run`)
  return response.data
}

export async function dismissSuggestion(id: number): Promise<{ id: number; dismissed: boolean }> {
  console.log('[debug-api] dismissSuggestion called with id:', id)
  const url = `/api/kb/suggestions/${id}/dismiss`
  console.log('[debug-api] calling URL:', url)
  const response = await request.post(url)
  console.log('[debug-api] response data:', response.data)
  return response.data
}

export async function deleteSuggestion(id: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/suggestions/${id}`)
  return response.data
}

// ── 分类阈值配置 ──

export interface ClassifyThresholds {
  judge_pass: number
  wrong_answer_correctness: number
  complete_faith_threshold: number
  wrong_answer_faith_threshold: number
}

export async function getClassifyThresholds(): Promise<ClassifyThresholds> {
  const response = await request.get('/api/kb/classify-thresholds')
  return response.data
}

export async function updateClassifyThresholds(thresholds: ClassifyThresholds): Promise<{
  thresholds: ClassifyThresholds
  reclassified_runs: number
}> {
  const response = await request.put('/api/kb/classify-thresholds', thresholds)
  return response.data
}

// ── 聊天反馈「测评集」 ──

export interface ChatFeedbackChunk {
  id: number
  document_id: number | null
  preview: string
}

export interface ChatFeedbackItem {
  id: number
  user_id: number
  conversation_id: number | null
  thread_id: string
  rating: number
  comment: string
  retrieved_chunk_ids: number[]
  status: string
  created_at: string
  question: string
  chunks: ChatFeedbackChunk[]
}

export async function listChatEvalItems(page = 1, pageSize = 50): Promise<{
  total: number
  items: ChatFeedbackItem[]
}> {
  const response = await request.get('/api/kb/chat-eval/items', { params: { page, page_size: pageSize } })
  return response.data
}

export async function generateFeedbackSuggestion(feedbackId: number): Promise<{ created: boolean; suggestion_id?: number; reason?: string }> {
  const response = await request.post(`/api/kb/feedback/${feedbackId}/generate-suggestion`)
  return response.data
}

export async function deleteChatFeedback(feedbackId: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/feedback/${feedbackId}`)
  return response.data
}

// ── 执行优化建议 ──

export interface ExecuteAction {
  type: 'chunk_modify' | 'add_sql_example' | 'reparse'
  chunk_id?: number
  new_content?: string
  reason?: string
  content?: string
  kb_id?: number
  document_id?: number
}

export async function modifyChunk(chunkId: number, newContent: string, reason: string): Promise<{
  success: boolean
  chunk_id: number
  document_id?: number
  old_content?: string
}> {
  const response = await request.post(`/api/kb/chunks/${chunkId}/modify`, {
    new_content: newContent,
    reason: reason,
  })
  return response.data
}

export async function executeSuggestionActions(suggestionId: number, actions: ExecuteAction[]): Promise<{
  executed: number
  failed: number
  results: Array<{ type: string; success: boolean; result?: any; error?: string }>
  verification_triggered: boolean
}> {
  const response = await request.post(`/api/kb/suggestions/${suggestionId}/execute`, { actions })
  return response.data
}
