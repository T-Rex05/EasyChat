// 聊天 API：SSE 流式 + 历史 + 取消 + 图片上传

import type { Message, ChatCallbacks, ChatImage, SubagentTask } from '@/types/chat'
import { useAuthStore } from '@/stores/auth'

const API_BASE = import.meta.env.VITE_API_BASE || ''

/** 已上传文件信息 */
export interface UploadedFile {
  filename: string
  size: number
  content_type: string
  content: string | null
  readable: boolean
}

/**
 * 上传聊天图片，返回 data_url 数组
 */
export async function uploadChatImages(files: File[]): Promise<ChatImage[]> {
  const form = new FormData()
  for (const f of files) {
    form.append('files', f)
  }

  const token = getAuthToken()
  const resp = await fetch(`${API_BASE}/api/chat/upload-images`, {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    body: form,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || '图片上传失败')
  }

  const data = await resp.json()
  return data.images || []
}

/**
 * 上传文件（md/pdf/txt/pptx 等），返回内容供前端注入提示词
 */
export async function uploadChatFiles(files: File[]): Promise<UploadedFile[]> {
  const form = new FormData()
  for (const f of files) {
    form.append('files', f)
  }

  const token = getAuthToken()
  const resp = await fetch(`${API_BASE}/api/chat/upload-files`, {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    body: form,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || '文件上传失败')
  }

  const data = await resp.json()
  return data.files || []
}

/**
 * 发送消息并建立 SSE 流式连接（GET 方式，纯文本）
 */
export function sendMessageStream(
  message: string,
  threadId: string,
  callbacks: ChatCallbacks,
  clientMsgId?: string,
  mode: string = 'normal',
  modelId?: number,
): { eventSource: EventSource; close: () => void } {
  // ── Token 预检 ──
  const token = getAuthToken()
  if (!token) {
    callbacks.onError?.('请先登录')
    // 返回一个假的 close 函数，保持接口一致
    return { eventSource: new EventSource('data:text/plain,'), close: () => {} }
  }
  // 不做本地过期预检：后端有宽限期刷新机制，由后端决定 token 是否可用
  // 如果 token 彻底失效，后端会返回 401，由下游处理

  const encodedMessage = encodeURIComponent(message)
  let url = `${API_BASE}/chat/stream?message=${encodedMessage}&thread_id=${threadId}`

  if (mode === 'disposal') {
    url += `&mode=disposal`
  }

  if (clientMsgId) {
    url += `&client_msg_id=${encodeURIComponent(clientMsgId)}`
  }

  if (modelId) {
    url += `&model_id=${modelId}`
  }

  // EventSource 无法携带 Header，登录态走 token 查询参数
  url += `&token=${encodeURIComponent(token)}`

  const eventSource = new EventSource(url)
  const state = { fullContent: '', isComplete: false }
  let manuallyClosed = false
  let connectionStartTime = Date.now()
  let receivedAnyMessage = false

  eventSource.addEventListener('message', (event) => {
    try {
      if (!event.data || event.data.trim() === '') {
        return
      }

      const data = JSON.parse(event.data)

      // ── 处理 token 续期事件 ──
      if (data.type === 'token_refresh' && data.token) {
        localStorage.setItem('authToken', data.token)
        try {
          const authStore = useAuthStore()
          authStore.token = data.token
        } catch { /* store 未初始化时忽略 */ }
        return
      }

      receivedAnyMessage = true
      dispatchStreamEvent(data, callbacks, state, () => eventSource.close())
    } catch (e: any) {
      if (callbacks.onError) {
        callbacks.onError(`解析事件失败：${e.message}`)
      }
      eventSource.close()
    }
  })

  eventSource.addEventListener('error', (_error) => {
    if (manuallyClosed) {
      return
    }
    if (eventSource.readyState === 2 && !state.isComplete) {
      // ── 区分认证失败和网络断开 ──
      // 如果连接建立后立刻断开（<3 秒）且没收到任何消息，基本是认证失败（401）
      const elapsed = Date.now() - connectionStartTime
      if (elapsed < 3000 && !receivedAnyMessage) {
        callbacks.onError?.('登录已过期，请重新登录')
      } else {
        callbacks.onError?.('SSE 连接意外断开，请重试')
      }
    }
  })

  return {
    eventSource,
    close: () => {
      manuallyClosed = true
      eventSource.close()
    },
  }
}

