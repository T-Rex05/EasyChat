// 系统配置 API

import request from './request'

export interface ModelConfig {
  id: number
  user_id?: number
  config_name: string
  config_type: string
  api_url: string
  api_key: string
  model_name: string
  provider: string
  category: string            // chat（聊天模型）| embedding（Embedding 模型）
  is_multimodal: number | boolean
  is_current: number | boolean
  enabled: number | boolean
  reasoning_effort?: string   // 推理深度: low/medium/high/max/ultra（仅 chat 分类）
  dimension?: number          // Embedding 向量维度（0=模型默认值）
  send_dimensions?: number    // 是否在 API 请求中发送 dimensions 参数
  cost_per_1k_input?: number  // 每1000输入token成本(USD)
  cost_per_1k_output?: number // 每1000输出token成本(USD)
  context_length?: number     // 模型上下文窗口大小
  capabilities?: Record<string, boolean> // 模型能力标签
  description?: string        // 模型描述
  circuit_state?: number      // 熔断状态（0=closed, 1=open, 2=half_open）
  created_at?: string
  updated_at?: string
}

/** 获取模型配置列表 */
export async function getModelConfigs(): Promise<{ configs: ModelConfig[]; env_configured: boolean; categories?: Record<string, string> }> {
  const res = await request.get('/api/model-configs')
  return res.data
}

/** 新增模型配置（保存后自动激活，按分类各自激活） */
export async function createModelConfig(data: {
  config_name: string
  config_type: string
  api_url: string
  api_key: string
  model_name: string
  provider?: string
  category?: string
  is_multimodal?: number
  reasoning_effort?: string
  dimension?: number
  send_dimensions?: number
  cost_per_1k_input?: number
  cost_per_1k_output?: number
  context_length?: number
  capabilities?: Record<string, boolean>
  description?: string
}): Promise<{ ok: boolean; id: number }> {
  const res = await request.post('/api/model-configs', data)
  return res.data
}

/** 设为当前激活 */
export async function setActiveModelConfig(id: number): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/model-configs/${id}/active`)
  return res.data
}

/** 删除配置 */
export async function deleteModelConfig(id: number): Promise<{ ok: boolean }> {
  const res = await request.delete(`/api/model-configs/${id}`)
  return res.data
}

/** 编辑已有配置（api_key 留空则保持原密钥） */
export async function updateModelConfig(
  id: number,
  data: {
    config_name: string
    config_type: string
    api_url: string
    api_key: string
    model_name: string
    provider?: string
    category?: string
    is_multimodal?: number
    reasoning_effort?: string
    dimension?: number
    send_dimensions?: number
    cost_per_1k_input?: number
    cost_per_1k_output?: number
    context_length?: number
    capabilities?: Record<string, boolean>
    description?: string
  },
): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/model-configs/${id}`, data)
  return res.data
}

export interface TestResult {
  ok: boolean
  status_code?: number
  latency_ms?: number
  models?: string[]
  is_multimodal?: boolean
  probe_multimodal?: boolean | null
  probe_message?: string
  message: string
}

/** 测试模型连接性 — 发 GET /v1/models */
export async function testModelConfig(id: number): Promise<TestResult> {
  const res = await request.post(`/api/model-configs/${id}/test`)
  return res.data
}

/** 测试 SMTP 连接 — 发一封测试邮件到指定收件人 */
export async function testSmtpConnection(data: {
  host: string; port: string; sender_email: string; sender_name: string; password: string; to_email?: string
}): Promise<{ ok: boolean; message: string }> {
  const res = await request.post('/api/platform-config/email/test', data)
  return res.data
}

// ── 邮箱多配置 API ──

export interface EmailConfig {
  id: number
  config_name: string
  host: string
  port: string
  sender_email: string
  sender_name: string
  password: string
  is_current: number | boolean
  enabled: number | boolean
  created_at?: string
  updated_at?: string
}

export async function getEmailConfigs(): Promise<{ configs: EmailConfig[] }> {
  const res = await request.get('/api/email-configs')
  return res.data
}

