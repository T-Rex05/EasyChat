// 聊天相关类型定义

/** 单步思考过程（每次 stream_reset 保存为一步） */
export interface ThinkingProcess {
  content: string
  timestamp?: string
}

/** 子 Agent 工具调用记录 */
export interface SubagentToolCall {
  tool_name: string
  preview?: string
  timestamp: string
}

/** 子 Agent 任务状态 */
export interface SubagentTask {
  subagent_id: string
  goal: string
  status: 'running' | 'completed' | 'failed'
  model?: string
  depth: number
  /** 流式输出文本（子 Agent 的回复） */
  output: string
  /** 工具调用记录 */
  tools: SubagentToolCall[]
  /** 执行时长（秒，完成时填充） */
  duration_seconds?: number
  /** Token 消耗（完成时填充） */
  tokens?: { input: number; output: number }
  /** API 调用次数 */
  api_calls?: number
  /** 完成摘要 */
  summary?: string
  /** 开始时间戳 */
  started_at: string
}

/** 聊天图片 */
export interface ChatImage {
  data_url: string
  mime: string
  filename?: string
}

/** 记忆引用（LLM 回答中标注的 [M1] 等引用的记忆详情） */
export interface MemoryCitation {
  id: number
  content: string
  memory_type: string
  created_at: string
}

/** 已上传的文件附件（显示在消息中） */
export interface ChatFile {
  filename: string
  size: number
  content_type: string
  /** 文本内容（注入提示词用，不存储到消息历史） */
  content?: string | null
  /** 是否可读文本 */
  readable: boolean
  /** 下载/查看 URL */
  url?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  conversation_id?: string
  status?: number
  source?: string
  json_data?: any
  rag_trace_ids?: string[]
  rag_decomposed?: boolean
  /** 思考过程列表（工具调用前的推理步骤，折叠展示） */
  thinkingProcesses?: ThinkingProcess[]
  /** 记忆引用列表（LLM 回答中标注的 [M1] 等引用的记忆详情） */
  memoryCitations?: MemoryCitation[]
  /** 图片附件（仅用户消息） */
  images?: ChatImage[]
  /** 文件附件（仅用户消息） */
  files?: ChatFile[]
  /** 用户反馈（1=赞，-1=踩） */
  feedback?: 1 | -1
  /** 子 Agent 委派任务列表（P0: 多 Agent 可视化） */
  subagentTasks?: SubagentTask[]
}

export interface ChatSession {
  id: string
  title: string
  source?: string
  user_question?: string
  create_time?: string
  update_time?: string
  end_time?: string
  start_time?: string
  is_schedule?: boolean | number
}

export interface StreamState {
  status: 'streaming' | 'completed' | 'stopped' | 'error'
  chatId: string
  clientMsgId?: string
  conversationId?: string
  assistantContent: string
  startedAt: number
  lastActivityAt?: number
  todos?: any[]
  eventSource?: EventSource
  close?: () => void
}

export interface SSEEvent {
  type: string
  content?: string
  thread_id?: string
  conversation_id?: string
  final_content?: string
  json_data?: any
  error?: string
  output?: string
  tool_name?: string
  rag_trace_ids?: string[]
  rag_decomposed?: boolean
}

export interface PendingStream {
  chatId: string
  userMessage: string
  clientMsgId?: string
  conversationId?: string
  startedAt: number
  userCancelled?: boolean
  todos?: any[]
}

export interface ChatCallbacks {
  onStart: (threadId: string, conversationId?: string) => void
  onChunk: (content: string, fullContent: string) => void
  onStatus: (text: string) => void
  onToolCall: (toolName: string) => void
  onToolOutput: (data: any) => void
  onStreamReset: (resetContent?: string) => void
  /** 流式思考过程（工具调用前的推理步骤，实时推送） */
  onThinkingStep?: (content: string) => void
  onExecApprovalRequest: (data: any) => void
  onDbWriteApprovalRequest: (data: any) => void
  onComplete: (data: any) => void
  onError: (error: string) => void
  /** P0: 子 Agent 开始执行 */
  onSubagentStart?: (data: any) => void
  /** P0: 子 Agent 流式 token */
  onSubagentToken?: (data: any) => void
  /** P0: 子 Agent 工具调用 */
  onSubagentTool?: (data: any) => void
  /** P0: 子 Agent 执行完成 */
  onSubagentComplete?: (data: any) => void
}
