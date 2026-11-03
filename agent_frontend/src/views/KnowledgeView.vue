<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">📚 知识库</h1>
      </div>
      <div class="header-actions">
        <span class="doc-count">共 {{ total }} 个文档</span>
      </div>
    </header>

    <!-- 上传区 -->
    <div
      class="upload-zone card"
      :class="{ dragging, hasError: uploadError }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="handleDrop"
    >
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.md,.markdown,.txt,.docx,.doc,.pptx,.xlsx,.csv,.json,.html,.htm,.log"
        style="display: none"
        @change="handleFileChange"
      />
      <!-- 右上角上传按钮 -->
      <div class="upload-zone-topbar">
        <button class="btn btn-primary btn-upload" @click="triggerFileInput" :disabled="uploading">
          {{ uploading ? '⏳ 解析中...' : '+ 上传文档' }}
        </button>
      </div>
      <div class="upload-zone-inner">
        <div class="upload-icon">📄</div>
        <div class="upload-text">
          拖拽文件到此处，或 <a @click="triggerFileInput">点击选择</a>
          <div class="upload-hint">支持 PDF / MD / TXT / DOCX / PPTX / XLSX / CSV，单文件 ≤ 50MB</div>
        </div>
        <div class="upload-options">
          <label>知识库
            <select v-model="optKbId">
              <option :value="null">默认知识库</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
                {{ kb.kb_name }}
              </option>
            </select>
          </label>
          <label>切分策略
            <select v-model="optStrategy">
              <option value="parent_child">父子分片（推荐）</option>
            </select>
          </label>
          <label>切分大小
            <input v-model.number="optChunkSize" type="number" min="100" max="8000" step="100" />
          </label>
          <label>重叠
            <input v-model.number="optChunkOverlap" type="number" min="0" max="2000" step="50" />
          </label>
          <label>解析器
            <select v-model="optParser">
              <option value="">auto（自动）</option>
              <option value="builtin">builtin（内置）</option>
              <option value="mineru_http">mineru_http（远程 MinerU）</option>
            </select>
          </label>
        </div>
      </div>
      <div v-if="uploadError" class="upload-error">{{ uploadError }}</div>
      <div v-if="uploadMsg" class="upload-msg">{{ uploadMsg }}</div>
    </div>

    <!-- 三栏主体 -->
    <div class="kb-layout">
      <!-- 左：知识库 + 文档列表 -->
      <div class="card kb-pane kb-doc-pane">
        <!-- 知识库列表 -->
        <div class="kb-selector">
          <div class="kb-selector-header">
            <span>知识库</span>
            <div class="kb-selector-actions">
              <button v-if="canManageKb" class="btn-icon" title="新建知识库" @click="openKbCreate">＋</button>
            </div>
          </div>
          <div class="kb-selector-list">
            <div
              v-for="kb in filteredKnowledgeBases"
              :key="kb.id"
              class="kb-item"
              :class="{ active: currentKbId === kb.id, disabled: !kb.is_enabled }"
              @click="switchKb(kb.id)"
            >
              <span class="kb-item-name" :title="kb.description || kb.kb_name">{{ kb.kb_name }}</span>
              <span class="kb-item-dept" :title="'部门: ' + getLayerNames(kb)">{{ getLayerNames(kb) }}</span>
              <span class="kb-item-stats" :title="kbStats(kb).title">{{ kbStats(kb).label }}</span>
              <span v-if="!kb.is_enabled" class="kb-item-disabled">已禁用</span>
              <span v-if="canManageKbItem(kb)" class="kb-item-actions">
                <button class="btn-icon" title="编辑" @click.stop="openKbEdit(kb)">✏️</button>
                <button class="btn-icon" :title="kb.is_enabled ? '禁用' : '启用'" @click.stop="toggleKb(kb)">{{ kb.is_enabled ? '⏸' : '▶️' }}</button>
                <button class="btn-icon" title="删除" @click.stop="deleteKb(kb)">🗑️</button>
              </span>
            </div>
          </div>
        </div>

        <!-- 文档列表 -->
        <div class="pane-header">
          <span>文档列表</span>
          <div class="pane-search">
            <input v-model="keyword" placeholder="搜索文件名..." @keyup.enter="loadDocuments(1)" />
            <button class="btn-icon" @click="loadDocuments(1)" title="搜索">🔍</button>
          </div>
        </div>
        <div class="pane-body">
          <div v-if="loadingDocs" class="pane-empty"><div class="spinner"></div></div>
          <div v-else-if="docs.length === 0" class="pane-empty">
            <p>暂无文档</p>
            <p class="pane-empty-hint">上传第一个文档开始构建知识库</p>
          </div>
          <div
            v-for="doc in docs"
            :key="doc.id"
            class="doc-item"
            :class="{ active: selected?.id === doc.id }"
            @click="selectDoc(doc)"
          >
            <div class="doc-item-top">
              <span class="doc-ext">{{ doc.ext.replace('.', '') || 'file' }}</span>
              <span class="doc-name" :title="doc.original_name">{{ doc.original_name }}</span>
            </div>
            <div class="doc-item-meta">
              <span :class="['status-badge', 'status-' + doc.status]">{{ statusText(doc.status) }}</span>
              <span v-if="doc.page_count" class="meta-chip">📄 {{ doc.page_count }}页</span>
              <span class="meta-chip">✂️ {{ doc.chunk_count }}块</span>
              <span v-if="doc.kb_id" class="meta-chip kb-chip" :title="kbNameOf(doc)">📚 {{ kbShortName(doc) }}</span>
            </div>
            <div class="doc-item-foot">
              <span class="doc-time">{{ formatTime(doc.created_at) }}</span>
              <span v-if="doc.parser === 'mineru_http'" class="parser-chip" title="由 MinerU 解析">MinerU</span>
            </div>
          </div>
        </div>
        <div class="pane-footer">
          <button class="btn btn-sm" :disabled="docPage <= 1" @click="loadDocuments(docPage - 1)">‹ 上一页</button>
          <span class="page-info">{{ docPage }} / {{ Math.max(1, docTotalPages) }}</span>
          <button class="btn btn-sm" :disabled="docPage >= docTotalPages" @click="loadDocuments(docPage + 1)">下一页 ›</button>
        </div>
      </div>

      <!-- 知识库编辑弹窗 -->
      <div v-if="kbDialogVisible" class="dialog-overlay" @click.self="kbDialogVisible = false">
        <div class="kb-dialog" @click.stop>
          <div class="dialog-header">
            <h3>{{ kbEditing ? '编辑知识库' : '新建知识库' }}</h3>
            <button class="btn-close" @click="kbDialogVisible = false">×</button>
          </div>
          <div class="dialog-body">
            <div class="form-group">
              <label>知识库名称 *</label>
              <input v-model="kbForm.kb_name" type="text" placeholder="例如：产品文档" />
            </div>
            <div class="form-group">
              <label>简介（用于 LLM 自动选库判断）</label>
              <textarea v-model="kbForm.description" rows="3" placeholder="描述这个库包含什么内容，LLM 会依据简介判断是否选它"></textarea>
            </div>
            <div class="form-group">
              <label>所属部门（可多选）</label>
              <div class="layer-checkboxes">
                <label v-for="layer in dataLayers" :key="layer.id" class="layer-checkbox">
                  <input type="checkbox" :value="layer.id" v-model="kbForm.layer_ids" />
                  <span>{{ layer.name }}</span>
                </label>
              </div>
              <div class="form-hint">不选则默认"全员"可见</div>
            </div>
          </div>
          <div class="dialog-footer">
            <button class="btn" @click="kbDialogVisible = false">取消</button>
            <button class="btn btn-primary" :disabled="kbSaving" @click="saveKb">{{ kbSaving ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>

      <!-- 中：Chunk 列表 -->
      <div class="card kb-pane kb-chunk-pane">
        <div class="pane-header">
          <span>知识块（Chunks）</span>
          <span v-if="selected" class="chunk-total">共 {{ selected.chunk_count }} 块</span>
        </div>
        <div class="pane-body">
          <div v-if="!selected" class="pane-empty"><p>← 选择左侧文档查看切分结果</p></div>
          <div v-else-if="loadingChunks" class="pane-empty"><div class="spinner"></div></div>
          <div v-else-if="chunks.length === 0" class="pane-empty">
            <p>{{ selected.status === 'needs_ocr' ? '⚠️ 扫描版 PDF 无文字层，无法切分' : selected.status === 'failed' ? '解析失败，无知识块' : '暂无知识块' }}</p>
            <p v-if="selected.error_message" class="pane-empty-hint error-text">{{ selected.error_message }}</p>
          </div>
          <div
            v-for="chunk in chunks"
            :key="chunk.id"
            class="chunk-item"
            :class="{ active: activeChunk?.id === chunk.id }"
            @click="activeChunk = chunk"
          >
            <div class="chunk-item-top">
              <span class="chunk-index">#{{ chunk.chunk_index + 1 }}</span>
              <span v-if="chunk.kind === 'parent'" class="kind-badge kind-parent" :title="`包含 ${chunk.child_count || 0} 个子片`">👨 父片</span>
              <span v-else-if="chunk.kind === 'child'" class="kind-badge kind-child" :title="`属于父片 #${getParentIndex(chunk.parent_chunk_id)}`">👧 子片</span>
              <span v-else-if="chunk.kind === 'topic'" class="kind-badge kind-topic" :title="chunk.topic_title || ''">🏷 主题块</span>
              <span v-else class="kind-badge kind-base">基础块</span>
              <span v-if="chunk.page_start" class="chunk-page">P{{ chunk.page_start }}{{ chunk.page_end && chunk.page_end !== chunk.page_start ? '-' + chunk.page_end : '' }}</span>
              <span class="chunk-chars">{{ chunk.char_count }} 字</span>
            </div>
            <div class="chunk-preview">{{ chunk.content.slice(0, 80) }}{{ chunk.content.length > 80 ? '…' : '' }}</div>
          </div>
        </div>
        <div class="pane-footer">
          <button class="btn btn-sm" :disabled="chunkPage <= 1 || !selected" @click="loadChunks(chunkPage - 1)">‹ 上一页</button>
          <span class="page-info">{{ chunkPage }} / {{ Math.max(1, chunkTotalPages) }}</span>
          <button class="btn btn-sm" :disabled="chunkPage >= chunkTotalPages || !selected" @click="loadChunks(chunkPage + 1)">下一页 ›</button>
        </div>
      </div>

      <!-- 右：内容预览 / 文档详情 -->
      <div class="card kb-pane kb-preview-pane">
        <template v-if="activeChunk">
          <div class="pane-header">
            <span>知识块 #{{ activeChunk.chunk_index + 1 }}</span>
            <div class="pane-header-actions">
              <div class="text-mode-switch">
                <button class="mode-btn" :class="{ active: chunkMode === 'render' }" @click="chunkMode = 'render'">渲染</button>
                <button class="mode-btn" :class="{ active: chunkMode === 'raw' }" @click="chunkMode = 'raw'">源码</button>
              </div>
              <button class="btn btn-sm" @click="activeChunk = null">返回文档</button>
            </div>
          </div>
          <div class="pane-body preview-body">
            <div class="chunk-meta">
              <span class="meta-chip">📄 {{ activeChunk.page_start ? '第 ' + activeChunk.page_start + ' 页' : '无页码' }}</span>
              <span class="meta-chip">{{ activeChunk.char_count }} 字符</span>
              <span v-if="activeChunk.kind === 'parent'" class="meta-chip kind-parent">
                👨 父片 · 包含 {{ activeChunk.child_count || 0 }} 个子片
              </span>
              <span v-else-if="activeChunk.kind === 'child'" class="meta-chip kind-child">
                👧 子片 · 属于父片 #{{ getParentIndex(activeChunk.parent_chunk_id) }}
              </span>
              <span v-else-if="activeChunk.kind === 'topic'" class="meta-chip kind-topic">🏷 主题块{{ activeChunk.topic_title ? ' · ' + activeChunk.topic_title : '' }}</span>
              <span v-else class="meta-chip">基础块</span>
            </div>
            <div v-if="activeChunk.kind === 'child'" class="chunk-hint">
              💡 <b>父子分片原理</b>：检索时命中此子片（{{ activeChunk.char_count }} 字），实际返回父片的完整内容（约 2000 字），确保 LLM 有足够上下文生成准确回答。
            </div>
            <div
              v-if="chunkMode === 'render'"
              class="markdown-body doc-text-md"
              v-html="activeChunkHtml"
            ></div>
            <pre v-else class="chunk-content">{{ activeChunk.content }}</pre>
          </div>
        </template>

        <template v-else-if="viewingText">
          <div class="pane-header">
            <span>📄 原文内容 · {{ docText?.original_name || '' }}</span>
            <div class="pane-header-actions">
              <div class="text-mode-switch">
                <button class="mode-btn" :class="{ active: textMode === 'render' }" @click="textMode = 'render'">渲染</button>
                <button class="mode-btn" :class="{ active: textMode === 'raw' }" @click="textMode = 'raw'">源码</button>
              </div>
              <button class="btn btn-sm" @click="viewingText = false">返回详情</button>
            </div>
          </div>
          <div class="pane-body preview-body">
            <div v-if="loadingText" class="pane-empty"><div class="spinner"></div></div>
            <div v-else-if="!docText || docText.needs_reprocess || !docText.text" class="pane-empty">
              <p>暂无原文文本</p>
              <p class="pane-empty-hint">旧数据未保存原文，请返回详情点击「重新解析」生成</p>
            </div>
            <template v-else>
              <div class="text-toolbar">
                <span class="meta-chip">{{ docText.char_count.toLocaleString() }} 字符</span>
                <span class="meta-chip">{{ textMode === 'render' ? 'Markdown 渲染' : '原始文本' }}</span>
              </div>
              <div
                v-if="textMode === 'render'"
                class="markdown-body doc-text-md"
                v-html="docTextHtml"
                @click="handleTextPaneClick"
              ></div>
              <pre v-else class="chunk-content">{{ docText.text }}</pre>
            </template>
          </div>
        </template>

        <template v-else-if="selected">
          <div class="pane-header"><span>文档详情</span></div>
          <div class="pane-body preview-body">
            <div class="doc-detail">
              <div class="doc-detail-name">{{ selected.original_name }}</div>
              <div class="doc-detail-grid">
                <div><span class="label">状态</span><span :class="['status-badge', 'status-' + selected.status]">{{ statusText(selected.status) }}</span></div>
                <div><span class="label">所属知识库</span>
                  <span class="doc-kb-info">
                    <span>{{ kbNameOf(selected) }}</span>
                    <select v-if="canManageKb && knowledgeBases.filter(kb => canManageKbItem(kb)).length > 1" v-model="moveKbId" class="kb-move-select" @change="moveDoc">
                      <option :value="null" disabled>移动到…</option>
                      <option v-for="kb in knowledgeBases.filter(kb => canManageKbItem(kb))" :key="kb.id" :value="kb.id" :disabled="kb.id === (selected as any).kb_id || !kb.is_enabled">
                        {{ kb.kb_name }}{{ !kb.is_enabled ? '（已禁用）' : '' }}
                      </option>
                    </select>
                  </span>
                </div>
                <div><span class="label">解析器</span><span>{{ selected.parser === 'mineru_http' ? 'MinerU（远程）' : '内置（pypdf）' }}</span></div>
                <div><span class="label">大小</span><span>{{ formatBytes(selected.size_bytes) }}</span></div>
                <div><span class="label">页数</span><span>{{ selected.page_count }}</span></div>
                <div><span class="label">字符数</span><span>{{ selected.char_count.toLocaleString() }}</span></div>
                <div><span class="label">知识块</span><span>{{ selected.chunk_count }}</span></div>
                <div><span class="label">切分参数</span><span>{{ selected.chunk_size }} / 重叠 {{ selected.chunk_overlap }}</span></div>
                <div><span class="label">切分策略</span><span>{{ strategyLabel(selected.chunk_strategy) }}</span></div>
                <div><span class="label">向量化</span><span>{{ selected.vectorized ? '✅ 已向量化' : '⏸ 未向量化' }}</span></div>
                <div><span class="label">知识图谱</span><span>{{ (selected as any).graph_extracted ? '✅ 已提取实体' : '⏸ 未提取' }}</span></div>
                <div><span class="label">上传时间</span><span>{{ formatTime(selected.created_at) }}</span></div>
                <div v-if="selected.sha256"><span class="label">SHA256</span><span class="sha" :title="selected.sha256">{{ selected.sha256.slice(0, 16) }}…</span></div>
              </div>
              <div v-if="selected.error_message" class="doc-error">❌ {{ selected.error_message }}</div>
              <div v-if="selected.status === 'needs_ocr'" class="doc-hint">
                ⚠️ 该 PDF 疑似扫描版（无文字层）。可在「系统配置」接入远程 MinerU 服务后重新解析，实现 OCR 级识别。
              </div>

              <div class="reprocess-box">
                <div class="reprocess-title">🔧 重新解析 / 切分</div>
                <div class="reprocess-row">
                  <label>切分策略
                    <select v-model="reStrategy">
                      <option value="parent_child">父子分片（推荐）</option>
                    </select>
                  </label>
                  <label>切分大小 <input v-model.number="reChunkSize" type="number" min="100" max="8000" step="100" /></label>
                  <label>重叠 <input v-model.number="reChunkOverlap" type="number" min="0" max="2000" step="50" /></label>
                  <label>解析器
                    <select v-model="reParser">
                      <option value="">auto</option>
                      <option value="builtin">builtin</option>
                      <option value="mineru_http">mineru_http</option>
                    </select>
                  </label>
                </div>
                <button class="btn btn-sm" :disabled="reprocessing" @click="handleReprocess">
                  {{ reprocessing ? '⏳ 解析中...' : '重新解析' }}
                </button>
              </div>

              <div class="doc-actions">
                <button class="btn btn-sm btn-primary" @click="handleViewText">📄 查看原文内容</button>
                <button class="btn btn-sm" @click="handleDownload">⬇️ 下载原文件</button>
                <button class="btn btn-sm" :disabled="graphExtracting" @click="handleGraphAction">
                  <template v-if="graphExtracting">⏳ 处理中...</template>
                  <template v-else-if="(selected as any).graph_extracted">🔄 刷新图谱</template>
                  <template v-else>🕸️ 提取图谱实体</template>
                </button>
                <button class="btn btn-sm btn-danger" @click="handleDelete(selected)">🗑️ 删除文档</button>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="pane-header"><span>文档详情</span></div>
          <div class="pane-body pane-empty">
            <p>选择左侧文档查看详情</p>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  deleteDocument as apiDeleteDocument,
  downloadDocument,
  getDocumentText as apiGetDocumentText,
  listChunks as apiListChunks,
  listDocuments as apiListDocuments,
  reprocessDocument as apiReprocess,
  uploadDocuments,
  type KbChunk,
  type KbDocument,
  type KbDocumentText,
} from '@/api/kb'
import { vectorizeDocument } from '@/api/kbEval'
import { renderMarkdown } from '@/utils/markdown'
import request from '@/api/request'

// ── 状态 ──
const docs = ref<KbDocument[]>([])
const total = ref(0)
const keyword = ref('')
const docPage = ref(1)
const pageSize = 20
const loadingDocs = ref(false)

const selected = ref<KbDocument | null>(null)
const chunks = ref<KbChunk[]>([])
const chunkPage = ref(1)
const chunkPageSize = 50
const chunkTotal = ref(0)
const loadingChunks = ref(false)
const activeChunk = ref<KbChunk | null>(null)

const viewingText = ref(false)
const docText = ref<KbDocumentText | null>(null)
const loadingText = ref(false)
const textMode = ref<'render' | 'raw'>('render')
const chunkMode = ref<'render' | 'raw'>('render')

const docTextHtml = computed(() => (docText.value ? renderMarkdown(docText.value.text) : ''))
const activeChunkHtml = computed(() => (activeChunk.value ? renderMarkdown(activeChunk.value.content) : ''))

const uploading = ref(false)
const uploadError = ref('')
const uploadMsg = ref('')
const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()
const optKbId = ref<number | null>(null)
const optStrategy = ref<'fixed' | 'topic' | 'parent_child'>('parent_child')
const optChunkSize = ref(2000)
const optChunkOverlap = ref(200)
const optParser = ref('')

const reprocessing = ref(false)
const reStrategy = ref<'fixed' | 'topic' | 'parent_child'>('parent_child')
const reChunkSize = ref(2000)
const reChunkOverlap = ref(200)
const reParser = ref('')
const graphExtracting = ref(false)

// ── 知识库列表与管理 ──
interface KnowledgeBase {
  id: number
  kb_name: string
  description: string
  is_enabled: number
  layer_ids?: number[]
  layer_names?: string[]
}
const knowledgeBases = ref<KnowledgeBase[]>([])
const currentKbId = ref<number | null>(null)
const kbDialogVisible = ref(false)
const kbEditing = ref<KnowledgeBase | null>(null)
const kbSaving = ref(false)
const kbForm = ref({ kb_name: '', description: '', layer_ids: [] as number[] })

// ── 数据层级（部门）──
interface DataLayer {
  id: number
  name: string
  description?: string
}
const dataLayers = ref<DataLayer[]>([])
const userLayerIds = ref<number[]>([0]) // 当前用户的部门

async function loadDataLayers() {
  try {
    const res = await request.get('/api/data-layers')
    dataLayers.value = res.data.data || []
  } catch (e) {
    console.error('加载部门失败:', e)
  }
}

async function loadUserLayers() {
  try {
    const userId = localStorage.getItem('chatUserId') || '0'
    const res = await request.get(`/api/data-layers/user/${userId}`)
    userLayerIds.value = res.data.layer_ids || [0]
  } catch (e) {
    console.error('加载用户部门失败:', e)
    userLayerIds.value = [0]
  }
}

function getLayerNames(kb: KnowledgeBase): string {
  if (kb.layer_names && kb.layer_names.length > 0) {
    return kb.layer_names.join(', ')
  }
  return '全员'
}

// 是否有知识库管理权限（kb.manage）
const canManageKb = computed(() => {
  const perms: string[] = JSON.parse(localStorage.getItem('userPermissions') || '[]')
  const role = localStorage.getItem('userRole') || ''
  return role === 'super_admin' || perms.includes('kb.manage')
})

// 检查用户是否可以管理指定的知识库（kb.manage 可管理所有知识库）
function canManageKbItem(kb: KnowledgeBase): boolean {
  const perms: string[] = JSON.parse(localStorage.getItem('userPermissions') || '[]')
  const role = localStorage.getItem('userRole') || ''
  // super_admin 或 kb.manage 可以管理所有知识库
  return role === 'super_admin' || perms.includes('kb.manage')
}

// 按部门筛选后的知识库列表
const filteredKnowledgeBases = computed(() => {
  return knowledgeBases.value
})

async function loadKnowledgeBases() {
  try {
    const res = await request.get('/api/kb/knowledge-bases')
    knowledgeBases.value = res.data.knowledge_bases || []
    // 默认选中第一个启用的知识库
    if (currentKbId.value === null && knowledgeBases.value.length > 0) {
      const first = knowledgeBases.value.find(kb => kb.is_enabled) || knowledgeBases.value[0]
      currentKbId.value = first.id
      optKbId.value = first.id
    }
    // 知识库列表加载后同步刷新文档列表（避免显示全部文档）
    if (currentKbId.value !== null) {
      await loadDocuments(1)
    }
  } catch (error) {
    console.error('加载知识库列表失败:', error)
  }
}

// 仅刷新知识库统计（doc_count/chunk_count），不重载文档列表
async function refreshKbStats() {
  try {
    const res = await request.get('/api/kb/knowledge-bases')
    knowledgeBases.value = res.data.knowledge_bases || []
  } catch { /* 静默 */ }
}

function switchKb(kbId: number) {
  currentKbId.value = kbId
  optKbId.value = kbId
  selected.value = null
  chunks.value = []
  loadDocuments(1)
}

function openKbCreate() {
  kbEditing.value = null
  kbForm.value = { kb_name: '', description: '', layer_ids: [0] }
  kbDialogVisible.value = true
}

function openKbEdit(kb: KnowledgeBase) {
  kbEditing.value = kb
  kbForm.value = { kb_name: kb.kb_name, description: kb.description || '', layer_ids: kb.layer_ids || [0] }
  kbDialogVisible.value = true
}

async function saveKb() {
  if (!kbForm.value.kb_name.trim()) {
    alert('请输入知识库名称')
    return
  }
  kbSaving.value = true
  try {
    const payload = { ...kbForm.value }
    if (kbEditing.value) {
      await request.put(`/api/kb/knowledge-bases/${kbEditing.value.id}`, payload)
      // 单独保存层级
      await request.put(`/api/data-layers/kb/${kbEditing.value.id}`, { layer_ids: kbForm.value.layer_ids })
    } else {
      const res = await request.post('/api/kb/knowledge-bases', payload)
      const newKbId = res.data.knowledge_base?.id
      if (newKbId) {
        await request.put(`/api/data-layers/kb/${newKbId}`, { layer_ids: kbForm.value.layer_ids })
      }
    }
    kbDialogVisible.value = false
    await loadKnowledgeBases()
    await loadDocuments(1)
  } catch (e: any) {
    alert('保存失败: ' + (e?.message || '未知错误'))
  } finally {
    kbSaving.value = false
  }
}

async function toggleKb(kb: KnowledgeBase) {
  try {
    await request.put(`/api/kb/knowledge-bases/${kb.id}`, { is_enabled: kb.is_enabled ? 0 : 1 })
    await loadKnowledgeBases()
    await loadDocuments(1)
  } catch (e: any) {
    alert('操作失败: ' + (e?.message || '未知错误'))
  }
}

async function deleteKb(kb: KnowledgeBase) {
  if (!confirm(`确定删除知识库"${kb.kb_name}"？该库下所有文档和分片将被删除。`)) return
  try {
    await request.delete(`/api/kb/knowledge-bases/${kb.id}`)
    if (currentKbId.value === kb.id) currentKbId.value = null
    await loadKnowledgeBases()
    await loadDocuments(1)
  } catch (e: any) {
    alert('删除失败: ' + (e?.message || '未知错误'))
  }
}

// 文档所属知识库名称
function kbNameOf(doc: KbDocument): string {
  const kbId = (doc as any).kb_id
  const kb = knowledgeBases.value.find(k => k.id === kbId)
  return kb ? kb.kb_name : '未分配'
}

// 文档所属知识库简称（用于列表显示）
function kbShortName(doc: KbDocument): string {
  const kbId = (doc as any).kb_id
  const kb = knowledgeBases.value.find(k => k.id === kbId)
  if (!kb) return ''
  // 取前4个字符作为简称
  return kb.kb_name.length > 4 ? kb.kb_name.slice(0, 4) + '…' : kb.kb_name
}

// 知识库统计信息（使用服务端返回的 doc_count / chunk_count）
function kbStats(kb: KnowledgeBase): { label: string; title: string } {
  const docCount = (kb as any).doc_count ?? 0
  const chunkCount = (kb as any).chunk_count ?? 0
  return {
    label: `${docCount}篇`,
    title: `${docCount} 篇文档，${chunkCount} 个分片`
  }
}

// 移动文档到其他知识库
const moveKbId = ref<number | null>(null)
async function moveDoc() {
  if (!selected.value || !moveKbId.value) return
  try {
    await request.post(`/api/kb/documents/${selected.value.id}/move`, { kb_id: moveKbId.value })
    moveKbId.value = null
    alert('✅ 文档已移动')
    // 若移动到了非当前知识库，从列表移除；否则刷新
    if (currentKbId.value !== null && currentKbId.value !== moveKbId.value) {
      docs.value = docs.value.filter(d => d.id !== selected.value?.id)
      selected.value = null
    }
    await loadDocuments(docPage.value)
    await refreshKbStats()
  } catch (e: any) {
    alert('移动失败: ' + (e?.message || '未知错误'))
  }
}

// ── 计算属性 ──
const docTotalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const chunkTotalPages = computed(() => Math.max(1, Math.ceil(chunkTotal.value / chunkPageSize)))

// ── 工具函数 ──
function strategyLabel(strategy: string): string {
  const labels: Record<string, string> = {
    fixed: '📏 固定窗口（已废弃）',
    topic: '🧩 主题聚合（旧）',
    parent_child: '👨‍👧 父子分片',
  }
  return labels[strategy] || strategy
}

// 获取父片的 chunk_index（用于子片显示"属于父片 #X"）
function getParentIndex(parentChunkId: number | null): string {
  if (!parentChunkId) return '?'
  const parent = chunks.value.find(c => c.id === parentChunkId)
  return parent ? String(parent.chunk_index + 1) : '?'
}

// ── 数据加载 ──

async function loadDocuments(page: number) {
  loadingDocs.value = true
  docPage.value = Math.max(1, page)
  try {
    const params: any = { keyword: keyword.value, page: docPage.value, page_size: pageSize }
    if (currentKbId.value !== null) params.kb_id = currentKbId.value
    const data = await apiListDocuments(params)
    docs.value = data.items
    total.value = data.total
  } catch (e: any) {
    uploadError.value = e?.message || '加载文档列表失败'
  } finally {
    loadingDocs.value = false
  }
}

async function loadChunks(page: number) {
  if (!selected.value) return
  loadingChunks.value = true
  chunkPage.value = Math.max(1, page)
  try {
    const data = await apiListChunks(selected.value.id, chunkPage.value, chunkPageSize)
    chunks.value = data.items
    chunkTotal.value = data.total
  } catch (e: any) {
    uploadError.value = e?.message || '加载知识块失败'
  } finally {
    loadingChunks.value = false
  }
}

function selectDoc(doc: KbDocument) {
  selected.value = doc
  activeChunk.value = null
  viewingText.value = false
  docText.value = null
  chunkPage.value = 1
  // 旧策略名 topic 归一化为 parent_child（合并后同一实现）
  const legacy = doc.chunk_strategy || 'fixed'
  reStrategy.value = (legacy === 'topic' ? 'parent_child' : legacy) as 'fixed' | 'topic' | 'parent_child'
  reChunkSize.value = doc.chunk_size || 2000
  reChunkOverlap.value = doc.chunk_overlap || 200
  reParser.value = ''
  loadChunks(1)
}

// ── 上传 ──

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    doUpload(Array.from(target.files))
    target.value = ''
  }
}