export async function createEmailConfig(data: {
  config_name: string; host: string; port: string; sender_email: string; sender_name: string; password: string
}): Promise<{ ok: boolean; id: number }> {
  const res = await request.post('/api/email-configs', data)
  return res.data
}

export async function updateEmailConfig(id: number, data: {
  config_name?: string; host?: string; port?: string; sender_email?: string; sender_name?: string; password?: string
}): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/email-configs/${id}`, data)
  return res.data
}

export async function setActiveEmailConfig(id: number): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/email-configs/${id}/active`)
  return res.data
}

export async function deleteEmailConfig(id: number): Promise<{ ok: boolean }> {
  const res = await request.delete(`/api/email-configs/${id}`)
  return res.data
}

export async function testEmailConfig(id: number): Promise<{ ok: boolean; message: string }> {
  const res = await request.post(`/api/email-configs/${id}/test`)
  return res.data
}

// ── 个人邮箱 API ──

export interface PersonalEmail {
  id: number
  email: string
  is_current: number | boolean
  created_at?: string
}

export async function getPersonalEmails(): Promise<{ emails: PersonalEmail[] }> {
  const res = await request.get('/api/personal-emails')
  return res.data
}

export async function addPersonalEmail(email: string): Promise<{ ok: boolean; id: number; duplicate?: boolean }> {
  const res = await request.post('/api/personal-emails', { email })
  return res.data
}

export async function setActivePersonalEmail(id: number): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/personal-emails/${id}/active`)
  return res.data
}

/** 手动切换模型多模态标记 */
export async function toggleMultimodal(id: number): Promise<{ ok: boolean; is_multimodal: boolean }> {
  const res = await request.put(`/api/model-configs/${id}/multimodal`)
  return res.data
}

export async function deletePersonalEmail(id: number): Promise<{ ok: boolean }> {
  const res = await request.delete(`/api/personal-emails/${id}`)
  return res.data
}

// ── 模型路由规则 API ──

export interface FallbackChainItem extends ModelConfig {
  circuit_state?: number
}

/** 获取降级链配置 */
export async function getFallbackChain(): Promise<{ ok: boolean; fallback_chain: FallbackChainItem[] }> {
  const res = await request.get('/api/model-routes/fallback-chain')
  return res.data
}

/** 更新降级链 */
export async function saveFallbackChain(modelIds: number[]): Promise<{ ok: boolean }> {
  const res = await request.put('/api/model-routes/fallback-chain', { model_ids: modelIds })
  return res.data
}

export interface SceneRoutingItem {
  model_config_id: number
  config_name?: string
  model_name?: string
}

/** 获取场景路由配置 */
export async function getSceneRouting(): Promise<{ ok: boolean; routing: Record<string, SceneRoutingItem> }> {
  const res = await request.get('/api/model-routes/scene-routing')
  return res.data
}

/** 更新场景路由 */
export async function saveSceneRouting(routing: Record<string, number>): Promise<{ ok: boolean }> {
  const res = await request.put('/api/model-routes/scene-routing', { routing })
  return res.data
}

/** 测试/预览路由结果 */
export async function evaluateRoute(scene?: string, category?: string): Promise<{
  ok: boolean
  scene: string
  selected_model: { id: number; model_name: string; config_name: string } | null
  route_path: string
  fallback_chain: number[]
  scene_routing: Record<string, number>
}> {
  const params = new URLSearchParams()
  if (scene) params.set('scene', scene)
  if (category) params.set('category', category)
  const res = await request.post(`/api/model-routes/evaluate?${params.toString()}`)
  return res.data
}

// ── 场景注册表 API ──

export interface SceneDefinition {
  key: string
  name: string
  category: string
  description: string
  recommended_model: string
  is_builtin: boolean
}

export interface SceneCategory {
  name: string
  icon: string
  order: number
}

/** 获取所有可用的 LLM 使用场景（供配置场景路由时选择） */
export async function getAvailableScenes(): Promise<{
  ok: boolean
  categories: Record<string, SceneCategory>
  scenes: SceneDefinition[]
}> {
  const res = await request.get('/api/model-routes/scenes')
  return res.data
}
