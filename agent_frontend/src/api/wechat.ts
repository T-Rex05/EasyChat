// 微信 A+C：人格/情绪/收件箱 API（展示服务端结果，不在前端算分）
import request from './request'

export interface AssistantProfile {
  owner_id: number
  persona_preset: string
  address_form: string
  max_chars: number
  emoji_level: string
  proactivity: string
  quiet_start: string
  quiet_end: string
  timezone: string
  custom_instruction: string
  mood_opt_in: boolean
  mood_retention_days: number
  persona_revision: number
}

export interface MoodEntry {
  id: string
  entry_date: string
  score: number
  labels: string[]
  summary: string
}

export interface InboxItem {
  id: string
  kind: string
  title: string
  url: string
  note: string
  summary: string
  tags: string[]
  status: string
  enrich_state: string
  created_at: string
}

export async function getProfile(): Promise<AssistantProfile> {
  const res = await request.get<{ profile: AssistantProfile }>('/api/profile')
  return res.data.profile
}

export async function updateProfile(patch: Partial<AssistantProfile>): Promise<AssistantProfile> {
  const res = await request.patch<{ profile: AssistantProfile }>('/api/profile', patch)
  return res.data.profile
}

export async function listMood(): Promise<MoodEntry[]> {
  const res = await request.get<{ entries: MoodEntry[] }>('/api/profile/mood')
  return res.data.entries || []
}

export async function deleteMood(): Promise<number> {
  const res = await request.delete<{ deleted: number }>('/api/profile/mood', {
    data: { confirm: true },
  })
  return res.data.deleted
}

export async function listInbox(status = '', limit = 30): Promise<InboxItem[]> {
  const res = await request.get<{ items: InboxItem[] }>('/api/inbox', {
    params: { status, limit },
  })
  return res.data.items || []
}

export async function searchInbox(q: string): Promise<InboxItem[]> {
  const res = await request.get<{ items: InboxItem[] }>('/api/inbox/search', { params: { q } })
  return res.data.items || []
}

export async function saveInbox(url: string, note = ''): Promise<InboxItem> {
  const res = await request.post<{ item: InboxItem }>('/api/inbox', { url, note })
  return res.data.item
}

export async function archiveInbox(itemId: string): Promise<InboxItem> {
  const res = await request.post<{ item: InboxItem }>(`/api/inbox/${itemId}/archive`)
  return res.data.item
}

export async function deleteInbox(itemId: string): Promise<void> {
  await request.delete(`/api/inbox/${itemId}`)
}
