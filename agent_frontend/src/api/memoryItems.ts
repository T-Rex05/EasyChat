// 记忆条目管理 API - 支持两层记忆系统（episodic + semantic）

import request from './request'

// ========== 类型定义 ==========

export interface MemoryItem {
  id: number
  user_id: number
  username?: string
  memory_type: 'preference' | 'fact' | 'event' | 'skill'
  content: string
  importance_score: number
  source_thread_id?: string
  access_count: number
  created_at?: string
  updated_at?: string
  expires_at?: string
  embedding_id?: string
  graph_node_id?: string
}

// 情景记忆（近期记忆）
export interface EpisodicMemory {
  id: number
  user_id: number
  memory_type: 'preference' | 'fact' | 'event' | 'skill'
  content: string
  importance_score: number
  access_count: number
  ttl_days: number
  expires_at?: string
  source_thread_id?: string
  created_at?: string
  updated_at?: string
  embedding_id?: string
}

// 语义记忆（永久知识）
export interface SemanticMemory {
  id: number
  user_id: number
  memory_type: 'preference' | 'fact' | 'event' | 'skill'
  content: string
  importance_score: number
  access_count: number
  source_thread_id?: string
  source_episodic_id?: number  // 从哪条情景记忆晋升而来
  created_at?: string
  updated_at?: string
  embedding_id?: string
  graph_node_id?: string
}

export interface MemoryStats {
  total: number
  by_type: Record<string, number>
}

export interface EpisodicStats {
  total: number
  active: number
  expired: number
  by_type: Record<string, number>
}

export interface SemanticStats {
  total: number
  by_type: Record<string, number>
  from_promotion: number
}

export interface SearchResult {
  memory: MemoryItem
  score: number
}

export interface SearchResponse {
  query: string
  count: number
  results: SearchResult[]
}

export interface GraphRelation {
  memory_id: number
  graph_available: boolean
  related_count: number
  related: MemoryItem[]
}

export interface ConsolidationResult {
  deduped: number
  merged: number
  expired: number
  delete_from_db: number[]
  update_count: number
  remaining: number
}

export interface MemoryUser {
  user_id: number
  username: string
  memory_count: number
}

// ========== Legacy API（保持兼容） ==========

// 获取记忆列表（legacy）
export async function getMemories(
  memoryType?: string,
  limit: number = 50,
  viewAll: boolean = false,
  targetUserId?: number
): Promise<MemoryItem[]> {
  const resp = await request.get<MemoryItem[]>('/api/memories', {
    params: {
      memory_type: memoryType || '',
      limit,
      view_all: viewAll,
      target_user_id: targetUserId
    }
  })
  return resp.data
}

// 获取记忆统计（legacy）
export async function getMemoryStats(
  viewAll: boolean = false,
  targetUserId?: number
): Promise<MemoryStats> {
  const resp = await request.get<MemoryStats>('/api/memories/stats', {
    params: {
      view_all: viewAll,
      target_user_id: targetUserId
    }
  })
  return resp.data
}

// ========== 两层记忆 API ==========

// 获取情景记忆列表（近期记忆）
export async function getEpisodicMemories(
  memoryType?: string,
  includeExpired: boolean = false,
  limit: number = 50
): Promise<EpisodicMemory[]> {
  const resp = await request.get<EpisodicMemory[]>('/api/memories/episodic', {
    params: {
      memory_type: memoryType || '',
      include_expired: includeExpired,
      limit
    }
  })
  return resp.data
}

// 获取语义记忆列表（永久知识）
export async function getSemanticMemories(
  memoryType?: string,
  limit: number = 50
): Promise<SemanticMemory[]> {
  const resp = await request.get<SemanticMemory[]>('/api/memories/semantic', {
    params: {
      memory_type: memoryType || '',
      limit
    }
  })
  return resp.data
}

// 晋升情景记忆为语义记忆
export async function promoteMemory(
  episodicId: number,
  content?: string,
  importance?: number
): Promise<SemanticMemory> {
  const resp = await request.post<SemanticMemory>(`/api/memories/episodic/${episodicId}/promote`, {
    content,
    importance
  })
  return resp.data
}

// 获取情景记忆统计
export async function getEpisodicStats(): Promise<EpisodicStats> {
  const resp = await request.get<EpisodicStats>('/api/memories/episodic/stats')
  return resp.data
}

// 获取语义记忆统计
export async function getSemanticStats(): Promise<SemanticStats> {
  const resp = await request.get<SemanticStats>('/api/memories/semantic/stats')
  return resp.data
}

// ========== Legacy API（其他） ==========

// 获取有记忆的用户列表（管理员用）
export async function getMemoryUsers(): Promise<{ users: MemoryUser[] }> {
  const resp = await request.get<{ users: MemoryUser[] }>('/api/memories/users')
  return resp.data
}

// 获取单个记忆
export async function getMemory(id: number): Promise<MemoryItem> {
  const resp = await request.get<MemoryItem>(`/api/memories/${id}`)
  return resp.data
}

// 创建记忆
export async function createMemory(
  memoryType: string,
  content: string,
  importance: number = 0.5
): Promise<MemoryItem> {
  const resp = await request.post<MemoryItem>('/api/memories', {
    memory_type: memoryType,
    content,
    importance
  })
  return resp.data
}

// 更新记忆
export async function updateMemory(
  id: number,
  content?: string,
  importance?: number
): Promise<MemoryItem> {
  const resp = await request.put<MemoryItem>(`/api/memories/${id}`, {
    content,
    importance
  })
  return resp.data
}

