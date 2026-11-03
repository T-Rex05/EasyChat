<template>
  <div class="chat-sidebar">
    <div class="sidebar-header">
      <h3>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><line x1="7" y1="9" x2="17" y2="9"/><line x1="7" y1="13" x2="14" y2="13"/></svg>
        <span>历史记录</span>
      </h3>
      <div class="header-actions">
        <button @click="newChat" class="btn-new-chat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新对话
        </button>
      </div>
    </div>

    <div class="history-list" @scroll="handleScroll">
      <div v-if="loading" class="loading-indicator">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      </div>
      <div v-else-if="sortedHistory.length === 0" class="empty-state">暂无历史对话</div>

      <div
        v-for="chat in sortedHistory"
        :key="chat.id"
        :class="['history-item', { active: chat.id === selectedChatId }]"
        @click="selectChat(chat.id)"
      >
        <div class="history-item-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
        </div>
        <div class="history-item-content">
          <input
            v-if="editingId === chat.id"
            v-model="editingTitle"
            class="history-item-title-input"
            :placeholder="chat.title || chat.user_question || '新对话'"
            @click.stop
            @keydown.enter.prevent="saveRename(chat.id)"
            @keydown.esc="cancelRename"
            @blur="saveRename(chat.id)"
            ref="renameInput" />
          <template v-else>
            <div class="history-item-title" :title="chat.title || chat.user_question || '新对话'">
              {{ chat.title || chat.user_question || '新对话' }}
            </div>
            <div class="history-item-time">{{ formatTime(chat.update_time || chat.create_time) }}</div>
          </template>
        </div>
        <div class="history-item-actions">
          <button @click.stop="startRename(chat)" class="btn-rename" title="重命名">✏️</button>
          <button @click.stop="deleteChat(chat.id)" class="btn-delete" title="删除">🗑️</button>
        </div>
      </div>

      <div v-if="hasMore" class="load-more-indicator">加载中...</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore } from '@/stores/chat'
import { getUserSessions, deleteSession, renameSession } from '@/api/session'
import { useAuthStore } from '@/stores/auth'

const sidebarStore = useSidebarStore()
const chatStore = useChatStore()
const authStore = useAuthStore()

const editingId = ref('')
const editingTitle = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const sortedHistory = computed(() => sidebarStore.sortedHistory)
const loading = computed(() => sidebarStore.loading)
const hasMore = computed(() => sidebarStore.hasMore)
const currentChatId = computed(() => chatStore.currentChatId)
const selectedChatId = computed(() => chatStore.currentChatId)

