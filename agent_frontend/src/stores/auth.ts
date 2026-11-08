// 认证状态管理

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types/auth'
import { login as apiLogin, register as apiRegister, verifyToken, refreshToken } from '@/api/auth'
import { useChatStore } from '@/stores/chat'

export const useAuthStore = defineStore(
  'auth',
  () => {
    // 受保护解析：缓存损坏返回空数组，不阻断启动
    function readStoredPermissions(): string[] {
      try {
        const raw = localStorage.getItem('userPermissions')
        const parsed = raw ? JSON.parse(raw) : []
        return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
      } catch {
        localStorage.removeItem('userPermissions')
        return []
      }
    }

    // 状态
    const token = ref<string | null>(localStorage.getItem('authToken'))
    const user = ref<User | null>(null)
    const userRole = ref<string>(localStorage.getItem('userRole') || '')
    const username = ref<string>(localStorage.getItem('username') || '')
    const permissions = ref<string[]>(readStoredPermissions())
    // 身份初始化状态：/me 对齐完成前，依赖身份的调用应等待（ready=false）
    const ready = ref(false)

    // 计算属性
    const isAuthenticated = computed(() => !!token.value)

    const userId = computed(() => {
      // 未知身份返回空串（T8）：调用方必须等待 ready 或显式处理空值，
      // 绝不再默认到 '1'（会把对话记到 admin 头上）
      return localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId') || ''
    })

    // 操作
    async function login(user: string, pass: string) {
      try {
        const response = await apiLogin({ username: user, password: pass })
        console.log('Login response:', response)

        token.value = response.token
        userRole.value = response.role || ''
        username.value = response.username || ''
        permissions.value = response.permissions || []

        // 持久化到 localStorage
        localStorage.setItem('authToken', response.token)
        localStorage.setItem('userRole', response.role || '')
        localStorage.setItem('username', response.username || '')
        localStorage.setItem('userPermissions', JSON.stringify(response.permissions || []))
        const uid = String(response.user_id || '')
        localStorage.setItem('chatUserId', uid)
        sessionStorage.setItem('chatUserId', uid)

        return true
      } catch (error: any) {
        console.error('登录失败:', error)
        console.error('Error response:', error.response?.data)
        console.error('Error status:', error.response?.status)
        throw new Error(error.response?.data?.detail || '登录失败')
      }
    }

    async function register(user: string, pass: string) {
      try {
        const response = await apiRegister({ username: user, password: pass })
        token.value = response.token
        userRole.value = response.role || ''
        username.value = response.username || ''
        permissions.value = response.permissions || []

        localStorage.setItem('authToken', response.token)
        localStorage.setItem('userRole', response.role || '')
        localStorage.setItem('username', response.username || '')
        localStorage.setItem('userPermissions', JSON.stringify(response.permissions || []))
        const uid = String(response.user_id || '')
        localStorage.setItem('chatUserId', uid)
        sessionStorage.setItem('chatUserId', uid)

        return true
      } catch (error) {
        console.error('注册失败:', error)
        throw error
      }
    }

    function markReady() {
      ready.value = true
    }

    async function verify() {
      if (!token.value) return false

      try {
        const userData = await verifyToken()
        user.value = userData
        userRole.value = userData.role
        username.value = userData.username
        permissions.value = userData.permissions || []

        // ★ 同步到 localStorage（路由守卫读的是 localStorage）
        localStorage.setItem('userRole', userData.role || '')
        localStorage.setItem('username', userData.username || '')
        localStorage.setItem('userPermissions', JSON.stringify(userData.permissions || []))

        // 刷新 token 时同步 chatUserId，避免 fallback 到 '1'（admin）
        if (userData.id) {
          const uid = String(userData.id)
          localStorage.setItem('chatUserId', uid)
          sessionStorage.setItem('chatUserId', uid)
        }
        return true
      } catch (error) {
        console.error('Token 验证失败:', error)
        // 注意：此处不再自动 logout，由调用方决定（App.vue 会先尝试 tryRefresh）
        throw error
      }
    }

    /**
     * 尝试静默刷新 Token（过期宽限期内免登录续期）。
     *
     * 调用时机：应用启动时，verify() 失败后（token 已过期），
     * 先尝试刷新而不是直接踢到登录页。
     *
     * @returns true = 刷新成功，token 已更新；false = 需要重新登录
     */
    async function tryRefresh(): Promise<boolean> {
      if (!token.value) return false

      try {
        const response = await refreshToken()
        if (response.token) {
          // 更新 token 和用户信息
          token.value = response.token
          userRole.value = response.role || ''
          username.value = response.username || ''
          permissions.value = response.permissions || []

          localStorage.setItem('authToken', response.token)
          localStorage.setItem('userRole', response.role || '')
          localStorage.setItem('username', response.username || '')
          localStorage.setItem('userPermissions', JSON.stringify(response.permissions || []))
          const uid = String(response.user_id || '')
          localStorage.setItem('chatUserId', uid)
          sessionStorage.setItem('chatUserId', uid)

          console.log('[Auth] Token 静默刷新成功')
          return true
        }
        return false
      } catch (error) {
        console.warn('[Auth] Token 刷新失败，需重新登录:', error)
        return false
      }
    }

    function logout() {
      token.value = null
      user.value = null
      userRole.value = ''
      username.value = ''
      permissions.value = []

      localStorage.removeItem('authToken')
      localStorage.removeItem('userRole')
      localStorage.removeItem('username')
      localStorage.removeItem('userPermissions')
      localStorage.removeItem('chatUserId')
      sessionStorage.clear()

      // 清空聊天状态（避免切换用户后看到上一用户的对话）
      useChatStore().resetAll()
    }

    function hasPerm(permission: string): boolean {
      // 超级管理员拥有所有权限
      if (userRole.value === 'super_admin') return true
      return permissions.value.includes(permission)
    }

    return {
      token,
      user,
      userRole,
      username,
      permissions,
      isAuthenticated,
      userId,
      login,
      register,
      verify,
      tryRefresh,
      logout,
      hasPerm,
      ready,
      markReady,
    }
  },
  {
    persist: {
      storage: localStorage,
      // 注：pinia-plugin-persistedstate v4 已用 pick/omit 取代 v3 的 paths；
      // 原 paths 键在 v4 下被静默忽略（等同全量持久化），删除以保持运行时行为不变。
    },
  }
)
