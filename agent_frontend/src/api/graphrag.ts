// GraphRAG 社区管理 API

import request from './request'

export interface Community {
  id: string
  level: number
  parent_id: string | null
  entity_count: number
  relationship_count: number
  entity_ids: string[]
}

export interface CommunityReport {
  community_id: string
  level: number
  title: string
  summary: string
  rating: number
  findings: string[]
  top_entities: string[]
}

export interface CommunityReportDetail extends CommunityReport {
  full_content: string
  status: string
  entity_count: number
  relationship_count: number
}

export interface SmartSearchResult {
  query_type: string
  answer?: string
  results?: any[]
  sources: string[]
  context?: string
  reports_used?: number
}

/** 执行社区检测 */
export function detectCommunities() {
  return request.post('/api/graph/communities/detect')
}

/** 生成社区报告 */
export function generateReports(level?: number | null) {
  return request.post('/api/graph/communities/generate-reports', { level: level ?? null })
}

/** 查询报告生成进度 */
export function getReportProgress(taskId: string) {
  return request.get(`/api/graph/communities/report-progress/${taskId}`)
}

/** 获取社区列表 */
export function listCommunities(level?: number | null) {
  const params: any = {}
  if (level !== null && level !== undefined) params.level = level
  return request.get('/api/graph/communities', { params })
}

/** 获取社区报告列表 */
export function listReports(level?: number | null, limit = 100) {
  const params: any = { limit }
  if (level !== null && level !== undefined) params.level = level
  return request.get('/api/graph/communities/reports', { params })
}

/** 获取单个社区报告详情 */
export function getReportDetail(communityId: string) {
  return request.get(`/api/graph/communities/${communityId}/report`)
}

/** 智能检索 */
export function smartSearch(query: string, mode = 'smart', top_k = 5) {
  return request.post('/api/graph/smart-search', { query, mode, top_k })
}
