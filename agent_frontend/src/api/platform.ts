// 平台配置 & 用户绑定 API（对接新 channels 模块）
import request from './request'

export interface PlatformConfig {
  platform: string
  config_json: Record<string, any>
  raw_config_json?: Record<string, any>
  enabled: boolean
  configured: boolean
  updated_at?: string
}

export async function getPlatformConfig(platform: string): Promise<PlatformConfig> {
  const res = await request.get<{ accounts: any[] }>('/api/channels/accounts')
  const account = (res.data.accounts || []).find((a) => a.platform === platform)
  return {
    platform,
    config_json: {},
    raw_config_json: account
      ? { account_id: account.account_id, bot_user_id: account.bot_user_id || '' }
      : {},
    enabled: account ? account.status === 'active' : false,
    configured: Boolean(account),
    updated_at: account?.updated_at,
  }
}

export async function savePlatformConfig(
  platform: string,
  data: { config_json: Record<string, any>; enabled: boolean },
): Promise<{ ok: boolean; id: string }> {
  const cfg = data.config_json || {}
  const res = await request.post<{ account: { id: string } }>('/api/channels/accounts', {
    platform,
    account_id: String(cfg.account_id || '').trim(),
    token: String(cfg.token || '').trim(),
    base_url: String(cfg.base_url || '').trim(),
    bot_user_id: String(cfg.bot_user_id || ''),
    display_name: String(cfg.nickname || ''),
  })
  return { ok: true, id: res.data.account.id }
}

export interface WechatListener {
  status: string
  last_error?: string
}

export async function startWechatListener(accountPk: string): Promise<WechatListener> {
  const res = await request.post<{ listener: WechatListener }>(
    `/api/channels/accounts/${encodeURIComponent(accountPk)}/start`,
  )
  return res.data.listener
}

export async function getPlatformBindings(platform: string): Promise<{ bindings: any[] }> {
  const res = await request.get<{ bindings: any[] }>('/api/channels/bindings')
  return { bindings: (res.data.bindings || []).filter((b) => b.platform === platform) }
}

export interface QrStartResult {
  session_id: string
  qr_image: string
  qr_scan_data: string
  status: string
}

export interface QrStatusResult {
  status: string
  qr_image?: string
  qr_scan_data?: string
  credentials?: Record<string, string>
  error?: string
}

export async function startWechatQr(): Promise<QrStartResult> {
  const res = await request.post<{ qr: any }>('/api/channels/wechat/qr/start')
  const qr = res.data.qr
  return {
    session_id: qr.session_id,
    qr_image: qr.qr_image,
    qr_scan_data: qr.qr_content || '',
    status: qr.status,
  }
}

export async function checkWechatQrStatus(sessionId: string): Promise<QrStatusResult> {
  const res = await request.get<{ qr: any }>(`/api/channels/wechat/qr/${sessionId}`)
  const qr = res.data.qr
  return { status: qr.status, qr_image: qr.qr_image, qr_scan_data: qr.qr_content || '', error: qr.error }
}

export async function bindWechatQr(sessionId: string) {
  const res = await request.post<{
    account: { id: string; has_credentials: boolean }
    binding: { external_user_id: string } | null
    listener: WechatListener
  }>(`/api/channels/wechat/qr/${encodeURIComponent(sessionId)}/bind`)
  return {
    account_pk: res.data.account.id,
    wechat_user_id: res.data.binding?.external_user_id || '',
    bot_configured: res.data.account.has_credentials,
    listener: res.data.listener,
  }
}

export interface UserBinding {
  id: string
  platform: string
  open_id: string
  nickname: string
  enabled: number
  created_at: string
}

export async function getUserBindings(ownerId: number): Promise<{ bindings: UserBinding[] }> {
  const res = await request.get<{ bindings: any[] }>('/api/channels/bindings')
  return {
    bindings: (res.data.bindings || []).filter(b => b.user_id === ownerId && b.status === 'active').map((b) => ({
      id: b.id,
      platform: b.platform,
      open_id: b.external_user_id,
      nickname: b.external_user_id,
      enabled: b.status === 'active' ? 1 : 0,
      created_at: b.created_at || '',
    })),
  }
}

export async function createUserBinding(data: { platform: string; account_id: string; open_id: string; nickname: string }): Promise<{ ok: boolean; id: number | string }> {
  const res = await request.post<{ binding: any }>('/api/channels/bindings', {
    platform: data.platform,
    account_id: data.account_id,
    external_user_id: data.open_id,
  })
  return { ok: true, id: res.data.binding?.id || '' }
}

export async function deleteUserBinding(id: string): Promise<{ ok: boolean }> {
  await request.delete(`/api/channels/bindings/${id}`)
  return { ok: true }
}

// WP-B：模块装配状态（登录可读、脱敏）——readyz/认证成功不代表模块可用
export interface ModuleStatus {
  assembled: boolean
  state: 'ready' | 'disabled' | 'misconfigured' | 'dependency_missing' | 'init_failed'
  reason: string
}

export async function getModuleStatus(): Promise<{ assistant: ModuleStatus; channels: ModuleStatus; runtime: ModuleStatus; secret_present: boolean }> {
  const res = await request.get('/api/system/module-status')
  return res.data
}
