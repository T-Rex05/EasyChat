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
