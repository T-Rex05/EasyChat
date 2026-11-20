import request from './request'

export interface MemorySource {
  kind: string
  ref: string
  quote?: string
  created_at?: string
}

export interface MemoryRecord {
  memory_id: string
  kind: string
  content: string
  source_refs: MemorySource[]
  status: string
  version: number
  pinned: boolean
  recorded_at: string
  tags: string[]
  persona_id?: string | null
  is_shared?: boolean
  supersedes?: string | null
}

export interface MemoryRevision {
  version: number
  content: string
  reason: string
  created_at: string
  source_refs: MemorySource[]
}

export interface RunMemory {
  recorded: boolean
  items: {
    memory_id: string
    version: number
    current_version: number
    kind: string
    summary: string
  }[]
}

const memoryPath = (id: string) => `/api/memory/${encodeURIComponent(id)}`

export async function listMemories(params: { persona_id?: string; query?: string; include_archived: boolean; limit: number }) {
  const { data } = await request.get<{ memories: MemoryRecord[] }>('/api/memory', { params })
  return data.memories
}

export async function recallMemories(query: string, personaId?: string) {
  const { data } = await request.post<{ items: { memory: MemoryRecord }[] }>('/api/memory/recall', {
    query, persona_id: personaId, top_k: 20, budget: 2000,
  })
  return data.items.map(item => item.memory)
}

export async function getMemory(id: string) {
  const { data } = await request.get<{ memory: MemoryRecord }>(memoryPath(id))
  return data.memory
}

export async function getMemoryRevisions(id: string, offset = 0) {
  const { data } = await request.get<{ revisions: MemoryRevision[] }>(`${memoryPath(id)}/revisions`, {
    params: { limit: 50, offset },
  })
  return data.revisions
}

export async function rememberMemory(body: {
  kind: string; content: string; source_refs: MemorySource[]
  pinned: boolean; persona_id?: string; is_shared: boolean
}) {
  await request.post('/api/memory/remember', { ...body, source_type: 'user_confirmed' })
}

export async function reviseMemory(id: string, expected_version: number, content: string) {
  const { data } = await request.put<{ memory: MemoryRecord }>(memoryPath(id), {
    expected_version, content, reason: 'user revision',
  })
  return data.memory
}

export async function setMemorySharing(id: string, is_shared: boolean) {
  const { data } = await request.patch<{ memory: MemoryRecord }>(`${memoryPath(id)}/sharing`, { is_shared })
  return data.memory
}

export async function forgetMemory(id: string) {
  await request.post('/api/memory/forget', { memory_id: id, reason: 'user forget' })
}

export async function getRunMemory(runId: string) {
  const { data } = await request.get<RunMemory>(`/api/assistant/runs/${encodeURIComponent(runId)}/memory`)
  return data
}
