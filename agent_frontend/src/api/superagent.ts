// 超级代理 API（对接 backend/modules/superagent）
import request from './request'

export interface SuperagentSettings {
  enabled: boolean
  repo_url: string
  base_branch: string
  github_token_mask: string
  has_github_token: boolean
  pr_labels: string
  max_concurrent: number
  updated_at: string
}

export interface SuperagentTask {
  task_id: string
  owner_id: number
  title: string
  requirement: string
  context_extra: string
  source: string
  status: string
  branch: string
  pr_url: string
  pr_number: number
  result_summary: string
  error: string
  attempts: number
  created_at: string
  updated_at: string
  started_at: string
  finished_at: string
}

export interface SuperagentEvent {
  event_id: number
  kind: string
  detail: string
  created_at: string
}

export async function getSuperagentSettings(): Promise<SuperagentSettings> {
  const res = await request.get<{ settings: SuperagentSettings }>('/api/superagent/settings')
  return res.data.settings
}

export async function updateSuperagentSettings(
  data: Partial<{ enabled: boolean; repo_url: string; base_branch: string; github_token: string; pr_labels: string; max_concurrent: number }>,
): Promise<SuperagentSettings> {
  const res = await request.put<{ settings: SuperagentSettings }>('/api/superagent/settings', data)
  return res.data.settings
}

export async function listSuperagentTasks(limit = 50): Promise<SuperagentTask[]> {
  const res = await request.get<{ tasks: SuperagentTask[] }>('/api/superagent/tasks', { params: { limit } })
  return res.data.tasks || []
}

export async function createSuperagentTask(title: string, requirement: string, contextExtra = ''): Promise<SuperagentTask> {
  const res = await request.post<{ task: SuperagentTask }>('/api/superagent/tasks', {
    title,
    requirement,
    context_extra: contextExtra,
  })
  return res.data.task
}

export async function cancelSuperagentTask(taskId: string): Promise<SuperagentTask> {
  const res = await request.post<{ task: SuperagentTask }>(`/api/superagent/tasks/${taskId}/cancel`)
  return res.data.task
}

export async function retrySuperagentTask(taskId: string): Promise<SuperagentTask> {
  const res = await request.post<{ task: SuperagentTask }>(`/api/superagent/tasks/${taskId}/retry`)
  return res.data.task
}

export async function listSuperagentEvents(taskId: string): Promise<SuperagentEvent[]> {
  const res = await request.get<{ events: SuperagentEvent[] }>(`/api/superagent/tasks/${taskId}/events`)
  return res.data.events || []
}
