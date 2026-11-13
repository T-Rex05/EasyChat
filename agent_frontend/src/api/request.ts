// Axios 实例配置 + 拦截器

import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { extractErrorMessage } from '@/utils/errorMessage'

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

      // 统一提取业务可读中文原因（P5）：兼容 detail（字符串/数组/对象）与
      // AppError 的顶层 message；提取结果写回 error.message 与 data.detail，
      // 老页面按 detail 读取同样拿到规范化文本，不再出现
      // "Request failed with status code 422" 或 "[object Object]"。
      const readable = extractErrorMessage(error)
      if (readable && data) {
        if (!(typeof data.detail === 'string' && data.detail.trim())) {
          data.detail = readable
        }
      }
      if (readable) {
        error.message = readable
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
