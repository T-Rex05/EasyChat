<template>
  <div class="app-shell">
    <AppSidebar v-if="showSidebar" />
    <main class="app-main" :class="{ 'full-width': !showSidebar }">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const showSidebar = computed(() => route.path !== '/login')

// 应用启动时验证 token 并刷新用户信息（完成后 auth.ready = true）
onMounted(async () => {
  if (!authStore.token) {
    authStore.markReady()
    return
  }
  try {
    await authStore.verify()
    authStore.markReady()
    console.log('[App] Token verified, userId:', authStore.userId || '(待初始化)')
  } catch (verifyErr) {
    console.warn('[App] Token verification failed, trying silent refresh:', verifyErr)
    // Token 验证失败（可能已过期），尝试静默刷新（宽限期内免登录）
    try {
      const refreshed = await authStore.tryRefresh()
      if (refreshed) {
        authStore.markReady()
        console.log('[App] Token silently refreshed, userId:', authStore.userId || '(待初始化)')
        return  // 刷新成功，正常进入应用
      }
    } catch (refreshErr) {
      console.warn('[App] Silent refresh also failed:', refreshErr)
    }
    // 验证和刷新都失败 → 彻底过期，logout 并跳转登录
    authStore.logout()
    authStore.markReady()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }
})
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-secondary);
}

.app-main.full-width {
  flex: 1;
}
</style>

<!-- 全局 Markdown 渲染样式（非 scoped，影响所有组件的 .markdown-body） -->
<style>
.markdown-body ul,
.markdown-body ol {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.markdown-body li {
  margin: 0.25em 0;
  line-height: 1.6;
}
.markdown-body li > ul,
.markdown-body li > ol {
  margin: 0;
}
.markdown-body blockquote {
  margin: 0.5em 0;
  padding: 0.5em 1em;
  border-left: 3px solid var(--brand, #6366f1);
  background: var(--bg-secondary, #f5f5f5);
  color: var(--text-secondary, #666);
  border-radius: 0 4px 4px 0;
}
.markdown-body blockquote p {
  margin: 0;
}
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75em 0;
  font-size: 13px;
}
.markdown-body th,
.markdown-body td {
  border: 1px solid var(--border-color, #e0e0e0);
  padding: 6px 12px;
  text-align: left;
}
.markdown-body th {
  background: var(--bg-secondary, #f5f5f5);
  font-weight: 600;
}
.markdown-body tr:nth-child(even) td {
  background: rgba(0,0,0,0.02);
}
.markdown-body strong {
  font-weight: 700;
  color: var(--text-primary, #333);
}
.markdown-body em {
  font-style: italic;
}
.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  margin: 1em 0 0.5em;
  line-height: 1.4;
}
.markdown-body h1 { font-size: 1.4em; }
.markdown-body h2 { font-size: 1.2em; }
.markdown-body h3 { font-size: 1.05em; }
.markdown-body hr {
  border: none;
  border-top: 1px solid var(--border-color, #e0e0e0);
  margin: 1em 0;
}
</style>