function handleDrop(e: DragEvent) {
  dragging.value = false
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    doUpload(Array.from(e.dataTransfer.files))
  }
}

async function doUpload(files: File[]) {
  uploading.value = true
  uploadError.value = ''
  uploadMsg.value = ''
  try {
    // 默认上传到当前选中的知识库（未选择则用下拉框的值）
    const targetKbId = currentKbId.value !== null ? currentKbId.value : optKbId.value
    const res = await uploadDocuments(files, {
      chunk_size: optChunkSize.value || undefined,
      chunk_overlap: optChunkOverlap.value,
      parser: optParser.value,
      chunk_strategy: optStrategy.value,
      kb_id: targetKbId || undefined,
    })
    const docs = res.documents || []
    const failed = docs.filter((d) => d.status === 'failed')
    const ocr = docs.filter((d) => d.status === 'needs_ocr')
    const ok = docs.filter((d) => d.status === 'parsed')

    const parts: string[] = []
    if (ok.length) parts.push(`✅ 成功解析 ${ok.length} 个文档`)
    if (ocr.length) parts.push(`⚠️ ${ocr.length} 个疑似扫描版（需 OCR）`)
    if (failed.length) parts.push(`❌ ${failed.length} 个解析失败`)
    uploadMsg.value = parts.join('，')

    await loadDocuments(1)
    await refreshKbStats()
    if (docs.length > 0) {
      const first = docs[0]
      selectDoc({ ...first, user_id: first.user_id || 0 } as KbDocument)
    }

    // ★ 上传成功后自动向量化（仅对解析成功的文档）
    const vectorizePromises = ok
      .filter((d) => d.id && !d.vectorized)
      .map(async (d) => {
        try {
          await vectorizeDocument(d.id)
          return { id: d.id, success: true }
        } catch (e: any) {
          console.warn(`[KB] 自动向量化失败 doc_id=${d.id}:`, e?.message || e)
          return { id: d.id, success: false, error: e?.message || '向量化失败' }
        }
      })
    if (vectorizePromises.length > 0) {
      uploadMsg.value += ` | ⏳ 正在向量化 ${vectorizePromises.length} 个文档...`
      const results = await Promise.allSettled(vectorizePromises)
      const successCount = results.filter(r => r.status === 'fulfilled' && r.value.success).length
      const failCount = results.length - successCount
      if (successCount > 0) {
        uploadMsg.value = uploadMsg.value.replace(/ \| ⏳ .*$/, '') + ` | ✅ 已向量化 ${successCount} 个文档`
      }
      if (failCount > 0) {
        uploadMsg.value += `（${failCount} 个失败）`
      }
      await loadDocuments(1)
      await refreshKbStats()
    }
  } catch (e: any) {
    uploadError.value = e?.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

// ── 操作 ──

async function handleDownload() {
  if (!selected.value) return
  try {
    await downloadDocument(selected.value.id, selected.value.original_name)
  } catch (e: any) {
    alert(e?.message || '下载失败')
  }
}

async function handleViewText() {
  if (!selected.value) return
  loadingText.value = true
  viewingText.value = true
  docText.value = null
  textMode.value = 'render'
  uploadError.value = ''
  try {
    docText.value = await apiGetDocumentText(selected.value.id)
  } catch (e: any) {
    uploadError.value = e?.message || '获取原文失败'
    viewingText.value = false
  } finally {
    loadingText.value = false
  }
}

/** 代码块复制按钮点击委托（markdown 渲染产物） */
function handleTextPaneClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest('.code-block-copy-btn')
  if (!btn) return
  const code = btn.closest('pre')?.querySelector('code')
  const text = code?.textContent || ''
  if (!text) return
  navigator.clipboard.writeText(text)
    .then(() => {
      btn.textContent = '✅'
      setTimeout(() => { btn.textContent = '复制' }, 1500)
    })
    .catch(() => {})
}

async function handleReprocess() {
  if (!selected.value) return
  reprocessing.value = true
  uploadError.value = ''
  try {
    const updated = await apiReprocess(selected.value.id, {
      chunk_size: reChunkSize.value || undefined,
      chunk_overlap: reChunkOverlap.value,
      parser: reParser.value,
      chunk_strategy: reStrategy.value,
    })
    selected.value = updated
    await loadChunks(1)
    await loadDocuments(docPage.value)
    uploadMsg.value = updated.status === 'parsed' ? '✅ 重新解析完成' : `⚠️ 状态: ${statusText(updated.status)}`
  } catch (e: any) {
    uploadError.value = e?.message || '重新解析失败'
  } finally {
    reprocessing.value = false
  }
}

async function handleDelete(doc: KbDocument) {
  if (!confirm(`确定删除「${doc.original_name}」？\n文件与全部知识块将一并删除，且不可恢复。`)) return
  try {
    await apiDeleteDocument(doc.id)
    if (selected.value?.id === doc.id) {
      selected.value = null
      activeChunk.value = null
      viewingText.value = false
      docText.value = null
      chunks.value = []
      chunkTotal.value = 0
    }
    await loadDocuments(1)
    await refreshKbStats()
  } catch (e: any) {
    uploadError.value = e?.message || '删除失败'
  }
}

// ── GraphRAG 操作 ──

async function handleGraphAction() {
  if (!selected.value) return
  
  const alreadyExtracted = (selected.value as any).graph_extracted
  
  // 如果已提取，需要确认是否刷新
  if (alreadyExtracted) {
    if (!confirm(`确定重新提取「${selected.value.original_name}」的知识图谱？\n这将删除旧实体后重新提取。`)) return
    await handleGraphRefresh()
  } else {
    await handleGraphExtract()
  }
}

async function handleGraphExtract() {
  if (!selected.value) return
  
  // 检查是否已在提取中
  try {
    const status = await request.get(`/api/graph/documents/${selected.value.id}/extracting`)
    if (status.data.extracting) {
      uploadError.value = '⏳ 文档正在提取中，请稍后再试'
      return
    }
  } catch (e) {
    // 忽略检查错误，继续提取
  }
  
  graphExtracting.value = true
  uploadError.value = ''
  try {
    const res = await request.post(`/api/graph/documents/${selected.value.id}/extract`)
    uploadMsg.value = `✅ 已提取 ${res.entities_created} 个实体，${res.relations_created} 个关系`
    if (selected.value) {
      (selected.value as any).graph_extracted = 1
    }
    await loadDocuments(docPage.value)
  } catch (e: any) {
    uploadError.value = e?.response?.data?.detail || e?.message || '提取失败'
  } finally {
    graphExtracting.value = false
  }
}

async function handleGraphRefresh() {
  if (!selected.value) return
  graphExtracting.value = true
  uploadError.value = ''
  try {
    const res = await request.post(`/api/graph/documents/${selected.value.id}/refresh`)
    uploadMsg.value = `✅ 已删除 ${res.deleted.deleted_entities} 个旧实体，重新提取 ${res.extracted.entities} 个实体`
    await loadDocuments(docPage.value)
  } catch (e: any) {
    uploadError.value = e?.response?.data?.detail || e?.message || '刷新失败'
  } finally {
    graphExtracting.value = false
  }
}

// ── 格式化工具 ──

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(2) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}

