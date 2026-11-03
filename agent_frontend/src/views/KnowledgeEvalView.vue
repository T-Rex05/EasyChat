<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">🧪 RAG 测评</h1>
        <p class="page-desc">分层评测：检索层（Recall@K / MRR / NDCG）+ 生成层（RAGAS LLM 裁判）</p>
      </div>
      <div class="header-actions">
        <button class="btn" @click="showGuide = !showGuide">{{ showGuide ? '收起说明' : '📖 使用说明' }}</button>
        <button class="btn btn-primary" @click="openCreateSet">+ 新建测评集</button>
      </div>
    </header>

    <!-- 使用说明（首次使用引导，默认展开） -->
    <div v-if="showGuide" class="card guide-card">
      <div class="guide-header">
        <span>📖 使用说明</span>
        <button class="guide-close-btn" title="收起说明" @click="showGuide = false">✕ 收起</button>
      </div>
      <div class="guide-steps">
        <div class="guide-step">
          <div class="step-num">1</div>
          <div class="step-body">
            <div class="step-title">准备知识库文档</div>
            <div class="step-desc">在「📚 知识库」上传 PDF / MD 等文档并完成切分。</div>
          </div>
        </div>
        <div class="guide-step">
          <div class="step-num">2</div>
          <div class="step-body">
            <div class="step-title">创建测评集 + 标注题目</div>
            <div class="step-desc">新建测评集后逐条添加：写一个真实会问的问题（如「Redis 为什么会缓存雪崩」），然后点「📌 选择正确 chunk」把<b>人工认定的正确答案所在块（GT）</b>勾选进来。GT 标得越准，评测越可信。</div>
          </div>
        </div>
        <div class="guide-step">
          <div class="step-num">3</div>
          <div class="step-body">
            <div class="step-title">运行评测</div>
            <div class="step-desc">选择参数后点「▶ 开始评测」：「生成答案」会模拟真实 RAG 生成流程；「LLM 裁判」使用 RAGAS 给生成层打分（需配置模型）。</div>
          </div>
        </div>
        <div class="guide-step">
          <div class="step-num">4</div>
          <div class="step-body">
            <div class="step-title">看结果、定位问题</div>
            <div class="step-desc">先看聚合指标：<b>检索层全高</b>说明检索没问题，问题在生成/提示词；<b>Recall@K 低</b>说明检索没找到正确答案（换切分策略或调 top-K）；展开逐条记录可看具体检索回了哪些块（✅ GT 高亮）和生成答案。</div>
          </div>
        </div>
      </div>
      <div class="guide-metrics">
        <div class="guide-metrics-title">指标速查</div>
        <div class="guide-metric-grid">
          <div class="guide-metric"><b>Recall@K</b>：正确答案出现在 top-K 中（0/1）</div>
          <div class="guide-metric"><b>MRR</b>：正确答案排名倒数的均值（1=永远第一名）</div>
          <div class="guide-metric"><b>NDCG@K</b>：正确块排得越靠前分越高</div>
          <div class="guide-metric"><b>Precision@K</b>：top-K 中正确块占比（检测垃圾块干扰）</div>
          <div class="guide-metric"><b>Faithfulness</b>：回答是否忠实于检索上下文（防幻觉）</div>
          <div class="guide-metric"><b>Answer Relevancy</b>：回答是否切题</div>
          <div class="guide-metric"><b>Context Precision</b>：检索上下文是否把正确内容排前面</div>
          <div class="guide-metric"><b>Answer Correctness</b>：答案正确性（需提供参考答案）</div>
        </div>
      </div>
      <div class="guide-notes">
        <div class="guide-notes-title">注意事项</div>
        <ul>
          <li><b>GT 标注</b>：标注的是知识块（chunk）而非整篇文档；问题对应的正确内容分散在多个块时可以多选。</li>
          <li><b>向量检索需 embedding 服务</b>：未配置 `RAG_EMBEDDING_*` 时自动降级 BM25 关键词检索（结果仍可对比策略）。</li>
          <li><b>切换切分策略会使 chunk id 全部变化</b>：已有题目的 GT 标注将失效，需重新标注。</li>
          <li><b>Answer Relevancy 指标</b>需要 embedding 服务，未配置时自动跳过（其余指标不受影响）。</li>
          <li>评测在后台运行，可离开页面；回来后在「运行历史」查看结果。</li>
        </ul>
      </div>
    </div>

    <div v-if="banner" class="eval-banner">{{ banner }}</div>

    <div class="eval-layout">
      <!-- 左：测评集列表 / 测评集详情 + 题目列表 -->
      <div class="card pane pane-left">
        <!-- ★ 详情模式：显示测评集详情 + 题目列表 -->
        <template v-if="detailMode && selectedSet">
          <div class="pane-header">
            <button class="btn btn-sm" @click="exitDetailMode">← 返回列表</button>
          </div>
          <div class="pane-body">
            <!-- 测评集详情卡片 -->
            <div class="set-detail-card">
              <div class="set-detail-name">{{ selectedSet.name }}</div>
              <div class="set-detail-meta">
                <div class="set-detail-row">
                  <span class="set-detail-label">📝 题目数量</span>
                  <span class="set-detail-value">{{ selectedSet.item_count }} 题</span>
                </div>
                <div class="set-detail-row">
                  <span class="set-detail-label">📅 创建时间</span>
                  <span class="set-detail-value">{{ formatTime(selectedSet.created_at) }}</span>
                </div>
                <div v-if="selectedSet.description" class="set-detail-row">
                  <span class="set-detail-label">📄 描述</span>
                  <span class="set-detail-value">{{ selectedSet.description }}</span>
                </div>
              </div>
              <div class="set-detail-actions">
                <button class="btn btn-sm btn-primary" @click="openItemEditor()">+ 添加题目</button>
                <button class="btn btn-sm" @click="openRenameSet(selectedSet)">✏️ 重命名</button>
              </div>
            </div>

            <!-- 题目列表 -->
            <div class="section-block" style="margin-top: 12px;">
              <div class="section-title">
                <span>📋 题目列表</span>
                <span v-if="itemSearchKeyword" class="search-count">({{ filteredItems.length }}/{{ items.length }})</span>
              </div>
              <!-- 搜索栏 -->
              <div class="item-search-bar">
                <input
                  v-model="itemSearchKeyword"
                  type="text"
                  placeholder="搜索问题或 chunk ID（支持前缀匹配）"
                  class="item-search-input"
                />
                <button v-if="itemSearchKeyword" class="btn-icon-sm" @click="itemSearchKeyword = ''">✕</button>
              </div>
              <div v-if="filteredItems.length === 0" class="pane-empty-hint">
                {{ items.length === 0 ? '暂无题目' : '未找到匹配的题目' }}
              </div>
              <div v-for="item in filteredItems" :key="item.id" class="item-card-compact">
                <div class="item-question-compact">{{ item.question }}</div>
                <div class="item-gt-compact">
                  <span v-if="item.ground_truth_chunk_ids.length === 0" class="gt-empty">未标注</span>
                  <span v-for="(cid, i) in item.ground_truth_chunk_ids.slice(0, 3)" :key="i" class="gt-chip-compact">#{{ cid }}</span>
                  <span v-if="item.ground_truth_chunk_ids.length > 3" class="gt-more">+{{ item.ground_truth_chunk_ids.length - 3 }}</span>
                </div>
                <div class="item-actions-compact">
                  <button class="btn-icon-sm" title="编辑" @click="openItemEditor(item)">✏️</button>
                  <button class="btn-icon-sm btn-danger-icon" title="删除" @click="handleDeleteItem(item)">🗑️</button>
                </div>
              </div>
            </div>
          </div>
        </template>
        <!-- ★ 正常模式：显示测评集列表 -->
        <template v-else>
          <div class="pane-header"><span>测评集</span></div>
          <div class="pane-body">
            <!-- ★ 聊天反馈「固定测评集」 -->
            <div
              class="set-item chat-feedback-entry"
              :class="{ active: chatFeedbackMode }"
              @click="enterChatFeedbackMode"
            >
              <div class="set-item-name">💬 聊天反馈</div>
              <div class="set-item-meta">用户点踩记录</div>
            </div>
            <div class="set-divider"></div>

            <div v-if="loadingSets" class="pane-empty"><div class="spinner"></div></div>
            <div v-else-if="sets.length === 0" class="pane-empty">
              <p>暂无测评集</p>
              <p class="pane-empty-hint">新建测评集后添加「问题 + 标注正确 chunk」</p>
            </div>
            <div
              v-for="set in sets"
            :key="set.id"
            class="set-item"
            :class="{ active: selectedSet?.id === set.id }"
            @click="selectSet(set)"
          >
            <div class="set-item-name">{{ set.name }}</div>
            <div class="set-item-meta">{{ set.item_count }} 题 · {{ set.user_id !== myUserId && canManageAll ? '他人' : '' }}</div>
            <div class="set-item-actions" @click.stop>
              <button class="btn-icon" title="重命名" @click="openRenameSet(set)">✏️</button>
              <button class="btn-icon btn-danger-icon" title="删除" @click="handleDeleteSet(set)">🗑️</button>
            </div>
          </div>
          </div>
        </template>
      </div>

      <!-- 中：运行评测配置 + 运行历史（详情模式和正常模式统一） -->
      <div class="card pane pane-mid">
        <div class="pane-header">
          <span>评测结果</span>
          <div style="display: flex; gap: 4px;">
            <button class="btn btn-sm btn-icon-only" title="分类阈值设置" @click="openThresholdSettings">⚙️</button>
          </div>
        </div>
        <div class="pane-body">
          <!-- 运行评测配置 -->
          <div class="section-block">
            <div class="section-title">▶ 运行评测</div>
            <div class="run-config">
              <label>top-K <input v-model.number="runTopK" type="number" min="1" max="50" /></label>
              <label><input v-model="runGenerate" type="checkbox" /> 生成答案</label>
              <label><input v-model="runJudge" type="checkbox" /> LLM 裁判</label>
              <label>检索器
                <select v-model="runRetriever">
                  <option value="auto">auto</option>
                  <option value="vector">vector</option>
                  <option value="bm25">bm25</option>
                </select>
              </label>
              <button class="btn btn-primary btn-sm" :disabled="running || !selectedSet" @click="handleRun">
                <template v-if="running">
                  <span>⏳ {{ runProgress.done }}/{{ runProgress.total }}</span>
                  <span v-if="runProgress.stage === 'judge'" class="judge-stage-hint"> (裁判中...)</span>
                </template>
                <template v-else>▶ 开始评测</template>
              </button>
            </div>
            <div v-if="errorMsg" class="eval-error">{{ errorMsg }}</div>
            <div v-if="!selectedSet" class="pane-empty-hint">请先选择测评集</div>
          </div>

          <!-- 运行历史 -->
          <div class="section-block">
            <div class="section-title">📋 运行历史</div>
            <div class="run-history">
              <div v-if="runs.length === 0" class="pane-empty-hint">暂无运行记录</div>
              <div
                v-for="run in runs"
                :key="run.id"
                class="run-item"
                :class="{ active: activeRun?.id === run.id }"
                @click="openRun(run)"
              >
                <span :class="['status-badge', 'status-' + run.status]">{{ runStatusText(run.status) }}</span>
                <span class="run-time">{{ formatTime(run.created_at) }}</span>
                <button class="btn-icon btn-danger-icon" title="删除" @click.stop="handleDeleteRun(run)">🗑️</button>
              </div>
            </div>

            <!-- 结果下钻（恢复原来的详细展示） -->
            <div v-if="activeRunDetail" class="run-detail">
              <div class="run-detail-head">
                <div class="section-title">Run #{{ activeRunDetail.id }} 结果</div>
                <div class="run-detail-actions">
                  <button class="btn btn-sm" :disabled="suggesting" @click="handleGenerateSuggestions">
                    {{ suggesting ? '⏳ 生成中' : '💡 生成优化建议' }}
                  </button>
                </div>
              </div>

              <!-- 六态分类计数 -->
              <div v-if="hasClassifications" class="classify-row">
                <span v-for="c in classificationCards" :key="c.key" class="classify-chip" :class="'cls-' + c.key">
                  {{ c.label }} {{ activeRunDetail.metrics.classifications?.[c.key] || 0 }}
                </span>
              </div>

              <!-- 聚合指标卡片 -->
              <div class="metric-grid">
                <div v-for="m in metricCards.filter(m => activeRunDetail.metrics[m.key] != null)" :key="m.key" class="metric-card" :class="'layer-' + m.layer" :title="m.desc">
                  <div class="metric-value">{{ formatMetric(activeRunDetail.metrics[m.key]) }}</div>
                  <div class="metric-name">{{ m.label }}</div>
                </div>
              </div>
              <div v-if="activeRunDetail.metrics.warnings?.length" class="eval-warnings">
                ⚠️ {{ activeRunDetail.metrics.warnings.join('；') }}
              </div>

              <!-- 逐条结果 -->
              <div class="result-list">
                <div v-for="(res, idx) in activeRunDetail.results" :key="res.id" class="result-item">
                  <details>
                    <summary>
                      <span class="result-index">{{ idx + 1 }}.</span>
                      <span class="result-question">{{ res.question }}</span>
                      <span v-if="res.classification" class="classify-chip" :class="'cls-' + res.classification">
                        {{ classificationLabel(res.classification) }}
                      </span>
                      <span class="result-quick">
                        R@K={{ formatMetric(res.metrics.recall_at_k) }}
                        MRR={{ formatMetric(res.metrics.mrr) }}
                        <template v-if="res.judge_metrics?.faithfulness != null">Faith={{ formatMetric(res.judge_metrics.faithfulness) }}</template>
                      </span>
                    </summary>
                    <div class="result-body">
                      <div class="result-section">
                        <div class="result-label">🔍 检索结果（top-K）</div>
                        <div v-for="c in res.retrieved_chunks" :key="c.chunk_id + '-' + c.score" class="retrieved-chunk" :class="{ gt: c.is_gt }">
                          <span class="rc-badge">{{ c.is_gt ? '✅ GT' : '·' }}</span>
                          <span class="rc-score">score={{ c.score }}</span>
                          <span class="rc-content">{{ c.content.slice(0, 120) }}…</span>
                        </div>
                        <div v-if="res.retrieved_chunks.length === 0" class="pane-empty-hint">无检索结果</div>
                      </div>
                      <div v-if="res.answer" class="result-section">
                        <div class="result-label">💬 生成答案</div>
                        <div class="result-answer markdown-body" v-html="renderAnswer(res.answer)"></div>
                      </div>
                      <div v-if="res.judge_metrics && Object.values(res.judge_metrics).some(v => v != null)" class="result-section">
                        <div class="result-label">⚖️ 裁判指标</div>
                        <div class="judge-row">
                          <template v-for="j in judgeCards" :key="j.key">
                            <span v-if="res.judge_metrics?.[j.key] != null" class="judge-metric">
                              {{ j.label }}: <b>{{ formatMetric(res.judge_metrics[j.key]) }}</b>
                            </span>
                          </template>
                        </div>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：优化建议 -->
      <div class="card pane pane-right">
        <div class="pane-header">
          <span>优化建议</span>
          <span v-if="visibleSuggestionCount" class="suggestion-count-badge">{{ visibleSuggestionCount }}</span>
        </div>
        <div class="pane-body">
          <!-- ★ 聊天反馈模式：显示反馈详情 + 优化建议 -->
          <template v-if="chatFeedbackMode">
            <!-- 选中的反馈详情 -->
            <div v-if="selectedFeedback" class="section-block feedback-detail-section">
              <div class="section-title">📋 反馈详情 #{{ selectedFeedback?.id }}</div>
              <div class="feedback-detail-card">
                <div class="feedback-detail-row">
                  <span class="feedback-detail-label">❓ 用户问题：</span>
                  <div class="feedback-detail-content">{{ selectedFeedback.question || '(无法获取问题)' }}</div>
                </div>
                <div v-if="selectedFeedback.comment" class="feedback-detail-row">
                  <span class="feedback-detail-label">💬 用户补充：</span>
                  <div class="feedback-detail-content feedback-comment">{{ selectedFeedback.comment }}</div>
                </div>
                <div class="feedback-detail-row">
                  <span class="feedback-detail-label">🔍 检索结果：</span>
                  <div class="feedback-detail-content">
                    <span v-if="selectedFeedback.chunks.length === 0" class="status-miss">🔴 未命中任何 chunk</span>
                    <div v-else class="chunk-list">
                      <div v-for="chunk in selectedFeedback.chunks" :key="chunk.id" class="chunk-item">
                        <span class="chunk-id">#{{ chunk.id }}</span>
                        <span class="chunk-preview">{{ chunk.preview.slice(0, 150) }}{{ chunk.preview.length > 150 ? '…' : '' }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 优化建议 -->
            <div class="section-block">
              <div class="section-title">
                <span v-if="selectedFeedback">💡 该反馈的优化建议</span>
                <span v-else>💡 全部反馈优化建议（{{ feedbackSuggestions.length }}）</span>
                <button v-if="selectedFeedback" class="btn btn-sm" @click="selectedFeedback = null">显示全部</button>
              </div>
              <div v-if="displayedFeedbackSuggestions.length === 0" class="pane-empty-hint">
                {{ selectedFeedback ? '该反馈暂无优化建议，点击"生成优化建议"按钮。' : '暂无反馈优化建议。' }}
              </div>
              <!-- 如果选中反馈但没有建议，显示生成按钮 -->
              <div v-if="selectedFeedback && displayedFeedbackSuggestions.length === 0" class="suggestion-actions" style="margin-top: 10px;">
                <button
                  class="btn btn-sm btn-primary"
                  :disabled="suggestionBusy"
                  @click="generateFeedbackSuggestion(selectedFeedback)"
                >
                  {{ suggestionBusy ? '⏳ 生成中...' : '🤖 生成优化建议' }}
                </button>
              </div>
              <div v-for="s in displayedFeedbackSuggestions" :key="s.id" class="suggestion-card">
                <div class="suggestion-card-head" @click="s._collapsed = !s._collapsed" style="cursor: pointer;">
                  <span class="suggestion-collapse-icon">{{ s._collapsed ? '▶' : '▼' }}</span>
                  <span :class="['status-badge', 'sg-' + s.status]">{{ suggestionStatusText(s.status) }}</span>
                  <span class="suggestion-kind">聊天点踩</span>
                  <span v-if="s.evidence?.retriever" class="suggestion-kind" style="background:#f0f1f4;color:#5f6368;">{{ s.evidence.retriever }}</span>
                  <button class="btn-icon btn-danger-icon suggestion-delete-btn" title="删除" @click.stop="deleteSuggestion(s)">🗑️</button>
                </div>
                <template v-if="!s._collapsed">
                <!-- 优化建议内容（Markdown 渲染） -->
                <div class="suggestion-content markdown-body" v-html="renderAnswer(s.summary)"></div>
                <div class="suggestion-meta">尝试 {{ s.attempts }} 次 · {{ formatTime(s.created_at) }}</div>
                <div class="suggestion-actions">
                  <button v-if="['pending','failed'].includes(s.status)" class="btn btn-sm" :disabled="suggestionBusy" @click="ignoreSuggestion(s)">忽略</button>
                </div>
                </template>
              </div>
            </div>
          </template>

          <!-- ★ 正常测评集模式 -->
          <template v-else>
            <div v-if="!selectedSet" class="pane-empty"><p>选择测评集后查看优化建议</p></div>
            <template v-else>
              <!-- 优化建议列表 -->
              <div class="section-block">
                <div v-if="suggestions.length === 0" class="pane-empty-hint">
                  暂无建议。在 Run 结果上方点「💡 生成优化建议」，或在聊天中对答案点踩自动生成。
                </div>

                <!-- 📌 来自评测 -->
                <div v-if="evalSuggestions.length > 0" class="suggestion-sub-group">
                  <div class="suggestion-sub-header">
                    <span>📌 来自评测</span>
                  </div>
                  <div v-for="s in evalSuggestions" :key="s.id" class="suggestion-card">
                    <div class="suggestion-card-head" @click="s._collapsed = !s._collapsed" style="cursor: pointer;">
                      <span class="suggestion-collapse-icon">{{ s._collapsed ? '▶' : '▼' }}</span>
                      <span :class="['status-badge', 'sg-' + s.status]">{{ suggestionStatusText(s.status) }}</span>
                      <span class="suggestion-kind">{{ s.kind === 'rechunk_suggest' ? '重解析建议' : s.kind === 'content_suggest' ? '内容补充建议' : '通用建议' }}</span>
                      <span v-if="s._collapsed && s._actions?.length" class="suggestion-action-count">{{ s._actions!.length }} 项修改</span>
                      <button class="btn-icon btn-danger-icon suggestion-delete-btn" title="删除" @click.stop="deleteSuggestion(s)">🗑️</button>
                    </div>
                    <template v-if="!s._collapsed">
                    <!-- 摘要（Markdown 渲染，清理掉 ORIGINAL/SUGGESTED 代码块） -->
                    <div class="suggestion-summary suggestion-summary-feedback markdown-body" v-html="renderAnswer(cleanSummaryForDisplay(s.summary))"></div>
                    <!-- 从 Markdown 中提取的可执行操作 -->
                    <div v-if="s._actions?.length" class="suggestion-actions-list">
                      <div class="actions-header">📌 可执行操作（点击修改 chunk）：</div>
                      <div v-for="(action, i) in s._actions" :key="i" class="action-item">
                        <label class="action-checkbox">
                          <input type="checkbox" v-model="s._selectedActions" :value="i" />
                          <span class="action-type">修改</span>
                          <span class="action-target">chunk #{{ action.chunkId }}</span>
                          <span v-if="resolveActionItemId(s, action)" class="action-item-id">问题 #{{ resolveActionItemId(s, action) }}</span>
                        </label>
                        <div class="action-note">{{ action.note }}</div>
                        <button
                          class="btn btn-sm action-preview-btn"
                          @click="previewAndEditChunk(action.chunkId, action.note, undefined, action.location, action.supplement, action.reason)"
                        >📝 预览并修改</button>
                      </div>
                      <!-- 批量执行按钮 -->
                      <div v-if="(s._selectedActions?.length || 0) > 0" class="action-execute-bar">
                        <button class="btn btn-sm btn-primary" @click="executeSelectedChunkActions(s)">
                          ⚡ 执行选中的 {{ s._selectedActions?.length || 0 }} 项
                        </button>
                      </div>
                    </div>
                    <!-- 指标对比 -->
                    <div v-if="hasMetrics(s)" class="suggestion-delta">
                      <span>before: R@K={{ formatMetric(s.before_metrics.recall_at_k) }} · MRR={{ formatMetric(s.before_metrics.mrr) }}</span>
                      <span v-if="Object.keys(s.after_metrics || {}).length"> → after: R@K={{ formatMetric(s.after_metrics.recall_at_k) }} · MRR={{ formatMetric(s.after_metrics.mrr) }}</span>
                    </div>
                    <div class="suggestion-meta">尝试 {{ s.attempts }} 次 · {{ formatTime(s.created_at) }}</div>
                    <div class="suggestion-actions">
                      <button v-if="['pending','failed'].includes(s.status) && s.eval_set_id" class="btn btn-sm" :disabled="suggestionBusy" @click="verifySuggestion(s)">▶ 验证效果</button>
                      <button v-if="['pending','failed'].includes(s.status)" class="btn btn-sm" :disabled="suggestionBusy" @click="ignoreSuggestion(s)">忽略</button>
                    </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
          </template>
        </div>
      </div>
    </div>

    <!-- 新建/重命名测评集弹窗 -->
    <div v-if="setDialog" class="modal-mask" @click.self="setDialog = false">
      <div class="modal-card">
        <div class="modal-title">{{ renameTarget ? '重命名测评集' : '新建测评集' }}</div>
        <input v-model="setDialogName" class="input" placeholder="测评集名称" @keyup.enter="saveSetDialog" />
        <input v-model="setDialogDesc" class="input" placeholder="描述（可选）" />
        <div class="modal-actions">
          <button class="btn" @click="setDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveSetDialog">保存</button>
        </div>
      </div>
    </div>

    <!-- Chunk 预览/编辑弹窗（带对比视图） -->
    <div v-if="chunkPreviewDialog" class="modal-mask" @click.self="chunkPreviewDialog = false">
      <div class="modal-card modal-wide modal-chunk-preview">
        <div class="modal-title">
          编辑 Chunk #{{ chunkPreviewData?.id }}
          <span class="chunk-preview-doc">文档ID: {{ chunkPreviewData?.document_id }}</span>
        </div>
        <!-- 三列布局 -->
        <div class="chunk-preview-3col">
          <!-- 第1列：Markdown 源码 -->
          <div class="preview-col">
            <div class="preview-col-header">📝 Markdown 源码</div>
            <textarea
              v-model="chunkPreviewContent"
              class="preview-col-body preview-textarea"
              placeholder="Chunk Markdown 源码"
            ></textarea>
          </div>

          <!-- 第2列：Markdown 渲染 -->
          <div class="preview-col">
            <div class="preview-col-header">👁️ 渲染预览</div>
            <div class="preview-col-body markdown-body" v-html="renderAnswer(chunkPreviewContent)"></div>
          </div>

          <!-- 第3列：AI 优化建议 -->
          <div class="preview-col">
            <div class="preview-col-header suggestion-col-header">💡 AI 优化建议</div>
            <div class="preview-col-body suggestion-col-body">
              <div v-if="chunkPreviewFullSuggestion" class="ai-suggestion-content">
                <div class="suggestion-section">
                  <div class="suggestion-label">📍 位置</div>
                  <div class="suggestion-value">{{ chunkPreviewLocation }}</div>
                </div>
                <div class="suggestion-section">
                  <div class="suggestion-label">📝 补充内容</div>
                  <div class="suggestion-value markdown-body" v-html="renderAnswer(chunkPreviewFullSuggestion)"></div>
                </div>
                <div v-if="chunkPreviewReason" class="suggestion-section">
                  <div class="suggestion-label">❓ 原因</div>
                  <div class="suggestion-value">{{ chunkPreviewReason }}</div>
                </div>
              </div>
              <div v-else-if="chunkPreviewHint && chunkPreviewHint !== `修改 chunk #${chunkPreviewData?.id}`" class="ai-suggestion-content markdown-body" v-html="renderAnswer(chunkPreviewHint)"></div>
              <div v-else class="no-suggestion">暂无具体建议</div>
            </div>
          </div>
        </div>


        <div class="modal-actions">
          <button class="btn" @click="chunkPreviewDialog = false">取消</button>
          <button class="btn btn-primary" :disabled="chunkPreviewBusy" @click="saveChunkEdit">
            {{ chunkPreviewBusy ? '保存中...' : '💾 保存修改' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 题目编辑弹窗 -->
    <div v-if="itemDialog" class="modal-mask" @click.self="closeItemEditor">
      <div class="modal-card modal-wide">
        <div class="modal-title">{{ editingItem ? '编辑题目' : '添加题目' }}</div>
        <textarea v-model="itemForm.question" class="input item-question-input" rows="3" placeholder="评测问题，如：Redis 为什么会缓存雪崩？"></textarea>
        <div class="gt-picker-row">
          <button class="btn btn-sm" @click="openGtPicker">📌 选择正确 chunk（已选 {{ itemForm.ground_truth_chunk_ids.length }}）</button>
          <div class="gt-selected">
            <span v-for="(cid, i) in itemForm.ground_truth_chunk_ids" :key="i" class="gt-chip gt-chip-removable" @click="removeGt(cid)">#{{ cid }} ✕</span>
          </div>
        </div>
        <textarea v-model="itemForm.ground_truth_answer" class="input" rows="2" placeholder="参考答案（可选，用于 Answer Correctness）"></textarea>
        <div class="modal-actions">
          <button class="btn" @click="closeItemEditor">取消</button>
          <button class="btn btn-primary" @click="saveItem">保存</button>
        </div>
      </div>
    </div>

    <!-- GT chunk 选择器弹窗 -->
    <div v-if="gtPicker" class="modal-mask" @click.self="gtPicker = false">
      <div class="modal-card modal-wide">
        <div class="modal-title">选择正确 chunk（ground truth）</div>
        <div class="gt-picker-toolbar">
          <select v-model="gtPickerDoc" @change="loadGtChunks(1)">
            <option :value="0">全部文档</option>
            <option v-for="d in gtDocs" :key="d.id" :value="d.id">{{ d.original_name }}</option>
          </select>
          <input v-model="gtPickerKeyword" class="input" placeholder="关键词搜索 chunk 内容..." @keyup.enter="loadGtChunks(1)" />
          <button class="btn btn-sm" @click="loadGtChunks(1)">🔍 搜索</button>
        </div>
        <div class="gt-picker-list">
          <div v-if="gtLoading" class="pane-empty"><div class="spinner"></div></div>
          <div v-else-if="gtChunks.length === 0" class="pane-empty"><p>无匹配 chunk</p></div>
          <div
            v-for="c in gtChunks"
            :key="c.id"
            class="gt-pick-item"
            :class="{ picked: itemForm.ground_truth_chunk_ids.includes(c.id) }"
            @click="toggleGt(c.id)"
          >
            <span class="gp-check">{{ itemForm.ground_truth_chunk_ids.includes(c.id) ? '✅' : '☐' }}</span>
            <div class="gp-body">
              <div class="gp-meta">
                <span class="gp-kind-badge" :class="'kind-' + (c.kind || 'base')">
                  {{ c.kind === 'parent' ? '👨 父片' : c.kind === 'child' ? '👧 子片' : c.kind === 'topic' ? '📁 主题' : '📄 基础块' }}
                </span>
                #{{ c.id }} · {{ c.document_name }} · {{ c.char_count }} 字
              </div>
              <div class="gp-content">{{ c.content.slice(0, 140) }}…</div>
            </div>
          </div>
        </div>
        <div class="gt-picker-footer">
          <button class="btn btn-sm" :disabled="gtPage <= 1" @click="loadGtChunks(gtPage - 1)">‹</button>
          <span class="page-info">{{ gtPage }} / {{ Math.max(1, gtTotalPages) }}</span>
          <button class="btn btn-sm" :disabled="gtPage >= gtTotalPages" @click="loadGtChunks(gtPage + 1)">›</button>
          <span class="gt-picker-count">已选 {{ itemForm.ground_truth_chunk_ids.length }}</span>
          <button class="btn btn-primary btn-sm" @click="gtPicker = false">完成</button>
        </div>
      </div>
    </div>

    <!-- ── 分类阈值设置弹窗 ── -->
    <div v-if="showThresholdModal" class="modal-backdrop" @click.self="showThresholdModal = false">
      <div class="modal-card threshold-modal">
        <div class="modal-header">
          <span class="modal-title">⚙️ 分类阈值设置</span>
          <button class="btn-icon" @click="showThresholdModal = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="threshold-desc">调整分类判定的阈值参数，修改后会自动重新分类所有历史评测结果。</p>

          <div class="threshold-field">
            <label>依据不足阈值 <span class="threshold-key">judge_pass</span></label>
            <div class="threshold-input-row">
              <input type="range" min="0.1" max="0.9" step="0.05" v-model.number="editThresholds.judge_pass" />
              <input type="number" class="threshold-number" min="0" max="1" step="0.05" v-model.number="editThresholds.judge_pass" />
            </div>
            <span class="threshold-hint">faithfulness 低于此值 → 🟠 依据不足（默认 0.6）</span>
          </div>

          <div class="threshold-field">
            <label>答案错误阈值 <span class="threshold-key">wrong_answer_correctness</span></label>
            <div class="threshold-input-row">
              <input type="range" min="0.05" max="0.8" step="0.05" v-model.number="editThresholds.wrong_answer_correctness" />
              <input type="number" class="threshold-number" min="0" max="1" step="0.05" v-model.number="editThresholds.wrong_answer_correctness" />
            </div>
            <span class="threshold-hint">answer_correctness 低于此值（且 faithfulness ≥ 下方阈值）→ ❌ 答案错误（默认 0.3）</span>
          </div>

          <div class="threshold-field">
            <label>完整命中阈值 <span class="threshold-key">complete_faith_threshold</span></label>
            <div class="threshold-input-row">
              <input type="range" min="0.5" max="1.0" step="0.05" v-model.number="editThresholds.complete_faith_threshold" />
              <input type="number" class="threshold-number" min="0" max="1" step="0.05" v-model.number="editThresholds.complete_faith_threshold" />
            </div>
            <span class="threshold-hint">faithfulness ≥ 此值 → ✅ 完整命中（答案高度可信，默认 0.9）</span>
          </div>

          <div class="threshold-field">
            <label>答案错误信任阈值 <span class="threshold-key">wrong_answer_faith_threshold</span></label>
            <div class="threshold-input-row">
              <input type="range" min="0.3" max="1.0" step="0.05" v-model.number="editThresholds.wrong_answer_faith_threshold" />
              <input type="number" class="threshold-number" min="0" max="1" step="0.05" v-model.number="editThresholds.wrong_answer_faith_threshold" />
            </div>
            <span class="threshold-hint">faithfulness ≥ 此值时 answer_correctness 信号才可信（默认 0.7）</span>
          </div>

          <div class="threshold-priority">
            <div class="threshold-priority-title">📊 分类优先级：</div>
            <div>1️⃣ faith &lt; judge_pass → 🟠 依据不足</div>
            <div>2️⃣ ac &lt; wrong_answer_correctness 且 faith ≥ wrong_answer_faith_threshold → ❌ 答案错误</div>
            <div>3️⃣ faith ≥ complete_faith_threshold → ✅ 完整命中</div>
            <div>4️⃣ 其余指标部分不达标 → ⚠️ 部分达标</div>
            <div>5️⃣ 全部达标 → ✅ 完整命中</div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showThresholdModal = false">取消</button>
          <button class="btn btn-primary" :disabled="thresholdSaving" @click="saveThresholds">
            {{ thresholdSaving ? '保存中…' : '保存并重新分类' }}
          </button>
        </div>
      </div>
    </div>

    
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  addEvalItem, createEvalSet, deleteEvalItem, deleteRun, deleteEvalSet,
  getEvalSet, getRun, listEvalSets, listRuns, runEval, searchChunks, updateEvalItem, updateEvalSet,
  generateSuggestionsForRun, listSuggestions, runSuggestion as apiRunSuggestion,
  dismissSuggestion as apiDismissSuggestion, deleteSuggestion as apiDeleteSuggestion,
  getClassifyThresholds, updateClassifyThresholds,
  listChatEvalItems, generateFeedbackSuggestion as generateFeedbackSuggestionAPI,
  deleteChatFeedback, modifyChunk,
  type KbEvalItem, type KbEvalRun, type KbEvalRunDetail, type KbEvalSet, type KbSuggestion,
  type ClassifyThresholds, type ChatFeedbackItem,
} from '@/api/kbEval'
import { listDocuments, type KbDocument } from '@/api/kb'
import { renderMarkdown } from '@/utils/markdown'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'

const authStore = useAuthStore()
const myUserId = computed(() => Number(authStore.userId || localStorage.getItem('chatUserId') || 0))
const canManageAll = computed(() => authStore.permissions.includes('kb.manage'))

// ── 测评集 ──
const sets = ref<KbEvalSet[]>([])
const selectedSet = ref<KbEvalSet | null>(null)
const items = ref<KbEvalItem[]>([])
const loadingSets = ref(false)
const detailMode = ref(false)  // ★ 详情模式：点击测评集后进入
const itemSearchKeyword = ref('')  // ★ 题目搜索关键词

// ★ 题目搜索过滤（支持问题关键字或 chunk ID 前缀匹配）
const filteredItems = computed(() => {
  const keyword = itemSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return items.value

  // 检测是否是 chunk id 搜索（#数字 或纯数字）
  const chunkIdMatch = keyword.match(/^#?(\d+)$/)

  return items.value.filter(item => {
    // 问题关键字搜索
    if (item.question.toLowerCase().includes(keyword)) return true

    // chunk id 前缀匹配（输入 9 匹配 9, 99, 9975 等）
    if (chunkIdMatch) {
      const searchPrefix = chunkIdMatch[1]
      if (item.ground_truth_chunk_ids.some(id => String(id).startsWith(searchPrefix))) {
        return true
      }
    }

    return false
  })
})

// ── 聊天反馈「测评集」 ──
const chatFeedbackMode = ref(false)
const chatFeedbackItems = ref<ChatFeedbackItem[]>([])
const chatFeedbackLoading = ref(false)
const chatFeedbackTotal = ref(0)
const selectedFeedback = ref<ChatFeedbackItem | null>(null)

// 按当前选中反馈过滤建议（显示该反馈对应的建议，或全部反馈建议）
const displayedFeedbackSuggestions = computed(() => {
  if (!selectedFeedback.value) return feedbackSuggestions.value
  // 匹配 feedback_id（如果 suggestion 有 feedback_id 且与选中项匹配）
  return feedbackSuggestions.value.filter(s =>
    s.evidence?.feedback_id === selectedFeedback.value?.id ||
    s.evidence?.thread_id === selectedFeedback.value?.thread_id
  )
})

function selectFeedbackItem(fb: ChatFeedbackItem) {
  selectedFeedback.value = fb
}

async function enterChatFeedbackMode() {
  chatFeedbackMode.value = true
  selectedSet.value = null
  selectedFeedback.value = null
  chatFeedbackLoading.value = true
  try {
    const data = await listChatEvalItems(1, 100)
    chatFeedbackItems.value = data.items
    chatFeedbackTotal.value = data.total
    // 加载反馈建议
    await loadSuggestions()
  } catch {
    chatFeedbackItems.value = []
  } finally {
    chatFeedbackLoading.value = false
  }
}

async function exitChatFeedbackMode() {
  chatFeedbackMode.value = false
  chatFeedbackItems.value = []
  selectedFeedback.value = null
}

async function generateFeedbackSuggestion(fb: ChatFeedbackItem) {
  if (suggestionBusy.value) return
  suggestionBusy.value = true
  try {
    const res = await generateFeedbackSuggestionAPI(fb.id)
    console.log('[debug] generateFeedbackSuggestion response:', res)
    if (res.created) {
      banner.value = `✅ 已生成优化建议（ID: ${res.suggestion_id}）`
      console.log('[debug] calling loadSuggestions...')
      await loadSuggestions()
      console.log('[debug] loadSuggestions done, count:', suggestions.value.length)
    } else {
      banner.value = res.reason || '无法生成建议'
    }
  } catch (e: any) {
    console.error('[debug] generateFeedbackSuggestion error:', e)
    errorMsg.value = e?.message || '生成建议失败'
  } finally {
    suggestionBusy.value = false
  }
}

// ── 运行 ──
const runs = ref<KbEvalRun[]>([])
const activeRun = ref<KbEvalRun | null>(null)
const activeRunDetail = ref<KbEvalRunDetail | null>(null)
const running = ref(false)
const runProgress = ref({ done: 0, total: 0, stage: 'retrieve', message: '' })
const runTopK = ref(5)
const runGenerate = ref(true)
const runJudge = ref(true)
const runRetriever = ref('auto')
const runKind = ref('all')
const errorMsg = ref('')
const banner = ref('')
const showGuide = ref(false)  // 默认折叠，用户手动点击展开
let pollTimer: ReturnType<typeof setInterval> | null = null

// ── 优化建议（评测闭环） ──
const suggestions = ref<KbSuggestion[]>([])
const suggesting = ref(false)
const suggestionBusy = ref(false)
const suggestionCollapsed = ref(true)  // ★ 默认折叠，减少视觉噪音

// ★ Chunk 预览/编辑
const chunkPreviewDialog = ref(false)
const chunkPreviewData = ref<{ id: number; document_id: number; content: string; chunk_strategy: string } | null>(null)
const chunkPreviewContent = ref('')
const chunkPreviewHint = ref('')
const chunkPreviewLocation = ref('')
const chunkPreviewFullSuggestion = ref('')
const chunkPreviewReason = ref('')
const chunkPreviewSuggested = ref('')  // AI 建议的完整内容（保留兼容）
const chunkPreviewBusy = ref(false)

// ★ 按来源分类（feedback 排除已忽略的）
const evalSuggestions = computed(() => suggestions.value.filter(s => s.source === 'eval' && s.status !== 'dismissed'))
const feedbackSuggestions = computed(() => {
  const all = suggestions.value.filter(s => s.source === 'feedback')
  const notDismissed = all.filter(s => s.status !== 'dismissed')
  console.log('[debug] feedbackSuggestions: total feedback=', all.length, 'not dismissed=', notDismissed.length)
  if (all.length > 0) {
    console.log('[debug] feedbackSuggestions: all feedback items:', all.map(s => ({ id: s.id, status: s.status, source: s.source })))
  }
  return notDismissed
})

// ★ 可见建议总数：根据当前模式只统计相关的建议
const visibleSuggestionCount = computed(() => {
  if (chatFeedbackMode.value) {
    // 聊天反馈模式：只统计反馈建议
    return feedbackSuggestions.value.length
  }
  // 正常测评集模式：只统计该测评集的 eval 建议
  return evalSuggestions.value.length
})

// ── 分类阈值配置 ──
const showThresholdModal = ref(false)
const thresholdSaving = ref(false)
const currentThresholds = ref<ClassifyThresholds>({
  judge_pass: 0.6,
  wrong_answer_correctness: 0.3,
  complete_faith_threshold: 0.9,
  wrong_answer_faith_threshold: 0.7,
})
const editThresholds = ref<ClassifyThresholds>({ ...currentThresholds.value })

async function openThresholdSettings() {
  try {
    currentThresholds.value = await getClassifyThresholds()
    editThresholds.value = { ...currentThresholds.value }
  } catch {
    editThresholds.value = { ...currentThresholds.value }
  }
  showThresholdModal.value = true
}

async function saveThresholds() {
  thresholdSaving.value = true
  try {
    const result = await updateClassifyThresholds(editThresholds.value)
    currentThresholds.value = result.thresholds
    showThresholdModal.value = false
    banner.value = `✅ 阈值已保存，已重新分类 ${result.reclassified_runs} 个 run`
    setTimeout(() => banner.value = '', 4000)
    // 刷新当前 run 详情（分类结果已更新）
    if (activeRunDetail.value) {
      const detail = await getRun(activeRunDetail.value.id)
      activeRunDetail.value = detail
    }
  } catch (e: any) {
    banner.value = '❌ 保存阈值失败：' + (e.response?.data?.detail || e.message)
    setTimeout(() => banner.value = '', 4000)
  } finally {
    thresholdSaving.value = false
  }
}

const classificationCards = [
  { key: 'complete', label: '✅ 完整命中' },
  { key: 'partial', label: '⚠️ 部分达标' },
  { key: 'retrieval_miss', label: '🔴 检索未命中' },
  { key: 'insufficient_context', label: '🟠 依据不足' },
  { key: 'wrong_answer', label: '❌ 答案错误' },
  { key: 'unjudgeable', label: '⚪ 无法判定' },
]
const classificationLabelMap: Record<string, string> = Object.fromEntries(
  classificationCards.map((c) => [c.key, c.label])
)

const hasClassifications = computed(() => {
  const cls = activeRunDetail.value?.metrics?.classifications
  return !!cls && Object.values(cls).some((v) => Number(v) > 0)
})

function classificationLabel(key: string): string {
  return classificationLabelMap[key] || key
}

function hasMetrics(s: KbSuggestion): boolean {
  return !!s.before_metrics && Object.keys(s.before_metrics).length > 0
}

function suggestionStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '⏳ 待处理',
    verifying: '🔄 验证中',
    verified: '✅ 已验证',
    failed: '🔴 验证未通过',
    dismissed: '⚪ 已忽略',
  }
  return map[status] || status
}

// suggestionSourceText 已不再需要（建议按来源分区显示）

async function loadSuggestions() {
  try {
    // 按当前测评集筛选评测建议
    const evalSetId = selectedSet.value?.id
    console.log('[debug] loadSuggestions: evalSetId=', evalSetId)
    const [evalData, feedbackData] = await Promise.all([
      listSuggestions('', 1, 30, evalSetId || undefined, 'eval'),
      listSuggestions('', 1, 30, undefined, 'feedback'),
    ])
    console.log('[debug] loadSuggestions: eval count=', evalData.items.length, 'feedback count=', feedbackData.items.length)
    console.log('[debug] loadSuggestions: feedback items:', feedbackData.items.map(s => ({ id: s.id, status: s.status, source: s.source })))
    suggestions.value = [...evalData.items, ...feedbackData.items].map(s => ({
      ...s,
      _selectedActions: [],
      _collapsed: true,
      _actions: extractChunkActions(s.summary),
    }))
    console.log('[debug] loadSuggestions: total suggestions=', suggestions.value.length)
  } catch (e) {
    console.error('[debug] loadSuggestions error:', e)
    /* 忽略（无权限时静默） */
  }
}

async function handleGenerateSuggestions() {
  if (!activeRunDetail.value || suggesting.value) return
  suggesting.value = true
  try {
    const res = await generateSuggestionsForRun(activeRunDetail.value.id)
    banner.value = res.created > 0
      ? `🔧 已生成 ${res.created} 条优化建议（同型未关闭建议自动去重）`
      : '🔧 未生成新建议：本次评测全部通过，或已有同型建议待处理'
    await loadSuggestions()
  } catch (e: any) {
    errorMsg.value = e?.message || '生成建议失败'
  } finally {
    suggesting.value = false
  }
}

async function verifySuggestion(s: KbSuggestion) {
  if (suggestionBusy.value) return
  suggestionBusy.value = true
  try {
    const res = await apiRunSuggestion(s.id)
    banner.value = `▶ 已发起验证 run #${res.run_id}，完成后自动结算 before/after 指标`
    await loadSuggestions()
    if (selectedSet.value) {
      const data = await listRuns(selectedSet.value.id)
      runs.value = data.items
    }
    // 启动轮询，等待验证 run 完成后自动刷新建议状态
    suggestionVerifyingRun = res.run_id
    if (!suggestionPollTimer) {
      suggestionPollTimer = setInterval(pollSuggestionVerification, 3000)
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '发起验证失败'
  } finally {
    suggestionBusy.value = false
  }
}

// 轮询验证 run 状态，完成后自动刷新建议列表
let suggestionPollTimer: ReturnType<typeof setInterval> | null = null
let suggestionVerifyingRun: number | null = null

async function pollSuggestionVerification() {
  if (!suggestionVerifyingRun) return
  try {
    const detail = await getRun(suggestionVerifyingRun)
    if (detail.status !== 'running') {
      // 验证完成，停止轮询并刷新
      if (suggestionPollTimer) { clearInterval(suggestionPollTimer); suggestionPollTimer = null }
      suggestionVerifyingRun = null
      await loadSuggestions()
      if (selectedSet.value) {
        const data = await listRuns(selectedSet.value.id)
        runs.value = data.items
      }
      if (detail.status === 'done') {
        banner.value = `✅ 验证完成：${metricCards.filter(m => detail.metrics[m.key] != null).map(m => `${m.label}=${formatMetric(detail.metrics[m.key])}`).join('，')}`
      } else {
        banner.value = `❌ 验证失败：${detail.error || '未知错误'}`
      }
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '轮询验证状态失败'
  }
}

async function ignoreSuggestion(s: KbSuggestion) {
  console.log('[debug] ignoreSuggestion called, id=', s.id, 'busy=', suggestionBusy.value)
  if (suggestionBusy.value) {
    console.log('[debug] early return - busy')
    return
  }
  suggestionBusy.value = true
  const originalLen = suggestions.value.length
  // ★ 先乐观更新：立即从本地列表移除（保证 UI 响应）
  suggestions.value = suggestions.value.filter(x => x.id !== s.id)
  console.log('[debug] filtered, before:', originalLen, 'after:', suggestions.value.length)

  // ★ 带重试的 API 调用（最多 2 次）
  let lastError: any = null
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      console.log(`[debug] calling apiDismissSuggestion with id=${s.id}, attempt ${attempt + 1}`)
      const result = await apiDismissSuggestion(s.id)
      console.log('[debug] apiDismissSuggestion result:', result)
      banner.value = `✅ 已忽略建议 #${s.id}`
      console.log('[debug] API success on attempt', attempt + 1)
      lastError = null
      break
    } catch (e: any) {
      lastError = e
      console.log('[debug] API error on attempt', attempt + 1, ':', e)
      if (attempt === 0) {
        // 等 500ms 后重试
        await new Promise(r => setTimeout(r, 500))
      }
    }
  }
  if (lastError) {
    banner.value = `⚠️ 建议已从视图移除，但后台同步失败：${lastError?.response?.data?.detail || lastError?.message || '未知'}（刷新后可能重现）`
  }
  setTimeout(() => banner.value = '', 5000)
  suggestionBusy.value = false
}

async function deleteSuggestion(s: KbSuggestion) {
  console.log('[debug] deleteSuggestion called, id=', s.id, 'busy=', suggestionBusy.value)
  if (suggestionBusy.value) {
    console.log('[debug] early return - busy')
    return
  }
  suggestionBusy.value = true
  const originalLen = suggestions.value.length
  // ★ 先乐观更新：立即从本地列表移除（保证 UI 响应）
  suggestions.value = suggestions.value.filter(x => x.id !== s.id)
  console.log('[debug] filtered, before:', originalLen, 'after:', suggestions.value.length)

  // ★ 带重试的 API 调用（最多 2 次）
  let lastError: any = null
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await apiDeleteSuggestion(s.id)
      banner.value = `✅ 已删除建议 #${s.id}`
      console.log('[debug] API success on attempt', attempt + 1)
      lastError = null
      break
    } catch (e: any) {
      lastError = e
      console.log('[debug] API error on attempt', attempt + 1, ':', e)
      if (attempt === 0) {
        await new Promise(r => setTimeout(r, 500))
      }
    }
  }
  if (lastError) {
    banner.value = `⚠️ 建议已从视图移除，但后台同步失败：${lastError?.response?.data?.detail || lastError?.message || '未知'}（刷新后可能重现）`
  }
  setTimeout(() => banner.value = '', 5000)
  suggestionBusy.value = false
}

