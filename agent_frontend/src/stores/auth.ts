// 认证状态管理

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, UserCapabilities } from '@/types/auth'
import { login as apiLogin, verifyToken, refreshToken } from '@/api/auth'
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
    const capabilities = ref<UserCapabilities | null>(null)
    const userId = ref(localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId') || '')
    // 身份初始化状态：/me 对齐完成前，依赖身份的调用应等待（ready=false）
    const ready = ref(false)

    // 计算属性
    const isAuthenticated = computed(() => !!token.value)

    function syncUserId(id?: number) {
      const value = id ? String(id) : ''
      userId.value = value
      if (value) {
        localStorage.setItem('chatUserId', value)
        sessionStorage.setItem('chatUserId', value)
      } else {
        localStorage.removeItem('chatUserId')
        sessionStorage.removeItem('chatUserId')
      }
    }

    // 操作
    async function login(user: string, pass: string) {
      try {
        const response = await apiLogin({ username: user, password: pass })

        token.value = response.token
        userRole.value = response.role || ''
        username.value = response.username || ''
        permissions.value = response.permissions || []
        capabilities.value = (response as any).capabilities || null
        persistCapabilities(capabilities.value)

        // 持久化到 localStorage
        localStorage.setItem('authToken', response.token)
        localStorage.setItem('userRole', response.role || '')
        localStorage.setItem('username', response.username || '')
        localStorage.setItem('userPermissions', JSON.stringify(response.permissions || []))
        syncUserId(response.user_id)

        return true
      } catch (error: any) {
        console.error('登录失败:', error)
        console.error('Error response:', error.response?.data)
        console.error('Error status:', error.response?.status)
        throw new Error(error.response?.data?.detail || '登录失败')
      }
    }

    function persistCapabilities(caps: UserCapabilities | null) {
      if (caps) localStorage.setItem('userCapabilities', JSON.stringify(caps))
      else localStorage.removeItem('userCapabilities')
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
        capabilities.value = (userData as any).capabilities || null
        persistCapabilities(capabilities.value)

        // ★ 同步到 localStorage（路由守卫读的是 localStorage）
        localStorage.setItem('userRole', userData.role || '')
        localStorage.setItem('username', userData.username || '')
        localStorage.setItem('userPermissions', JSON.stringify(userData.permissions || []))

        syncUserId(userData.id)
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
          capabilities.value = (response as any).capabilities || null
          persistCapabilities(capabilities.value)

          localStorage.setItem('authToken', response.token)
          localStorage.setItem('userRole', response.role || '')
          localStorage.setItem('username', response.username || '')
          localStorage.setItem('userPermissions', JSON.stringify(response.permissions || []))
          syncUserId(response.user_id)

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
      capabilities.value = null
      localStorage.removeItem('userCapabilities')

      localStorage.removeItem('authToken')
      localStorage.removeItem('userRole')
      localStorage.removeItem('username')
      localStorage.removeItem('userPermissions')
      syncUserId()
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
      verify,
      tryRefresh,
      logout,
      hasPerm,
      ready,
      markReady,
      capabilities,
    }
  },
  {
    persist: {
      storage: localStorage,
      // chatUserId 由 syncUserId 持久化，避免同一身份出现两份缓存。
      omit: ['userId'],
    },
  }
)
