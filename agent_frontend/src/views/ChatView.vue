<template>
  <div class="chat-view">
    <!-- 左侧历史侧边栏 -->
    <ChatSidebar ref="sidebarRef" />

    <!-- 主聊天区域 -->
    <div class="chat-main">
      <!-- 顶部栏 -->
      <header class="chat-header">
        <div class="header-title">
          <div class="header-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
          </div>
          <div class="header-titles">
            <h2 class="page-title">智能对话</h2>
            <span class="page-subtitle">与 AI 智能体自由交流</span>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn-new-chat" @click="newChat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>新对话</span>
          </button>
        </div>
      </header>

      <!-- 消息列表 -->
      <div class="messages-container" ref="messagesContainer">
        <!-- 欢迎屏幕 -->
        <div v-if="!hasMessages" class="welcome-screen">
          <div class="welcome-icon-wrap">
            <div class="welcome-icon">
              <svg viewBox="0 0 36 36" fill="none">
                <defs>
                  <linearGradient id="welcomeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#4e6ef2" />
                    <stop offset="100%" stop-color="#6b83f5" />
                  </linearGradient>
                </defs>
                <rect width="36" height="36" rx="11" fill="url(#welcomeGrad)" />
                <path d="M18 9l7.5 3.3v4.7c0 5.2-3.3 8.4-7.5 9.8-4.2-1.4-7.5-4.6-7.5-9.8v-4.7L18 9z"
                      fill="rgba(255,255,255,0.92)" stroke="none" />
              </svg>
            </div>
          </div>
          <h2 class="welcome-title">你好，欢迎使用 AgentForge</h2>
          <p class="welcome-desc">我是您的 AI 智能助手，可以回答问题、执行任务、分析信息。</p>
          <div class="quick-prompts">
            <button @click="sendQuickPrompt('现在几点')" class="prompt-card">
              <span class="prompt-icon">⏰</span>
              <span class="prompt-text">现在几点</span>
            </button>
            <button @click="sendQuickPrompt('帮我总结一下今天的新闻')" class="prompt-card">
              <span class="prompt-icon">📰</span>
              <span class="prompt-text">今日新闻</span>
            </button>
            <button @click="sendQuickPrompt('写一首关于春天的诗')" class="prompt-card">
              <span class="prompt-icon">📝</span>
              <span class="prompt-text">写首诗</span>
            </button>
            <button @click="sendQuickPrompt('解释一下量子计算')" class="prompt-card">
              <span class="prompt-icon">🔬</span>
              <span class="prompt-text">量子计算</span>
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <div
          v-for="message in messages"
          :key="message.id"
          :id="messageAnchorId(message)"
          :data-role="message.role"
          class="message-anchor"
        >
          <MessageBubble
            :message="message"
          />
        </div>

        <!-- exec 审批卡片（主机白名单远程命令 / 危险命令）— 放在消息列表末尾 -->
        <div v-if="pendingApproval" class="approval-banner">
          <div class="approval-banner-main">
            <span class="approval-banner-title">🔐 命令执行审批</span>
            <span class="approval-banner-desc">{{ pendingApproval.description || '该命令需要人工审批' }}</span>
            <code class="approval-banner-cmd">{{ pendingApproval.command }}</code>
          </div>
          <div class="approval-banner-actions">
            <button class="btn btn-sm btn-primary" @click="approveExec('allow-once')">✓ 允许本次</button>
            <button class="btn btn-sm btn-danger" @click="approveExec('deny')">✗ 拒绝</button>
          </div>
        </div>
      </div>

      <!-- 悬浮消息导航：到顶 / 用户问题圆点 / 到底 -->
      <div v-show="hasMessages" class="msg-nav">
        <button
          class="msg-nav-btn"
          :class="{ 'is-visible': !isAtTop }"
          title="回到顶部"
          @click="scrollToTop"
        >⬆</button>

        <!-- 用户问题圆点导航：每个用户问题一个圆点，点击跳转 -->
        <div class="msg-nav-dots">
          <button
            v-for="(item, idx) in userMessageAnchors"
            :key="item.id"
            class="msg-nav-dot"
            :class="{
              'is-current': activeDotIndex === idx,
              'is-last': idx === userMessageAnchors.length - 1,
            }"
            :title="shortPreview(item.content)"
            @click="scrollToMessage(item.id)"
          ></button>
        </div>

        <button
          class="msg-nav-btn"
          :class="{ 'is-visible': !isAtBottom }"
          title="滚动到底部"
          @click="scrollToBottomBtn"
        >⬇</button>
      </div>

      <!-- 输入区域 -->
      <div class="input-area" @paste="handlePaste" @dragover.prevent @drop.prevent="handleDrop">
        <!-- 图片预览条 -->
        <div v-if="attachedImages.length > 0" class="image-preview-strip">
          <div
            v-for="(img, idx) in attachedImages"
            :key="idx"
            class="image-preview-item"
          >
            <img :src="img.data_url" :alt="img.filename || '图片'" />
            <button class="image-remove-btn" @click="removeImage(idx)" title="移除图片">×</button>
          </div>
          <!-- 继续添加按钮 -->
          <label class="image-add-btn" title="继续添加图片">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <input type="file" accept="image/*" multiple hidden @change="onFileInput" />
          </label>
        </div>
        <!-- 文件预览条 -->
        <div v-if="attachedFiles.length > 0" class="file-preview-strip">
          <div v-for="(f, idx) in attachedFiles" :key="'file-'+idx" class="file-preview-item">
            <span class="file-icon">{{ f.readable ? '📄' : '📎' }}</span>
            <span class="file-name">{{ f.filename }}</span>
            <button class="image-remove-btn" @click="removeFile(idx)" title="移除文件">×</button>
          </div>
          <label class="image-add-btn" title="继续添加文件">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <input type="file" accept=".md,.pdf,.txt,.docx,.xlsx,.pptx,.py,.js,.json,.csv,.html,.css,.yaml,.yml,.xml,.sql,.log,.zip" multiple hidden @change="onFileInputChange" />
          </label>
        </div>
        <textarea
          ref="textareaRef"
          v-model="inputMessage"
          :placeholder="attachedImages.length > 0 ? '输入文字描述图片... (Enter 发送)' : attachedFiles.length > 0 ? '输入问题... (Enter 发送)' : '输入消息... (Enter 发送，Shift+Enter 换行，支持粘贴图片)'"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.exact="handleNewline"
          :disabled="isStreaming"
          rows="3"
          class="chat-input"
        ></textarea>
        <div class="input-actions">
          <label class="upload-btn" title="上传图片">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            <input type="file" accept="image/*" multiple hidden @change="onFileInput" />
          </label>
          <label class="upload-btn" title="上传文件">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
            <input type="file" accept=".md,.pdf,.txt,.docx,.xlsx,.pptx,.py,.js,.json,.csv,.html,.css,.yaml,.yml,.xml,.sql,.log,.zip" multiple hidden @change="onFileInputChange" />
          </label>
          <!-- 服务器列表按钮（仅对有主机白名单权限的用户显示） -->
          <button
            v-if="canAccessHosts"
            class="upload-btn server-list-btn"
            title="可访问的服务器"
            @click="showServerList = true"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
          </button>
          <!-- 模型选择器 -->
          <div v-if="chatModels.length > 1" class="model-selector-wrap">
            <button class="model-selector-btn" @click="showModelDropdown = !showModelDropdown" :title="'当前模型: ' + currentModelName">
              <span class="model-selector-icon">🤖</span>
              <span class="model-selector-name">{{ currentModelName }}</span>
              <span class="model-selector-arrow">▾</span>
            </button>
            <div v-if="showModelDropdown" class="model-dropdown">
              <div
                v-for="m in chatModels"
                :key="m.id"
                class="model-dropdown-item"
                :class="{ active: selectedModelId === m.id || (!selectedModelId && m.is_current) }"
                @click="selectModel(m.id)"
              >
                <span class="model-dropdown-name">{{ m.config_name }}</span>
                <span class="model-dropdown-model">{{ m.model_name }}</span>
                <span v-if="!selectedModelId && m.is_current" class="model-dropdown-default">默认</span>
              </div>
              <div v-if="selectedModelId" class="model-dropdown-divider"></div>
              <div v-if="selectedModelId" class="model-dropdown-item model-dropdown-reset" @click="clearModelSelection">
                ↩ 恢复默认（路由器自动选择）
              </div>
            </div>
          </div>
          <button
            v-if="!isStreaming"
            @click="handleSend"
            :disabled="!inputMessage.trim() && attachedImages.length === 0"
            class="send-btn"
          >
            发送
          </button>
          <button v-else @click="handleStop" class="stop-btn">
            停止
          </button>
        </div>
      </div>
    </div>

    <!-- 服务器列表弹窗 -->
    <div v-if="showServerList" class="modal-overlay" @click.self="showServerList = false">
      <div class="modal-dialog">
        <div class="modal-header">
          <h3>🖥️ 可访问的服务器</h3>
          <button class="modal-close" @click="showServerList = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="serverListLoading" class="loading-state">
            <div class="spinner"></div>
            <p>加载中...</p>
          </div>
          <div v-else-if="accessibleHosts.length === 0" class="empty-state">
            <p>暂无可访问的服务器</p>
            <p class="empty-hint">请联系管理员在系统管理 - 主机白名单中添加</p>
          </div>
          <table v-else class="server-table">
            <thead>
              <tr>
                <th>主机</th>
                <th>端口</th>
                <th>登录用户</th>
                <th>认证方式</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="host in accessibleHosts" :key="host.host_identifier">
                <td><code>{{ host.host_identifier }}</code></td>
                <td>{{ host.access_port }}</td>
                <td>{{ host.access_user || 'root' }}</td>
                <td>
                  <span class="auth-badge" :class="host.auth_method">
                    {{ authMethodLabel(host.auth_method) }}
                  </span>
                </td>
                <td>{{ host.remark || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-footer">
          <p class="modal-hint">💡 你可以让 AI 通过 SSH 连接这些服务器执行命令</p>
          <button class="btn btn-secondary" @click="showServerList = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import { useChat } from '@/composables/useChat'
import { useChatStore } from '@/stores/chat'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import { getPendingExecApproval } from '@/api/chat'
import { getModelConfigs, type ModelConfig } from '@/api/config'

const chatStore = useChatStore()

// 权限检查
const auth = useAuthStore()
const canAccessHosts = computed(() => auth.hasPerm('system.manage'))

// 服务器列表相关
const showServerList = ref(false)
const accessibleHosts = ref<any[]>([])
const serverListLoading = ref(false)

function authMethodLabel(method: string): string {
  const labels: Record<string, string> = {
    'password': '密码',
    'key': '密钥',
    'none': '免密'
  }
  return labels[method] || method
}

async function loadAccessibleHosts() {
  if (!canAccessHosts.value) return
  serverListLoading.value = true
  try {
    const res = await request.get('/api/admin/chat-host-whitelist')
    accessibleHosts.value = res.data || []
  } catch (e) {
    console.error('加载可访问服务器列表失败:', e)
    accessibleHosts.value = []
  } finally {
    serverListLoading.value = false
  }
}

// 监听弹窗打开时加载数据
watch(showServerList, (newVal) => {
  if (newVal && accessibleHosts.value.length === 0) {
    loadAccessibleHosts()
  }
})

// 使用 composables
const {
  inputMessage,
  messages,
  hasMessages,
  isStreaming,
  sendMessage,
  stopStream,
  newChat,
  sendQuickPrompt,
  loadChatHistory,
  reconnectStream,
  attachedImages,
  addImagesFromFiles,
  addImageFromDataUrl,
  removeImage,
  // 文件
  attachedFiles,
  addFilesFromInput,
  removeFile,
  // exec 审批
  pendingApproval,
  approveExec,
  // 模型选择
  selectedModelId,
} = useChat()

// ── 模型选择器 ──
const chatModels = ref<ModelConfig[]>([])
const showModelDropdown = ref(false)

const currentModelName = computed(() => {
  if (selectedModelId.value) {
    const m = chatModels.value.find(c => c.id === selectedModelId.value)
    if (m) return m.config_name
  }
  const defaultModel = chatModels.value.find(c => c.is_current)
  return defaultModel?.config_name || '默认模型'
})

async function loadChatModels() {
  try {
    const data = await getModelConfigs()
    chatModels.value = (data.configs || []).filter(
      (c: ModelConfig) => (c.category || 'chat') === 'chat' && c.enabled
    )
  } catch (e) { console.error('加载模型列表失败:', e) }
}

function selectModel(id: number) {
  selectedModelId.value = id
  showModelDropdown.value = false
}

function clearModelSelection() {
  selectedModelId.value = null
  showModelDropdown.value = false
}

// ── 恢复待审批状态（页面切换后重新进入时） ──
watch(() => chatStore.currentChatId, async (newChatId) => {
  if (!newChatId) return
  // 如果已经有审批（正在流式中收到），不覆盖
  if (pendingApproval.value) return
  try {
    const result = await getPendingExecApproval(newChatId)
    if (result?.pending && result.approval_id) {
      pendingApproval.value = {
        approvalId: result.approval_id,
        command: result.command || '',
        description: result.description || '',
      }
    }
  } catch (e) {
    console.error('恢复待审批状态失败:', e)
  }
}, { immediate: true })

// ── 图片处理 ──
function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    addImagesFromFiles(input.files)
    input.value = ''
  }
}

