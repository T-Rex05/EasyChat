// 聊天状态管理

import { defineStore } from 'pinia'
import { reactive, ref, computed } from 'vue'
import type { Message, StreamState, PendingStream, SubagentTask, SubagentToolCall } from '@/types/chat'

// LRU 缓存上限：最多保留 N 个会话的消息在内存中，超出的自动淘汰（切换回来时从后端重新加载）
const MAX_CACHED_SESSIONS = 8

export const useChatStore = defineStore('chat', () => {
  // 状态
  const currentChatId = ref<string>(sessionStorage.getItem('currentChatId') || '')
  // 每个会话独立存储消息，流式 token 在后台继续写入对应会话，切换不丢失
  const messagesByChat = reactive<Record<string, Message[]>>({})
  const streamingSessions = ref<Map<string, StreamState>>(new Map())
  const pendingUserMessages = ref<string[]>([])
  const autoScroll = ref(true)

  // LRU: 每个会话的最后访问时间，用于淘汰决策
  const sessionLastAccess = new Map<string, number>()

  // 计算属性
  const messages = computed<Message[]>(() => {
    if (!currentChatId.value) return []
    return messagesByChat[currentChatId.value] || []
  })

  const hasMessages = computed(() => messages.value.length > 0)

  // 当前会话是否正在流式输出（按会话隔离）
  const isStreaming = computed(() => {
    if (!currentChatId.value) return false
    const state = streamingSessions.value.get(currentChatId.value)
    return state?.status === 'streaming'
  })

  const currentStreamState = computed(() => {
    if (!currentChatId.value) return null
    return streamingSessions.value.get(currentChatId.value) || null
  })

  // 内部：获取指定会话的消息数组（不存在则创建）
  function _messagesOf(chatId?: string): Message[] {
    const cid = chatId || currentChatId.value
    if (!cid) return []
    if (!messagesByChat[cid]) messagesByChat[cid] = []
    return messagesByChat[cid]
  }

  // ── LRU 内部方法 ──

  /** 更新会话最后访问时间 */
  function _touchSession(chatId: string) {
    sessionLastAccess.set(chatId, Date.now())
  }

  /** 淘汰最久不活跃的会话消息，释放内存。流式中的会话永不淘汰。 */
  function _evictStaleSessions() {
    const allIds = Object.keys(messagesByChat).filter(id => messagesByChat[id]?.length > 0)
    if (allIds.length <= MAX_CACHED_SESSIONS) return

    const current = currentChatId.value
    // 正在流式输出的会话必须保留（后台继续累积 token）
    const streamingIds = new Set<string>()
    streamingSessions.value.forEach((state, id) => {
      if (state.status === 'streaming') streamingIds.add(id)
    })

    // 必须保留：当前会话 + 流式中的会话
    const mustKeep = new Set<string>([current, ...streamingIds].filter(Boolean))

    // 可淘汰的会话按最后访问时间排序
    const evictable = allIds
      .filter(id => !mustKeep.has(id))
      .map(id => ({ id, ts: sessionLastAccess.get(id) || 0 }))
      .sort((a, b) => b.ts - a.ts)

    // 保留 MAX_CACHED_SESSIONS - mustKeep.size 个最近访问的
    const keepCount = Math.max(0, MAX_CACHED_SESSIONS - mustKeep.size)

    for (const e of evictable.slice(keepCount)) {
      delete messagesByChat[e.id]
      sessionLastAccess.delete(e.id)
    }
  }

  // 操作
  function setCurrentChatId(chatId: string) {
    currentChatId.value = chatId
    sessionStorage.setItem('currentChatId', chatId)
    if (chatId) {
      _touchSession(chatId)
      // 延迟淘汰，避免影响当前操作
      setTimeout(_evictStaleSessions, 0)
    }
  }

  function setMessages(newMessages: Message[], chatId?: string) {
    const cid = chatId || currentChatId.value
    if (!cid) return
    messagesByChat[cid] = [...newMessages]
    _touchSession(cid)
  }

  function addMessage(message: Message, chatId?: string) {
    _messagesOf(chatId).push(message)
  }

  function updateLastAssistantMessage(content: string, metadata?: Partial<Message>, chatId?: string) {
    const cid = chatId || currentChatId.value
    // 如果会话已被 LRU 淘汰，跳过写入（流式回调安全忽略）
    const msgs = cid ? messagesByChat[cid] : undefined
    if (!msgs || msgs.length === 0) return
    const lastMsg = msgs[msgs.length - 1]
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.content = content
      if (metadata) {
        // 保留已有的 thinkingProcesses（除非 metadata 显式覆盖）
        if (!metadata.thinkingProcesses && lastMsg.thinkingProcesses?.length) {
          metadata.thinkingProcesses = lastMsg.thinkingProcesses
        }
        Object.assign(lastMsg, metadata)
      }
    }
  }

  /** 将当前积累的文本保存为一步思考过程（stream_reset 时调用） */
  function appendThinkingProcess(content: string, chatId?: string) {
    if (!content || !content.trim()) return
    const cid = chatId || currentChatId.value
    // 如果会话已被 LRU 淘汰，跳过写入
    const msgs = cid ? messagesByChat[cid] : undefined
    if (!msgs || msgs.length === 0) return
    const lastMsg = msgs[msgs.length - 1]
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!lastMsg.thinkingProcesses) {
        lastMsg.thinkingProcesses = []
      }
      // 去重：检查是否已存在相似内容（包含关系或高相似度）
      const trimmedContent = content.trim()
      const exists = lastMsg.thinkingProcesses.some(tp => {
        const existing = tp.content.trim()
        // 完全相同
        if (existing === trimmedContent) return true
        // 包含关系
        if (existing.includes(trimmedContent) || trimmedContent.includes(existing)) return true
        // 高相似度（去掉标点后比较）
        const normalize = (s: string) => s.replace(/[，。！？、：；""''（）\s]/g, '')
        const n1 = normalize(existing)
        const n2 = normalize(trimmedContent)
        if (n1 === n2) return true
        // 相似度 > 80%
        if (n1.length > 0 && n2.length > 0) {
          const longer = n1.length > n2.length ? n1 : n2
          const shorter = n1.length > n2.length ? n2 : n1
          if (longer.includes(shorter) && shorter.length / longer.length > 0.8) return true
        }
        return false
      })
      if (!exists) {
        lastMsg.thinkingProcesses.push({
          content: trimmedContent,
          timestamp: new Date().toISOString(),
        })
      }
    }
  }

  function clearMessages(chatId?: string) {
    const cid = chatId || currentChatId.value
    if (cid) {
      delete messagesByChat[cid]
      sessionLastAccess.delete(cid)
    }
  }

  /** 读取用：不创建空数组（避免副作用导致 LRU 误判） */
  function getMessages(chatId?: string): Message[] {
    const cid = chatId || currentChatId.value
    if (!cid) return []
    return messagesByChat[cid] || []
  }

  function resetAll() {
    currentChatId.value = ''
    Object.keys(messagesByChat).forEach((k) => delete messagesByChat[k])
    streamingSessions.value = new Map()
    pendingUserMessages.value = []
    sessionLastAccess.clear()
    sessionStorage.removeItem('currentChatId')
  }

  // setStreaming 保留兼容，但实际状态由 streamingSessions 驱动
  function setStreaming(streaming: boolean) {
    // 如果当前会话存在流式会话，更新其状态
    if (currentChatId.value) {
      const state = streamingSessions.value.get(currentChatId.value)
      if (state && streaming) {
        state.status = 'streaming'
      }
    }
  }

  function createStreamingSession(chatId: string, clientMsgId?: string): StreamState {
    const state: StreamState = {
      status: 'streaming',
      chatId,
      clientMsgId,
      assistantContent: '',
      startedAt: Date.now(),
      lastActivityAt: Date.now(),
    }

    streamingSessions.value.set(chatId, state)
    return state
  }

  function updateStreamingSession(chatId: string, updates: Partial<StreamState>) {
    const state = streamingSessions.value.get(chatId)
    if (state) {
      Object.assign(state, updates)
      state.lastActivityAt = Date.now()
    }
  }

  function removeStreamingSession(chatId: string) {
    streamingSessions.value.delete(chatId)
  }

  function getStreamingSession(chatId: string): StreamState | null {
    return streamingSessions.value.get(chatId) || null
  }

  function queueUserMessage(message: string) {
    // 最多排队 2 条
    if (pendingUserMessages.value.length < 2) {
      pendingUserMessages.value.push(message)
      return true
    }
    return false
  }

  function dequeueUserMessage(): string | null {
    return pendingUserMessages.value.shift() || null
  }

  function clearPendingMessages() {
    pendingUserMessages.value = []
  }

  function setAutoScroll(enabled: boolean) {
    autoScroll.value = enabled
  }

  // 持久化 pending streams 到 sessionStorage
  function savePendingStreamsToStorage(chatId: string, stream: PendingStream) {
    const pending = JSON.parse(sessionStorage.getItem('pendingStreams') || '{}')
    pending[chatId] = stream
    sessionStorage.setItem('pendingStreams', JSON.stringify(pending))
  }

  function loadPendingStreamsFromStorage(): Record<string, PendingStream> {
    return JSON.parse(sessionStorage.getItem('pendingStreams') || '{}')
  }

  function clearPendingStreamFromStorage(chatId: string) {
    const pending = loadPendingStreamsFromStorage()
    delete pending[chatId]
    sessionStorage.setItem('pendingStreams', JSON.stringify(pending))
  }

  // ── P0: 子 Agent 委派状态管理 ──

  /** 获取当前会话最后一条 assistant 消息（安全访问） */
  function _lastAssistant(chatId?: string) {
    const cid = chatId || currentChatId.value
    const msgs = cid ? messagesByChat[cid] : undefined
    if (!msgs || msgs.length === 0) return null
    const last = msgs[msgs.length - 1]
    return last?.role === 'assistant' ? last : null
  }

  /** 添加子 Agent 任务（按 subagent_id 幂等：重复/迟到的 start 帧不会产生重复卡片） */
  function addSubagentTask(task: SubagentTask, chatId?: string) {
    const msg = _lastAssistant(chatId)
    if (!msg) return
    // 空 id 直接丢弃：后端所有后续帧都按 subagent_id 匹配，收下只会变成永远"执行中"的僵尸卡片
    if (!task?.subagent_id) return
    if (!msg.subagentTasks) msg.subagentTasks = []
    const exists = msg.subagentTasks.find(t => t.subagent_id === task.subagent_id)
    if (exists) {
      // 重放：只刷新目标/模型等元信息，不重置已累积的 output/tools/status
      exists.goal = exists.goal || task.goal
      exists.model = exists.model || task.model
      exists.depth = task.depth ?? exists.depth
      return
    }
    msg.subagentTasks.push(task)
  }

  /** 追加子 Agent 流式 token */
  function appendSubagentToken(subagentId: string, content: string, chatId?: string) {
    if (!subagentId || !content) return
    const msg = _lastAssistant(chatId)
    if (!msg?.subagentTasks) return
    const task = msg.subagentTasks.find(t => t.subagent_id === subagentId)
    if (task) {
      task.output += content
    }
  }

  /** 添加子 Agent 工具调用记录 */
  function addSubagentToolCall(subagentId: string, toolName: string, preview?: string, chatId?: string) {
    if (!subagentId || !toolName) return
    const msg = _lastAssistant(chatId)
    if (!msg?.subagentTasks) return
    const task = msg.subagentTasks.find(t => t.subagent_id === subagentId)
    if (task) {
      if (!task.tools) task.tools = []
      const call: SubagentToolCall = {
        tool_name: toolName,
        preview: preview || undefined,
        timestamp: new Date().toISOString(),
      }
      task.tools.push(call)
    }
  }

  /** 完成子 Agent 任务（填充统计信息）
   *
   * 注意：只覆盖后端真的传了的字段。此前无条件赋值会把 undefined 写进 summary/tokens，
   * 把已经拿到的数据抹掉。
   */
  function completeSubagentTask(subagentId: string, data: {
    status?: string
    summary?: string
    duration_seconds?: number
    tokens?: { input: number; output: number }
    api_calls?: number
  }, chatId?: string) {
    if (!subagentId) return
    const msg = _lastAssistant(chatId)
    if (!msg?.subagentTasks) return
    const task = msg.subagentTasks.find(t => t.subagent_id === subagentId)
    if (task) {
      // 运行时校验 status 值，避免非法状态
      const validStatuses: ReadonlyArray<SubagentTask['status']> = ['running', 'completed', 'failed']
      const rawStatus = data.status || 'completed'
      task.status = validStatuses.includes(rawStatus as SubagentTask['status'])
        ? rawStatus as SubagentTask['status']
        : 'completed'
      if (data.summary !== undefined) task.summary = data.summary
      if (data.duration_seconds !== undefined) task.duration_seconds = data.duration_seconds
      // 后端空 tokens 是 {}（真值），面板会显示 "0 tokens" —— 只有真的有数字才写
      if (data.tokens && (data.tokens.input || data.tokens.output)) task.tokens = data.tokens
      if (data.api_calls !== undefined) task.api_calls = data.api_calls
    }
  }

  return {
    currentChatId,
    messages,
    isStreaming,
    streamingSessions,
    pendingUserMessages,
    autoScroll,
    hasMessages,
    currentStreamState,
    setCurrentChatId,
    setMessages,
    addMessage,
    updateLastAssistantMessage,
    appendThinkingProcess,
    clearMessages,
    getMessages,
    resetAll,
    setStreaming,
    createStreamingSession,
    updateStreamingSession,
    removeStreamingSession,
    getStreamingSession,
    queueUserMessage,
    dequeueUserMessage,
    clearPendingMessages,
    setAutoScroll,
    savePendingStreamsToStorage,
    loadPendingStreamsFromStorage,
    clearPendingStreamFromStorage,
    // P0: 子 Agent 委派
    addSubagentTask,
    appendSubagentToken,
    addSubagentToolCall,
    completeSubagentTask,
  }
})