// ── 弹窗 ──
const setDialog = ref(false)
const setDialogName = ref('')
const setDialogDesc = ref('')
const renameTarget = ref<KbEvalSet | null>(null)

const itemDialog = ref(false)
const editingItem = ref<KbEvalItem | null>(null)
const itemForm = ref({ question: '', ground_truth_chunk_ids: [] as number[], ground_truth_answer: '' })

const gtPicker = ref(false)
const gtDocs = ref<KbDocument[]>([])
const gtPickerDoc = ref(0)
const gtPickerKeyword = ref('')
const gtChunks = ref<any[]>([])
const gtPage = ref(1)
const gtTotal = ref(0)
const gtLoading = ref(false)
const gtPageSize = 20

const gtTotalPages = computed(() => Math.max(1, Math.ceil(gtTotal.value / gtPageSize)))

// ── 指标定义 ──
const metricCards = [
  { key: 'recall_at_k', label: 'Recall@K', layer: 'retrieval', desc: '任一 GT chunk 出现在 top-K' },
  { key: 'mrr', label: 'MRR', layer: 'retrieval', desc: '首个 GT chunk 排名倒数' },
  { key: 'ndcg_at_k', label: 'NDCG@K', layer: 'retrieval', desc: 'GT 排名质量' },
  { key: 'precision_at_k', label: 'Precision@K', layer: 'retrieval', desc: 'top-K 中 GT 占比' },
  // RAGAS 核心指标
  { key: 'faithfulness', label: 'Faithfulness', layer: 'generation', desc: '忠实度（防幻觉）' },
  { key: 'answer_relevancy', label: 'Answer Relevancy', layer: 'generation', desc: '答案相关性' },
  { key: 'context_recall', label: 'Context Recall', layer: 'generation', desc: '上下文召回' },
  { key: 'answer_correctness', label: 'Answer Correctness', layer: 'generation', desc: '答案正确性' },
]
const judgeCards = metricCards.filter((m) => m.layer === 'generation')

