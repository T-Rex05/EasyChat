import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatView.vue'),
    meta: { title: '智能对话', icon: '', requiresAuth: true, permission: 'chat.use', capModule: 'chat', capLevel: 'use' },
  },
  {
    path: '/skills',
    name: 'Skills',
    component: () => import('../views/SkillsView.vue'),
    meta: { title: '技能管理', icon: '', requiresAuth: true, permission: 'skill.create', capModule: 'skills', capLevel: 'use' },
  },
  {
    path: '/wechat',
    name: 'WeChatSettings',
    component: () => import('../views/WeChatSettingsView.vue'),
    meta: { title: '微信偏好', icon: '💬', requiresAuth: true, permission: 'chat.use', capModule: 'chat', capLevel: 'use' },
  },
  {
    path: '/schedules',
    name: 'Schedules',
    component: () => import('../views/SchedulesView.vue'),
    meta: { title: '提醒', icon: '', requiresAuth: true, permission: 'cron.create', capModule: 'schedule', capLevel: 'use' },
  },
  {
    path: '/ledger',
    name: 'Ledger',
    component: () => import('../views/LedgerView.vue'),
    meta: { title: '账单', icon: '📄', requiresAuth: true, permission: 'ledger.view', capModule: 'ledger', capLevel: 'read' },
  },
  {
    path: '/superagent',
    name: 'Superagent',
    component: () => import('../views/SuperagentView.vue'),
    meta: { title: '超级代理', icon: '🤖', requiresAuth: true, permission: 'superagent.view', capModule: 'superagent', capLevel: 'read' },
  },
  {
    path: '/memory',
    name: 'Memory',
    component: () => import('../views/MemoryView.vue'),
    meta: { title: '记忆管理', icon: '', requiresAuth: true, permission: 'memory.edit', capModule: 'memory', capLevel: 'read' },
  },
  {
    path: '/trace',
    name: 'Trace',
    component: () => import('../views/UsageView.vue'),
    meta: { title: '用量与排行', icon: '', requiresAuth: true, permission: 'trace.view', capModule: 'trace', capLevel: 'read' },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('../views/AdminView.vue'),
    meta: { title: '系统管理', icon: '', requiresAuth: true, permission: 'system.manage', capModule: 'identity', capLevel: 'manage' },
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('../views/ConfigView.vue'),
    meta: { title: '系统配置', icon: '', requiresAuth: true, permission: 'system.config', capModule: 'config', capLevel: 'manage' },
  },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 标记是否已在本次会话中同步过 chatUserId，避免每次路由跳转都调接口
let chatUserIdSynced = false

// 路由守卫：检查认证和权限
router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('authToken')
  const userRole = localStorage.getItem('userRole') || ''
  let permissions: string[] = []
  try {
    const parsed = JSON.parse(localStorage.getItem('userPermissions') || '[]')
    permissions = Array.isArray(parsed) ? parsed.filter((x: unknown) => typeof x === 'string') : []
  } catch {
    localStorage.removeItem('userPermissions')
  }
  let capabilities: { modules?: Record<string, { read: boolean; use: boolean; manage: boolean }> } | null = null
  try {
    capabilities = JSON.parse(localStorage.getItem('userCapabilities') || 'null')
  } catch {
    capabilities = null
  }

  // 需要认证的页面
  if (to.meta.requiresAuth && !token) {
    next('/login')
    return
  }

  // 已登录访问登录页，跳转到聊天页
  if (to.path === '/login' && token) {
    next('/chat')
    return
  }

  // token 存在但 chatUserId 缺失时，异步同步用户信息（不阻塞路由）
  // 这是兜底逻辑：老版本登录 / 页面刷新后 chatUserId 可能丢失，导致 fallback 到 '1'（admin）
  if (token && !chatUserIdSynced) {
    chatUserIdSynced = true
    const existingUid = localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId')
    if (!existingUid) {
      // 异步同步，不阻塞路由跳转
      import('../api/request').then(async ({ default: request }) => {
        try {
          const resp = await request.get('/api/auth/me')
          const userData = resp.data
          if (userData && userData.id) {
            const uid = String(userData.id)
            localStorage.setItem('chatUserId', uid)
            sessionStorage.setItem('chatUserId', uid)
          }
        } catch (e) {
          // 同步失败，重置标记，下次再试
          chatUserIdSynced = false
        }
      })
    }
  }

  // 检查页面权限（权限整改 P2：capabilities 模块档位优先，原子权限兜底；kb.eval 分支已随 RAG 退役移除）
  if (to.meta.permission && userRole !== 'super_admin') {
    const perm = to.meta.permission as string
    let hasPerm = false
    if (to.meta.capModule) {
      const mod = capabilities?.modules?.[to.meta.capModule as string]
      if (mod) {
        const level = to.meta.capLevel as 'read' | 'use' | 'manage'
        hasPerm = level === 'read' ? mod.read : level === 'use' ? mod.use : mod.manage
      } else {
        hasPerm = permissions.includes(perm)
      }
    } else if (perm === 'trace.view') {
      hasPerm = permissions.includes('trace.view') || permissions.includes('trace.manage')
    } else if (perm === 'memory.edit') {
      hasPerm = permissions.includes('memory.edit') || permissions.includes('memory.view')
    } else if (perm === 'skill.create') {
      hasPerm = permissions.includes('skill.create') || permissions.includes('skill.manage')
    } else {
      hasPerm = permissions.includes(perm)
    }
    if (!hasPerm) {
      // ★ 避免无限重定向：已登录用户权限不足时，不再送去 /login（会与 121 行成环）
      if (to.path === '/chat') {
        // 用户连 chat.use 权限都没有，停在原地（或可跳转到 /no-permission 页面）
        next(false)
      } else {
        next('/chat')
      }
      return
    }
  }

  next()
})