// ── 文件处理 ──
function onFileInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    addFilesFromInput(input.files)
    input.value = ''
  }
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return

  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const blob = item.getAsFile()
      if (!blob) continue

      const reader = new FileReader()
      reader.onload = () => {
        addImageFromDataUrl(reader.result as string, item.type)
      }
      reader.readAsDataURL(blob)
      break // 一次粘贴只取第一张图
    }
  }
}

function handleDrop(e: DragEvent) {
  const allFiles = e.dataTransfer?.files
  if (!allFiles || allFiles.length === 0) return

  const images: File[] = []
  const docs: File[] = []
  for (const f of Array.from(allFiles)) {
    if (f.type.startsWith('image/')) images.push(f)
    else docs.push(f)
  }
  if (images.length > 0) addImagesFromFiles(images)
  if (docs.length > 0) addFilesFromInput(docs)
}

// 消息容器引用
const messagesContainer = ref<HTMLElement | null>(null)

// ── 悬浮消息导航状态 ──
const isAtTop = ref(true)
const isAtBottom = ref(true)
const activeDotIndex = ref(-1)
const scrollTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// 所有用户消息（作为圆点导航的锚点），id 使用与 DOM 一致的消息锚点 id
const userMessageAnchors = computed(() =>
  messages.value
    .filter((m) => m.role === 'user')
    .map((m) => ({ id: messageAnchorId(m), content: m.content || '' })),
)

