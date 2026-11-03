<template>
  <div :class="['message-bubble', message.role]">
    <div class="message-header">
      <span class="role-label">
        {{ message.role === 'user' ? '👤 我' : '🤖 助手' }}
      </span>
      <span v-if="message.source && message.source !== 'web'" class="source-badge" :class="'source-' + message.source">
        {{ sourceLabel(message.source) }}
      </span>
      <span class="timestamp">{{ message.timestamp }}</span>
    </div>

    <!-- 思考过程（可折叠） -->
    <!-- 非受控折叠：用本地 isOpen 管理，用户手动 toggle 后不再被 message.content 变化覆盖 -->
    <div
      v-if="message.role === 'assistant' && message.thinkingProcesses?.length"
      class="thinking-processes"
    >
      <details :open="isOpen" @toggle="onToggle" ref="thinkingDetailsRef">
        <summary class="thinking-summary">
          🧠 思考过程（{{ message.thinkingProcesses.length }} 步）
        </summary>
        <div
          v-for="(tp, i) in message.thinkingProcesses"
          :key="i"
          class="thinking-step"
        >
          <div class="thinking-step-header">步骤 {{ i + 1 }}</div>
          <div
            class="thinking-step-content markdown-body"
            v-html="renderTPContent(tp.content)"
          ></div>
        </div>
        <div class="thinking-collapse-bar" @click="collapseThinking">
          ▲ 收起思考过程
        </div>
      </details>
    </div>

    <!-- P0: 子 Agent 委派面板 -->
    <SubagentPanel
      v-if="message.role === 'assistant' && message.subagentTasks?.length"
      :tasks="message.subagentTasks"
    />

    <div v-if="message.role === 'user'" class="message-content">
      <!-- 用户消息的图片附件 -->
      <div v-if="message.images?.length" class="message-images">
        <img
          v-for="(img, idx) in message.images"
          :key="idx"
          :src="img.data_url"
          :alt="img.filename || '图片'"
          class="message-image"
          @click="openImagePreview(img.data_url)"
        />
      </div>
      <!-- 用户消息的文件附件 -->
      <div v-if="message.files?.length" class="message-files">
        <div
          v-for="(f, idx) in message.files"
          :key="'f-'+idx"
          class="message-file-item"
          @click="openFile(f)"
        >
          <span class="file-type-icon">{{ fileIcon(f) }}</span>
          <span class="file-info">
            <span class="file-name-text">{{ f.filename }}</span>
            <span class="file-size-text">{{ formatFileSize(f.size) }}</span>
          </span>
        </div>
      </div>
      <div v-text="message.content"></div>
    </div>

    <!-- 助手消息：等待思考状态 -->
    <div v-else-if="isThinking" class="thinking-indicator">
      <div class="thinking-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <span class="thinking-text">思考中...</span>
    </div>

    <div v-else class="message-content markdown-body" v-html="renderedContent"></div>

    <!-- 记忆引用（可折叠） -->
    <div
      v-if="message.role === 'assistant' && message.memoryCitations?.length && !isThinking"
      class="memory-citations"
    >
      <details class="citations-details">
        <summary class="citations-summary">
          📎 引用了 {{ message.memoryCitations.length }} 条记忆
        </summary>
        <div class="citations-list">
          <div
            v-for="(cite, idx) in message.memoryCitations"
            :key="cite.id || idx"
            class="citation-item"
          >
            <span class="citation-type" :class="'type-' + cite.memory_type">
              {{ typeLabel(cite.memory_type) }}
            </span>
            <span class="citation-content">{{ cite.content }}</span>
            <span v-if="cite.created_at" class="citation-time">
              {{ formatCitationTime(cite.created_at) }}
            </span>
          </div>
        </div>
      </details>
    </div>

    <!-- 消息操作按钮（仅助手消息） -->
    <div v-if="message.role === 'assistant'" class="message-actions">
      <template v-if="message.conversation_id && !isThinking">
        <button
          class="action-btn"
          :class="{ 'feedback-active': currentFeedback === 1 }"
          :title="currentFeedback === 1 ? '已赞' : '赞'"
          @click="submitFeedback(1)"
        >👍</button>
        <button
          class="action-btn"
          :class="{ 'feedback-active': currentFeedback === -1 }"
          :title="currentFeedback === -1 ? '已踩' : '踩'"
          @click="submitFeedback(-1)"
        >👎</button>
      </template>
      <button @click="copyMessage" class="action-btn" :title="copied ? '已复制 ✓' : '复制'">
        {{ copied ? '✅' : '📋' }}
      </button>
    </div>

    <!-- 反馈评论（点踩后可选填写，用于生成 RAG 优化建议） -->
    <div v-if="currentFeedback === -1 && feedbackSubmitted" class="feedback-comment-box">
      <span class="feedback-comment-hint">💡 已记录踩。可补充问题说明（将用于生成知识库优化建议）：</span>
      <div class="feedback-comment-row">
        <input
          v-model="commentText"
          class="feedback-comment-input"
          placeholder="例如：回答引用了无关文档…"
          @keyup.enter="submitComment"
        />
        <button class="feedback-comment-btn" @click="submitComment">提交</button>
      </div>
      <div v-if="commentSent" class="feedback-comment-ok">✅ 已提交，感谢反馈</div>
    </div>

    <!-- 图片预览模态框 -->
    <Teleport to="body">
      <div v-if="previewImage" class="image-preview-modal" @click="closeImagePreview">
        <div class="image-preview-content" @click.stop>
          <img :src="previewImage" alt="预览" class="image-preview-img" />
          <button class="image-preview-close" @click="closeImagePreview">×</button>
        </div>
      </div>
    </Teleport>

    <!-- 文件预览模态框 -->
    <Teleport to="body">
      <div v-if="previewFile" class="image-preview-modal" @click="closeFilePreview">
        <div class="image-preview-content file-preview-content" @click.stop>
          <div class="file-preview-header">
            <span>{{ previewFile.filename }}</span>
            <a v-if="previewFile.url" :href="fileDownloadUrl" :download="previewFile.filename" class="file-download-btn" title="下载">⬇</a>
          </div>
          <pre v-if="previewLoading" class="file-preview-body" style="color:var(--text-tertiary);">加载中...</pre>
          <pre v-else class="file-preview-body">{{ previewFile.content || '(无法预览，点击下载按钮查看)' }}</pre>
          <button class="image-preview-close" @click="closeFilePreview">×</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { renderMarkdown, sanitizeModelOutput } from '@/utils/markdown'
