// 会话 API：列表/删除/重命名

import request from './request'
import type { ChatSession } from '@/types/chat'

/**
 * 获取用户的会话列表
 */
export async function getUserSessions(
  userId: string | number,
  offset: number = 0,
  limit: number = 50,
  sessionType: string = 'conversation'
): Promise<{ sessions: ChatSession[]; has_more: boolean }> {
  const response = await request.get('/api/data/sessions', {
    params: {
      user_id: userId,
      offset,
      limit,
      session_type: sessionType,
    },
  })

  return response.data
}

/**
 * 删除会话
 */
export async function deleteSession(chatId: string): Promise<void> {
  await request.delete(`/api/data/sessions/${encodeURIComponent(chatId)}`)
}

/**
 * 重命名会话
 */
export async function renameSession(chatId: string, title: string): Promise<void> {
  await request.put(`/api/history/${encodeURIComponent(chatId)}`, {
    title,
  })
}
