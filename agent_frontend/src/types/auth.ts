// 认证相关类型定义

export interface User {
  id: number
  username: string
  role: string
  permissions: string[]
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  ok: boolean
  user_id: number
  username: string
  role: string
  token: string
  permissions: string[]
}

export interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
}

// 权限整改 P2：统一 capability 出口（/api/auth/me.capabilities）
export interface ModuleCapability {
  label: string
  enabled: boolean
  read: boolean
  use: boolean
  manage: boolean
}

export interface UserCapabilities {
  modules: Record<string, ModuleCapability>
  tools: string[]
  super_admin: boolean
  permissions: string[]
}
