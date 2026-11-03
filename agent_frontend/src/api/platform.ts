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
): Promise<{ ok: boolean }> {
  const cfg = data.config_json || {}
  await request.post('/api/channels/accounts', {
    platform,
    account_id: String(cfg.account_id || '').trim(),
    token: String(cfg.token || '').trim(),
    bot_user_id: String(cfg.bot_user_id || ''),
    display_name: String(cfg.nickname || ''),
  })
  return { ok: true }
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
  return { status: qr.status, qr_image: qr.qr_image, error: qr.error }
}

export async function bindWechatQr(sessionId: string): Promise<{ ok: boolean; wechat_user_id: string; bot_configured: boolean }> {
  const res = await request.post<any>(`/api/channels/wechat/qr/${sessionId}/bind`)
  return {
    ok: res.data.ok ?? true,
    wechat_user_id: res.data.external_user_id || res.data.wechat_user_id || '',
    bot_configured: true,
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

export async function getUserBindings(): Promise<{ bindings: UserBinding[] }> {
  const res = await request.get<{ bindings: any[] }>('/api/channels/bindings')
  return {
    bindings: (res.data.bindings || []).map((b) => ({
      id: b.id,
      platform: b.platform,
      open_id: b.external_user_id,
      nickname: b.external_user_id,
      enabled: b.status === 'active' ? 1 : 0,
      created_at: b.created_at || '',
    })),
  }
}

export async function createUserBinding(data: { platform: string; open_id: string; nickname: string }): Promise<{ ok: boolean; id: number | string }> {
  const res = await request.post<{ binding: any }>('/api/channels/bindings', {
    platform: data.platform,
    external_user_id: data.open_id,
  })
  return { ok: true, id: res.data.binding?.id || '' }
}

export async function deleteUserBinding(id: string): Promise<{ ok: boolean }> {
  await request.delete(`/api/channels/bindings/${id}`)
  return { ok: true }
}