function formatTime(t: string): string {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    parsing: '⏳ 解析中',
    parsed: '🟢 已解析',
    failed: '🔴 失败',
    needs_ocr: '⚠️ 需OCR',
  }
  return map[status] || status
}

onMounted(() => {
  loadDocuments(1)
  loadKnowledgeBases()
  loadDataLayers()
  loadUserLayers()
})
</script>

<style scoped>
.page-container { padding: 24px; max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; height: 100vh; box-sizing: border-box; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-shrink: 0; }
.page-title { font-size: 22px; font-weight: 600; margin: 0; color: var(--text-primary); }
.page-desc { color: var(--text-tertiary); font-size: 13px; margin: 6px 0 0; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.doc-count { font-size: 13px; color: var(--text-secondary); }

.btn { border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; transition: var(--transition); background: var(--bg-hover); color: var(--text-primary); text-decoration: none; display: inline-flex; align-items: center; gap: 4px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--brand-gradient); color: white; }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn-danger { background: var(--danger-light, #fdecea); color: #d93025; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 2px 6px; border-radius: 6px; }
.btn-icon:hover { background: var(--bg-hover); }

.card { background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 12px; }

/* ── 上传区 ── */
.upload-zone { padding: 14px 18px; transition: border-color 0.2s; flex-shrink: 0; position: relative; }
.upload-zone.dragging { border-color: var(--brand); border-style: dashed; }
.upload-zone-topbar { position: absolute; top: 10px; right: 12px; z-index: 1; }
.btn-upload { padding: 5px 12px; font-size: 12px; }
.upload-zone.dragging { border-color: var(--brand); border-style: dashed; }
.upload-zone-inner { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.upload-icon { font-size: 26px; }
.upload-text { font-size: 13px; color: var(--text-secondary); }
.upload-text a { color: var(--brand); cursor: pointer; }
.upload-hint { font-size: 11px; color: var(--text-placeholder); margin-top: 2px; }
.upload-options { margin-left: auto; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.upload-options label, .reprocess-row label { font-size: 12px; color: var(--text-secondary); display: inline-flex; align-items: center; gap: 5px; }
.upload-options input, .upload-options select, .reprocess-row input, .reprocess-row select {
  background: var(--bg-secondary, #f5f6f8); border: 1px solid var(--border-primary); color: var(--text-primary);
  border-radius: 6px; padding: 4px 8px; font-size: 12px; width: 90px;
}
.upload-options select, .reprocess-row select { width: auto; }
.upload-error { margin-top: 8px; color: #d93025; font-size: 12px; }
.upload-msg { margin-top: 8px; color: var(--brand); font-size: 12px; }

/* ── 三栏布局 ── */
.kb-layout { display: grid; grid-template-columns: 300px minmax(280px, 1fr) minmax(320px, 1.2fr); gap: 14px; flex: 1; min-height: 0; }
.kb-pane { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.pane-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border-primary); font-size: 13px; font-weight: 600; color: var(--text-primary); flex-shrink: 0; gap: 8px; }

/* ── 知识库选择器 ── */
.kb-selector { border-bottom: 1px solid var(--border-primary); flex-shrink: 0; max-height: 180px; overflow-y: auto; }
.kb-selector-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; font-size: 12px; font-weight: 600; color: var(--text-tertiary); }
.kb-selector-actions { display: flex; align-items: center; gap: 4px; }
.kb-type-filter { font-size: 11px; padding: 2px 6px; border: 1px solid var(--border-primary); border-radius: 4px; background: var(--bg-primary); color: var(--text-secondary); cursor: pointer; outline: none; }
.kb-type-filter:focus { border-color: var(--brand); }
.kb-selector-list { padding: 0 8px 8px; }
.kb-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 8px; cursor: pointer; font-size: 12px; transition: var(--transition); }
.kb-item:hover { background: var(--bg-hover); }
.kb-item.active { background: var(--brand-light); color: var(--brand); font-weight: 500; }
.kb-item.disabled { opacity: 0.55; background: rgba(198, 40, 40, 0.04); }
.kb-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-item-type { font-size: 10px; color: var(--text-tertiary); background: var(--bg-tertiary); padding: 1px 6px; border-radius: 8px; flex-shrink: 0; }
.kb-item-stats { font-size: 10px; color: var(--text-tertiary); flex-shrink: 0; }
.kb-item-disabled { font-size: 10px; color: #c62828; background: #ffebee; padding: 1px 6px; border-radius: 8px; flex-shrink: 0; font-weight: 600; }
.kb-item-actions { display: flex; gap: 2px; flex-shrink: 0; opacity: 0; transition: opacity 0.2s; }
.kb-item:hover .kb-item-actions { opacity: 1; }
.kb-item-actions .btn-icon { font-size: 12px; padding: 2px 4px; }

/* 文档所属知识库 */
.doc-kb-info { display: flex; align-items: center; gap: 6px; }
.kb-move-select { padding: 2px 6px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 11px; max-width: 150px; }
.kb-chip { background: var(--brand-light); color: var(--brand); }

/* ── 知识库编辑弹窗 ── */
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.kb-dialog { background: var(--bg-primary); border-radius: 12px; width: 90%; max-width: 480px; max-height: 90vh; overflow-y: auto; }
.dialog-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-primary); }
.dialog-header h3 { margin: 0; font-size: 16px; }
.btn-close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text-tertiary); }
.dialog-body { padding: 20px; }
.dialog-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 20px; border-top: 1px solid var(--border-primary); }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; }
.form-group textarea { resize: vertical; min-height: 70px; }
.form-hint { font-size: 11px; color: var(--text-tertiary); margin-top: 4px; }
.layer-checkboxes { display: flex; flex-wrap: wrap; gap: 8px; }
.layer-checkbox { display: flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer; }
.layer-checkbox input { width: auto; margin: 0; }
.kb-item-dept { font-size: 10px; color: var(--text-tertiary); background: var(--bg-secondary); padding: 1px 5px; border-radius: 3px; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pane-header .chunk-total { font-size: 11px; font-weight: 400; color: var(--text-tertiary); }
.pane-body { flex: 1; overflow-y: auto; padding: 8px; min-height: 0; }
.pane-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-placeholder); font-size: 13px; gap: 6px; text-align: center; padding: 16px; }
.pane-empty-hint { font-size: 12px; }
.error-text { color: #d93025; }
.pane-footer { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 8px; border-top: 1px solid var(--border-primary); flex-shrink: 0; }
.page-info { font-size: 12px; color: var(--text-secondary); min-width: 60px; text-align: center; }

.spinner { width: 28px; height: 28px; border: 3px solid var(--border-primary); border-top-color: var(--brand); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 文档列表 ── */
.pane-search { display: flex; align-items: center; gap: 4px; }
.pane-search input { background: var(--bg-secondary, #f5f6f8); border: 1px solid var(--border-primary); color: var(--text-primary); border-radius: 6px; padding: 4px 8px; font-size: 12px; width: 130px; }
.doc-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; transition: background 0.15s; }
.doc-item:hover { background: var(--bg-hover); }
.doc-item.active { background: var(--brand-light); }
.doc-item-top { display: flex; align-items: center; gap: 6px; }
.doc-ext { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--brand); background: var(--brand-light); border-radius: 4px; padding: 1px 5px; flex-shrink: 0; }
.doc-name { font-size: 13px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.doc-item-meta { display: flex; align-items: center; gap: 6px; margin-top: 5px; }
.doc-item-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
.doc-time { font-size: 11px; color: var(--text-placeholder); }
.meta-chip { font-size: 11px; color: var(--text-tertiary); }
.parser-chip { font-size: 10px; color: #b26a00; background: #fff4e0; padding: 1px 5px; border-radius: 4px; }

/* ── 状态徽标 ── */
.status-badge { font-size: 11px; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
.status-parsed { background: #e6f4ea; color: #188038; }
.status-parsing { background: #e8f0fe; color: #1a73e8; }
.status-failed { background: #fdecea; color: #d93025; }
.status-needs_ocr { background: #fff4e0; color: #b26a00; }

/* ── Chunk 列表 ── */
.chunk-item { padding: 7px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; transition: background 0.15s; border: 1px solid transparent; }
.chunk-item:hover { background: var(--bg-hover); }
.chunk-item.active { background: var(--brand-light); border-color: var(--brand); }
.chunk-item-top { display: flex; align-items: center; gap: 8px; }
.chunk-index { font-size: 12px; font-weight: 600; color: var(--brand); }
.kind-badge { font-size: 10px; padding: 1px 6px; border-radius: 4px; flex-shrink: 0; }
.kind-base { background: var(--bg-secondary, #f0f1f4); color: var(--text-tertiary); }
.kind-topic { background: #e6f4ea; color: #188038; }
.kind-parent { background: #e8f0fe; color: #1967d2; }
.kind-child { background: #fce8e6; color: #c5221f; }
.chunk-page { font-size: 11px; color: var(--text-tertiary); }
.chunk-chars { font-size: 11px; color: var(--text-placeholder); margin-left: auto; }
.chunk-preview { font-size: 12px; color: var(--text-secondary); margin-top: 3px; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ── 预览/详情 ── */
.preview-body { padding: 14px; }
.pane-header-actions { display: flex; align-items: center; gap: 8px; }
.text-mode-switch { display: inline-flex; border: 1px solid var(--border-primary); border-radius: 6px; overflow: hidden; }
.mode-btn { background: none; border: none; cursor: pointer; font-size: 11px; padding: 4px 10px; color: var(--text-secondary); transition: background 0.15s; }
.mode-btn.active { background: var(--brand); color: white; }
.text-toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.doc-text-md { font-size: 13px; line-height: 1.7; color: var(--text-primary); background: var(--bg-secondary, #f7f8fa); border: 1px solid var(--border-primary); border-radius: 8px; padding: 14px; overflow: auto; }
.doc-text-md :deep(pre) { background: rgba(0,0,0,0.04); border-radius: 6px; padding: 10px 12px; overflow-x: auto; }
.doc-text-md :deep(pre.code-block) { position: relative; padding-top: 26px; }
.doc-text-md :deep(.code-block-copy-btn) {
  position: absolute; right: 6px; top: 4px;
  font-size: 11px; padding: 2px 8px; border-radius: 4px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary, #fff); color: var(--text-secondary);
  cursor: pointer;
}
.doc-text-md :deep(.code-block-copy-btn:hover) { color: var(--brand); border-color: var(--brand); }
.chunk-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.meta-chip.kind-parent { background: #e8f0fe; color: #1967d2; }
.meta-chip.kind-child { background: #fce8e6; color: #c5221f; }
.meta-chip.kind-topic { background: #e6f4ea; color: #188038; }
.chunk-hint { 
  font-size: 12px; 
  padding: 10px 12px; 
  margin-bottom: 12px; 
  background: #fff3cd; 
  border-left: 3px solid #ffc107; 
  border-radius: 4px;
  color: #856404;
  line-height: 1.6;
}
.chunk-content { font-family: inherit; font-size: 13px; line-height: 1.7; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; margin: 0; background: var(--bg-secondary, #f7f8fa); border: 1px solid var(--border-primary); border-radius: 8px; padding: 14px; }
.doc-detail-name { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; word-break: break-all; }
.doc-detail-grid { display: grid; grid-template-columns: auto 1fr; gap: 8px 14px; font-size: 13px; align-items: center; }
.doc-detail-grid .label { color: var(--text-tertiary); font-size: 12px; }
.doc-error { margin-top: 12px; background: #fdecea; color: #d93025; border-radius: 8px; padding: 8px 12px; font-size: 12px; word-break: break-all; }
.doc-hint { margin-top: 12px; background: #fff4e0; color: #b26a00; border-radius: 8px; padding: 8px 12px; font-size: 12px; }
.sha { font-family: monospace; font-size: 12px; }
.reprocess-box { margin-top: 16px; border: 1px dashed var(--border-primary); border-radius: 8px; padding: 10px 12px; }
.reprocess-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.reprocess-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.doc-actions { display: flex; gap: 10px; margin-top: 16px; }

@media (max-width: 1100px) {
  .kb-layout { grid-template-columns: 260px 1fr; }
  .kb-preview-pane { grid-column: 1 / -1; max-height: 380px; }
}
</style>
