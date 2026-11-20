import type { MemoryRecord } from '@/api/memoryManagement'

export const memoryKinds: Record<string, string> = {
  fact: '事实', event: '事件', preference: '偏好', experience: '经验',
}

export function memoryKindLabel(kind: string): string {
  return memoryKinds[kind] ?? kind
}

export function memoryLocator(value: unknown): string | undefined {
  return typeof value === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(value) ? value : undefined
}

export function memoryVersion(value: unknown): string | undefined {
  return typeof value === 'string' && /^[1-9]\d{0,8}$/.test(value) ? value : undefined
}

export function memoryReturnLocation(value: unknown, revision?: unknown): string | { name: 'Memory'; query: Record<string, string> } {
  const memory = memoryLocator(value)
  if (!memory) return '/chat'
  const version = memoryVersion(revision)
  return { name: 'Memory', query: version ? { memory, version } : { memory } }
}

export function memoryLoginHash(hash: string): string | undefined {
  const [path, query] = hash.split('?')
  if (path !== '#/memory') return undefined
  const params = new URLSearchParams(query)
  const target = memoryReturnLocation(params.get('memory'), params.get('version'))
  return typeof target === 'string' ? '#/login' : '#/login?' + new URLSearchParams(target.query)
}

export function memoryAccess(
  permissions: string[],
  capabilities?: { read: boolean; use: boolean },
  isSuperAdmin = false,
) {
  const view = isSuperAdmin || (permissions.includes('memory.view') && (capabilities?.read ?? true))
  const edit = view && (isSuperAdmin || (permissions.includes('memory.edit') && (capabilities?.use ?? true)))
  return { view, edit }
}

export function matchesMemoryScope(
  record: Pick<MemoryRecord, 'is_shared' | 'persona_id'>,
  scope: string,
): boolean {
  if (scope === 'all') return true
  if (scope === 'shared') return record.is_shared === true
  if (record.is_shared) return false
  return scope === 'default' ? !record.persona_id : record.persona_id === scope
}

export function groupMemories<T extends Pick<MemoryRecord, 'memory_id' | 'kind' | 'tags'>>(
  items: T[],
  grouping: 'kind' | 'tag',
) {
  const groups = new Map<string, T[]>()
  const sorted = [...items].sort((a, b) => a.memory_id.localeCompare(b.memory_id))
  for (const item of sorted) {
    const tags = item.tags?.length ? [...new Set(item.tags)] : ['未标记']
    const labels = grouping === 'kind' ? [memoryKindLabel(item.kind)] : tags
    for (const label of labels) {
      const members = groups.get(label) ?? []
      members.push(item)
      groups.set(label, members)
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
    .map(([label, items]) => ({ label, items }))
}
