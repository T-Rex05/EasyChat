// 平台配置 & 用户绑定 API

import request from './request'

// ── 平台配置 ──
export interface PlatformConfig {
  platform: string
  config_json: Record<string, any>
  raw_config_json?: Record<string, any>
  enabled: boolean
  configured: boolean
  updated_at?: string
}

export async function getPlatformConfig(platform: string): Promise<PlatformConfig> {
  const res = await request.get(`/api/platform-config/${platform}`)
  return res.data
}

export async function savePlatformConfig(platform: string, data: { config_json: Record<string, any>; enabled: boolean }): Promise<{ ok: boolean }> {
  const res = await request.put(`/api/platform-config/${platform}`, data)
  return res.data
}

export async function getPlatformBindings(platform: string): Promise<{ bindings: any[] }> {
  const res = await request.get(`/api/platform-config/${platform}/bindings`)
  return res.data
}

// ── 微信 QR 扫码 ──
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
  const res = await request.post('/api/platform-config/wechat/qr/start')
  return res.data
}

export async function checkWechatQrStatus(sessionId: string): Promise<QrStatusResult> {
  const res = await request.get(`/api/platform-config/wechat/qr/${sessionId}/status`)
  return res.data
}

export async function bindWechatQr(sessionId: string): Promise<{ ok: boolean; wechat_user_id: string; bot_configured: boolean }> {
  const res = await request.post(`/api/platform-config/wechat/qr/${sessionId}/bind`)
  return res.data
}

// ── 用户绑定 ──
export interface UserBinding {
  id: number
  platform: string
  open_id: string
  nickname: string
  enabled: number
  created_at: string
}

export async function getUserBindings(): Promise<{ bindings: UserBinding[] }> {
  const res = await request.get('/api/user-bindings')
  return res.data
}

export async function createUserBinding(data: { platform: string; open_id: string; nickname: string }): Promise<{ ok: boolean; id: number }> {
  const res = await request.post('/api/user-bindings', data)
  return res.data
}

export async function deleteUserBinding(id: number): Promise<{ ok: boolean }> {
  const res = await request.delete(`/api/user-bindings/${id}`)
  return res.data
}
