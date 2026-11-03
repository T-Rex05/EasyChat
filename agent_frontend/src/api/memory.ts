// 记忆管理 API

import request from './request'

export interface MemoryShare {
  id: number
  source: string
  title: string
  content?: string
  status?: string
  reject_reason?: string
  author?: string
  author_id?: number
  created_at?: string
  reviewed_at?: string
}

export interface OwnMemory {
  user: string
  memory: string
  my_shares: MemoryShare[]
  can_manage: boolean
}

export interface MemoryUser {
  user_id: number
  username: string
  has_user: boolean
  has_memory: boolean
}

export async function getOwnMemory(): Promise<OwnMemory> {
  const resp = await request.get<OwnMemory>('/api/memory')
  return resp.data
}

export async function saveUserMd(content: string): Promise<void> {
  await request.put('/api/memory/user', { content })
}

export async function saveMemoryMd(content: string): Promise<void> {
  await request.put('/api/memory/main', { content })
}

export async function shareMemory(source: string, title: string, content: string, category: string = '通用'): Promise<any> {
  const resp = await request.post('/api/memory/share', { source, title, content, category })
  return resp.data
}

export async function getMemoryPool(category?: string): Promise<MemoryShare[]> {
  const resp = await request.get<MemoryShare[]>('/api/memory/pool', { params: { category: category || '' } })
  return resp.data
}

export async function getPoolCategories(): Promise<string[]> {
  const resp = await request.get<string[]>('/api/memory/pool/categories')
  return resp.data
}

export async function getMemoryUsers(): Promise<MemoryUser[]> {
  const resp = await request.get<MemoryUser[]>('/api/memory/users')
  return resp.data
}

export async function getUserMemory(userId: number): Promise<{ user_id: number; user: string; memory: string }> {
  const resp = await request.get(`/api/memory/users/${userId}`)
  return resp.data
}