// ── 数据加载 ──

async function loadSets() {
  loadingSets.value = true
  try {
    const data = await listEvalSets()
    sets.value = data.items
  } catch (e: any) {
    errorMsg.value = e?.message || '加载测评集失败'
  } finally {
    loadingSets.value = false
  }
}

async function selectSet(set: KbEvalSet) {
  exitChatFeedbackMode()
  selectedSet.value = set
  detailMode.value = true  // ★ 进入详情模式
  activeRun.value = null
  activeRunDetail.value = null
  try {
    const detail = await getEvalSet(set.id)
    items.value = detail.items
    const runData = await listRuns(set.id)
    runs.value = runData.items
    await loadSuggestions()  // ★ 切换测评集时刷新建议
  } catch (e: any) {
    errorMsg.value = e?.message || '加载测评集详情失败'
  }
}

// ★ 退出详情模式
function exitDetailMode() {
  detailMode.value = false
  selectedSet.value = null
  items.value = []
  itemSearchKeyword.value = ''  // 清空搜索
  runs.value = []
  activeRun.value = null
  activeRunDetail.value = null
  suggestions.value = []
}

// ★ 从 Markdown 内容中提取 chunk 修改建议（题目编号 + 位置 + 补充内容 + 原因）
function extractChunkActions(summary: string): { chunkId: number; note: string; itemId?: number; location?: string; supplement?: string; reason?: string }[] {
  const actions: { chunkId: number; note: string; itemId?: number; location?: string; supplement?: string; reason?: string }[] = []
  if (!summary) return actions

  let match

  // 新格式：题目编号 + 位置 + 补充内容 + 原因
  const modifyBlockPattern = /item_id[：:]\s*(\d+)\s*\n\s*chunk_id:\s*(\d+)\s*\n位置[：:]\s*(.+?)\s*\n补充内容[：:]?\s*\n((?:>\s*.+\n?)+)\s*\n原因[：:]\s*(.+?)\s*\n```/g
  while ((match = modifyBlockPattern.exec(summary)) !== null) {
    const itemId = parseInt(match[1], 10)
    const chunkId = parseInt(match[2], 10)
    const location = match[3].trim()
    const supplement = match[4].replace(/^>\s*/gm, '').trim()
    const reason = match[5].trim()
    if (!isNaN(chunkId) && !actions.find(a => a.chunkId === chunkId)) {
      actions.push({ chunkId, itemId: !isNaN(itemId) ? itemId : undefined, note: `在「${location}」补充内容`, location, supplement, reason })
    }
  }

  // 兼容无 item_id 的新格式
  const modifyNoItemPattern = /```modify\s*\nchunk_id:\s*(\d+)\s*\n位置[：:]\s*(.+?)\s*\n补充内容[：:]?\s*\n((?:>\s*.+\n?)+)\s*\n原因[：:]\s*(.+?)\s*\n```/g
  while ((match = modifyNoItemPattern.exec(summary)) !== null) {
    const chunkId = parseInt(match[1], 10)
    const location = match[2].trim()
    const supplement = match[3].replace(/^>\s*/gm, '').trim()
    const reason = match[4].trim()
    if (!isNaN(chunkId) && !actions.find(a => a.chunkId === chunkId)) {
      actions.push({ chunkId, note: `在「${location}」补充内容`, location, supplement, reason })
    }
  }

  // 兼容旧格式
  const pattern = /(?:chunk\s*)?#(\d+)[^#\d]*?[:：]\s*([^\n]+)/g
  while ((match = pattern.exec(summary)) !== null) {
    const chunkId = parseInt(match[1], 10)
    const note = match[2].trim().slice(0, 100)
    if (!isNaN(chunkId) && !actions.find(a => a.chunkId === chunkId)) {
      actions.push({ chunkId, note })
    }
  }

  return actions
}

// ★ 解析 action 对应的题目编号（优先用 LLM 输出的 item_id，兜底用 chunk_to_items 映射）
function resolveActionItemId(suggestion: any, action: any): number | null {
  if (action.itemId) return action.itemId
  const mapping = suggestion?.evidence?.chunk_to_items
  if (mapping && mapping[String(action.chunkId)]) {
    const ids = mapping[String(action.chunkId)]
    if (Array.isArray(ids) && ids.length > 0) return ids[0]
  }
  return null
}

// ★ 清理 summary 显示（移除 ORIGINAL/SUGGESTED 代码块，只保留诊断和建议文字）
function cleanSummaryForDisplay(summary: string): string {
  if (!summary) return ''
  let cleaned = summary
  // 移除 ```modify ... ``` 代码块
  cleaned = cleaned.replace(/```modify\s*\n[\s\S]*?\n```/g, '')
  // 移除无代码块的 chunk_id/ORIGINAL/SUGGESTED 段落（到下一个 chunk_id: 或末尾）
  cleaned = cleaned.replace(/chunk_id:\s*\d+\s*\n---ORIGINAL---\s*\n[\s\S]*?(?=\nchunk_id:|$)/g, '')
  // 移除 ```add ... ``` 代码块
  cleaned = cleaned.replace(/```add\s*\n[\s\S]*?\n```/g, '')
  // 移除无代码块的 document/CONTENT 段落（到下一个 document: 或末尾）
  cleaned = cleaned.replace(/document:\s*[^\n]+\s*\n---CONTENT---\s*\n[\s\S]*?(?=\ndocument:|$)/g, '')
  // 移除 LLM 输出中的 section 标题（可能残留）
  cleaned = cleaned.replace(/^###?\s*(需要修改的\s*chunk|需要补充的内容|其他建议)\s*\n?/gm, '')
  // 清理多余空行
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim()
  return cleaned
}

// ★ 预览并编辑 chunk（带建议）
async function previewAndEditChunk(chunkId: number, suggestedNote: string, suggestedContent?: string, location?: string, supplement?: string, reason?: string) {
  console.log('[previewAndEditChunk] 调用参数:', { chunkId, suggestedNote, location, supplementLength: supplement?.length || 0, reason })
  try {
    const res = await request.get(`/api/kb/chunks/${chunkId}`)
    chunkPreviewData.value = res.data
    chunkPreviewContent.value = res.data.content || ''
    chunkPreviewHint.value = suggestedNote
    chunkPreviewLocation.value = location || ''
    chunkPreviewFullSuggestion.value = supplement || ''
    chunkPreviewReason.value = reason || ''
    chunkPreviewSuggested.value = suggestedContent || ''
    chunkPreviewDialog.value = true
  } catch (e: any) {
    errorMsg.value = e?.message || '加载 chunk 失败'
  }
}

// ★ 执行选中的 chunk 修改
async function executeSelectedChunkActions(s: KbSuggestion) {
  const selectedIndices = s._selectedActions || []
  if (selectedIndices.length === 0) {
    banner.value = '⚠️ 请先勾选要执行的操作'
    return
  }

  const actions = s._actions || extractChunkActions(s.summary)  // 优先用缓存，兜底重新解析
  const selectedActions = selectedIndices.map((i: number) => actions[i]).filter(Boolean)

  if (selectedActions.length === 0) return

  suggestionBusy.value = true
  let executed = 0
  let failed = 0

  for (const action of selectedActions) {
    try {
      // 获取 chunk 内容
      const res = await request.get(`/api/kb/chunks/${action.chunkId}`)
      const chunk = res.data

      // 弹窗让用户确认修改内容
      const newContent = prompt(`修改 chunk #${action.chunkId}：\n\n建议：${action.note}\n\n请输入新内容（或取消跳过）：`, chunk.content)
      if (newContent && newContent !== chunk.content) {
        await modifyChunk(action.chunkId, newContent, '优化建议执行')
        executed++
      }
    } catch (e: any) {
      console.error('执行 chunk 修改失败:', e)
      failed++
    }
  }

  suggestionBusy.value = false
  if (executed > 0) {
    banner.value = `✅ 已修改 ${executed} 个 chunk`
  }
  if (failed > 0) {
    banner.value += `，${failed} 个失败`
  }

  // 刷新建议列表
  await loadSuggestions()
}

