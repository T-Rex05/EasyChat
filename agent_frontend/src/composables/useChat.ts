// 聊天核心逻辑 composable

import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { sendMessageStream, sendMessageStreamPost, uploadChatImages, uploadChatFiles, cancelStream, getChatMessages, resolveExecApproval, type UploadedFile } from '@/api/chat'
import { generateUUID } from '@/utils/uuid'
import type { Message, ChatCallbacks, ChatImage, ThinkingProcess, SubagentTask } from '@/types/chat'

/** 将后端 process_log JSON 字符串解析为 ThinkingProcess 数组 */
function parseProcessLog(processLog?: string): { content: string; timestamp: string }[] {
  if (!processLog) return []
  try {
    const items = JSON.parse(processLog)
    if (!Array.isArray(items)) return []
    // 后端返回的是简单的字符串列表，直接转换为 ThinkingProcess
    return items
      .filter((item: any) => typeof item === 'string' && item.trim())
      .map((note: string) => ({
        content: note.trim(),
        timestamp: new Date().toISOString()
      }))
  } catch {
    return []
  }
}

function truncate(s: any, maxLen: number): string {
  const str = typeof s === 'string' ? s : JSON.stringify(s || '')
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str
}

/** 合并已有流式思考步骤和后端补全步骤，按内容去重 */
function mergeThinkingSteps(
  existing: ThinkingProcess[],
  backend: ThinkingProcess[],
): ThinkingProcess[] {
  const seen = new Set(existing.map((s) => s.content.trim()))
  const merged = [...existing]
  for (const s of backend) {
    const key = s.content.trim()
    if (key && !seen.has(key)) {
      seen.add(key)
      merged.push(s)
    }
  }
  return merged
}