/** 生成消息锚点 id（包裹层的 DOM id，用于滚动定位） */
function messageAnchorId(message: any): string {
  return `msg-${(message.id || message.conversation_id || message.timestamp || Date.now()).toString().replace(/[^a-zA-Z0-9_-]/g, '')}`
}

/** 圆点 hover 提示：截取用户问题前 N 字 */
function shortPreview(content: string): string {
  const c = content.replace(/\s+/g, ' ').trim()
  return c.length > 24 ? c.slice(0, 24) + '…' : c
}

/** 判断是否贴近顶部（threshold 200px） */
function isNearTop(el: HTMLElement, threshold = 200): boolean {
  return el.scrollTop <= threshold
}

/** 判断是否贴近底部（threshold 200px） */
function isNearBottom(el: HTMLElement, threshold = 200): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
}

/** 滚动到顶部 */
function scrollToTop() {
  messagesContainer.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

/** 滚动到底部（按钮强制滚动，无视自动滚动守卫） */
function scrollToBottomBtn() {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  refreshNavState()
}

/** 捕捉当前浏览位置 → 刷新圆心高亮与顶/底按钮可见性 */
function refreshNavState() {
  const el = messagesContainer.value
  if (!el) return
  isAtTop.value = isNearTop(el)
  isAtBottom.value = isNearBottom(el)

  // 定位当前所在的用户问题：取 scrollTop 之上最近的一条 user 消息
  const anchors = Array.from(el.querySelectorAll<HTMLElement>('.message-anchor'))
  let lastUserIdx = -1
  anchors.forEach((msgEl, i) => {
    // offsetTop 是相对 .message-anchor 父级(容器) 的偏移，接近容器顶部视为当前
    if (msgEl.offsetTop <= el.scrollTop + 60 && msgEl.dataset.role === 'user') {
      lastUserIdx = i
    }
  })
  if (lastUserIdx >= 0) {
    // 把锚点下标换算成"第几个用户消息"
    const userCount = anchors
      .slice(0, lastUserIdx + 1)
      .filter((a) => a.dataset.role === 'user').length
    activeDotIndex.value = userCount - 1
  } else {
    activeDotIndex.value = -1
  }
}

/** 滚动到指定用户消息 */
function scrollToMessage(anchorId: string) {
  const el = messagesContainer.value
  if (!el) return
  const target = el.querySelector('#' + anchorId.replace(/[^a-zA-Z0-9_-]/g, '')) as HTMLElement | null
  if (!target) return
  el.scrollTo({ top: target.offsetTop - 12, behavior: 'smooth' })
}

// 容器滚动事件：更新导航状态（节流）
function handleContainerScroll() {
  if (scrollTimer.value) clearTimeout(scrollTimer.value)
  scrollTimer.value = setTimeout(refreshNavState, 120)
}

// 智能滚动
const { smartScrollToBottom, scrollToBottom } = useAutoScroll(messagesContainer)

// 监听消息变化，自动滚动
let lastMessageCount = 0
function watchMessages() {
  if (messages.value.length !== lastMessageCount) {
    lastMessageCount = messages.value.length
    smartScrollToBottom()
  }
}

// 发送消息
function handleSend() {
  sendMessage()
  // 等待 DOM 更新后滚动
  setTimeout(watchMessages, 100)
}

// 停止流式生成
function handleStop() {
  stopStream()
}

// 换行（Shift+Enter：允许默认行为插入换行符）
function handleNewline(_e: KeyboardEvent) {
  // 允许默认行为（插入换行符）
}

// 监听流式内容变化：仅当出现新内容时才滚动，避免每 500ms 强拉底部造成"上下跳"
let lastStreamedLength = 0
let watchStreamingTimer: ReturnType<typeof setInterval> | null = null
function watchStreaming() {
  if (isStreaming.value) {
    const msgs = messages.value
    const lastMsg = msgs[msgs.length - 1]
    // 统计思考过程 + 正文的总长度，作为是否出现新内容依据
    let totalLen = lastMsg && typeof lastMsg.content === 'string' ? lastMsg.content.length : 0
    if (lastMsg && Array.isArray(lastMsg.thinkingProcesses)) {
      totalLen += lastMsg.thinkingProcesses.reduce((s, tp) => s + (tp?.content?.length || 0), 0)
    }
    // 内容真的变长了才滚动（新 token 到达）；思考折叠/开合引起的高度变化不强拉
    if (totalLen !== lastStreamedLength) {
      lastStreamedLength = totalLen
      smartScrollToBottom()
    }
  } else {
    // 流结束后重置计数，便于下一轮重新统计
    lastStreamedLength = 0
  }
}

// 初始化
onMounted(() => {
  loadChatModels()
  // 设置定时检查滚动（保存 ID，卸载时清除 — 修复定时器泄漏）
  watchStreamingTimer = setInterval(watchStreaming, 500)

  // 监听消息容器滚动，更新悬浮导航状态
  messagesContainer.value?.addEventListener('scroll', handleContainerScroll)
  refreshNavState()

  // ── 初次加载：恢复上次会话 + 重连流式 ──
  ;(async () => {
    const chatId = chatStore.currentChatId
    if (!chatId) return

    // 优先尝试重连 SSE（若该会话有未完成的流）
    const reconnected = await reconnectStream(chatId)
    if (reconnected) {
      // 等待 DOM 渲染后滚动到底部，确保看到最新输出
      await nextTick()
      requestAnimationFrame(() => {
        scrollToBottom(false)
        refreshNavState()
      })
      return
    }

    // 没有 pending stream，正常加载历史消息
    await loadChatHistory(chatId)
    await nextTick()
    requestAnimationFrame(() => {
      scrollToBottom(false)
      refreshNavState()
    })
  })()

  // 监听侧边栏点击事件，加载历史聊天
  const handleLoadHistory = async (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.chatId) {
      await loadChatHistory(detail.chatId)
      // 等待 Vue DOM 更新完成 + 浏览器布局完成后再滚动
      await nextTick()
      requestAnimationFrame(() => {
        scrollToBottom(false)
        refreshNavState()
      })
    }
  }
  window.addEventListener('chat:loadHistory', handleLoadHistory)

  // 点击外部关闭模型选择下拉框
  function closeModelDropdown(e: MouseEvent) {
    const target = e.target as HTMLElement
    if (!target.closest('.model-selector-wrap')) {
      showModelDropdown.value = false
    }
  }
  document.addEventListener('click', closeModelDropdown)

  onUnmounted(() => {
    // 清除定时器（修复内存泄漏）
    if (watchStreamingTimer) {
      clearInterval(watchStreamingTimer)
      watchStreamingTimer = null
    }
    window.removeEventListener('chat:loadHistory', handleLoadHistory)
    messagesContainer.value?.removeEventListener('scroll', handleContainerScroll)
    if (scrollTimer.value) clearTimeout(scrollTimer.value)
    document.removeEventListener('click', closeModelDropdown)
  })
})
</script>

