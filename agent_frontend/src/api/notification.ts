import request from './request'

/**
 * 获取各类型待审核数量（用于前端红点显示）
 */
export function getPendingCounts(): Promise<{
  skill: number
  memory: number
  suggestion: number
  graphCandidate: number
}> {
  return request.get('/api/notifications/pending-counts')
}
