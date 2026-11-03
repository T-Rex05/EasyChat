// 定时任务 API
import request from './request'

export interface CronJob {
  id: number
  user_id: number
  name: string
  prompt: string
  schedule_type: string  // once / daily / cron / interval
  schedule_value: string // 如 "0 9 * * *", "30m", "09:00", "2026-08-10 09:00"
  deliver_to: string     // wechat / email / both
  report_format: string  // pdf / text / markdown
  email_sender_id?: number | null
  email_receiver_id?: number | null
  enabled: boolean
  last_run_at?: string
  next_run_at?: string
  last_exec_status?: number | null  // 最近一次执行状态：1=成功 2=失败 0=执行中 -1=从未执行
  created_at: string
  updated_at: string
}

export interface CronExecution {
  id: number
  job_id: number
  session_id: string
  status: number        // 0=执行中 1=成功 2=失败
  result_text: string
  error_message: string
  deliver_status: string
  started_at: string
  finished_at?: string
}

export interface CronJobCreate {
  user_id: number
  name: string
  prompt: string
  schedule_type: string
  schedule_value: string
  deliver_to: string
  report_format?: string
  email_sender_id?: number | null
  email_receiver_id?: number | null
}

export interface CronJobUpdate {
  name?: string
  prompt?: string
  schedule_type?: string
  schedule_value?: string
  deliver_to?: string
  report_format?: string
  email_sender_id?: number | null
  email_receiver_id?: number | null
}

/** 获取定时任务列表 */
export async function getCronJobs(userId: number): Promise<{ success: boolean; jobs: CronJob[]; count: number }> {
  const response = await request.get('/api/cron-jobs', { params: { user_id: userId } })
  return response.data
}

/** 创建定时任务 */
export async function createCronJob(data: CronJobCreate): Promise<{ success: boolean; job_id: number; message: string }> {
  const response = await request.post('/api/cron-jobs', data)
  return response.data
}

/** 更新定时任务 */
export async function updateCronJob(jobId: number, data: CronJobUpdate, userId: number): Promise<{ success: boolean; message: string }> {
  const response = await request.put(`/api/cron-jobs/${jobId}`, data, { params: { user_id: userId } })
  return response.data
}

/** 删除定时任务 */
export async function deleteCronJob(jobId: number, userId: number): Promise<{ success: boolean; message: string }> {
  const response = await request.delete(`/api/cron-jobs/${jobId}`, { params: { user_id: userId } })
  return response.data
}

/** 启用/禁用定时任务 */
export async function toggleCronJob(jobId: number): Promise<{ success: boolean; enabled: boolean; message: string }> {
  const response = await request.put(`/api/cron-jobs/${jobId}/toggle`)
  return response.data
}

/** 立即执行定时任务 */
export async function runCronJobNow(jobId: number): Promise<{ success: boolean; message: string }> {
  const response = await request.post(`/api/cron-jobs/${jobId}/run-now`)
  return response.data
}

/** 获取执行历史 */
export async function getCronExecutions(jobId: number, limit = 20): Promise<{ success: boolean; executions: CronExecution[]; count: number }> {
  const response = await request.get(`/api/cron-jobs/${jobId}/executions`, { params: { limit } })
  return response.data
}

/** 投递选项 */
export interface DeliveryOptions {
  wechat_binding: { open_id: string; nickname: string } | null
  email_senders: { id: number; name: string; email: string; sender_name: string; is_current: boolean }[]
  email_receivers: { id: number; email: string; is_current: boolean }[]
}

/** 获取用户投递选项 */
export async function getDeliveryOptions(userId: number): Promise<{ success: boolean; data: DeliveryOptions }> {
  const response = await request.get('/api/cron-jobs/delivery-options', { params: { user_id: userId } })
  return response.data
}