// ★ 预览 Chunk
async function previewChunk(chunkId: number, hint: string, suggestedContent?: string) {
  try {
    const res = await request.get(`/api/kb/chunks/${chunkId}`)
    chunkPreviewData.value = res.data
    chunkPreviewContent.value = res.data.content || ''
    chunkPreviewHint.value = hint
    chunkPreviewSuggested.value = suggestedContent || ''
      chunkPreviewDialog.value = true
  } catch (e: any) {
    errorMsg.value = e?.message || '加载 chunk 失败'
  }
}

// ★ 保存 Chunk 编辑
async function saveChunkEdit() {
  if (!chunkPreviewData.value || !chunkPreviewContent.value.trim()) return
  chunkPreviewBusy.value = true
  try {
    await modifyChunk(chunkPreviewData.value.id, chunkPreviewContent.value, '优化建议执行')
    banner.value = `✅ 已修改 chunk #${chunkPreviewData.value.id}`
    chunkPreviewDialog.value = false
    chunkPreviewData.value = null
  } catch (e: any) {
    errorMsg.value = e?.message || '保存失败'
  } finally {
    chunkPreviewBusy.value = false
  }
}

// ★ 执行选中的优化建议动作
async function executeSelectedActions(s: KbSuggestion) {
  const selectedIndices = s._selectedActions || []
  if (selectedIndices.length === 0) {
    banner.value = '⚠️ 请先勾选要执行的操作'
    return
  }

  const actions = s.evidence?.detailed_actions || []
  const selectedActions = selectedIndices.map((i: number) => actions[i]).filter(Boolean)

  if (selectedActions.length === 0) return

  suggestionBusy.value = true
  let executed = 0
  let failed = 0

  for (const action of selectedActions) {
    if (action.type === 'chunk_modify' && action.chunk_id) {
      try {
        // 获取 chunk 内容
        const res = await request.get(`/api/kb/chunks/${action.chunk_id}`)
        const chunk = res.data

        // 根据建议修改内容（简化：在开头插入建议）
        const newContent = action.note + '\n\n' + chunk.content
        await modifyChunk(action.chunk_id, newContent, '优化建议自动执行')
        executed++
      } catch (e: any) {
        console.error('执行 chunk 修改失败:', e)
        failed++
      }
    }
  }

  suggestionBusy.value = false
  banner.value = `✅ 执行完成：${executed} 成功，${failed} 失败`

  // 刷新建议列表
  await loadSuggestions()
}

