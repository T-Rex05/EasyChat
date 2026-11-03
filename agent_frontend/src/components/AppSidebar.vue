<template>
  <aside class="sidebar" :class="{ collapsed }">
    <!-- Logo -->
    <div class="sidebar-logo" @click="$router.push('/chat')">
      <div class="logo-icon">
        <svg viewBox="0 0 36 36" width="36" height="36">
          <defs>
            <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#4e6ef2" />
              <stop offset="100%" stop-color="#6b83f5" />
            </linearGradient>
          </defs>
          <rect width="36" height="36" rx="10" fill="url(#brandGrad)" />
          <path d="M18 8l8 3.5v5c0 5.5-3.5 9-8 10.5-4.5-1.5-8-5-8-10.5v-5L18 8z"
                fill="rgba(255,255,255,0.9)" />
        </svg>
      </div>
      <transition name="fade">
        <div v-if="!collapsed" class="logo-text">
          <span class="logo-title">AgentForge</span>
          <span class="logo-sub">AI Agent Scaffold</span>
        </div>
      </transition>
    </div>

    <!-- 导航菜单（分组） -->
    <nav class="sidebar-nav">
      <template v-for="group in menuGroups" :key="group.label">
        <div class="nav-group-label" v-if="!collapsed">{{ group.label }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: $route.path === item.path }"
          :title="item.title"
        >
          <span class="nav-icon" v-html="item.icon"></span>
          <span v-if="!collapsed" class="nav-label">{{ item.title }}</span>
          <span v-if="getPendingCount(item.path) > 0" class="nav-badge">{{ getPendingCount(item.path) }}</span>
        </router-link>
      </template>
    </nav>

    <!-- 底部操作区 -->
    <div class="sidebar-footer">
      <div v-if="!collapsed" class="user-info">
        <span class="user-role">{{ userRoleText }}</span>
        <span class="user-name">{{ username }}</span>
      </div>
      <!-- 折叠态只保留展开按钮，避免 3 个按钮在 64px 宽度内互相覆盖 -->
      <template v-if="!collapsed">
        <button class="sidebar-btn" @click="toggleTheme" :title="isDark ? '亮色模式' : '暗色模式'">
          <svg v-if="!isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
        </button>
        <button class="sidebar-btn" @click="handleLogout" title="退出登录">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </button>
      </template>
      <button class="sidebar-btn" @click="collapsed = !collapsed" :title="collapsed ? '展开侧边栏' : '折叠侧边栏'">
        <svg v-if="collapsed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getPendingCounts } from '@/api/notification'

const router = useRouter()
const authStore = useAuthStore()

const collapsed = ref(false)
const isDark = ref(false)

// 待审核数量（用于红点显示）
const pendingCounts = ref({
  skill: 0,
  memory: 0,
  suggestion: 0,
  graphCandidate: 0,
})

// 路径到待审核类型的映射
const pathToPendingType: Record<string, keyof typeof pendingCounts.value> = {
  '/pool-review': 'skill',  // 技能池审核显示 skill+memory 的总和
  '/kb-eval': 'suggestion',
  '/kg-review': 'graphCandidate',
}

// 获取菜单项的待审核数量
const getPendingCount = (path: string): number => {
  if (path === '/pool-review') {
    // 技能池审核显示所有类型的总和
    return pendingCounts.value.skill + pendingCounts.value.memory
  }
  const type = pathToPendingType[path]
  return type ? pendingCounts.value[type] : 0
}

// 获取待审核数量
const fetchPendingCounts = async () => {
  try {
    const counts = await getPendingCounts()
    pendingCounts.value = counts
  } catch (error) {
    console.error('Failed to fetch pending counts:', error)
  }
}

// 定时刷新待审核数量（每 60 秒）
let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchPendingCounts()
  refreshTimer = setInterval(fetchPendingCounts, 60000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})

const userRoleText = computed(() => {
  const role = authStore.userRole
  const map: Record<string, string> = {
    super_admin: '超级管理员',
    admin: '管理员',
    user: '用户',
  }
  return map[role] || role
})

const username = computed(() => authStore.username)
const permissions = computed(() => authStore.permissions)
const userRole = computed(() => authStore.userRole)

