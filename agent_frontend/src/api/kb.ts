// 知识库 API

import request from './request'

export interface KbDocument {
  id: number
  user_id: number
  original_name: string
  ext: string
  size_bytes: number
  sha256: string
  page_count: number
  char_count: number
  chunk_count: number
  status: string            // parsing | parsed | failed | needs_ocr
  parser: string            // builtin | mineru_http
  chunk_size: number
  chunk_overlap: number
  chunk_strategy: string    // fixed | topic
  error_message: string
  vectorized: boolean
  created_at: string
  updated_at: string
}

export interface KbChunk {
  id: number
  chunk_index: number
  char_count: number
  page_start: number | null
  page_end: number | null
  content: string
  strategy: string          // fixed | topic
  kind: string              // base | topic
  topic_id: number | null
  topic_title?: string | null
}

export interface KbDocumentList {
  total: number
  page: number
  page_size: number
  items: KbDocument[]
}

export interface KbChunkList {
  total: number
  page: number
  page_size: number
  items: KbChunk[]
}

export interface KbDocumentText {
  id: number
  original_name: string
  text: string
  char_count: number
  needs_reprocess: boolean
}

export interface UploadOptions {
  chunk_size?: number
  chunk_overlap?: number
  parser?: string
  chunk_strategy?: string   // fixed | topic
  kb_id?: number            // 知识库ID
}

const API_BASE = import.meta.env.VITE_API_BASE || ''

function getAuthToken(): string {
  try {
    return localStorage.getItem('authToken') || ''
  } catch { /* ignore */ }
  return ''
}

/**
 * multipart 请求统一走裸 fetch：
 * axios 实例全局默认 Content-Type: application/json 会导致 FormData 被
 * JSON 序列化（文件丢失，FastAPI 报 422 Field required），
 * 与 chat.ts 上传保持同一模式（浏览器自动设置 multipart boundary）。
 */
async function postForm(url: string, form: FormData, timeoutMs = 10 * 60 * 1000): Promise<any> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const token = getAuthToken()
    const resp = await fetch(`${API_BASE}${url}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal: controller.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '请求失败' }))
      const detail = err?.detail
      const msg = typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? detail[0].msg
          : '请求失败'
      throw new Error(msg)
    }
    return await resp.json()
  } finally {
    clearTimeout(timer)
  }
}

/**
 * 上传文档（multipart，可多文件）
 */
export async function uploadDocuments(files: File[], options: UploadOptions = {}): Promise<{ documents: KbDocument[] }> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (options.chunk_size) form.append('chunk_size', String(options.chunk_size))
  if (options.chunk_overlap !== undefined) form.append('chunk_overlap', String(options.chunk_overlap))
  if (options.parser) form.append('parser', options.parser)
  if (options.chunk_strategy) form.append('chunk_strategy', options.chunk_strategy)
  if (options.kb_id !== undefined) form.append('kb_id', String(options.kb_id))

  return await postForm('/api/kb/documents', form)
}

/**
 * 文档列表（分页 + 关键词）
 */
export async function listDocuments(params: { keyword?: string; page?: number; page_size?: number } = {}): Promise<KbDocumentList> {
  const response = await request.get('/api/kb/documents', { params })
  return response.data
}

/**
 * 文档详情
 */
export async function getDocument(id: number): Promise<KbDocument> {
  const response = await request.get(`/api/kb/documents/${id}`)
  return response.data
}

/**
 * chunk 分页列表（kind: all/base/topic）
 */
export async function listChunks(id: number, page = 1, pageSize = 50, kind = 'all'): Promise<KbChunkList> {
  const response = await request.get(`/api/kb/documents/${id}/chunks`, {
    params: { page, page_size: pageSize, kind },
  })
  return response.data
}

/**
 * 文档解析出的完整原文
 */
export async function getDocumentText(id: number): Promise<KbDocumentText> {
  const response = await request.get(`/api/kb/documents/${id}/text`)
  return response.data
}

/**
 * 重新解析/切分
 */
export async function reprocessDocument(id: number, options: UploadOptions = {}): Promise<KbDocument> {
  const form = new FormData()
  if (options.chunk_size) form.append('chunk_size', String(options.chunk_size))
  if (options.chunk_overlap !== undefined) form.append('chunk_overlap', String(options.chunk_overlap))
  if (options.parser) form.append('parser', options.parser)
  if (options.chunk_strategy) form.append('chunk_strategy', options.chunk_strategy)

  return await postForm(`/api/kb/documents/${id}/reprocess`, form)
}

/**
 * 删除文档
 */
export async function deleteDocument(id: number): Promise<{ id: number; deleted: boolean }> {
  const response = await request.delete(`/api/kb/documents/${id}`)
  return response.data
}

/**
 * 下载原始文件（通过 fetch + blob，带 Authorization）
 */
export async function downloadDocument(id: number, filename: string): Promise<void> {
  const base = import.meta.env.VITE_API_BASE || ''
  const token = localStorage.getItem('token') || ''
  const resp = await fetch(`${base}/api/kb/documents/${id}/download`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!resp.ok) {
    throw new Error(`下载失败: ${resp.status}`)
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