async function loadGtDocs() {
  try {
    const data = await listDocuments({ page_size: 100 })
    gtDocs.value = data.items
  } catch { /* 忽略 */ }
}

async function loadGtChunks(page: number) {
  gtLoading.value = true
  gtPage.value = Math.max(1, page)
  try {
    const data = await searchChunks(
      gtPickerKeyword.value,  // 直接传空字符串，后端会处理
      gtPage.value,
      gtPageSize,
      gtPickerDoc.value || undefined,
    )
    gtChunks.value = data.items
    gtTotal.value = data.total
  } catch (e: any) {
    errorMsg.value = e?.message || '搜索 chunk 失败'
  } finally {
    gtLoading.value = false
  }
}

// ── 测评集操作 ──

function openCreateSet() {
  renameTarget.value = null
  setDialogName.value = ''
  setDialogDesc.value = ''
  setDialog.value = true
}

function openRenameSet(set: KbEvalSet) {
  renameTarget.value = set
  setDialogName.value = set.name
  setDialogDesc.value = set.description
  setDialog.value = true
}

async function saveSetDialog() {
  if (!setDialogName.value.trim()) return
  try {
    if (renameTarget.value) {
      await updateEvalSet(renameTarget.value.id, setDialogName.value.trim(), setDialogDesc.value)
    } else {
      const created = await createEvalSet(setDialogName.value.trim(), setDialogDesc.value)
      await loadSets()
      selectedSet.value = null
      activeRun.value = null
      activeRunDetail.value = null
      items.value = []
      runs.value = []
      await selectSet(created as KbEvalSet)
    }
    setDialog.value = false
    await loadSets()
    if (selectedSet.value) await selectSet(selectedSet.value)
  } catch (e: any) {
    errorMsg.value = e?.message || '保存失败'
  }
}