import type { Message } from '@/types/chat'
import SubagentPanel from './SubagentPanel.vue'

const props = defineProps<{
  message: Message
}>()

// 渠道标签映射
function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    wechat: '💬 微信',
    weixin: '💬 微信',
    feishu: '🦜 飞书',
  }
  return map[source] || '🌐 ' + source
}

// 记忆类型标签
function typeLabel(memType: string): string {
  const map: Record<string, string> = {
    fact: '📌 事实',
    preference: '💡 偏好',
    event: '📅 事件',
    task_state: '⚙️ 状态',
    skill: '🔧 技能',
  }
  return map[memType] || memType
}

// 记忆时间格式化
function formatCitationTime(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return ''
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffDays = Math.floor(diffMs / 86400000)
    if (diffDays === 0) return '今天'
    if (diffDays === 1) return '昨天'
    if (diffDays < 7) return `${diffDays}天前`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

// ── 思考过程折叠状态（非受控） ──
// 默认：无正文时展开（思考/流式阶段），有正文时折叠（给出答案后）。
// 用户手动 toggle 后置 userToggled=true，之后 message.content 的更新不再覆盖用户展开状态。
const isOpen = ref<boolean>(!props.message.content)
const userToggled = ref<boolean>(false)
const thinkingDetailsRef = ref<HTMLDetailsElement | null>(null)

// 底部收起按钮
function collapseThinking(e: MouseEvent) {
  e.preventDefault()
  if (thinkingDetailsRef.value) {
    thinkingDetailsRef.value.open = false
    isOpen.value = false
    userToggled.value = true
  }
}

// 用户点击 summary 时同步真实开合状态（浏览器实际 open）
function onToggle(e: Event) {
  const el = e.target as HTMLDetailsElement
  isOpen.value = el.open
  userToggled.value = true
}

// 流式阶段：新一轮思考会更新 message.content（清空→再填充）。
// 仅在用户未手动干预时，自动跟随"有内容则折叠、无内容则展开"。
watch(
  () => props.message.content,
  (val) => {
    if (!userToggled.value) {
      isOpen.value = !val
    }
  },
)

// ── 流式渲染节流：用 requestAnimationFrame 减少 Markdown 重渲染频率 ──
// 流式阶段每个 token 都会更新 content，但 Markdown 解析开销大，
// 通过 RAF 合并同一帧内的多次更新，每帧最多渲染一次。
const displayContent = ref(props.message.content)
let rafId: number | null = null

watch(() => props.message.content, () => {
  if (rafId !== null) return // 已有 pending 的 RAF，跳过（RAF 回调时读取最新值）
  rafId = requestAnimationFrame(() => {
    displayContent.value = props.message.content // 读取最新值
    rafId = null
  })
})

onUnmounted(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
})