<style scoped>
.chat-view {
  display: flex;
  height: 100%;
  background: var(--bg-secondary);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative; /* 供 .msg-nav 绝对定位 */
}

.chat-header {
  padding: 14px 28px;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-logo {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--brand-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}

.header-logo svg {
  width: 20px;
  height: 20px;
}

.header-titles {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 12px;
  color: var(--text-tertiary);
}

.btn-new-chat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-gradient);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: var(--brand-shadow);
}

.btn-new-chat svg {
  width: 15px;
  height: 15px;
}

.btn-new-chat:hover {
  transform: translateY(-1px);
  box-shadow: var(--brand-shadow-lg);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative; /* 使 .message-anchor 的 offsetTop 相对本容器（滚动定位基准） */
}

/* 消息内容布局：居中限宽，两侧留白 */
.message-anchor {
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
}

.message-anchor[data-role="user"] {
  justify-content: flex-end;
}

.message-anchor[data-role="assistant"] {
  justify-content: flex-start;
}

.welcome-screen {
  text-align: center;
  max-width: 560px;
  margin: auto;
  padding: 0 20px;
  color: var(--text-secondary);
  animation: msgIn 0.4s ease;
}

.welcome-icon-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: 24px;
}

.welcome-icon {
  width: 84px;
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  filter: drop-shadow(0 8px 24px rgba(78, 110, 242, 0.25));
  animation: floatUp 3s ease-in-out infinite;
}