/**
 * 发送消息并建立 SSE 流式连接（POST 方式，支持图片）
 */
export function sendMessageStreamPost(
  message: string,
  threadId: string,
  callbacks: ChatCallbacks,
  clientMsgId?: string,
  mode: string = 'normal',
  images?: ChatImage[],
  files?: { filename: string; url: string; content?: string | null }[],
  modelId?: number,
): { close: () => void } {
  const token = getAuthToken()

  // ── Token 预检 ──
  if (!token) {
    callbacks.onError?.('请先登录')
    return { close: () => {} }
  }
  // 不做本地过期预检，同 GET 版：后端宽限期刷新机制处理

  const url = `${API_BASE}/chat/stream`

  const body: any = {
    message,
    thread_id: threadId,
    mode,
  }
  if (clientMsgId) {
    body.client_msg_id = clientMsgId
  }
  if (modelId) {
    body.model_id = modelId
  }
  if (images && images.length > 0) {
    body.images = images.map(img => ({ data_url: img.data_url, mime: img.mime }))
  }
  if (files && files.length > 0) {
    body.files = files.map(f => ({ filename: f.filename, url: f.url, content: f.content }))
  }

  const state = { fullContent: '', isComplete: false }
  let manuallyClosed = false
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null

  const abortController = new AbortController()

  // 启动 fetch 流式读取
  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: abortController.signal,
  }).then(async (response) => {
    // ── 401 认证失败：精确识别 ──
    if (response.status === 401) {
      callbacks.onError?.('登录已过期，请重新登录')
      localStorage.removeItem('authToken')
      window.location.href = '/login'
      return
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: '请求失败' }))
      callbacks.onError?.(err.detail || `HTTP ${response.status}`)
      return
    }

    // ── 自动接收续期 token（fetch 可读响应头） ──
    const newToken = response.headers.get('x-new-token')
    if (newToken) {
      localStorage.setItem('authToken', newToken)
      try {
        const authStore = useAuthStore()
        authStore.token = newToken
      } catch { /* store 未初始化时忽略 */ }
    }

    reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr || jsonStr === '{}') continue

          try {
            const data = JSON.parse(jsonStr)
            // 处理 token 续期事件（兜底：POST 也可能收到 SSE 事件）
            if (data.type === 'token_refresh' && data.token) {
              localStorage.setItem('authToken', data.token)
              continue
            }
            dispatchStreamEvent(data, callbacks, state, () => { /* noop - handled by onComplete */ })
          } catch {
            // skip malformed JSON
          }
        }
      }
    } catch (e: any) {
      if (!manuallyClosed && !state.isComplete) {
        callbacks.onError?.(`连接中断: ${e.message}`)
      }
    }
  }).catch((e) => {
    if (!manuallyClosed && !state.isComplete) {
      callbacks.onError?.(`请求失败: ${e.message}`)
    }
  })

  return {
    close: () => {
      manuallyClosed = true
      abortController.abort()
      reader?.cancel().catch(() => {})
    },
  }
}

/**
 * 分发 SSE 事件到对应回调
 */
