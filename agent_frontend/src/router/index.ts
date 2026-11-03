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
    meta: { title: '智能对话', icon: '', requiresAuth: true, permission: 'chat.use' },
  },
  {
    path: '/skills',
    name: 'Skills',
    component: () => import('../views/SkillsView.vue'),
    meta: { title: '技能管理', icon: '', requiresAuth: true, permission: 'skill.create' },
  },
  {
    path: '/schedules',
    name: 'Schedules',
    component: () => import('../views/SchedulesView.vue'),
    meta: { title: '提醒', icon: '', requiresAuth: true, permission: 'cron.create' },
  },
  {
    path: '/memory',
    name: 'Memory',
    component: () => import('../views/MemoryView.vue'),
    meta: { title: '记忆管理', icon: '', requiresAuth: true, permission: 'memory.edit' },
  },
  {
    path: '/trace',
    name: 'Trace',
    component: () => import('../views/TraceView.vue'),
    meta: { title: '可观测性', icon: '', requiresAuth: true, permission: 'trace.view' },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('../views/AdminView.vue'),
    meta: { title: '系统管理', icon: '', requiresAuth: true, permission: 'system.manage' },
  },
  {
    path: '/audit-log',
    name: 'AuditLog',
    component: () => import('../views/AuditLogView.vue'),
    meta: { title: '操作审计', icon: '', requiresAuth: true, permission: 'terminal.audit' },
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('../views/ConfigView.vue'),
    meta: { title: '系统配置', icon: '', requiresAuth: true, permission: 'system.config' },
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
  const permissions: string[] = JSON.parse(localStorage.getItem('userPermissions') || '[]')

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

  // 检查页面权限
  if (to.meta.permission && userRole !== 'super_admin') {
    const perm = to.meta.permission as string
    let hasPerm = false
    if (perm === 'kb.eval') {
      // RAG 测评：**只认 kb.eval**。此前「kb.eval 或 kb.manage」会让该勾选框
      // 形同虚设（勾了「管理知识库」就能进）。数据范围仍由后端按 kb.manage 放宽。
      hasPerm = permissions.includes('kb.eval')
    } else if (perm === 'trace.view') {
      // trace.ranking 已并入 trace.view；trace.manage 保留兜底，
      // 否则只有「查看全部用户」的角色进不去自己的标签页。
      hasPerm = permissions.includes('trace.view') || permissions.includes('trace.manage')
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