// 根据权限过滤菜单项
// 图标使用内联 SVG（stroke=currentColor），随激活/hover 自动变色，视觉更统一专业
const menuItems = computed(() => {
  const allItems = [
    {
      path: '/chat', title: '智能对话', perm: 'chat.use',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`,
    },
    {
      path: '/skills', title: '技能管理', perm: 'skill.create',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
    },
    {
      path: '/pool-review', title: '技能池审核', perm: 'skill.pool.review',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 11.5 11 13.5 15 9.5"/></svg>`,
    },
    {
      path: '/memory', title: '记忆管理', perm: 'memory.edit',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`,
    },
    {
      path: '/memory-dashboard', title: '记忆监控', perm: 'memory.view',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
    },
    {
      path: '/knowledge', title: '知识库', perm: 'kb.manage',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
    },
    {
      path: '/kb-eval', title: 'RAG 测评', perm: 'kb.eval',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/><path d="M21 12h-4l-3 8-4-16-3 8H3"/></svg>`,
    },
    {
      path: '/graph', title: '知识图谱', perm: 'graph.manage',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/><circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/><line x1="6" y1="6" x2="9" y2="10"/><line x1="18" y1="6" x2="15" y2="10"/><line x1="6" y1="18" x2="9" y2="14"/><line x1="18" y1="18" x2="15" y2="14"/></svg>`,
    },
    {
      path: '/kg-review', title: '图谱审核', perm: 'graph.manage',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
    },
    {
      path: '/communities', title: '社区管理', perm: 'graph.manage',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><circle cx="8" cy="16" r="3"/><circle cx="16" cy="16" r="3"/><line x1="10.5" y1="9.5" x2="13.5" y2="9.5"/><line x1="10.5" y1="14.5" x2="13.5" y2="14.5"/><line x1="8" y1="11" x2="8" y2="13"/><line x1="16" y1="11" x2="16" y2="13"/></svg>`,
    },
    {
      path: '/trace', title: '可观测性', perm: 'trace.view',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
    },
    {
      path: '/admin', title: '系统管理', perm: 'system.manage',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    },
    {
      path: '/audit-log', title: '操作审计', perm: 'terminal.audit',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
    },
    {
      path: '/config', title: '系统配置', perm: 'system.config',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
    },
    {
      path: '/paper-reproduction', title: '论文复现', perm: 'paper.use',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
    },
  ]

  // super_admin 拥有所有权限
  if (userRole.value === 'super_admin') {
    return allItems
  }

  return allItems.filter(item => {
    // trace 菜单：trace.ranking 已并入 trace.view；trace.manage 保留兜底，
    // 否则只有「查看全部用户」的角色进不去自己的那个标签页。
    if (item.perm === 'trace.view') {
      return permissions.value.includes('trace.view')
        || permissions.value.includes('trace.manage')
    }
    // kb 菜单：有 kb.manage 权限即可
    if (item.perm === 'kb.manage') {
      return permissions.value.includes('kb.manage')
    }
    // kb.eval 菜单（RAG 测评）：**只认 kb.eval**。
    // 此前放行条件是「kb.eval 或 kb.manage」，导致「RAG 测评」这个勾选框
    // 从未生效 —— 只要勾了「管理知识库」菜单就会出现（实测 qqq/test-1 没有
    // kb.eval 却有 kb.manage，因此看得到该功能）。
    if (item.perm === 'kb.eval') {
      return permissions.value.includes('kb.eval')
    }
    // 技能池审核菜单：**只认 skill.pool.review**。
    // 此前是「skill.pool.review 或 skill.manage」，与已修复的 kb.eval 同类 ——
    // 取消勾选「技能池审核」后只要还留着「管理全部技能」，菜单照样出现。
    if (item.perm === 'skill.pool.review') {
      return permissions.value.includes('skill.pool.review')
    }
    // 记忆管理菜单：有个人记忆管理权限即可
    if (item.perm === 'memory.edit') {
      return permissions.value.includes('memory.edit')
    }
    return permissions.value.includes(item.perm)
  })
})

// 分组：对话与观测 / 技能与记忆 / 知识库 / 系统（与角色编辑弹窗的功能权限分组一致）
const MENU_GROUP_RULES: { label: string; paths: string[] }[] = [
  { label: '对话与观测', paths: ['/chat', '/trace', '/paper-reproduction'] },
  { label: '技能与记忆', paths: ['/skills', '/pool-review', '/memory', '/memory-dashboard'] },
  { label: '知识库', paths: ['/knowledge', '/kb-eval', '/graph', '/kg-review', '/communities'] },
  { label: '系统', paths: ['/admin', '/audit-log', '/config'] },
]

const menuGroups = computed(() => {
  const pathToGroup = new Map<string, string>()
  for (const rule of MENU_GROUP_RULES) {
    for (const p of rule.paths) pathToGroup.set(p, rule.label)
  }
  const groups: { label: string; items: typeof menuItems.value }[] = MENU_GROUP_RULES.map(r => ({ label: r.label, items: [] }))
  for (const item of menuItems.value) {
    const g = groups.find(x => x.label === (pathToGroup.get(item.path) || "系统"))
    if (g) g.items.push(item)
  }
  return groups.filter(g => g.items.length > 0)
})

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

function handleLogout() {
  if (confirm('确定要退出登录吗？')) {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.sidebar {
  width: 240px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-primary);
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.logo-text {
  display: flex;
  flex-direction: column;
}

.logo-title {
  font-size: 16px;
  font-weight: 600;
  background: var(--brand-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.3px;
}

.logo-sub {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* ─── 导航 ─── */
.sidebar-nav {
  flex: 1;
  padding: 12px 0;
  overflow-y: auto;
  min-height: 0;
}

.nav-group-label {
  padding: 8px 18px 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-placeholder);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  margin: 2px 8px;
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: var(--transition);
  cursor: pointer;
  position: relative;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 当前项：品牌色 + 左侧高亮条 */
.nav-item.active {
  background: var(--brand-light);
  color: var(--brand);
  font-weight: 500;
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  border-radius: 3px;
  background: var(--brand);
}

.nav-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-icon svg {
  width: 18px;
  height: 18px;
}

/* 待审核数量红点 */
.nav-badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* ─── 底部 ── */
.sidebar-footer {
  padding: 10px 8px;
  border-top: 1px solid var(--border-primary);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  flex-wrap: nowrap;
  overflow: hidden;
}

.sidebar.collapsed .sidebar-footer {
  padding: 8px 2px;
  gap: 0;
  justify-content: center;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 0 6px;
  min-width: 0;
}

.user-role {
  font-size: 11px;
  color: var(--brand);
  font-weight: 500;
}

.user-name {
  font-size: 12px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  transition: background 0.2s, color 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.sidebar-btn svg {
  width: 17px;
  height: 17px;
}

.sidebar.collapsed .sidebar-btn {
  width: 30px;
  height: 30px;
}

.sidebar-btn:hover {
  background: var(--bg-hover);
  color: var(--brand);
}
</style>