function dispatchStreamEvent(
  data: any,
  callbacks: ChatCallbacks,
  state: { fullContent: string; isComplete: boolean },
  onClose: () => void
): void {
  switch (data.type) {
    case 'token':
      state.fullContent += data.content || ''
      if (callbacks.onChunk) {
        callbacks.onChunk(data.content, state.fullContent)
      }
      break

    case 'stream_reset':
      {
        const resetContent = state.fullContent
        state.fullContent = ''
        if (callbacks.onStreamReset) {
          callbacks.onStreamReset(resetContent || undefined)
        }
      }
      break

    case 'thinking_step':
      // 流式思考过程：工具调用前的推理步骤
      if (callbacks.onThinkingStep) {
        callbacks.onThinkingStep(data.content || '')
      }
      break

    case 'status':
      if (callbacks.onStatus) {
        callbacks.onStatus(data.content || '')
      }
      break

    case 'tool_call':
      if (callbacks.onToolCall) {
        callbacks.onToolCall(data.tool_name || '')
      }
      break

    case 'tool_output':
      if (callbacks.onToolOutput) {
        callbacks.onToolOutput(data)
      }
      break

    case 'exec_approval_request':
      if (callbacks.onExecApprovalRequest) {
        callbacks.onExecApprovalRequest(data)
      }
      break

    case 'db_write_approval_request':
      if (callbacks.onDbWriteApprovalRequest) {
        callbacks.onDbWriteApprovalRequest(data)
      }
      break

    case 'start':
    case 'chat_start':
      if (data.conversation_id && callbacks.onStart) {
        callbacks.onStart(data.thread_id || '', data.conversation_id)
      }
      break

    case 'chat_complete':
      state.isComplete = true
      if (callbacks.onComplete) {
        callbacks.onComplete(data)
      }
      onClose()
      break

    case 'error':
      state.isComplete = true
      if (callbacks.onError) {
        callbacks.onError(data.error || '未知错误')
      }
      onClose()
      break

    // ── P0: 子 Agent 委派事件 ──
    case 'subagent_start':
      callbacks.onSubagentStart?.(data)
      break

    case 'subagent_token':
      callbacks.onSubagentToken?.(data)
      break

    case 'subagent_tool':
      callbacks.onSubagentTool?.(data)
      break

    case 'subagent_complete':
      callbacks.onSubagentComplete?.(data)
      break

    default:
      console.warn('未知的 SSE 事件类型:', data.type)
  }
}

/**
 * 取消正在进行的流式生成
 */
export async function cancelStream(
  threadId: string,
  clientMsgId?: string,
  conversationId?: string
): Promise<boolean> {
  try {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE}/chat/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        thread_id: threadId,
        client_msg_id: clientMsgId,
        conversation_id: conversationId || null,
      }),
    })

    if (!response.ok) {
      return false
    }

    const data = await response.json()
    return data.run_cancelled === true
  } catch (error) {
    console.error('取消流式生成失败:', error)
    return false
  }
}

/**
 * 查询指定会话当前是否有待审批命令（页面切换后恢复审批卡片）
 */
export async function getPendingExecApproval(
  threadId: string
): Promise<{ pending: boolean; approval_id?: string; command?: string; description?: string } | null> {
  try {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE}/chat/exec-approval/pending?thread_id=${encodeURIComponent(threadId)}`, {
      headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
    })
    if (!response.ok) return null
    return await response.json()
  } catch (error) {
    console.error('查询待审批失败:', error)
    return null
  }
}

/**
 * 提交 exec 审批决议（允许本次/允许会话/拒绝）
 */
export async function resolveExecApproval(
  threadId: string, approvalId: string, decision: 'allow-once' | 'allow-session' | 'deny'
): Promise<boolean> {
  try {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE}/chat/exec-approval`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
      body: JSON.stringify({ thread_id: threadId, approval_id: approvalId, decision }),
    })
    if (!response.ok) return false
    const data = await response.json()
    return data.ok === true
  } catch (error) {
    console.error('审批决议失败:', error)
    return false
  }
}

/**
 * 提交聊天反馈（RAG 评测闭环入口：👍/👎）
 */