// 渲染 Markdown（基于节流后的 displayContent）
const renderedContent = computed(() => {
  const sanitized = sanitizeModelOutput(displayContent.value)
  return renderMarkdown(sanitized)
})

// 判断是否在思考中（助手消息，无内容，无思考过程）
const isThinking = computed(() => {
  return (
    props.message.role === 'assistant' &&
    !props.message.content &&
    (!props.message.thinkingProcesses || props.message.thinkingProcesses.length === 0)
  )
})

// 渲染思考过程内容
function renderTPContent(content: string): string {
  const sanitized = sanitizeModelOutput(content)
  return renderMarkdown(sanitized)
}

// 复制消息
const copied = ref(false)
async function copyMessage() {
  const text = typeof props.message.content === 'string' ? props.message.content : String(props.message.content || '')
  if (!text) return
  
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

// ── 聊天反馈（RAG 评测闭环：👍/👎 → /api/chat/feedback） ──
import { submitFeedback as apiSubmitFeedback } from '@/api/chat'

const currentFeedback = computed<1 | -1 | 0>(() => props.message.feedback ?? 0)
const feedbackSubmitted = ref(false)
const commentText = ref('')
const commentSent = ref(false)

async function submitFeedback(rating: 1 | -1) {
  const convId = props.message.conversation_id
  if (!convId) return
  // 同值重复点击：忽略（后端不支持取消，保持简单）
  if (currentFeedback.value === rating) return
  const ok = await apiSubmitFeedback(convId, rating)
  if (ok) {
    props.message.feedback = rating
    feedbackSubmitted.value = true
  }
}

async function submitComment() {
  const convId = props.message.conversation_id
  const text = commentText.value.trim()
  if (!convId || !text) return
  const ok = await apiSubmitFeedback(convId, props.message.feedback === -1 ? -1 : 1, text)
  if (ok) {
    commentSent.value = true
    commentText.value = ''
  }
}

// 图片预览
const previewImage = ref<string | null>(null)
function openImagePreview(url: string) {
  previewImage.value = url
}
function closeImagePreview() {
  previewImage.value = null
}

// 文件预览
import type { ChatFile } from '@/types/chat'
// 可预览的文本文件扩展名
const TEXT_PREVIEW_EXTS = new Set(['.md','.txt','.py','.js','.ts','.json','.csv','.html','.css','.yaml','.yml','.xml','.sql','.log','.toml','.ini','.cfg'])

const previewFile = ref<ChatFile | null>(null)
const previewLoading = ref(false)
const fileDownloadUrl = computed(() => {
  if (!previewFile.value?.url) return ''
  const url = previewFile.value.url
  if (url.startsWith('http')) return url
  return (import.meta.env.VITE_API_BASE || '') + url
})
function isTextPreviewable(filename: string): boolean {
  const ext = '.' + (filename || '').split('.').pop()?.toLowerCase()
  return TEXT_PREVIEW_EXTS.has(ext)
}
async function openFile(f: ChatFile) {
  // 二进制文件：不预览，直接下载
  if (!isTextPreviewable(f.filename)) {
    const apiBase = import.meta.env.VITE_API_BASE || ''
    // f.url 上传链路恒有值；此处用非空断言（运行时行为不变）
    const fullUrl = f.url!.startsWith('http') ? f.url! : `${apiBase}${f.url!}`
    window.open(fullUrl, '_blank')
    return
  }
  // 文本文件：已有内容直接展示，否则从 URL 拉取
  if (f.content) {
    previewFile.value = f
    return
  }
  if (!f.url) {
    previewFile.value = { ...f, content: '(无法获取文件内容)' }
    return
  }
  previewLoading.value = true
  previewFile.value = { ...f, content: '加载中...' }
  try {
    const apiBase = import.meta.env.VITE_API_BASE || ''
    const fullUrl = f.url.startsWith('http') ? f.url : `${apiBase}${f.url}`
    const resp = await fetch(fullUrl)
    if (resp.ok) {
      const text = await resp.text()
      previewFile.value = { ...f, content: text || '(文件为空)' }
    } else {
      previewFile.value = { ...f, content: '(加载失败)' }
    }
  } catch {
    previewFile.value = { ...f, content: '(加载失败)' }
  } finally {
    previewLoading.value = false
  }
}
function closeFilePreview() {
  previewFile.value = null
}
function fileIcon(f: ChatFile): string {
  const ext = (f.filename || '').toLowerCase()
  if (ext.endsWith('.pdf')) return '📄'
  if (ext.endsWith('.md')) return '📝'
  if (ext.endsWith('.txt')) return '📃'
  if (ext.endsWith('.docx')) return '📰'
  if (ext.endsWith('.xlsx')) return '📊'
  if (ext.endsWith('.pptx')) return '📽️'
  if (ext.endsWith('.py') || ext.endsWith('.js') || ext.endsWith('.ts')) return '💻'
  if (ext.endsWith('.json') || ext.endsWith('.csv')) return '📋'
  if (ext.endsWith('.zip')) return '📦'
  return '📎'
}
function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

</script>
<style scoped>
.message-bubble {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  animation: fadeIn 0.3s ease;
  position: relative;
  box-shadow: var(--shadow-sm);
}

.message-bubble.user {
  align-self: flex-end;
  background: var(--brand-gradient);
  color: white;
  border-bottom-right-radius: 4px;
}

.message-bubble.assistant {
  align-self: flex-start;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-bottom-left-radius: 4px;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  opacity: 0.7;
}

.message-bubble.user .message-header {
  opacity: 0.9;
}

.role-label {
  font-weight: 600;
}

.timestamp {
  font-size: 11px;
}

.source-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
}
.source-wechat, .source-weixin { background: #e8f5e9; color: #2e7d32; }
.source-feishu { background: #e3f2fd; color: #1565c0; }

.message-content {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  overflow-wrap: break-word;
  min-width: 0;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.message-image {
  max-width: 100%;
  max-height: 300px;
  border-radius: 6px;
  object-fit: contain;
  cursor: pointer;
  transition: transform 0.2s;
}

.message-image:hover {
  transform: scale(1.02);
}

.markdown-body {
  /* 继承消息根部的溢出约束 */
  max-width: 100%;
  overflow-x: auto;
}

.markdown-body pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-all;
}

.markdown-body code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  max-width: 100%;
  word-break: break-word;
}

/* 内联 code 防止撑破 */
.markdown-body :not(pre) > code {
  word-break: break-word;
  white-space: pre-wrap;
  background: var(--bg-code);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12.5px;
}

.markdown-body p {
  margin: 8px 0;
  max-width: 100%;
}

.markdown-body ul,
.markdown-body ol {
  margin: 8px 0;
  padding-left: 24px;
  max-width: 100%;
}

.markdown-body li {
  word-break: break-word;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3 {
  margin: 16px 0 8px;
  max-width: 100%;
}

.markdown-body table {
  max-width: 100%;
  display: block;
  overflow-x: auto;
  border-collapse: collapse;
}

.markdown-body td,
.markdown-body th {
  padding: 6px 12px;
  border: 1px solid var(--border-primary);
  word-break: break-word;
}

.markdown-body img {
  max-width: 100%;
  height: auto;
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-bubble:hover .message-actions {
  opacity: 1;
}

.action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s;
}

.action-btn:hover {
  background: var(--bg-hover);
}

.action-btn.feedback-active {
  background: var(--primary-color, #4a6cf7);
  opacity: 1;
  border-radius: 6px;
}

/* 反馈评论框 */
.feedback-comment-box {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px dashed var(--border-color, #e0e0e0);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary, #666);
}

.feedback-comment-hint {
  display: block;
  margin-bottom: 6px;
}

.feedback-comment-row {
  display: flex;
  gap: 8px;
}

.feedback-comment-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg-secondary, #fff);
  color: var(--text-primary, #333);
}

.feedback-comment-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: var(--primary-color, #4a6cf7);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.feedback-comment-ok {
  margin-top: 6px;
  color: var(--success-color, #16a34a);
}

/* 思考过程折叠块 */
.thinking-processes {
  margin-bottom: 12px;
  position: relative;
}

/* 思考过程和回答之间的分隔 */
.thinking-processes::after {
  content: '';
  display: block;
  margin-top: 10px;
  border-bottom: 1px dashed var(--border-secondary);
}

.thinking-processes details {
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  overflow: hidden;
}

.thinking-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  user-select: none;
  transition: background 0.2s;
}

.thinking-summary:hover {
  background: var(--bg-hover);
}

.thinking-step {
  padding: 8px 12px;
  border-top: 1px solid var(--border-primary);
}

.thinking-step-header {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  font-weight: 500;
}

.thinking-step-content {
  font-size: 13px;
  line-height: 1.5;
  opacity: 0.85;
  max-height: 300px;
  overflow-y: auto;
}

.thinking-collapse-bar {
  padding: 8px 12px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  border-top: 2px solid var(--brand-light);
  background: linear-gradient(to bottom, var(--bg-secondary), var(--bg-primary));
  transition: all 0.2s;
  user-select: none;
  letter-spacing: 1px;
}

.thinking-collapse-bar:hover {
  background: var(--brand-light);
  color: var(--brand);
  border-top-color: var(--brand);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 图片预览模态框 */
.image-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}

.image-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
}

.image-preview-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.image-preview-close {
  position: absolute;
  top: -40px;
  right: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  border: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.image-preview-close:hover {
  background: #fff;
  transform: scale(1.1);
}

/* 思考中动画 */
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.thinking-dots {
  display: flex;
  gap: 4px;
}

.thinking-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: thinking-bounce 1.4s infinite ease-in-out both;
}

.thinking-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.thinking-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes thinking-bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.thinking-text {
  font-size: 13px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* ── 文件附件 ── */
.message-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.message-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  max-width: 240px;
}

.message-file-item:hover {
  background: var(--bg-hover);
}

.file-type-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.file-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.file-name-text {
  font-size: 12.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.file-size-text {
  font-size: 10.5px;
  color: var(--text-tertiary);
}

/* ── 文件预览模态框 ── */
.file-preview-content {
  max-width: 700px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.file-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-primary);
  font-size: 14px;
  font-weight: 600;
}

.file-download-btn {
  font-size: 18px;
  text-decoration: none;
  padding: 4px 8px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  transition: background 0.15s;
}

.file-download-btn:hover {
  background: var(--bg-hover);
}

.file-preview-body {
  flex: 1;
  overflow: auto;
  padding: 16px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  background: var(--bg-secondary);
  max-height: 60vh;
}

/* 记忆引用区域 */
.memory-citations {
  margin-top: 8px;
  font-size: 13px;
}

.citations-details {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.citations-summary {
  padding: 6px 12px;
  cursor: pointer;
  color: var(--text-secondary, #666);
  background: var(--bg-secondary, #f5f5f5);
  user-select: none;
  font-size: 12px;
}

.citations-summary:hover {
  background: var(--bg-tertiary, #ebebeb);
}

.citations-list {
  padding: 4px 0;
}

.citation-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-color, #f0f0f0);
}

.citation-item:last-child {
  border-bottom: none;
}

.citation-type {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.citation-type.type-fact {
  background: #e3f2fd;
  color: #1565c0;
}

.citation-type.type-preference {
  background: #f3e5f5;
  color: #7b1fa2;
}

.citation-type.type-event {
  background: #e8f5e9;
  color: #2e7d32;
}

.citation-type.type-task_state {
  background: #fff3e0;
  color: #e65100;
}

.citation-type.type-skill {
  background: #fce4ec;
  color: #c62828;
}

.citation-content {
  flex: 1;
  color: var(--text-primary, #333);
  line-height: 1.5;
  word-break: break-word;
}

.citation-time {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary, #999);
}
</style>
