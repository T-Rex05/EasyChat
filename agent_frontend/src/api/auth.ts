// 认证 API：登录/注册/验证/刷新

import request from './request'
import type { LoginRequest, LoginResponse, User } from '@/types/auth'

/**
 * 用户登录
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await request.post<LoginResponse>('/api/auth/login', data)
  return response.data
}

/**
 * 用户注册
 */
export async function register(data: LoginRequest): Promise<LoginResponse> {
  const response = await request.post<LoginResponse>('/api/auth/register', data)
  return response.data
}

/**
 * 验证当前 Token（获取用户信息）
 */
export async function verifyToken(): Promise<User> {
  const response = await request.get<User>('/api/auth/me')
  return response.data
}

/**
 * 刷新 Token（过期宽限期内免登录续期）
 *
 * 后端支持：
 * - Token 未过期但在续期窗口内（默认 7 天）→ 刷新成功
 * - Token 已过期但在宽限期内（默认 7 天）→ 刷新成功
 * - 超出宽限期 → 401，需重新登录
 */
export async function refreshToken(): Promise<LoginResponse> {
  const response = await request.post<LoginResponse>('/api/auth/refresh')
  return response.data
}