async function handleDeleteSet(set: KbEvalSet) {
  if (!confirm(`确定删除测评集「${set.name}」？\n其题目与全部运行记录将一并删除。`)) return
  try {
    await deleteEvalSet(set.id)
    if (selectedSet.value?.id === set.id) {
      selectedSet.value = null
      items.value = []
      runs.value = []
      activeRun.value = null
      activeRunDetail.value = null
    }
    await loadSets()
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  }
}

// ── 题目操作 ──

function openItemEditor(item?: KbEvalItem) {
  editingItem.value = item || null
  itemForm.value = item
    ? { question: item.question, ground_truth_chunk_ids: [...item.ground_truth_chunk_ids], ground_truth_answer: item.ground_truth_answer }
    : { question: '', ground_truth_chunk_ids: [], ground_truth_answer: '' }
  itemDialog.value = true
}

function closeItemEditor() {
  itemDialog.value = false
  gtPicker.value = false
}

async function saveItem() {
  if (!selectedSet.value) return
  if (!itemForm.value.question.trim()) {
    errorMsg.value = '问题不能为空'
    return
  }
  try {
    if (editingItem.value) {
      await updateEvalItem(selectedSet.value.id, editingItem.value.id, {
        question: itemForm.value.question.trim(),
        ground_truth_chunk_ids: itemForm.value.ground_truth_chunk_ids,
        ground_truth_answer: itemForm.value.ground_truth_answer,
      })
    } else {
      await addEvalItem(selectedSet.value.id, {
        question: itemForm.value.question.trim(),
        ground_truth_chunk_ids: itemForm.value.ground_truth_chunk_ids,
        ground_truth_answer: itemForm.value.ground_truth_answer,
      })
    }
    itemDialog.value = false
    await selectSet(selectedSet.value)
  } catch (e: any) {
    errorMsg.value = e?.message || '保存题目失败'
  }
}

async function handleDeleteItem(item: KbEvalItem) {
  if (!selectedSet.value) return
  if (!confirm(`确定删除题目「${item.question.slice(0, 40)}...」？`)) return
  try {
    await deleteEvalItem(selectedSet.value.id, item.id)
    await selectSet(selectedSet.value)
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  }
}

async function handleDeleteFeedback(fb: ChatFeedbackItem) {
  if (!fb || !fb.id) return
  if (!confirm(`确定删除这条聊天反馈？\n问题: ${fb.question?.slice(0, 50) || '(无问题)'}...`)) return
  try {
    await deleteChatFeedback(fb.id)
    banner.value = `✅ 已删除反馈 #${fb.id}`
    // 清除选中状态（在刷新列表之前）
    if (selectedFeedback.value?.id === fb.id) {
      selectedFeedback.value = null
    }
    // 刷新列表
    await enterChatFeedbackMode()
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  }
}

// ── GT 选择器 ──

async function openGtPicker() {
  gtPicker.value = true
  gtPickerKeyword.value = ''
  gtPickerDoc.value = 0
  if (gtDocs.value.length === 0) await loadGtDocs()
  await loadGtChunks(1)
}

function toggleGt(id: number) {
  const idx = itemForm.value.ground_truth_chunk_ids.indexOf(id)
  if (idx >= 0) itemForm.value.ground_truth_chunk_ids.splice(idx, 1)
  else itemForm.value.ground_truth_chunk_ids.push(id)
}

function removeGt(id: number) {
  const idx = itemForm.value.ground_truth_chunk_ids.indexOf(id)
  if (idx >= 0) itemForm.value.ground_truth_chunk_ids.splice(idx, 1)
}

// ── 运行 ──

async function handleRun() {
  if (!selectedSet.value || running.value) return
  errorMsg.value = ''
  try {
    const res = await runEval(selectedSet.value.id, {
      top_k: runTopK.value,
      generate_answer: runGenerate.value,
      judge_enabled: runJudge.value,
      retriever: runRetriever.value,
      chunk_kind: runKind.value,
    })
    running.value = true
    runProgress.value = { done: 0, total: res.total }
    pollTimer = setInterval(pollRun, 2000)
    await pollRun()
  } catch (e: any) {
    errorMsg.value = e?.message || '启动评测失败'
  }
}

