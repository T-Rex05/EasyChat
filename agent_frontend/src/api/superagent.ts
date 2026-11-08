// 超级代理 API（对接 backend/modules/superagent；T6 工作台契约）
import request from './request'

export interface SuperagentCapabilities {
  view: boolean
  create: boolean
  cancel: boolean
  manage: boolean
  enabled: boolean
  configured: boolean
  credentials_ready: boolean
  runner_ready: boolean
  reasons: string[]
  repo_url: string
}

export interface SuperagentSettings {
  enabled: boolean
  repo_url: string
  base_branch: string
  github_token_mask: string
  has_github_token: boolean
  pr_labels: string
  max_concurrent: number
  verify_profile: string
  allow_unverified_draft: boolean
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
  phase: string
  branch: string
  repo_url: string
  base_branch: string
  pr_url: string
  pr_number: number
  pr_state: string
  outcome: string
  result_summary: string
  error: string
  attempts: number
  active_attempt_id: string
  cancel_requested: boolean
  legacy_config_unknown: boolean
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

export interface SuperagentReport {
  report_id: string
  kind: string
  summary: string
  question: string
  head_sha: string
  verification_ref: string
  created_at: string
}

export interface TaskPage {
  tasks: SuperagentTask[]
  next_cursor: string
}

export async function getSuperagentCapabilities(): Promise<SuperagentCapabilities> {
  const res = await request.get<{ capabilities: SuperagentCapabilities }>('/api/superagent/capabilities')
  return res.data.capabilities
}

export async function getSuperagentSettings(): Promise<SuperagentSettings> {
  const res = await request.get<{ settings: SuperagentSettings }>('/api/superagent/settings')
  return res.data.settings
}

export async function updateSuperagentSettings(
  data: Partial<{
    enabled: boolean; repo_url: string; base_branch: string; github_token: string
    pr_labels: string; max_concurrent: number; verify_profile: string; allow_unverified_draft: boolean
  }>,
): Promise<SuperagentSettings> {
  const res = await request.put<{ settings: SuperagentSettings }>('/api/superagent/settings', data)
  return res.data.settings
}

export async function listSuperagentTasks(params?: {
  limit?: number; cursor?: string; status?: string
}): Promise<TaskPage> {
  const res = await request.get<TaskPage>('/api/superagent/tasks', { params })
  return res.data
}

export async function createSuperagentTask(
  title: string, requirement: string, contextExtra = '', idempotencyKey?: string,
): Promise<SuperagentTask> {
  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  const res = await request.post<{ task: SuperagentTask }>(
    '/api/superagent/tasks',
    { title, requirement, context_extra: contextExtra },
    { headers },
  )
  return res.data.task
}

export async function appendSuperagentTaskInput(
  taskId: string, text: string, idempotencyKey?: string,
): Promise<void> {
  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
  await request.post(`/api/superagent/tasks/${taskId}/inputs`, { text }, { headers })
}

export async function cancelSuperagentTask(taskId: string): Promise<SuperagentTask> {
  const res = await request.post<{ task: SuperagentTask }>(`/api/superagent/tasks/${taskId}/cancel`)
  return res.data.task
}

export async function retrySuperagentTask(taskId: string): Promise<SuperagentTask> {
  const res = await request.post<{ task: SuperagentTask }>(`/api/superagent/tasks/${taskId}/retry`)
  return res.data.task
}

export async function listSuperagentEvents(taskId: string, afterId = 0): Promise<{
  events: SuperagentEvent[]
  next_after_id: number
}> {
  const res = await request.get<{ events: SuperagentEvent[]; next_after_id: number }>(
    `/api/superagent/tasks/${taskId}/events`, { params: { after_id: afterId } },
  )
  return res.data
}

export async function listSuperagentReports(taskId: string): Promise<SuperagentReport[]> {
  const res = await request.get<{ reports: SuperagentReport[] }>(`/api/superagent/tasks/${taskId}/reports`)
  return res.data.reports || []
}

export interface SuperagentOpsMetrics {
  tasks_by_status: Record<string, number>
  attempts: { total: number; succeeded: number; failed: number; avg_duration_seconds: number }
  verification: { total: number; blocked: number; allow_unverified_draft: boolean; verify_commands: number }
  deliveries_by_status: Record<string, number>
  webhook_pending: number
  runner_ready: boolean
  credentials_ready: boolean
  enabled: boolean
}

export async function getSuperagentOpsMetrics(): Promise<SuperagentOpsMetrics> {
  const res = await request.get<{ metrics: SuperagentOpsMetrics }>('/api/superagent/ops/metrics')
  return res.data.metrics
}