.welcome-icon svg {
  width: 84px;
  height: 84px;
}

.welcome-title {
  font-size: 26px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.welcome-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-bottom: 36px;
  line-height: 1.6;
}

.quick-prompts {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin: 0 auto;
  max-width: 460px;
}

.prompt-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 18px 16px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.22s ease;
  box-shadow: var(--shadow-sm);
}

.prompt-card:hover {
  border-color: var(--brand);
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.prompt-icon {
  font-size: 22px;
}

.prompt-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.prompt-card:hover .prompt-text {
  color: var(--brand);
}

@keyframes floatUp {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-10px);
  }
}

.input-area {
  padding: 16px 28px 20px;
  border-top: 1px solid var(--border-primary);
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

/* ─── exec 审批卡片 ─── */
.approval-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin: 8px 0;
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 10px;
}

.approval-banner-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.approval-banner-title {
  font-weight: 600;
  color: #e65100;
  font-size: 13px;
}

.approval-banner-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

.approval-banner-cmd {
  font-family: monospace;
  font-size: 12px;
  background: rgba(0,0,0,0.05);
  padding: 4px 8px;
  border-radius: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.approval-banner-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* 输入区外层包裹成一个悬浮圆角卡片 */
.chat-input {
  flex: 1;
  min-height: 52px;
  max-height: 180px;
  padding: 14px 16px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 14px;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.chat-input::placeholder {
  color: var(--text-placeholder);
}

.chat-input:hover {
  border-color: var(--border-secondary);
}

.chat-input:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-shadow);
  background: var(--bg-input);
}

