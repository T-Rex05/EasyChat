// Axios 实例配置 + 拦截器

import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'

// API 基础路径（从环境变量或默认值）
const API_BASE = import.meta.env.VITE_API_BASE || ''

// 防止并发 401 重复触发 logout/跳转
let _isHandling401 = false

// 创建 Axios 实例
const request: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：自动附加 Token
// 注意：不做本地过期预检！后端有宽限期刷新机制（TOKEN_REFRESH_GRACE_PERIOD），
// 由后端决定 token 是否可用。过期 token 由响应 401 拦截器统一处理。
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：统一错误处理 + 自动续期 + 401 处理
request.interceptors.response.use(
  (response: AxiosResponse) => {
    // 自动接收滑动窗口续期 token
    const newToken = response.headers['x-new-token']
    if (newToken) {
      const authStore = useAuthStore()
      authStore.token = newToken
      localStorage.setItem('authToken', newToken)
    }
    return response
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response

      // 即使报错，也先尝试接收续期 token
      const newToken = error.response.headers?.['x-new-token']
      if (newToken) {
        const authStore = useAuthStore()
        authStore.token = newToken
        localStorage.setItem('authToken', newToken)
      }

      // 提取后端返回的中文 detail 信息。
      // detail 可能是字符串（HTTPException）、对象或数组（FastAPI 422 校验错误），
      // 统一压成可读字符串，并写回 data.detail，避免视图 alert 出 "[object Object]"。
      if (data && data.detail) {
        let msg = ''
        if (typeof data.detail === 'string') {
          msg = data.detail
        } else if (Array.isArray(data.detail)) {
          msg = data.detail.map((d: any) => {
            if (typeof d === 'string') return d
            if (d && typeof d === 'object') {
              const loc = Array.isArray(d.loc) ? d.loc.filter((x: any) => typeof x === 'string').join('.') : ''
              const text = d.msg || JSON.stringify(d)
              return loc ? loc + ': ' + text : text
            }
            return String(d)
          }).filter(Boolean).join('；')
        } else if (typeof data.detail === 'object') {
          try { msg = JSON.stringify(data.detail) } catch { /* ignore */ }
        }
        if (msg) {
          error.message = msg
          data.detail = msg
        }
      }

      // 401 未授权：清除 token 并跳转登录（去重，防止并发请求重复触发）
      if (status === 401 && !_isHandling401) {
        _isHandling401 = true
        const authStore = useAuthStore()
        authStore.logout()
        // 跳转到登录页（如果在路由环境中）
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        // 延迟重置标记，避免页面跳转前的其他请求再次触发
        setTimeout(() => { _isHandling401 = false }, 3000)
      }

      // 403 权限不足
      if (status === 403) {
        console.error('权限不足:', error.message)
      }

      // 500 服务器错误
      if (status === 500) {
        console.error('服务器错误:', error.message)
      }
    }

    return Promise.reject(error)
  }
)

export default request