export function useChat(chatMode: string = 'normal') {
  const chatStore = useChatStore()

  const inputMessage = ref('')
  const currentEventSource = ref<EventSource | null>(null)
  const currentCloseFn = ref<(() => void) | null>(null)
  // 图片附件
  const attachedImages = ref<ChatImage[]>([])
  // 正在上传图片
  const uploadingImages = ref(false)
  // exec 审批卡片（主机白名单远程命令 / 危险命令）
  const pendingApproval = ref<{ approvalId: string; command: string; description: string } | null>(null)
  // 手动选择的模型 ID（null = 走路由器自动选择）
  const selectedModelId = ref<number | null>(null)

  // 计算属性
  const messages = computed(() => chatStore.messages)
  const hasMessages = computed(() => chatStore.hasMessages)
  const isStreaming = computed(() => chatStore.isStreaming)
  const currentChatId = computed(() => chatStore.currentChatId)
  const currentStreamState = computed(() => chatStore.currentStreamState)

  // 添加图片（从文件）
  async function addImagesFromFiles(files: FileList | File[]) {
    const fileArr = Array.from(files).filter(f => f.type.startsWith('image/'))
    if (fileArr.length === 0) return

    uploadingImages.value = true
    try {
      const uploaded = await uploadChatImages(fileArr)
      attachedImages.value.push(...uploaded)
    } catch (e: any) {
      console.error('图片上传失败:', e)
      alert('图片上传失败: ' + (e.message || '未知错误'))
    } finally {
      uploadingImages.value = false
    }
  }

  // 添加图片（从 data URL — 粘贴/拖拽）
  function addImageFromDataUrl(dataUrl: string, mime?: string) {
    const mimeType = mime || dataUrl.split(';')[0]?.replace('data:', '') || 'image/png'
    attachedImages.value.push({
      data_url: dataUrl,
      mime: mimeType,
    })
  }

  // 移除图片
  function removeImage(index: number) {
    attachedImages.value.splice(index, 1)
  }

  // 清空图片
  function clearImages() {
    attachedImages.value = []
  }

  // ── 文件附件 ──
  const attachedFiles = ref<UploadedFile[]>([])
  const uploadingFiles = ref(false)

  async function addFilesFromInput(files: FileList | File[]) {
    const fileArr = Array.from(files)
    if (fileArr.length === 0) return

    uploadingFiles.value = true
    try {
      const uploaded = await uploadChatFiles(fileArr)
      attachedFiles.value.push(...uploaded)
    } catch (e: any) {
      console.error('文件上传失败:', e)
      alert('文件上传失败: ' + (e.message || '未知错误'))
    } finally {
      uploadingFiles.value = false
    }
  }

  function removeFile(index: number) {
    attachedFiles.value.splice(index, 1)
  }

  function clearFiles() {
    attachedFiles.value = []
  }

  // 发送消息
  async function sendMessage(message?: string) {
    const text = (message || inputMessage.value).trim()
    const hasImages = attachedImages.value.length > 0
    const hasFiles = attachedFiles.value.length > 0
    if ((!text && !hasImages && !hasFiles) || isStreaming.value) return

    // 清空输入
    inputMessage.value = ''

    // 判断是否为新会话
    let chatId = currentChatId.value
    const isNewChat = !chatId || messages.value.length === 0
    if (isNewChat) {
      const userId = localStorage.getItem('chatUserId') || '1'
      chatId = `${userId}_${Date.now()}`
      chatStore.setCurrentChatId(chatId)
    }

    // 快照当前图片和文件（在清空前）
    const currentImages = [...attachedImages.value]
    const currentFiles = [...attachedFiles.value]
    clearImages()
    clearFiles()

    // 新会话立即添加到侧边栏
    if (isNewChat) {
      const titleText = text || (currentFiles.length > 0 ? currentFiles[0].filename : currentImages.length > 0 ? '[图片]' : '[新对话]')
      window.dispatchEvent(new CustomEvent('chat:newSession', {
        detail: { chatId, title: titleText.substring(0, 20) }
      }))
    }

    // 传给 API 的文件列表（含内容用于后端注入 LLM）
    const filesForApi = currentFiles.map(f => ({
      filename: f.filename, url: (f as any).url || '', content: f.content || '',
    }))
    // 存入消息的文件列表（仅元数据，不含内容）
    const messageFiles = currentFiles.length > 0 ? currentFiles.map(f => ({
      filename: f.filename, size: f.size, content_type: f.content_type,
      readable: f.readable, url: (f as any).url || '',
    })) : undefined

    let displayText = text || ''
    if (!displayText && currentImages.length > 0) displayText = '[图片消息]'
    if (!displayText && currentFiles.length > 0) displayText = '[文件消息]'

    // 用户消息（消息文本不含文件内容）
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: displayText,
      timestamp: new Date().toLocaleString('zh-CN'),
      images: currentImages.length > 0 ? currentImages : undefined,
      files: messageFiles,
    }
    chatStore.addMessage(userMessage)

    // 创建流式会话状态
    const clientMsgId = generateUUID()
    const streamState = chatStore.createStreamingSession(chatId, clientMsgId)

    // 添加空的助手消息占位
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toLocaleString('zh-CN'),
    }
    chatStore.addMessage(assistantMessage)

    // 保存 pending stream 到 sessionStorage
    chatStore.savePendingStreamsToStorage(chatId, {
      chatId,
      userMessage: text,
      clientMsgId,
      startedAt: Date.now(),
    })

    // 建立 SSE 连接
    // 阈值判断：长消息（>1500字符）用 POST 避免 URL 长度限制
    const usePost = hasImages || hasFiles || text.length > 1500
    try {
      if (usePost) {
        // 使用 POST 方式（支持图片/文件附件，或长消息）
        const { close } = sendMessageStreamPost(
          text, chatId, createCallbacks(streamState), clientMsgId, chatMode,
          currentImages.length > 0 ? currentImages : undefined,
          filesForApi.length > 0 ? filesForApi : undefined,
          selectedModelId.value || undefined,
        )
        currentCloseFn.value = close
      } else {
        // 使用 GET EventSource（纯文本短消息）
        const { eventSource, close } = sendMessageStream(
          text, chatId, createCallbacks(streamState), clientMsgId, chatMode,
          selectedModelId.value || undefined,
        )
        currentEventSource.value = eventSource
        currentCloseFn.value = close
      }
    } catch (error) {
      console.error('SSE 连接失败:', error)
      cleanup()
    }
  }

  // 创建 SSE 回调
  function createCallbacks(streamState: any): ChatCallbacks {
    // 所有消息操作都针对 streamState.chatId，切换会话后旧会话流式在后台继续累积
    const cid = streamState.chatId

    return {
      onStart: (threadId, conversationId) => {
        console.log('SSE 开始:', threadId, conversationId)
        if (conversationId) {
          chatStore.updateStreamingSession(cid, { conversationId })
        }
      },

      onChunk: (_content, fullContent) => {
        chatStore.updateLastAssistantMessage(fullContent, undefined, cid)
      },

      onStatus: (text) => {
        console.log('状态:', text)
      },

      onToolCall: (toolName) => {
        console.log('工具调用:', toolName)
        chatStore.updateStreamingSession(cid, {
          lastActivityAt: Date.now(),
        })
      },

      onToolOutput: (data) => {
        console.log('工具输出:', data)
        chatStore.updateStreamingSession(cid, {
          lastActivityAt: Date.now(),
        })
      },

      onStreamReset: (resetContent?: string) => {
        if (resetContent && resetContent.trim()) {
          chatStore.appendThinkingProcess(resetContent.trim(), cid)
        }
        chatStore.updateLastAssistantMessage('', undefined, cid)
      },

      onThinkingStep: (content: string) => {
        // 流式思考过程：直接保存，无需等待 stream_reset
        if (content && content.trim()) {
          chatStore.appendThinkingProcess(content.trim(), cid)
        }
      },

      onExecApprovalRequest: (data) => {
        pendingApproval.value = {
          approvalId: data.approval_id || '',
          command: data.command || '',
          description: data.description || '',
        }
      },

      onDbWriteApprovalRequest: (data) => {
        console.log('数据库写入审批:', data)
      },

      onComplete: (data) => {
        console.log('完成:', data)
        const finalContent = data.final_content || data.content || ''
        if (finalContent) {
          // 思考过程只使用流式推送的内容，不再合并 process_log
          // （避免重复：流式已经推送过的，后端 process_log 可能也有）
          const metadata: any = {
            conversation_id: data.conversation_id,
            json_data: data.json_data,
          }
          // 记忆引用
          if (data.memory_citations?.length) {
            metadata.memoryCitations = data.memory_citations
          }
          // 不再合并 process_log，保留流式推送的思考过程
          const chatMsgs = chatStore.getMessages(cid)
          const existingTPs = chatMsgs[chatMsgs.length - 1]?.thinkingProcesses || []
          if (existingTPs.length > 0) {
            metadata.thinkingProcesses = existingTPs
          }
          chatStore.updateLastAssistantMessage(finalContent, metadata, cid)
        }
        cleanup()
        window.dispatchEvent(new CustomEvent('chat:refreshHistory'))
      },

      onError: (error) => {
        console.error('错误:', error)
        chatStore.updateLastAssistantMessage(`错误：${error}`, undefined, cid)
        cleanup()
      },

      // ── P0: 子 Agent 委派事件 ──
      onSubagentStart: (data) => {
        // 空 subagent_id 的帧直接丢弃（后续帧都按 id 匹配，收下只会变僵尸卡片）
        if (!data?.subagent_id) return
        const task: SubagentTask = {
          subagent_id: data.subagent_id,
          goal: data.goal || '',
          status: 'running',
          model: data.model || undefined,
          depth: data.depth || 0,
          output: '',
          tools: [],
          started_at: new Date().toISOString(),
        }
        chatStore.addSubagentTask(task, cid)
      },

      onSubagentToken: (data) => {
        chatStore.appendSubagentToken(data.subagent_id || '', data.content || '', cid)
      },

      onSubagentTool: (data) => {
        chatStore.addSubagentToolCall(
          data.subagent_id || '',
          data.tool_name || '',
          data.preview,
          cid,
        )
      },

      onSubagentComplete: (data) => {
        chatStore.completeSubagentTask(data.subagent_id || '', {
          status: data.status,
          summary: data.summary,
          duration_seconds: data.duration_seconds,
          tokens: data.tokens,
          api_calls: data.api_calls,
        }, cid)
      },
    }
  }

  // 审批决议
  async function approveExec(decision: 'allow-once' | 'allow-session' | 'deny') {
    const pa = pendingApproval.value
    if (!pa || !currentChatId.value) return
    await resolveExecApproval(currentChatId.value, pa.approvalId, decision)
    pendingApproval.value = null
  }

  // 停止流式生成
  async function stopStream() {
    if (currentCloseFn.value) {
      currentCloseFn.value()
    }

    if (currentChatId.value) {
      const streamState = chatStore.getStreamingSession(currentChatId.value)
      await cancelStream(
        currentChatId.value,
        streamState?.clientMsgId,
        streamState?.conversationId
      )
    }

    cleanup()
    chatStore.updateLastAssistantMessage('⏹️ 已停止输出')
  }

  // 清理流式状态
  function cleanup() {
    if (currentEventSource.value) {
      currentEventSource.value.close()
      currentEventSource.value = null
    }
    if (currentCloseFn.value) {
      currentCloseFn.value = null
    }

    if (currentChatId.value) {
      chatStore.removeStreamingSession(currentChatId.value)
      chatStore.clearPendingStreamFromStorage(currentChatId.value)
    }
  }

  // 加载聊天历史
  async function loadChatHistory(chatId: string) {
    const prevChatId = chatStore.currentChatId
    console.log('loadChatHistory called:', chatId, 'current:', prevChatId, 'msgs:', chatStore.messages.length)

    if (prevChatId === chatId && chatStore.messages.length > 0) {
      console.log('跳过加载：当前会话已有消息')
      return
    }

    // 如果目标会话正在流式中，内存已有流式中间状态，不要从后端覆盖
    const targetStreamState = chatStore.getStreamingSession(chatId)
    const existingMsgs = chatStore.getMessages(chatId)
    if ((targetStreamState && targetStreamState.status === 'streaming') || existingMsgs.length > 0) {
      console.log('跳过加载：目标会话内存已有数据，使用内存数据')
      chatStore.setCurrentChatId(chatId)
      return
    }

    try {
      chatStore.setCurrentChatId(chatId)
      const historyMessages = await getChatMessages(chatId)
      console.log('加载到消息:', historyMessages.length, '条')
      chatStore.setMessages(historyMessages)
      console.log('setMessages 后 messages 长度:', chatStore.messages.length, 'currentChatId:', chatStore.currentChatId)
    } catch (error) {
      console.error('加载历史消息失败:', error)
    }
  }

  // 新建对话
  function newChat() {
    chatStore.setCurrentChatId('')
    chatStore.clearMessages()
    chatStore.clearPendingMessages()
    clearImages()
  }

  // 恢复流式连接（刷新后调用）
  async function reconnectStream(chatId: string): Promise<boolean> {
    const pending = chatStore.loadPendingStreamsFromStorage()
    const pendingStream = pending[chatId]
    if (!pendingStream) return false
    // 超过 5 分钟视为过期（后端 RUN_TTL=300s），不再重连
    if (Date.now() - pendingStream.startedAt > 5 * 60 * 1000) {
      chatStore.clearPendingStreamFromStorage(chatId)
      return false
    }

    console.log('[useChat] 恢复流式连接:', chatId, pendingStream.userMessage)
    chatStore.setCurrentChatId(chatId)

    // 先加载已有消息（含后端已持久化的部分回复）
    try {
      const historyMessages = await getChatMessages(chatId)
      chatStore.setMessages(historyMessages)
    } catch (e) {
      console.warn('[useChat] 恢复时加载历史消息失败:', e)
    }

    // 如果末尾已有完整的助手回复（后端已完成并持久化），无需重连
    const msgs = chatStore.getMessages(chatId)
    const lastMsg = msgs[msgs.length - 1]
    if (lastMsg?.role === 'assistant' && lastMsg.content && (lastMsg as any).status === 'completed') {
      chatStore.clearPendingStreamFromStorage(chatId)
      return false
    }

    // 创建流式会话，用相同的 client_msg_id 让后端命中 ring buffer 断线续传
    const clientMsgId = pendingStream.clientMsgId || generateUUID()
    chatStore.createStreamingSession(chatId, clientMsgId)

    // 末尾没有助手消息占位时才添加（后端回放帧会更新最后一条 assistant 消息）
    if (!lastMsg || lastMsg.role !== 'assistant') {
      chatStore.addMessage({
        id: `assistant-reconnect-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleString('zh-CN'),
      })
    }

    // 建立 SSE 连接（后端会先回放 ring buffer 已有帧，再续传后续帧）
    const streamState = chatStore.getStreamingSession(chatId)!
    const callbacks = createCallbacks(streamState)
    const usePost = pendingStream.userMessage.length > 1500

    try {
      if (usePost) {
        const { close } = sendMessageStreamPost(
          pendingStream.userMessage, chatId, callbacks, clientMsgId, 'normal',
        )
        currentCloseFn.value = close
      } else {
        const { eventSource, close } = sendMessageStream(
          pendingStream.userMessage, chatId, callbacks, clientMsgId,
        )
        currentEventSource.value = eventSource
        currentCloseFn.value = close
      }
      return true
    } catch (e) {
      console.warn('[useChat] 重连 SSE 失败:', e)
      cleanup()
      return false
    }
  }

  // 快捷发送
  function sendQuickPrompt(message: string) {
    sendMessage(message)
  }

  return {
    inputMessage,
    messages,
    hasMessages,
    isStreaming,
    currentChatId,
    currentStreamState,
    attachedImages,
    uploadingImages,
    sendMessage,
    stopStream,
    loadChatHistory,
    reconnectStream,
    newChat,
    sendQuickPrompt,
    cleanup,
    addImagesFromFiles,
    addImageFromDataUrl,
    removeImage,
    clearImages,
    // 文件
    attachedFiles,
    uploadingFiles,
    addFilesFromInput,
    removeFile,
    clearFiles,
    // exec 审批
    pendingApproval,
    approveExec,
    // 模型选择
    selectedModelId,
  }
}