.chat-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── 输入区底部操作栏 ── */
.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.upload-btn svg {
  width: 20px;
  height: 20px;
}

.upload-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--bg-card);
}

/* ── 图片预览条 ── */
.image-preview-strip {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}

.image-preview-item {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.image-preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-remove-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}

.image-preview-item:hover .image-remove-btn {
  opacity: 1;
}

.image-add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border: 2px dashed var(--border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-tertiary);
  flex-shrink: 0;
  transition: all 0.2s;
}

.image-add-btn svg {
  width: 20px;
  height: 20px;
}

.image-add-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.send-btn,
.stop-btn {
  padding: 14px 26px;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 88px;
  letter-spacing: 0.3px;
}

.send-btn {
  background: var(--brand-gradient);
  color: white;
  box-shadow: var(--brand-shadow);
}

.send-btn:hover:not(:disabled) {
  opacity: 0.95;
  transform: translateY(-2px);
  box-shadow: var(--brand-shadow-lg);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.stop-btn {
  background: #f56c6c;
  color: white;
}

.stop-btn:hover {
  background: #f78989;
}

/* ── 模型选择器 ── */
.model-selector-wrap {
  position: relative;
  margin-left: auto;
}
.model-selector-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px 4px 8px;
  border: 1px solid var(--border-primary);
  border-radius: 16px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  max-width: 180px;
}
.model-selector-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--bg-card);
}
.model-selector-icon { font-size: 14px; line-height: 1; }
.model-selector-name {
  max-width: 110px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 500;
}
.model-selector-arrow { font-size: 10px; color: var(--text-placeholder); }
.model-dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  right: 0;
  min-width: 220px;
  max-height: 260px;
  overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  z-index: 100;
  padding: 4px;
}
.model-dropdown-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.12s;
}
.model-dropdown-item:hover { background: var(--bg-hover); }
.model-dropdown-item.active {
  background: var(--brand-light, #e0e7ff);
  color: var(--brand);
  font-weight: 600;
}
.model-dropdown-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-dropdown-model { font-size: 11px; color: var(--text-tertiary); }
.model-dropdown-default {
  font-size: 10px; padding: 1px 6px;
  border-radius: 8px;
  background: var(--brand-light, #e0e7ff);
  color: var(--brand);
}
.model-dropdown-divider {
  height: 1px;
  background: var(--border-primary);
  margin: 4px 0;
}
.model-dropdown-reset {
  color: var(--text-tertiary);
  font-size: 12px;
}
.model-dropdown-reset:hover { color: var(--text-primary); }

/* ── 悬浮消息导航 ── */
.msg-nav {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  z-index: 30;
}

.msg-nav-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 18px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.14);
  opacity: 0;
  transform: scale(0.8);
  transition: opacity 0.25s, transform 0.25s, background 0.2s, border-color 0.2s;
}

