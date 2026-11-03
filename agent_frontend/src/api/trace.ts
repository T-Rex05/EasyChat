// 可观测性 API

import request from './request'

// ── 类型定义 ──

export interface TraceSummary {
  total_traces: number
  total_tokens: number
  avg_latency_ms: number
  success_rate: number
}

export interface DailyTrend {
  date: string
  tokens: number
  traces: number
}

export interface ModelUsage {
  model: string
  traces: number
  tokens: number
}

export interface SourceDistribution {
  source: string
  traces: number
  percentage: number
}

export interface ToolUsage {
  tool: string
  calls: number
  avg_duration_ms: number
}

export interface DashboardStats {
  summary: TraceSummary
  daily_trend: DailyTrend[]
  model_usage: ModelUsage[]
  source_distribution: SourceDistribution[]
  tool_usage: ToolUsage[]
}

export interface TraceItem {
  id: number
  session_id: string
  user_id: number
  username?: string
  source: string
  model: string
  provider: string
  turn_index: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  total_tokens: number
  latency_ms: number
  estimated_cost_usd: number
  finish_reason: string
  api_call_count: number
  status: number
  error_message: string
  span_count: number
  created_at: string
  // 按会话聚合（turns）时附加
  api_calls?: number
  total_latency_ms?: number
  started_at?: string
  ended_at?: string
  user_question?: string
  ai_reply?: string
}

export interface TraceSpan {
  id: number
  trace_id: number
  span_type: string
  tool_name: string
  duration_ms: number
  status: number
  error_message: string
  created_at: string
  // 聚合后的字段（按工具名合并）
  calls?: number
  total_duration_ms?: number
  avg_duration_ms?: number
  first_at?: string
  last_at?: string
}

/** turn_detail 的 qna_list 元素（conversations 表问答轮次） */
export interface TraceTurnQna {
  question: string
  reply: string
  created_at: string
}

/** turn_detail 的 traces（有内容回复的子 trace） */
export interface TraceTurnSubTrace {
  id: number
  turn_index: number
  model: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  latency_ms: number
  finish_reason: string
  api_call_count: number
  status: number
  prompt_text: string
  completion_text: string
  created_at: string
}

export interface TraceDetail extends TraceItem {
  prompt_text?: string
  completion_text?: string
  spans: TraceSpan[]
  // turn_detail（/api/traces/turns/{session_id}）附加字段
  total_latency_ms?: number
  qna_list?: TraceTurnQna[]
  traces?: TraceTurnSubTrace[]
}

export interface TraceConfig {
  trace_detail_enabled: boolean
  trace_max_text_chars: number
  trace_retention_days: number
}

// ── API 函数 ──

export async function getDashboardStats(days: number = 7): Promise<DashboardStats> {
  const response = await request.get<DashboardStats>('/api/traces/dashboard', {
    params: { days },
  })
  return response.data
}

export async function getTraces(params: {
  session_id?: string
  model?: string
  source?: string
  status?: number
  days?: number
  offset?: number
  limit?: number
}): Promise<{ turns: TraceItem[]; total: number; has_more: boolean }> {
  const response = await request.get('/api/traces', { params })
  return response.data
}

export async function getAllTraces(params: {
  user_id?: number
  username?: string
  session_id?: string
  model?: string
  source?: string
  status?: number
  days?: number
  when?: string
  aggregated?: number
  offset?: number
  limit?: number
}): Promise<{ turns: TraceItem[]; traces: TraceItem[]; total: number; has_more: boolean }> {
  const response = await request.get('/api/traces/all', { params })
  return response.data
}

export interface UserRanking {
  rank: number
  user_id: number
  username: string
  total_tokens: number
  api_calls: number
  active_days: number
}

export async function getRanking(days: number = 7, limit: number = 20): Promise<{ ranking: UserRanking[]; days: number }> {
  const response = await request.get('/api/traces/ranking', { params: { days, limit } })
  return response.data
}

/** @deprecated Use {@link getRanking} instead */
export const getUserRanking = getRanking

export async function searchUsers(q: string, limit: number = 10): Promise<{ id: number; username: string }[]> {
  const response = await request.get('/api/traces/users/search', { params: { q, limit } })
  return response.data
}

export async function getTraceDetail(traceId: number): Promise<TraceDetail> {
  const response = await request.get<TraceDetail>(`/api/traces/${traceId}`)
  return response.data
}

export async function getTurnDetail(sessionId: string): Promise<TraceDetail> {
  const response = await request.get<TraceDetail>(`/api/traces/turns/${encodeURIComponent(sessionId)}`)
  return response.data
}

export async function getTraceConfig(): Promise<TraceConfig> {
  const response = await request.get<TraceConfig>('/api/traces/config/me')
  return response.data
}

export async function updateTraceConfig(config: Partial<TraceConfig>): Promise<void> {
  await request.put('/api/traces/config', config)
}
