// 侧边栏状态管理（历史列表）

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatSession } from '@/types/chat'

export const useSidebarStore = defineStore('sidebar', () => {
  // 状态
  const chatHistory = ref<ChatSession[]>([])
  const historyFilter = ref<string>('conversation') // 'conversation' | 'schedule' | 'all'
  const hasMore = ref(true)
  const offset = ref(0)
  const loading = ref(false)
  const currentOffset = ref(0)
  const pageSize = ref(50)

  // 计算属性
  const filteredHistory = computed(() => {
    if (historyFilter.value === 'all') return chatHistory.value
    if (historyFilter.value === 'schedule') {
      return chatHistory.value.filter((chat) => chat.is_schedule)
    }
    return chatHistory.value.filter((chat) => !chat.is_schedule)
  })

  const sortedHistory = computed(() => {
    return [...filteredHistory.value].sort((a, b) => {
      const timeA = a.update_time || a.end_time || a.create_time || ''
      const timeB = b.update_time || b.end_time || b.create_time || ''
      return timeB.localeCompare(timeA)
    })
  })

  // 操作
  function setChatHistory(sessions: ChatSession[]) {
    // 按 ID 去重
    const seen = new Set<string>()
    chatHistory.value = sessions.filter(s => {
      if (seen.has(s.id)) return false
      seen.add(s.id)
      return true
    })
  }

  function prependChatHistory(session: ChatSession) {
    // 移除已存在的相同 ID
    const idx = chatHistory.value.findIndex((c) => c.id === session.id)
    if (idx !== -1) {
      chatHistory.value.splice(idx, 1)
    }
    // 添加到顶部
    chatHistory.value.unshift(session)
  }

  function appendChatHistory(sessions: ChatSession[]) {
    // 按 ID 去重后再追加
    const existingIds = new Set(chatHistory.value.map(c => c.id))
    const newSessions = sessions.filter(s => !existingIds.has(s.id))
    chatHistory.value.push(...newSessions)
  }

  function removeFromHistory(chatId: string) {
    const index = chatHistory.value.findIndex((c) => c.id === chatId)
    if (index !== -1) {
      chatHistory.value.splice(index, 1)
    }
  }

  function updateInHistory(chatId: string, updates: Partial<ChatSession>) {
    const chat = chatHistory.value.find((c) => c.id === chatId)
    if (chat) {
      Object.assign(chat, updates)
    }
  }

  function setFilter(filter: string) {
    historyFilter.value = filter
    offset.value = 0
  }

  function setLoading(flag: boolean) {
    loading.value = flag
  }

  function setHasMore(flag: boolean) {
    hasMore.value = flag
  }

  function setOffset(newOffset: number) {
    offset.value = newOffset
    currentOffset.value = newOffset
  }

  function clearHistory() {
    chatHistory.value = []
    offset.value = 0
    currentOffset.value = 0
    hasMore.value = true
  }

  return {
    chatHistory,
    historyFilter,
    hasMore,
    offset,
    loading,
    currentOffset,
    pageSize,
    filteredHistory,
    sortedHistory,
    setChatHistory,
    prependChatHistory,
    appendChatHistory,
    removeFromHistory,
    updateInHistory,
    setFilter,
    setLoading,
    setHasMore,
    setOffset,
    clearHistory,
  }
})