.msg-nav-btn.is-visible {
  opacity: 1;
  transform: scale(1);
}

.msg-nav-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
  border-width: 2px;
  font-weight: 800;
}

/* 圆点导航：竖排，长对话可滚动 */
.msg-nav-dots {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px 7px;
  max-height: 360px;
  overflow-y: auto;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.10);
  scrollbar-width: none;
}
.msg-nav-dots::-webkit-scrollbar { display: none; }

.msg-nav-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: none;
  padding: 0;
  flex-shrink: 0;
  background: var(--border-primary);
  cursor: pointer;
  transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
}

.msg-nav-dot:hover {
  background: var(--brand);
  transform: scale(1.3);
}

/* 当前浏览位置对应的圆点：品牌色高亮放大 */
.msg-nav-dot.is-current {
  background: var(--brand);
  width: 12px;
  height: 12px;
  box-shadow: 0 0 0 2px var(--brand-light);
}

/* 最新一条用户问题的圆点：更强的强调 */
.msg-nav-dot.is-last:not(.is-current) {
  background: var(--text-secondary);
  width: 11px;
  height: 11px;
}

/* 消息锚点容器（用于滚动定位） */
.message-anchor {
  display: flex;
  flex-direction: column;
}

/* ── 文件预览条 ── */
.file-preview-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 10px;
  flex-wrap: wrap;
}

.file-preview-item {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 12px;
  position: relative;
}

.file-icon {
  font-size: 14px;
}

.file-name {
  color: var(--text-secondary);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 服务器列表按钮 ── */
.server-list-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
}

.server-list-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.server-list-btn svg {
  width: 20px;
  height: 20px;
}

/* ── 服务器列表弹窗 ── */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-width: 800px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 28px;
  color: var(--text-tertiary);
  cursor: pointer;
  line-height: 1;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.modal-hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}

.loading-state .spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-primary);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-hint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.server-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.server-table thead {
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  z-index: 1;
}

.server-table th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 2px solid var(--border-primary);
}

.server-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-primary);
  color: var(--text-primary);
}

.server-table tbody tr:hover {
  background: var(--bg-secondary);
}

.server-table code {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: var(--brand);
}

.auth-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.auth-badge.password {
  background: rgba(255, 152, 0, 0.15);
  color: #ff9800;
}

.auth-badge.key {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
}

.auth-badge.none {
  background: rgba(33, 150, 243, 0.15);
  color: #2196f3;
}

.btn {
  padding: 8px 20px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
  border-color: var(--brand);
}
</style>