async function pollRun() {
  if (!activeRun.value && runs.value[0]) activeRun.value = runs.value[0]
  // 从列表找最新的 running run
  try {
    const data = await listRuns(selectedSet.value!.id)
    runs.value = data.items
    const current = data.items.find((r) => r.status === 'running') || data.items[0]
    if (!current) return
    const detail = await getRun(current.id)
    activeRun.value = current
    activeRunDetail.value = detail
    runProgress.value = detail.progress || { done: 0, total: 0 }
    if (detail.status !== 'running') {
      running.value = false
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
      if (detail.status === 'done') {
        banner.value = `✅ 评测完成：${metricCards.filter(m => detail.metrics[m.key] != null).map(m => `${m.label}=${formatMetric(detail.metrics[m.key])}`).join('，')}`
      } else {
        banner.value = `❌ 评测失败：${detail.error || '未知错误'}`
      }
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '轮询失败'
  }
}

async function openRun(run: KbEvalRun) {
  try {
    const detail = await getRun(run.id)
    activeRun.value = run
    activeRunDetail.value = detail
    if (run.status === 'running') {
      running.value = true
      runProgress.value = run.progress || { done: 0, total: 0 }
      if (!pollTimer) pollTimer = setInterval(pollRun, 2000)
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '加载运行记录失败'
  }
}

async function handleDeleteRun(run: KbEvalRun) {
  if (!confirm(`确定删除运行记录 #${run.id}？`)) return
  try {
    await deleteRun(run.id)
    if (selectedSet.value) {
      const data = await listRuns(selectedSet.value.id)
      runs.value = data.items
    }
    if (activeRun.value?.id === run.id) {
      activeRun.value = null
      activeRunDetail.value = null
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  }
}

// ── 格式化 ──

function formatMetric(v: number | null | undefined): string {
  if (v == null) return '-'
  const n = Number(v)
  return n >= 100 ? String(Math.round(n)) : n.toFixed(2)
}

function runStatusText(status: string): string {
  const map: Record<string, string> = { running: '⏳ 运行中', done: '✅ 完成', failed: '🔴 失败' }
  return map[status] || status
}

function formatTime(t: string): string {
  if (!t) return '-'
  // 后端返回的是 UTC 时间（如 "2024-01-01T12:00:00" 或 "2024-01-01 12:00:00"）
  let dateStr = t
  if (!dateStr.includes('T') && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
    // 没有时区信息，假设是 UTC 时间
    dateStr = t.replace(' ', 'T') + 'Z'
  }
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return t
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function renderAnswer(text: string): string {
  return renderMarkdown(text || '')
}

onMounted(() => {
  loadSets()
  loadSuggestions()
})

// ★ 组件卸载时清除所有定时器，避免阻塞页面跳转
onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (suggestionPollTimer) {
    clearInterval(suggestionPollTimer)
    suggestionPollTimer = null
  }
})
</script>

<style scoped>
.page-container { padding: 24px; max-width: 1500px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; height: 100vh; box-sizing: border-box; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-shrink: 0; }
.page-title { font-size: 22px; font-weight: 600; margin: 0; color: var(--text-primary); }
.page-desc { color: var(--text-tertiary); font-size: 13px; margin: 6px 0 0; }
.header-actions { display: flex; gap: 10px; }

.eval-banner { background: var(--brand-light); color: var(--brand); border-radius: 8px; padding: 8px 14px; font-size: 12px; flex-shrink: 0; }

/* ── 使用说明 ── */
.guide-card { padding: 14px 16px; font-size: 12px; color: var(--text-secondary); flex-shrink: 0; overflow-y: auto; max-height: 46vh; }
.guide-header { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
.guide-close-btn { background: var(--bg-secondary, #f0f1f4); border: 1px solid var(--border-primary); border-radius: 6px; padding: 3px 10px; font-size: 11px; cursor: pointer; color: var(--text-secondary); }
.guide-close-btn:hover { background: var(--bg-hover); color: var(--brand); }
.guide-steps { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.guide-step { display: flex; gap: 10px; align-items: flex-start; }
.step-num {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  background: var(--brand-gradient); color: white; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; margin-top: 1px;
}
.step-body { min-width: 0; }
.step-title { font-weight: 600; color: var(--text-primary); }
.step-desc { line-height: 1.6; margin-top: 2px; }
.step-desc b, .guide-notes b { color: var(--text-primary); }
.guide-metrics-title, .guide-notes-title { font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.guide-metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px; margin-bottom: 12px; }
.guide-metric { background: var(--bg-secondary, #f7f8fa); border-radius: 6px; padding: 6px 10px; line-height: 1.5; }
.guide-metric b { color: var(--brand); }
.guide-notes ul { margin: 0; padding-left: 18px; }
.guide-notes li { margin-bottom: 4px; line-height: 1.6; }
.eval-error { background: #fdecea; color: #d93025; border-radius: 8px; padding: 6px 12px; font-size: 12px; margin-top: 8px; }
.judge-stage-hint { color: #1976d2; font-size: 11px; }
.eval-warnings { background: #fff4e0; color: #b26a00; border-radius: 8px; padding: 6px 12px; font-size: 12px; margin-top: 8px; }

.eval-layout { display: grid; grid-template-columns: 240px minmax(380px, 1.2fr) minmax(320px, 1fr); gap: 14px; flex: 1; min-height: 0; }
/* ★ 详情模式：中间栏加宽给评测结果 */
.eval-layout.detail-mode { grid-template-columns: 260px minmax(450px, 1.4fr) minmax(320px, 1fr); }
.card { background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 12px; }
.pane { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.pane-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border-primary); font-size: 13px; font-weight: 600; color: var(--text-primary); flex-shrink: 0; gap: 8px; }
.pane-body { flex: 1; overflow-y: auto; padding: 10px; min-height: 0; }
.pane-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-placeholder); font-size: 13px; gap: 6px; text-align: center; padding: 16px; }
.pane-empty-hint { font-size: 11px; color: var(--text-placeholder); }

.btn { border: none; border-radius: 8px; padding: 7px 14px; font-size: 13px; cursor: pointer; transition: var(--transition); background: var(--bg-hover); color: var(--text-primary); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--brand-gradient); color: white; }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn-danger { background: var(--danger-light, #fdecea); color: #d93025; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 2px 6px; border-radius: 6px; }
.btn-icon:hover { background: var(--bg-hover); }
.btn-danger-icon:hover { background: #fdecea; }
.input { background: var(--bg-secondary, #f5f6f8); border: 1px solid var(--border-primary); color: var(--text-primary); border-radius: 6px; padding: 7px 10px; font-size: 13px; width: 100%; box-sizing: border-box; }

.spinner { width: 26px; height: 26px; border: 3px solid var(--border-primary); border-top-color: var(--brand); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ★ 测评集详情卡片（详情模式） */
.set-detail-card { padding: 12px; }
.set-detail-name { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; word-break: break-all; }
.set-detail-meta { background: var(--bg-secondary); border-radius: 8px; padding: 10px; margin-bottom: 12px; }
.set-detail-row { display: flex; justify-content: space-between; align-items: flex-start; padding: 6px 0; border-bottom: 1px solid var(--border-primary); }
.set-detail-row:last-child { border-bottom: none; }
.set-detail-label { font-size: 12px; color: var(--text-tertiary); }
.set-detail-value { font-size: 12px; color: var(--text-primary); text-align: right; flex: 1; margin-left: 12px; word-break: break-all; }
.set-detail-actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* ★ 紧凑版题目卡片（详情模式左栏） */
.item-card-compact { border: 1px solid var(--border-primary); border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; position: relative; }
.item-question-compact { font-size: 12px; color: var(--text-primary); line-height: 1.4; word-break: break-all; padding-right: 50px; }
.item-gt-compact { margin-top: 4px; display: flex; align-items: center; gap: 3px; flex-wrap: wrap; }
.gt-chip-compact { font-size: 10px; background: var(--brand-light); color: var(--brand); border-radius: 3px; padding: 1px 4px; }
.gt-more { font-size: 10px; color: var(--text-tertiary); }
.item-actions-compact { position: absolute; right: 4px; top: 4px; display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s; }
.item-card-compact:hover .item-actions-compact { opacity: 1; }
.btn-icon-sm { background: none; border: none; cursor: pointer; font-size: 12px; padding: 2px 4px; border-radius: 4px; }
.btn-icon-sm:hover { background: var(--bg-hover); }
.btn-icon-sm.btn-danger-icon:hover { background: #fce8e6; }

/* ★ 题目搜索栏 */
.item-search-bar { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
.item-search-input { flex: 1; padding: 6px 8px; font-size: 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); }
.item-search-input:focus { outline: none; border-color: var(--brand); }
.item-search-input::placeholder { color: var(--text-placeholder); }
.search-count { font-size: 11px; color: var(--text-tertiary); margin-left: 4px; }

/* 测评集列表 */
.set-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; position: relative; }
.set-item:hover { background: var(--bg-hover); }
.set-item.active { background: var(--brand-light); }
.set-item-name { font-size: 13px; color: var(--text-primary); font-weight: 500; padding-right: 44px; word-break: break-all; }
.set-item-meta { font-size: 11px; color: var(--text-placeholder); margin-top: 2px; }
.set-item-actions { position: absolute; right: 6px; top: 6px; display: flex; gap: 2px; }

/* 题目 */
.item-card { border: 1px solid var(--border-primary); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.item-question { font-size: 13px; color: var(--text-primary); line-height: 1.5; }
.item-gt { margin-top: 6px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.gt-label { font-size: 11px; color: var(--text-tertiary); }
.gt-empty { font-size: 11px; color: #d93025; }
.gt-chip { font-size: 11px; background: var(--brand-light); color: var(--brand); border-radius: 4px; padding: 1px 6px; }
.gt-answer { background: #e6f4ea; color: #188038; }
.item-actions { margin-top: 6px; display: flex; gap: 6px; }

/* 运行配置 */
.run-config { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.run-config label { font-size: 12px; color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.run-config input[type="number"], .run-config select { background: var(--bg-secondary, #f5f6f8); border: 1px solid var(--border-primary); color: var(--text-primary); border-radius: 6px; padding: 4px 6px; font-size: 12px; width: 64px; }
.run-config select { width: auto; }

.section-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin: 12px 0 6px; border-bottom: 1px dashed var(--border-primary); padding-bottom: 4px; display: flex; justify-content: space-between; align-items: center; }

/* ── 右侧面板分块 ── */
.section-block { border-bottom: 1px solid var(--border-primary); padding-bottom: 12px; margin-bottom: 12px; }
.section-block:last-child { border-bottom: none; padding-bottom: 0; margin-bottom: 0; }
.section-title.collapsible { cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none; }
.section-title.collapsible:hover { color: var(--brand-primary); }
.collapse-icon { font-size: 11px; color: var(--text-placeholder); }

/* ── 优化建议（评测闭环） ── */
.suggestion-section { margin-top: 6px; }
.suggestion-count-badge { background: var(--brand, #4f46e5); color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 10px; margin-left: 4px; font-weight: 600; }
.suggestion-sub-group { margin-top: 8px; }
.suggestion-sub-header { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; padding-bottom: 3px; border-bottom: 1px dashed var(--border-primary); }
.suggestion-card { border: 1px solid var(--border-primary); border-radius: 8px; padding: 8px 10px; margin-bottom: 6px; }
.suggestion-card-head { display: flex; align-items: center; gap: 6px; }
.suggestion-kind { font-size: 11px; color: var(--text-placeholder); background: var(--bg-secondary, #f5f5f5); padding: 1px 6px; border-radius: 4px; }
.suggestion-delete-btn { margin-left: auto; opacity: 0.4; transition: opacity 0.15s; font-size: 13px; }
.suggestion-delete-btn:hover { opacity: 1; }
.suggestion-evidence { margin-top: 6px; padding: 6px 8px; background: var(--bg-secondary, #f9fafb); border-radius: 6px; font-size: 11px; color: var(--text-secondary); line-height: 1.6; }
.evidence-item { margin-bottom: 3px; }
.evidence-label { font-weight: 600; color: var(--text-primary); }
.evidence-action-item { padding: 2px 0 2px 8px; border-left: 2px solid var(--brand, #4f46e5); margin-top: 3px; }
.evidence-chunk-preview { padding: 2px 0 2px 12px; border-left: 2px solid var(--border-primary); margin-top: 2px; font-size: 11px; color: var(--text-placeholder); word-break: break-all; }
.evidence-fail-question { margin-top: 6px; padding: 6px 8px; background: var(--bg-primary, #fff); border: 1px solid var(--border-primary); border-radius: 6px; }
.fq-header { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 4px; }
.fq-cls { font-size: 10px; padding: 1px 6px; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }
.fq-cls-retrieval_miss { background: #fee2e2; color: #dc2626; }
.fq-cls-insufficient_context { background: #ffedd5; color: #ea580c; }
.fq-cls-wrong_answer { background: #fef3c7; color: #d97706; }
.fq-question { font-size: 12px; color: var(--text-primary); font-weight: 500; }
.fq-detail { font-size: 11px; margin-top: 3px; padding-left: 4px; }
.chunk-score { font-size: 10px; color: var(--text-placeholder); margin-right: 4px; font-family: monospace; }
.chunk-is-gt { border-left-color: #16a34a !important; background: #f0fdf4; }
.chunk-gt-badge { font-size: 9px; color: #16a34a; font-weight: 600; margin-right: 4px; }
.suggestion-summary { font-size: 12px; color: var(--text-primary); line-height: 1.5; margin-top: 4px; }
.suggestion-summary-feedback {  }
.suggestion-meta { font-size: 11px; color: var(--text-placeholder); margin-top: 3px; }
.suggestion-actions-list { margin-top: 8px; padding: 8px; background: var(--bg-secondary); border-radius: 6px; }
.actions-header { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; }
.action-item { font-size: 12px; color: var(--text-primary); padding: 8px 0; border-bottom: 1px dashed var(--border-primary); display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.action-item:last-child { border-bottom: none; }
.action-checkbox { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.action-checkbox input { margin: 0; }
.action-type { display: inline-block; background: var(--brand-light); color: var(--brand); border-radius: 4px; padding: 1px 6px; font-size: 11px; }
.action-target { color: var(--brand); font-weight: 500; }
.action-item-id { display: inline-block; background: #e0f2fe; color: #0369a1; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 500; }
.suggestion-collapse-icon { font-size: 10px; color: var(--text-placeholder); margin-right: 4px; transition: transform 0.15s; flex-shrink: 0; }
.suggestion-action-count { display: inline-block; background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 500; margin-left: auto; margin-right: 4px; }
.suggestion-card-head { cursor: pointer; user-select: none; }
.suggestion-card-head:hover { background: var(--bg-secondary, #f9fafb); }
.action-note { flex: 1; color: var(--text-secondary); min-width: 150px; font-size: 11px; }
.action-preview-btn { padding: 2px 8px; font-size: 11px; margin-left: auto; }
.action-execute-bar { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-primary); text-align: right; }
.action-more { font-size: 11px; color: var(--text-placeholder); margin-top: 4px; }

/* Chunk 预览弹窗 */
.chunk-preview-info { font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px; display: flex; gap: 16px; }
.chunk-preview-doc { font-size: 12px; color: var(--text-tertiary); margin-left: 12px; font-weight: normal; }
.chunk-edit-hint { font-size: 12px; color: var(--brand); background: var(--brand-light); padding: 8px 12px; border-radius: 6px; margin-bottom: 10px; display: flex; align-items: flex-start; gap: 4px; }
.chunk-edit-hint .hint-markdown { flex: 1; }
.chunk-edit-hint .hint-markdown :deep(p) { margin: 0; }
.chunk-edit-hint .hint-markdown :deep(ul), .chunk-edit-hint .hint-markdown :deep(ol) { margin: 2px 0; padding-left: 16px; }
.chunk-content-input { font-family: monospace; font-size: 12px; line-height: 1.5; }

/* Chunk 预览弹窗 - 三列布局 */
.chunk-preview-3col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 10px;
}
.preview-col {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.preview-col-header {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}
.suggestion-col-header {
  background: #f0fdf4;
  color: #166534;
  border-bottom-color: #bbf7d0;
}
.preview-col-body {
  flex: 1;
  height: 350px;
  overflow-y: auto;
  background: var(--bg-primary, #fff);
}
.preview-textarea {
  width: 100%;
  height: 350px;
  border: none;
  resize: none;
  padding: 10px;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  box-shadow: none;
  outline: none;
}
.preview-textarea:focus {
  outline: none;
  box-shadow: none;
}
.suggestion-col-body {
  padding: 10px;
  font-size: 13px;
  line-height: 1.6;
}
.ai-suggestion-content :deep(p) { margin: 0 0 6px; }
.ai-suggestion-content :deep(ul), .ai-suggestion-content :deep(ol) { padding-left: 18px; margin: 4px 0; }
.ai-suggestion-content :deep(code) { background: var(--bg-secondary); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.ai-suggestion-content :deep(pre) { background: var(--bg-secondary); padding: 8px; border-radius: 6px; overflow-x: auto; }
.suggestion-section {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--border, #e5e7eb);
}
.suggestion-section:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}
.suggestion-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  margin-bottom: 4px;
}
.suggestion-value {
  font-size: 13px;
  color: var(--text-primary, #1f2937);
  line-height: 1.6;
  background: #f9fafb;
  border-radius: 6px;
  padding: 8px 10px;
}
.suggestion-value.markdown-body :deep(p) { margin: 0 0 6px; }
.suggestion-value.markdown-body :deep(code) { background: #e5e7eb; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.no-suggestion {
  color: var(--text-tertiary);
  font-size: 12px;
  text-align: center;
  padding: 40px 10px;
}
.edit-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.edit-panel-header {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.edit-panel-preview .edit-panel-header { background: #f0f9ff; color: var(--brand); }
.edit-textarea {
  flex: 1;
  height: 280px;
  resize: none;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
.edit-preview-body {
  padding: 10px 12px;
  height: 280px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  background: var(--bg-primary, #fff);
  flex: 1;
}
.edit-preview-body :deep(p) { margin: 0 0 6px; }
.edit-preview-body :deep(ul), .edit-preview-body :deep(ol) { padding-left: 18px; margin: 4px 0; }
.edit-preview-body :deep(code) { background: var(--bg-secondary); padding: 1px 4px; border-radius: 3px; font-size: 12px; }

.modal-card.modal-wide.modal-chunk-preview { width: 1900px !important; max-width: 98vw !important; }
.suggestion-delta { font-size: 11px; color: var(--text-secondary); margin-top: 3px; background: var(--bg-secondary, #f7f8fa); border-radius: 4px; padding: 3px 8px; display: flex; flex-direction: column; gap: 2px; }
.suggestion-actions { margin-top: 6px; display: flex; gap: 6px; }
.status-badge.sg-pending { background: #fff4e0; color: #b26a00; }
.status-badge.sg-verifying { background: #e8f0fe; color: #1a73e8; }
.status-badge.sg-verified { background: #e6f4ea; color: #188038; }
.status-badge.sg-failed { background: #fdecea; color: #d93025; }
.status-badge.sg-dismissed { background: #f1f3f4; color: #5f6368; }

/* ── 六态分类 ── */
.run-detail-head { display: flex; justify-content: space-between; align-items: center; }
.run-detail-actions { display: flex; gap: 6px; align-items: center; }
.btn-icon-only { padding: 2px 6px !important; font-size: 14px; background: transparent; border: 1px solid var(--border-light, #dadce0); border-radius: 6px; cursor: pointer; }
.btn-icon-only:hover { background: var(--bg-hover, #f1f3f4); }
.classify-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.classify-chip { font-size: 11px; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
.cls-complete { background: #e6f4ea; color: #188038; }
.cls-partial { background: #fff4e0; color: #b26a00; }
.cls-retrieval_miss { background: #fdecea; color: #d93025; }
.cls-insufficient_context { background: #fef0e0; color: #c05a00; }
.cls-wrong_answer { background: #fdecea; color: #d93025; }
.cls-unjudgeable { background: #f1f3f4; color: #5f6368; }

/* 运行历史 */
.run-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; margin-bottom: 2px; }
.run-item:hover { background: var(--bg-hover); }
.run-item.active { background: var(--brand-light); }
.run-time { font-size: 11px; color: var(--text-placeholder); flex: 1; }

.status-badge { font-size: 11px; padding: 1px 7px; border-radius: 10px; white-space: nowrap; }
.status-running { background: #e8f0fe; color: #1a73e8; }
.status-done { background: #e6f4ea; color: #188038; }
.status-failed { background: #fdecea; color: #d93025; }

/* 指标卡片 */
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 8px; }
.metric-card { border-radius: 8px; padding: 8px 6px; text-align: center; }
.metric-card.layer-retrieval { background: var(--brand-light); }
.metric-card.layer-generation { background: #e6f4ea; }
.metric-value { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.metric-name { font-size: 10px; color: var(--text-tertiary); margin-top: 2px; }

/* 结果下钻 */
.result-list { margin-top: 10px; }
.result-item { border: 1px solid var(--border-primary); border-radius: 8px; margin-bottom: 6px; overflow: hidden; }
.result-item summary { cursor: pointer; padding: 8px 10px; font-size: 12px; display: flex; gap: 6px; align-items: baseline; list-style: none; }
.result-item summary::-webkit-details-marker { display: none; }
.result-index { color: var(--brand); font-weight: 600; }
.result-question { flex: 1; color: var(--text-primary); }
.result-quick { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }
.result-body { padding: 0 10px 10px; }
.result-section { margin-top: 8px; }
.result-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }
.retrieved-chunk { display: flex; gap: 6px; align-items: flex-start; font-size: 11px; padding: 4px 6px; border-radius: 4px; margin-bottom: 2px; color: var(--text-secondary); background: var(--bg-secondary, #f7f8fa); }
.retrieved-chunk.gt { background: #e6f4ea; color: #188038; }
.rc-badge { flex-shrink: 0; font-weight: 600; }
.rc-score { flex-shrink: 0; color: var(--text-placeholder); }
.rc-content { word-break: break-all; }
.result-answer { font-size: 12px; line-height: 1.6; color: var(--text-primary); background: var(--bg-secondary, #f7f8fa); border-radius: 6px; padding: 8px 10px; }
.judge-row { display: flex; flex-wrap: wrap; gap: 8px; }
.judge-metric { font-size: 11px; color: var(--text-secondary); background: var(--bg-secondary, #f7f8fa); border-radius: 4px; padding: 3px 8px; }
.judge-metric b { color: var(--brand); }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--bg-primary); border-radius: 12px; padding: 18px; width: 420px; max-width: 92vw; display: flex; flex-direction: column; gap: 10px; max-height: 86vh; overflow-y: auto; }
.modal-wide { width: 680px; }
.modal-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.item-question-input { resize: vertical; }

/* GT 选择器 */
.gt-picker-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.gt-selected { display: flex; gap: 4px; flex-wrap: wrap; }
.gt-chip-removable { cursor: pointer; }
.gt-picker-toolbar { display: flex; gap: 8px; align-items: center; }
.gt-picker-toolbar select { background: var(--bg-secondary, #f5f6f8); border: 1px solid var(--border-primary); color: var(--text-primary); border-radius: 6px; padding: 6px 8px; font-size: 12px; max-width: 200px; }
.gt-picker-list { max-height: 46vh; overflow-y: auto; border: 1px solid var(--border-primary); border-radius: 8px; margin-top: 4px; }
.gt-pick-item { display: flex; gap: 8px; padding: 8px 10px; cursor: pointer; border-bottom: 1px solid var(--border-primary); }
.gt-pick-item:last-child { border-bottom: none; }
.gt-pick-item:hover { background: var(--bg-hover); }
.gt-pick-item.picked { background: var(--brand-light); }
.gp-check { flex-shrink: 0; font-size: 13px; }
.gp-body { min-width: 0; }
.gp-meta { font-size: 11px; color: var(--text-placeholder); display: flex; align-items: center; gap: 6px; }
.gp-kind-badge { 
  font-size: 10px; 
  padding: 1px 6px; 
  border-radius: 4px; 
  flex-shrink: 0;
  font-weight: 500;
}
.gp-kind-badge.kind-parent { background: #e8f0fe; color: #1967d2; }
.gp-kind-badge.kind-child { background: #fce8e6; color: #c5221f; }
.gp-kind-badge.kind-base { background: var(--bg-secondary, #f0f1f4); color: var(--text-tertiary); }
.gp-content { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.gt-picker-footer { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.gt-picker-count { flex: 1; font-size: 12px; color: var(--brand); }
.page-info { font-size: 12px; color: var(--text-secondary); }

/* ── 阈值设置弹窗 ── */
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal-card {
  background: #fff; border-radius: 16px; box-shadow: 0 12px 48px rgba(0,0,0,0.25);
  width: 640px; max-width: 92vw; max-height: 88vh; overflow: auto;
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20px 24px; border-bottom: 1px solid var(--border-light, #e8eaed);
}
.modal-title { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.modal-body { padding: 24px; }
.modal-footer {
  display: flex; justify-content: flex-end; gap: 12px;
  padding: 16px 24px; border-top: 1px solid var(--border-light, #e8eaed);
}
.threshold-desc { font-size: 14px; color: var(--text-secondary); margin: 0 0 20px; line-height: 1.5; }
.threshold-field { margin-bottom: 20px; }
.threshold-field label {
  display: block; font-size: 15px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;
}
.threshold-key {
  font-size: 12px; color: var(--text-tertiary, #80868b); font-weight: normal; font-family: monospace;
  background: var(--bg-secondary, #f0f1f4); padding: 2px 8px; border-radius: 4px;
}
.threshold-input-row { display: flex; align-items: center; gap: 12px; }
.threshold-input-row input[type="range"] { flex: 1; accent-color: var(--brand); height: 8px; }
.threshold-number {
  width: 72px; padding: 6px 10px; border: 1px solid var(--border-light, #dadce0);
  border-radius: 6px; font-size: 15px; text-align: center; font-family: monospace;
}
.threshold-hint { display: block; font-size: 13px; color: var(--text-tertiary, #80868b); margin-top: 4px; line-height: 1.4; }
.threshold-note {
  display: block; font-size: 12px; color: #b26a00;
  background: #fff8e1; padding: 4px 8px; border-radius: 4px; margin-top: 4px;
}
.threshold-priority {
  background: var(--bg-secondary, #f8f9fa); border-radius: 10px; padding: 14px 16px;
  font-size: 14px; color: var(--text-secondary); line-height: 1.8;
}
.threshold-priority-title { font-weight: 600; color: var(--text-primary); margin-bottom: 8px; font-size: 15px; }

/* ── 反馈建议卡片增强 ── */
.fb-query {
  font-size: 13px; font-weight: 500; color: var(--text-primary);
  padding: 4px 8px; background: var(--bg-secondary, #f8f9fa); border-radius: 5px; margin-top: 2px;
}
.fb-answer {
  font-size: 12px; color: var(--text-secondary); line-height: 1.5;
  padding: 6px 8px; background: #f0f7ff; border-left: 3px solid var(--brand, #1a73e8);
  border-radius: 0 5px 5px 0; margin-top: 2px; max-height: 120px; overflow-y: auto;
}
.fb-comment {
  font-size: 12px; color: #b26a00; padding: 4px 8px;
  background: #fff8e1; border-radius: 5px; margin-top: 2px;
}

/* ── 聊天反馈入口 + 题目卡片 ── */
.chat-feedback-entry {
  border: 1px dashed var(--brand, #1a73e8);
  border-radius: 8px;
  margin-bottom: 6px;
  background: linear-gradient(135deg, #eef5ff 0%, #f8fbff 100%);
}
.chat-feedback-entry.active {
  background: var(--brand-light, #e8f0fe);
  border-style: solid;
}
.set-divider {
  height: 1px; background: var(--border-light, #e8eaed); margin: 8px 0;
}
.chat-fb-item { border-left: 3px solid #fbbc04; }
.chat-fb-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px;
}
.chat-fb-left { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.chat-fb-rating { font-size: 14px; }
.chat-fb-time { color: var(--text-placeholder); }
.chat-fb-comment {
  background: #fff8e1; padding: 1px 6px; border-radius: 4px; color: #b26a00;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-fb-chunk {
  display: flex; align-items: flex-start; gap: 6px; margin-top: 3px;
  font-size: 12px; color: var(--text-secondary);
}
.chat-fb-chunk-preview {
  flex: 1; line-height: 1.4; word-break: break-all;
}
.chat-fb-selected {
  border-left-color: var(--brand, #1a73e8) !important;
  background: var(--brand-light, #e8f0fe) !important;
  box-shadow: 0 0 0 1px var(--brand, #1a73e8);
}

/* 聊天反馈状态标签 */
.chat-fb-summary { margin-top: 6px; }
.chat-fb-status {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 500;
}
.chat-fb-status.status-miss { background: #fce8e6; color: #c5221f; }
.chat-fb-status.status-hit { background: #e6f4ea; color: #137333; }

/* 反馈详情区域 */
.feedback-detail-section { margin-bottom: 16px; }
.feedback-detail-card {
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 8px; padding: 12px;
}
.feedback-detail-row {
  margin-bottom: 10px;
}
.feedback-detail-row:last-child { margin-bottom: 0; }
.feedback-detail-label {
  display: block; font-size: 12px; font-weight: 500;
  color: var(--text-secondary); margin-bottom: 4px;
}
.feedback-detail-content {
  font-size: 13px; color: var(--text-primary); line-height: 1.5;
}
.feedback-comment {
  background: #fff8e1; padding: 6px 10px; border-radius: 5px;
  border-left: 3px solid #f9a825;
}
.chunk-list { margin-top: 4px; }
.chunk-item {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid var(--border-light, #e8eaed);
}
.chunk-item:last-child { border-bottom: none; }
.chunk-id {
  flex-shrink: 0;
  background: var(--brand-light, #e8f0fe); color: var(--brand, #1a73e8);
  padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 500;
}
.chunk-preview {
  flex: 1; font-size: 11px; color: var(--text-secondary);
  line-height: 1.4; word-break: break-all;
}

/* 优化建议内容 */
.suggestion-content {
  font-size: 12px; line-height: 1.6; color: var(--text-primary);
  padding: 8px 0;
}
.suggestion-content ul,
.suggestion-summary ul {
  list-style: disc;
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.suggestion-content li,
.suggestion-summary li {
  margin: 0.25em 0;
}

@media (max-width: 1200px) {
  .eval-layout { grid-template-columns: 220px 1fr; }
  .pane-right { grid-column: 1 / -1; max-height: 460px; }
}
</style>