// 删除记忆
export async function deleteMemory(id: number): Promise<void> {
  await request.delete(`/api/memories/${id}`)
}

// 搜索记忆
export async function searchMemories(
  query: string,
  memoryType?: string,
  topK: number = 10
): Promise<SearchResponse> {
  const resp = await request.post<SearchResponse>('/api/memories/search', {
    query,
    memory_type: memoryType,
    top_k: topK
  })
  return resp.data
}

// 获取图关联
export async function getMemoryGraph(
  memoryId: number,
  maxHops: number = 2
): Promise<GraphRelation> {
  const resp = await request.get<GraphRelation>(`/api/memories/${memoryId}/graph`, {
    params: { max_hops: maxHops }
  })
  return resp.data
}

// 触发记忆合并
export async function triggerConsolidation(): Promise<{
  message: string
  result: ConsolidationResult | null
}> {
  const resp = await request.post('/api/memories/consolidate')
  return resp.data
}

// ========== 版本历史 API ==========

// 记忆版本
export interface MemoryVersion {
  id: number
  memory_id: number
  version: number
  content: string
  importance_score: number
  memory_type?: string
  change_reason: string
  source_memory_id?: number
  created_at?: string
}

// 版本历史响应
export interface VersionHistory {
  memory_id: number
  current_content: string
  current_importance: number
  versions: MemoryVersion[]
  total_versions: number
}

// 获取版本历史
export async function getMemoryVersions(
  memoryId: number,
  limit: number = 50
): Promise<VersionHistory> {
  const resp = await request.get<VersionHistory>(`/api/memories/${memoryId}/versions`, {
    params: { limit }
  })
  return resp.data
}

// 获取特定版本
export async function getMemoryVersion(
  memoryId: number,
  version: number
): Promise<MemoryVersion> {
  const resp = await request.get<MemoryVersion>(`/api/memories/${memoryId}/versions/${version}`)
  return resp.data
}

// 恢复到指定版本
export async function restoreMemoryVersion(
  memoryId: number,
  version: number
): Promise<MemoryItem> {
  const resp = await request.post<MemoryItem>(`/api/memories/${memoryId}/restore/${version}`)
  return resp.data
}

// ========== 常量 ==========

// 记忆看板数据类型
export interface MemoryDashboard {
  memory_counts: {
    legacy: { total: number; active: number; deleted: number }
    episodic: { total: number; active: number; expired: number; deleted: number }
    semantic: { total: number; active: number; deleted: number }
    grand_total: number
  }
  consolidation_stats: {
    total_versions: number
    by_change_reason: Record<string, number>
    by_consolidation_type: Record<string, number>
  }
  outbox_health: {
    by_status: Record<string, number>
    by_layer: Record<string, Record<string, number>>
    pending: number
    processing: number
    processed: number
    dead: number
    /** @deprecated 兼容旧字段，等同 processed */
    completed?: number
    /** @deprecated 兼容旧字段，等同 dead */
    failed?: number
  }
  vector_coverage: Record<string, { total: number; vectorized: number; coverage: number }>
  graph_coverage: Record<string, { total: number; graphed: number; coverage: number }>
  kg_store_stats?: {
    available: boolean
    entity_count: number
    relation_count: number
    quality: { avg_confidence?: number; low_confidence_count?: number; orphan_entity_count?: number }
    confidence_distribution: Record<string, number>
    conflicts: { type: string; person: string; companies: string[] }[]
    archive: { archived_count?: number }
    error?: string
  }
  encryption_stats: Record<string, { total: number; encrypted: number; plaintext: number; coverage: number }>
  version_stats: {
    memories_with_versions: number
    avg_versions_per_memory: number
    last_7_days_trend: { date: string; count: number }[]
  }
  ttl_expiry: {
    within_1_day: number
    within_7_days: number
    within_30_days: number
    after_30_days: number
  }
}

// 获取记忆监控看板数据
export async function getMemoryDashboard(): Promise<MemoryDashboard> {
  const resp = await request.get<MemoryDashboard>('/api/memories/dashboard')
  return resp.data
}

// 记忆类型标签映射
export const MEMORY_TYPE_LABELS: Record<string, string> = {
  preference: '偏好',
  fact: '事实',
  event: '事件',
  skill: '技能'
}

// 记忆类型颜色映射
export const MEMORY_TYPE_COLORS: Record<string, string> = {
  preference: '#9c27b0',
  fact: '#2196f3',
  event: '#ff9800',
  skill: '#4caf50'
}


// ========== Outbox 死信队列 ==========

export interface OutboxEvent {
  id: number
  event_id: string
  memory_id: number
  memory_version: number
  event_type: string
  target: string
  payload: Record<string, any> | null
  status: string
  attempts: number
  last_error: string | null
  memory_layer: string
  available_at: string | null
  locked_at: string | null
  locked_by: string | null
  processed_at: string | null
  created_at: string
}

export interface OutboxListResponse {
  total: number
  limit: number
  offset: number
  events: OutboxEvent[]
}

/**
 * 查询 Outbox 事件列表（默认查死信）
 */
export async function listOutboxEvents(params: {
  status?: string
  target?: string
  event_type?: string
  limit?: number
  offset?: number
}): Promise<OutboxListResponse> {
  const resp = await request.get<OutboxListResponse>('/api/memories/outbox/list', { params })
  return resp.data
}

/**
 * 重试死信事件
 */
export async function retryOutboxEvents(params: {
  event_ids?: number[]
  retry_all?: boolean
}): Promise<{ ok: boolean; retried: number }> {
  const resp = await request.post('/api/memories/outbox/retry', null, { params })
  return resp.data
}