async function startRename(chat: { id: string; title?: string; user_question?: string }) {
  editingId.value = chat.id
  editingTitle.value = chat.title || chat.user_question || ''
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

function cancelRename() {
  editingId.value = ''
  editingTitle.value = ''
}

async function saveRename(chatId: string) {
  if (editingId.value !== chatId) return
  const newTitle = editingTitle.value.trim()
  editingId.value = ''
  const previousTitle = sidebarStore.chatHistory.find((c) => c.id === chatId)?.title
  if (!newTitle || newTitle === previousTitle) return
  try {
    await renameSession(chatId, newTitle)
    sidebarStore.updateInHistory(chatId, { title: newTitle, user_question: newTitle })
  } catch (error: any) {
    console.error('重命名失败:', error)
    alert(error?.response?.data?.error?.message || '重命名失败，请重试')
  }
}

async function loadHistory(append = false) {
  sidebarStore.setLoading(true)
  try {
    const offset = append ? sidebarStore.offset : 0
    const result = await getUserSessions(authStore.userId, offset, sidebarStore.pageSize, 'conversation')
    const normalized = (result.sessions || []).map((s) => ({
      ...s,
      id: s.id || (s as any).session_id || '',
      title: s.title || s.user_question || '',
    }))
    if (append) sidebarStore.appendChatHistory(normalized)
    else sidebarStore.setChatHistory(normalized)
    sidebarStore.setHasMore(result.has_more)
    sidebarStore.setOffset(offset + normalized.length)
  } catch (error) {
    console.error('加载历史失败:', error)
  } finally {
    sidebarStore.setLoading(false)
  }
}

async function selectChat(chatId: string) {
  if (chatId === selectedChatId.value) return
  window.dispatchEvent(new CustomEvent('chat:loadHistory', { detail: { chatId } }))
}

async function deleteChat(chatId: string) {
  if (!confirm('确定要删除这个对话吗？')) return
  try {
    await deleteSession(chatId)
    sidebarStore.removeFromHistory(chatId)
    if (chatId === currentChatId.value) {
      chatStore.clearMessages()
      chatStore.setCurrentChatId('')
    }
  } catch (error) {
    console.error('删除对话失败:', error)
  }
}

function newChat() {
  chatStore.clearMessages()
  chatStore.setCurrentChatId('')
}

function handleScroll(e: Event) {
  const target = e.target as HTMLElement
  if (target.scrollTop + target.clientHeight >= target.scrollHeight - 100) {
    if (!loading.value && hasMore.value) loadHistory(true)
  }
}

function formatTime(time?: string): string {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

onMounted(() => {
  loadHistory(false)
  const handleRefreshHistory = () => loadHistory(false)
  const handleNewSession = (e: Event) => {
    const detail = (e as CustomEvent).detail
    const now = new Date().toLocaleString('zh-CN')
    sidebarStore.removeFromHistory(detail.chatId)
    sidebarStore.prependChatHistory({
      id: detail.chatId, title: detail.title, user_question: detail.title,
      update_time: now, create_time: now, is_schedule: 0,
    })
  }
  window.addEventListener('chat:refreshHistory', handleRefreshHistory)
  window.addEventListener('chat:newSession', handleNewSession)
  onUnmounted(() => {
    window.removeEventListener('chat:refreshHistory', handleRefreshHistory)
    window.removeEventListener('chat:newSession', handleNewSession)
  })
  watch(() => authStore.isAuthenticated, (isAuth) => { if (isAuth) loadHistory(false) })
})
</script>

<style scoped>
.chat-sidebar {
  width: 280px; flex-shrink: 0; display: flex; flex-direction: column;
  background: var(--bg-sidebar, var(--bg-secondary)); border-right: 1px solid var(--border-primary);
  height: 100%; overflow: hidden;
}
.sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 12px; border-bottom: 1px solid var(--border-primary); }
.sidebar-header h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 15px; font-weight: 600; }
.sidebar-header h3 svg { width: 18px; height: 18px; }
.btn-new-chat { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--border-primary); background: transparent; color: var(--text-secondary); border-radius: 6px; padding: 5px 8px; font-size: 12px; cursor: pointer; }
.btn-new-chat:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.btn-new-chat svg { width: 13px; height: 13px; }
.history-list { flex: 1; overflow-y: auto; padding: 6px; }
.history-item { display: flex; align-items: center; gap: 8px; padding: 9px; border-radius: 7px; cursor: pointer; }
.history-item:hover { background: var(--bg-tertiary); }
.history-item.active { background: var(--bg-tertiary); }
.history-item-icon svg { width: 15px; height: 15px; color: var(--text-tertiary); }
.history-item-content { flex: 1; min-width: 0; }
.history-item-title { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.history-item-time { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.history-item-title-input { width: 100%; border: 1px solid var(--accent, #4a7cff); border-radius: 4px; padding: 2px 4px; background: var(--bg-primary); color: inherit; font-size: 13px; }
.history-item-actions { display: none; gap: 2px; }
.history-item:hover .history-item-actions { display: flex; }
.history-item-actions button { border: 0; background: transparent; cursor: pointer; padding: 2px; font-size: 12px; opacity: .7; }
.history-item-actions button:hover { opacity: 1; }
.empty-state, .load-more-indicator { text-align: center; color: var(--text-tertiary); font-size: 12px; padding: 24px 0; }
.loading-indicator { display: flex; justify-content: center; gap: 4px; padding: 20px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-tertiary); animation: blink 1s infinite alternate; }
.dot:nth-child(2) { animation-delay: .2s; } .dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { from { opacity: .25; } to { opacity: 1; } }
</style>
