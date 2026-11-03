// 会话 API：列表/删除/重命名

import request from './request'
import type { ChatSession } from '@/types/chat'

/**
 * 获取用户的会话列表
 */
export async function getUserSessions(
  _userId: string | number,
  offset: number = 0,
  limit: number = 50,
  _sessionType: string = 'conversation'
): Promise<{ sessions: ChatSession[]; has_more: boolean }> {
  const response = await request.get<{ sessions: any[]; offset: number; limit: number }>(
    '/api/history', { params: { offset, limit } },
  )
  const sessions = (response.data.sessions || []).map((s) => ({
    id: s.session_id || s.id || '',
    title: s.title || '',
    source: s.source,
    user_question: s.title || '',
    create_time: s.created_at,
    update_time: s.updated_at,
    is_schedule: 0,
  }))
  return { sessions, has_more: sessions.length >= limit }
}

/**
 * 删除会话
 */
export async function deleteSession(chatId: string): Promise<void> {
  await request.delete(`/api/history/${encodeURIComponent(chatId)}`)
}

/**
 * 重命名会话
 */
export async function renameSession(chatId: string, title: string): Promise<void> {
  await request.put(`/api/history/${encodeURIComponent(chatId)}`, {
    title,
  })
}