export async function submitFeedback(
  conversationId: string | number,
  rating: 1 | -1,
  comment?: string
): Promise<boolean> {
  try {
    const token = getAuthToken()
    const response = await fetch(`${API_BASE}/api/chat/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        conversation_id: conversationId,
        rating,
        comment: comment || '',
      }),
    })
    if (!response.ok) {
      console.error('提交反馈失败:', response.status)
      return false
    }
    return true
  } catch (error) {
    console.error('提交反馈失败:', error)
    return false
  }
}

/**
 * 把后端留痕表（delegation_tasks）的记录映射成前端 SubagentTask。
 *
 * 刷新/切会话后 SSE 帧早就没了，面板此前会直接消失；这些行是唯一的历史来源。
 * 状态收敛到前端的三态：running / completed / failed（error、interrupted、
 * runtime_lost、rejected_sync 都算失败，但 summary/error 里保留原始原因）。
 */
function mapHistorySubagentTasks(rows: any): SubagentTask[] | undefined {
  if (!Array.isArray(rows) || rows.length === 0) return undefined
  const mapStatus = (s: string): SubagentTask['status'] => {
    if (s === 'running') return 'running'
    if (s === 'completed') return 'completed'
    return 'failed'
  }
  const tasks: SubagentTask[] = rows.map((r: any, i: number) => {
    const input = Number(r.input_tokens) || 0
    const output = Number(r.output_tokens) || 0
    return {
      subagent_id: r.subagent_id || `${r.delegation_id || 'delegation'}-${r.task_index ?? i}`,
      goal: r.goal || '',
      status: mapStatus(String(r.status || 'completed')),
      model: r.model || undefined,
      depth: Number(r.depth) || 0,
      output: '',
      tools: [],
      duration_seconds: r.duration_seconds != null ? Number(r.duration_seconds) : undefined,
      tokens: (input || output) ? { input, output } : undefined,
      api_calls: r.api_calls != null ? Number(r.api_calls) : undefined,
      summary: r.summary || r.error_message || undefined,
      started_at: String(r.started_at || '').replace(' ', 'T'),
    }
  })
  return tasks.length ? tasks : undefined
}

/**
 * 获取聊天历史消息
 */
export async function getChatMessages(chatId: string): Promise<Message[]> {
  try {
    const response = await fetch(`${API_BASE}/api/history/${encodeURIComponent(chatId)}`, {
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Authorization': `Bearer ${getAuthToken()}`,
      },
    })

    if (response.ok) {
      const data = await response.json()
      const rawMessages = Array.isArray(data?.messages) ? data.messages : []
      return rawMessages.map((m: any, i: number) => {
        const conversationId = m.conversation_id
        return {
          id: m.id || (conversationId ? `${m.role}-${conversationId}` : `${m.role}-${i}`),
          role: m.role,
          content: m.content ?? '',
          timestamp: m.timestamp || '',
          conversation_id: conversationId,
          status: m.status,
          json_data: m.json_data || m.jsonData || null,
          images: m.images || null,
          subagentTasks: mapHistorySubagentTasks(m.subagent_tasks),
        }
      })
    }
  } catch (error) {
    console.warn('加载历史消息失败，重试旧接口:', error)
  }

  // 兜底
  try {
    const response = await fetch(`${API_BASE}/api/data/conversations/session/${encodeURIComponent(chatId)}`, {
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Authorization': `Bearer ${getAuthToken()}`,
      },
    })

    if (response.ok) {
      const conversations = await response.json()
      if (Array.isArray(conversations)) {
        return convertConversationsToMessages(conversations)
      }
    }
  } catch (error) {
    console.warn('数据层接口加载失败:', error)
  }

  return []
}

function getAuthToken(): string {
  try {
    return localStorage.getItem('authToken') || ''
  } catch { /* ignore */ }
  return ''
}

function convertConversationsToMessages(conversations: any[]): Message[] {
  if (!Array.isArray(conversations)) {
    return []
  }

  const messages: Message[] = []

  conversations.forEach((conv) => {
    const conversationId = conv.id || conv.conversation_id
    const userContent = String(conv.user_question || '').trim()
    const assistantContent = String(conv.agent_answer || '').trim()
    const status = typeof conv.status === 'number' ? conv.status : null
    const jsonData = conv.json_data || null

    if (userContent) {
      messages.push({
        id: `user-${conversationId}`,
        role: 'user',
        content: userContent,
        timestamp: formatApiTimestamp(conv.create_time),
        conversation_id: conversationId,
        status,
      })
    }

    let displayContent = assistantContent
    if (status === 2 && !displayContent) {
      displayContent = '️ 请求异常，可能为网络波动，请刷新或者重试。'
    } else if (status === 3 && !displayContent) {
      displayContent = '⏹️ 已中断输出。'
    } else if (status === 3 && displayContent) {
      displayContent = displayContent + '\n\n---\n⏹️ 已中断输出'
    }

    if (displayContent) {
      messages.push({
        id: `assistant-${conversationId}`,
        role: 'assistant',
        content: displayContent,
        json_data: jsonData,
        timestamp: formatApiTimestamp(conv.update_time || conv.create_time),
        conversation_id: conversationId,
        status,
      })
    }
  })

  return messages
}

function formatApiTimestamp(value: string): string {
  if (!value) return ''
  return String(value).trim().replace(' ', 'T')
}
