<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">⚙️ 系统配置</h1>
        <p class="page-desc">配置模型、渠道绑定、邮箱等系统参数</p>
      </div>
    </header>

    <!-- Tab 导航 -->
    <nav class="config-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <!-- ──────────────────────────────────────────── -->
    <!-- Tab 1: 模型配置 -->
    <!-- ──────────────────────────────────────────── -->
    <div v-show="activeTab === 'model'" class="tab-content">
      <!-- ── 降级链配置 ── -->
      <div class="card" style="margin-bottom: 16px;">
        <div class="card-header collapsible-header" @click="showFallbackChain = !showFallbackChain">
          <span>{{ showFallbackChain ? '▼' : '▶' }} 🔗 降级链配置</span>
          <span class="badge badge-info">{{ fallbackChainItems.length }} 个模型</span>
        </div>
        <div v-if="showFallbackChain" class="card-body">
          <p class="section-tip">
            当主模型不可用时，系统按以下顺序自动尝试。拖拽 ≡ 图标调整优先级。
          </p>
          <div v-if="fallbackChainItems.length === 0" class="empty-state" style="padding:16px;">
            降级链为空，请从下方模型列表中添加
          </div>
          <div v-else class="chain-list">
            <div
              v-for="(item, idx) in fallbackChainItems"
              :key="item.id"
              class="chain-item"
              :class="{ 'chain-dragging': dragIndex === idx }"
              draggable="true"
              @dragstart="onDragStart(idx)"
              @dragover="onDragOver($event, idx)"
              @drop="onDrop($event, idx)"
              @dragend="onDragEnd"
            >
              <span class="chain-drag-handle" title="拖拽排序">≡</span>
              <span class="chain-priority">#{{ idx + 1 }}</span>
              <div class="chain-info">
                <div class="chain-name">{{ item.config_name }}</div>
                <div class="chain-meta">{{ item.model_name }} · {{ item.provider || 'auto' }}</div>
              </div>
              <span class="chain-circuit">{{ circuitLabel(item.circuit_state) }}</span>
              <button class="btn btn-danger btn-sm" @click="removeFromChain(idx)">移除</button>
            </div>
          </div>
          <div v-if="availableForChain.length > 0" class="chain-add-row">
            <select class="select select-sm" @change="(e: Event) => { const id = Number((e.target as HTMLSelectElement).value); const cfg = configs.find((c: ModelConfig) => c.id === id); if (cfg) addToChain(cfg); (e.target as HTMLSelectElement).value = ''; }">
              <option value="">+ 从已有模型添加到降级链...</option>
              <option v-for="cfg in availableForChain" :key="cfg.id" :value="cfg.id">{{ formatModelLabel(cfg) }}</option>
            </select>
          </div>
          <button v-if="fallbackChainItems.length > 0" class="btn btn-primary btn-sm" @click="saveChain" :disabled="fallbackChainSaving" style="margin-top:12px;">
            {{ fallbackChainSaving ? '保存中...' : '💾 保存降级链' }}
          </button>
        </div>
      </div>

      <!-- ── 场景路由 ── -->
      <div class="card" style="margin-bottom: 16px;">
        <div class="card-header collapsible-header" @click="showSceneRouting = !showSceneRouting">
          <span>{{ showSceneRouting ? '▼' : '▶' }} 🎯 场景路由 <span class="form-optional">（高级）</span></span>
        </div>
        <div v-if="showSceneRouting" class="card-body">
          <p class="section-tip">
            为不同 LLM 使用场景指定专属模型。内置场景覆盖记忆提取、RAG 检索、上下文压缩等内部操作，可配置便宜模型降低成本。
            <b>前端聊天不触发场景路由</b>，需后端入口传入 scene 参数（如微信/定时任务自动携带）。
          </p>
          <div v-if="Object.keys(sceneRouting).length === 0" class="empty-state" style="padding:12px;">
            暂未配置场景路由，所有场景使用默认模型
          </div>
          <div v-else class="scene-grouped">
            <div v-for="([catKey, group]) in groupedSceneRouting" :key="catKey" class="scene-group">
              <div class="scene-group-title">{{ group.icon }} {{ group.name }}</div>
              <div class="scene-group-items">
                <div v-for="item in group.items" :key="item.key" class="scene-row">
                  <div class="scene-row-info">
                    <span class="scene-row-name">{{ getSceneName(item.key) }}</span>
                    <span class="scene-row-hint" :title="getSceneDescription(item.key)">{{ getSceneRecommendation(item.key) }}</span>
                    <span class="scene-row-arrow">→</span>
                    <span class="scene-row-model">{{ getModelName(item.model_config_id) }}</span>
                  </div>
                  <div class="scene-row-actions">
                    <button class="btn btn-secondary btn-sm" @click="startEditScene(item.key)">编辑</button>
                    <button class="btn btn-danger btn-sm" @click="removeSceneRoute(item.key)">移除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- 编辑弹窗 -->
          <div v-if="editingSceneKey" class="modal-backdrop" @click.self="cancelEditScene">
            <div class="modal-box">
              <div class="modal-header">
                <span class="modal-title">编辑场景路由</span>
                <button class="modal-close" @click="cancelEditScene">×</button>
              </div>
              <div class="modal-body">
                <div class="modal-field">
                  <label class="modal-label">场景</label>
                  <span class="modal-scene-name">{{ getSceneName(editingSceneKey) }}</span>
                  <span class="modal-scene-hint">{{ getSceneRecommendation(editingSceneKey) }}</span>
                </div>
                <div class="modal-field">
                  <label class="modal-label">选择模型</label>
                  <select v-model="editingModelId" class="select">
                    <option v-for="cfg in chatConfigs" :key="cfg.id" :value="cfg.id">{{ formatModelLabel(cfg) }}</option>
                  </select>
                </div>
                <div v-if="getSceneDescription(editingSceneKey)" class="modal-description">
                  💡 {{ getSceneDescription(editingSceneKey) }}
                </div>
              </div>
              <div class="modal-footer">
                <button class="btn btn-secondary" @click="cancelEditScene">取消</button>
                <button class="btn btn-primary" @click="saveEditScene">确定</button>
              </div>
            </div>
          </div>
          <!-- 新增场景 -->
          <div class="scene-add-row" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:12px;">
            <select v-model="newSceneKey" class="select select-sm" style="width:240px;">
              <option value="">选择场景...</option>
              <optgroup v-for="([catKey, group]) in groupedScenes" :key="catKey" :label="`${group.category.icon} ${group.category.name}`">
                <option v-for="scene in group.scenes" :key="scene.key" :value="scene.key" :disabled="!!sceneRouting[scene.key]">
                  {{ scene.name }}{{ sceneRouting[scene.key] ? ' (已配置)' : '' }}
                </option>
              </optgroup>
            </select>
            <select v-model="newSceneModelId" class="select select-sm" style="flex:1; min-width:180px;">
              <option :value="0">选择模型...</option>
              <option v-for="cfg in chatConfigs" :key="cfg.id" :value="cfg.id">{{ formatModelLabel(cfg) }}</option>
            </select>
            <button class="btn btn-secondary btn-sm" @click="addSceneRoute" :disabled="!newSceneKey.trim() || !newSceneModelId">添加</button>
          </div>
          <div v-if="selectedSceneDescription" class="scene-description-hint" style="font-size:12px; color:var(--text-tertiary); margin-top:6px;">
            💡 {{ selectedSceneDescription }}
          </div>
          <button v-if="Object.keys(sceneRouting).length > 0" class="btn btn-primary btn-sm" @click="saveSceneRoute" :disabled="sceneRoutingSaving" style="margin-top:12px;">
            {{ sceneRoutingSaving ? '保存中...' : '💾 保存场景路由' }}
          </button>

          <!-- 路由评测 -->
          <div class="route-eval-section" style="margin-top:16px;">
            <h4 class="subsection-title" style="font-size:13px;">🔍 路由评测</h4>
            <div style="display:flex;gap:8px;align-items:center;">
              <input v-model="routeEvalScene" class="input input-sm" placeholder="场景名（留空=默认）" style="width:160px;" />
              <button class="btn btn-secondary btn-sm" @click="doEvaluateRoute">评测</button>
            </div>
            <pre v-if="routeEvalResult" class="route-eval-result">{{ routeEvalResult }}</pre>
          </div>
        </div>
      </div>

      <div class="split-layout">
        <!-- 左：模型列表 -->
        <div class="card">
          <div class="card-header">
            <span>🤖 LLM 模型配置</span>
            <span v-if="envConfigured" class="badge badge-info">.env 兜底</span>
          </div>
          <!-- 分类 Tab：每类模型各自维护「当前」 -->
          <div class="model-cat-tabs">
            <button
              v-for="(label, key) in modelCategories"
              :key="key"
              class="model-cat-tab"
              :class="{ active: modelCategory === key }"
              @click="switchModelCategory(key)"
            >
              {{ label }}
              <span class="model-cat-count">{{ configs.filter(c => (c.category || 'chat') === key).length }}</span>
            </button>
          </div>
          <div class="card-body">
            <p class="section-tip">
              {{ modelCategory === 'chat' ? '用于智能对话与 RAG 评测裁判，每类可保存多条配置，点击「设为当前」切换。' : modelCategory === 'embedding' ? '用于知识库向量化与语义检索（含 RAG 评测 AnswerRelevancy），配置后无需改后端 .env。' : '用于 RAG 检索精排（如 DashScope gte-rerank-v2），配置后自动启用检索精排。' }}
            </p>
            <div v-if="filteredConfigs.length === 0" class="empty-state">暂无{{ modelCategories[modelCategory] }}配置，请在右侧新增</div>
            <div v-else class="config-mini-list">
              <div v-for="cfg in filteredConfigs" :key="cfg.id" class="mini-item" :class="{ active: cfg.is_current, editing: editingId === cfg.id }">
                <template v-if="editingId === cfg.id">
                  <div class="mini-edit">
                    <input v-model="editForm.config_name" class="input input-sm" placeholder="名称" />
                    <input v-model="editForm.model_name" class="input input-sm" placeholder="模型" />
                    <input v-model="editForm.api_url" class="input input-sm" placeholder="API URL" />
                    <p class="input-hint" style="font-size:10px;">⚠️ 不填 <code>/v1</code> 等后缀，系统自动补全</p>
                    <select v-model="editForm.provider" class="select select-sm">
                      <option value="">自动检测</option>
                      <option value="deepseek">DeepSeek</option>
                      <option value="alibaba">Qwen Cloud</option>
                      <option value="alibaba-coding-plan">Alibaba Coding Plan</option>
                      <option value="zhipu">GLM / 智谱</option>
                      <option value="kimi-coding">Kimi Coding</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="gemini">Gemini</option>
                      <option value="xai">xAI Grok</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                    <select v-model="editForm.reasoning_effort" class="select select-sm">
                      <option value="">推理深度: 默认</option>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="max">Max</option>
                      <option value="ultra">Ultra</option>
                    </select>
                    <label v-if="editForm.category === 'embedding'" class="checkbox-label" style="font-size:12px;">
                      <input type="checkbox" :checked="!!editForm.is_multimodal" @change="editForm.is_multimodal = ($event.target as HTMLInputElement).checked ? 1 : 0" />
                      多模态 Embedding
                    </label>
                    <template v-if="editForm.category === 'embedding'">
                      <div style="display:flex;gap:6px;align-items:center;font-size:12px;">
                        <label>维度:</label>
                        <input v-model.number="editForm.dimension" class="input input-sm" type="number" min="0" max="8192" style="width:80px;" placeholder="默认" />
                        <label class="checkbox-label" style="font-size:11px;margin:0;">
                          <input type="checkbox" :checked="!!editForm.send_dimensions" @change="editForm.send_dimensions = ($event.target as HTMLInputElement).checked ? 1 : 0" />
                          发送 dimensions
                        </label>
                      </div>
                      <p class="input-hint" style="font-size:10px;color:#d97706;">⚠️ 切换维度需清空向量库重新向量化</p>
                    </template>
                    <input v-model="editForm.api_key" class="input input-sm" type="password" placeholder="Key（留空不修改）" />
                    <div class="mini-edit-actions">
                      <button class="btn btn-primary btn-sm" @click="saveEdit(cfg.id)">保存</button>
                      <button class="btn btn-secondary btn-sm" @click="cancelEdit">取消</button>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="mini-main">
                    <div class="mini-name">{{ cfg.config_name }} <span v-if="cfg.is_current" class="badge badge-success">当前</span><span v-if="cfg.is_multimodal" class="badge badge-multimodal" title="支持图片识别">🖼️ 多模态</span><span v-if="cfg.reasoning_effort" class="badge badge-effort" :title="'推理深度: ' + cfg.reasoning_effort">🧠 {{ effortLabel(cfg.reasoning_effort) }}</span><span v-if="cfg.category === 'embedding' && cfg.dimension" class="badge" style="background:#e0f2fe;color:#0369a1;font-size:11px;" :title="'向量维度: ' + cfg.dimension + (cfg.send_dimensions ? '（已启用）' : '（未发送）')">{{ cfg.dimension }}d{{ cfg.send_dimensions ? '' : '?' }}</span></div>
                    <div class="mini-meta">{{ cfg.model_name }}<template v-if="cfg.provider"> · {{ cfg.provider }}</template> · {{ cfg.api_url }}</div>
                    <div v-if="cfg.category === 'chat' && (cfg.cost_per_1k_input || cfg.context_length)" class="mini-capabilities">
                      <span v-if="cfg.cost_per_1k_input || cfg.cost_per_1k_output" class="cap-tag" title="成本">💰 {{ formatCost(cfg.cost_per_1k_input) }}/{{ formatCost(cfg.cost_per_1k_output) }}</span>
                      <span v-if="cfg.context_length" class="cap-tag" title="上下文窗口">📏 {{ formatContext(cfg.context_length) }}</span>
                      <span v-if="cfg.circuit_state === 1" class="cap-tag cap-circuit-open" title="熔断中">🔴 熔断</span>
                      <span v-if="cfg.circuit_state === 2" class="cap-tag cap-circuit-half" title="半开">🟡 半开</span>
                    </div>
                  </div>
                  <div class="mini-actions">
                    <button v-if="!cfg.is_current" class="btn btn-primary btn-sm" @click="setActive(cfg.id)">设为当前</button>
                    <button class="btn btn-secondary btn-sm" @click="testConn(cfg.id)" :disabled="testingId === cfg.id">{{ testingId === cfg.id ? '测试中' : '测试' }}</button>
                    <button class="btn btn-secondary btn-sm" @click="startEdit(cfg)">编辑</button>
                    <button class="btn btn-danger btn-sm" @click="remove(cfg)">删除</button>
                  </div>
                </template>
              </div>
              <div v-if="testResult" class="test-result" :class="{ ok: testResult.ok, fail: !testResult.ok }">
                <span>{{ testResult.ok ? '✅' : '❌' }}</span>
                <span>{{ testResult.message }}</span>
                <span v-if="testResult.is_multimodal" class="badge badge-multimodal" style="margin-left:6px;" title="该模型支持图片识别">🖼️ 多模态</span>
                <span v-else-if="testResult.probe_multimodal === true" class="badge badge-multimodal" style="margin-left:6px;" title="图片探测：该模型支持图片识别">🖼️ 多模态</span>
                <span v-else-if="testResult.probe_multimodal === false" class="badge" style="margin-left:6px;background:#eee;color:#888;font-size:11px;" :title="testResult.probe_message || '图片探测：纯文本模型'">📝 纯文本</span>
                <span v-else-if="testResult.is_multimodal === false" class="badge" style="margin-left:6px;background:#eee;color:#888;font-size:11px;" title="静态规则：未匹配多模态关键词">📝 纯文本</span>
                <button class="btn-text" @click="testResult = null">✕</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 右：新增表单 -->
        <div class="card">
          <div class="card-header">➕ 新增{{ modelCategories[modelCategory] }}配置</div>
          <div class="card-body">
            <p class="section-tip" style="margin-bottom:12px;">
              当前分类：<b>{{ modelCategories[modelCategory] }}</b>
              <template v-if="modelCategory === 'embedding'"> — 保存后用于知识库向量化/检索与 RAG 评测 AnswerRelevancy</template>
              <template v-else-if="modelCategory === 'rerank'"> — 保存后用于 RAG 检索精排（如 DashScope gte-rerank-v2）</template>
              <template v-else> — 用于智能对话与 RAG 评测裁判</template>
            </p>
            <div class="form-group">
              <label class="form-label">配置名称</label>
              <input v-model="form.config_name" class="input" placeholder="如：公司 GPT-4" />
            </div>
            <div class="form-group">
              <label class="form-label">模型名称</label>
              <input v-model="form.model_name" class="input" :placeholder="modelCategory === 'embedding' ? '如：text-embedding-v3 / bge-large-zh' : modelCategory === 'rerank' ? '如：gte-rerank-v2' : '如：gpt-4 / qwen-max'" />
            </div>
            <div class="form-group">
              <label class="form-label">Provider <span class="form-optional">（可选）</span></label>
              <select v-model="form.provider" class="select">
                <option value="">自动检测（推荐）</option>
                <optgroup label="──── 国内厂商 ────">
                  <option value="deepseek">DeepSeek</option>
                  <option value="alibaba">Qwen Cloud / DashScope</option>
                  <option value="alibaba-coding-plan">Alibaba Coding Plan</option>
                  <option value="zhipu">Z.AI / GLM（智谱）</option>
                  <option value="kimi-coding">Kimi Coding Plan</option>
                  <option value="kimi-coding-cn">Kimi / Moonshot（国内）</option>
                  <option value="minimax">MiniMax</option>
                  <option value="minimax-cn">MiniMax（国内）</option>
                  <option value="stepfun">StepFun</option>
                  <option value="xiaomi">Xiaomi MiMo</option>
                </optgroup>
                <optgroup label="──── 海外厂商 ────">
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="xai">xAI / Grok</option>
                  <option value="openrouter">OpenRouter</option>
                  <option value="nous">Nous Portal</option>
                  <option value="fireworks">Fireworks AI</option>
                  <option value="nvidia">NVIDIA NIM</option>
                </optgroup>
                <optgroup label="──── 其他 ────">
                  <option value="bedrock">AWS Bedrock</option>
                  <option value="ollama">Ollama</option>
                  <option value="lmstudio">LM Studio</option>
                  <option value="custom">Custom Endpoint</option>
                </optgroup>
              </select>
              <p class="input-hint">💡 留空则根据 API URL 自动检测。使用代理/中转时建议手动指定。</p>
            </div>
            <div v-if="modelCategory === 'chat'" class="form-group">
              <label class="form-label">推理深度 <span class="form-optional">（可选）</span></label>
              <select v-model="form.reasoning_effort" class="select">
                <option value="">默认（不启用）</option>
                <option value="low">Low — 快速响应</option>
                <option value="medium">Medium — 平衡</option>
                <option value="high">High — 深度思考</option>
                <option value="max">Max — 最大推理</option>
                <option value="ultra">Ultra — 极限推理</option>
              </select>
              <p class="input-hint">💡 需要模型本身支持 reasoning。不支持的模型会忽略此参数。</p>
            </div>
            <div v-if="modelCategory === 'embedding'" class="form-group">
              <label class="form-label checkbox-label">
                <input type="checkbox" :checked="!!form.is_multimodal" @change="form.is_multimodal = ($event.target as HTMLInputElement).checked ? 1 : 0" />
                多模态 Embedding（如 doubao-embedding-vision）
              </label>
              <p class="input-hint">💡 多模态 embedding 走 <code>/embeddings/multimodal</code> 端点（内容块格式），适配火山方舟 doubao-embedding-vision 等。模型名含 vision/multimodal 时自动启用，也可手动勾选（如使用 ep-xxx 接入点 ID）。</p>
            </div>
            <div v-if="modelCategory === 'embedding'" class="form-group">
              <label class="form-label">向量维度 <span class="form-optional">（可选）</span></label>
              <input v-model.number="form.dimension" class="input" type="number" min="0" max="8192" step="128" placeholder="0 = 使用模型默认值" />
              <p class="input-hint">💡 <b>填 0 或不填则使用模型默认维度</b>。常见维度：1024、1536、2048。请查阅模型文档确认支持的维度值。</p>
            </div>
            <div v-if="modelCategory === 'embedding'" class="form-group">
              <label class="form-label checkbox-label">
                <input type="checkbox" :checked="!!form.send_dimensions" @change="form.send_dimensions = ($event.target as HTMLInputElement).checked ? 1 : 0" />
                发送维度参数（dimensions）给 API
              </label>
              <p class="input-hint">⚠️ 仅当模型 API 支持 <code>dimensions</code> 请求参数时勾选。勾选后会在请求体中附加 <code>"dimensions": N</code>，使模型输出指定维度的向量。</p>
              <details style="margin-top:6px;font-size:12px;color:#666;">
                <summary style="cursor:pointer;">📋 常见模型维度支持参考（点击展开）</summary>
                <table style="margin-top:4px;border-collapse:collapse;font-size:11px;width:100%;">
                  <thead><tr style="background:#f5f5f5;"><th style="padding:3px 8px;text-align:left;border:1px solid #ddd;">模型</th><th style="padding:3px 8px;text-align:left;border:1px solid #ddd;">支持 dimensions</th><th style="padding:3px 8px;text-align:left;border:1px solid #ddd;">可选维度</th></tr></thead>
                  <tbody>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">OpenAI text-embedding-3-*</td><td style="padding:3px 8px;border:1px solid #ddd;color:green;">✅ 支持</td><td style="padding:3px 8px;border:1px solid #ddd;">128 ~ 3072</td></tr>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">阿里云 text-embedding-v3</td><td style="padding:3px 8px;border:1px solid #ddd;color:green;">✅ 支持</td><td style="padding:3px 8px;border:1px solid #ddd;">512 / 768 / 1024 / 1536 / 2048</td></tr>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">阿里云 text-embedding-v2/v1</td><td style="padding:3px 8px;border:1px solid #ddd;color:red;">❌ 不支持</td><td style="padding:3px 8px;border:1px solid #ddd;">固定 1536 / 1024</td></tr>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">智谱 embedding-3</td><td style="padding:3px 8px;border:1px solid #ddd;color:green;">✅ 支持</td><td style="padding:3px 8px;border:1px solid #ddd;">最高 2048</td></tr>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">BGE / Ollama 本地模型</td><td style="padding:3px 8px;border:1px solid #ddd;color:red;">❌ 不支持</td><td style="padding:3px 8px;border:1px solid #ddd;">模型固定维度</td></tr>
                    <tr><td style="padding:3px 8px;border:1px solid #ddd;">其他 / 不确定</td><td style="padding:3px 8px;border:1px solid #ddd;color:orange;">🤔 先不勾选试试</td><td style="padding:3px 8px;border:1px solid #ddd;">勾选后若报 400 错误则不支持</td></tr>
                  </tbody>
                </table>
              </details>
              <p class="input-hint" style="color: #d97706; margin-top: 4px;">🔒 <b>维度一致性</b>：文档向量化入库后，Chroma 向量库的维度就固定了。切换模型或修改维度时，<b>新维度必须与已有向量一致</b>，否则检索会报错。不一致时需清空向量库并重新向量化所有文档。</p>
            </div>
            <div class="form-group">
              <label class="form-label">API Base URL</label>
              <input v-model="form.api_url" class="input" placeholder="https://api.openai.com/v1" />
              <p class="input-hint">
                💡 填 API 根地址即可，<b>无需手动加</b> <code>/v1</code>、<code>/chat/completions</code> 等路径后缀，系统自动补全。<br/>
                · OpenAI 兼容（GPT/Qwen/GLM 等）：填 <code>https://api.openai.com</code> 或 <code>https://dashscope.aliyuncs.com/compatible-mode</code><br/>
                · Anthropic 兼容（Claude/DeepSeek 等）：填 <code>https://api.deepseek.com/anthropic</code><br/>
                · Embedding（DashScope）：<code>https://dashscope.aliyuncs.com/compatible-mode</code>，模型填 <code>text-embedding-v3</code> 等
              </p>
            </div>
            <div class="form-group">
              <label class="form-label">API Key</label>
              <input v-model="form.api_key" class="input" type="password" placeholder="sk-..." />
            </div>
            <button class="btn btn-primary" @click="create" :disabled="!canCreate || creating" style="width:100%;margin-top:8px;">{{ creating ? '保存中...' : '保存并设为当前' }}</button>
            <p class="config-tips" style="margin-top:8px;font-size:12px;">💡 支持 OpenAI 兼容接口，保存后立即生效（每类模型独立激活）。</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ──────────────────────────────────────────── -->
    <!-- Tab 2: 渠道绑定 -->
    <!-- ──────────────────────────────────────────── -->
    <div v-show="activeTab === 'channel'" class="tab-content">
      <!-- 微信 -->
      <div class="card">
        <div class="card-header">🟢 微信 <span v-if="wechatConfigured" class="badge badge-success">已配置</span></div>
        <div class="card-body">
          <p class="section-tip">通过扫码或手动填写 Token 绑定微信 Bot，实现 Web 端与微信消息双向互通。</p>

          <!-- QR 扫码区域（正在扫码时显示） -->
          <div v-if="qrSessionId" class="qr-scan-area">
            <div class="qr-container">
              <img v-if="qrImage" :src="qrImage" class="qr-image" alt="微信扫码" />
              <div v-else class="qr-loading">⏳ 生成二维码中...</div>
            </div>
            <div class="qr-status-text">
              <template v-if="qrStatus === 'wait' || qrStatus === 'wait_refreshed'">📱 请使用微信扫描上方二维码</template>
              <template v-else-if="qrStatus === 'scaned'">👆 已扫码，请在微信中点击确认</template>
              <template v-else-if="qrStatus === 'expired'">❌ 二维码已过期，请重新发起</template>
            </div>
            <button class="btn btn-secondary btn-sm" @click="cancelQr">取消</button>
          </div>

          <!-- 两种绑定方式 -->
          <div v-else class="wechat-bind-methods">
            <div class="bind-method-card">
              <div class="bind-method-icon">📱</div>
              <div class="bind-method-title">扫码绑定</div>
              <div class="bind-method-desc">iLink 扫码自动获取凭证</div>
              <button class="btn btn-primary btn-sm" @click="startQrBind" :disabled="qrLoading">{{ qrLoading ? '生成中...' : '开始扫码' }}</button>
            </div>
            <div class="bind-method-card">
              <div class="bind-method-icon">⌨️</div>
              <div class="bind-method-title">手动绑定</div>
              <div class="bind-method-desc">已有 Token，直接填写</div>
              <button class="btn btn-secondary btn-sm" @click="showManualBind = !showManualBind">{{ showManualBind ? '收起' : '手动绑定' }}</button>
            </div>
          </div>

          <!-- 手动绑定表单 -->
          <div v-if="showManualBind" class="manual-bind-form">
            <div class="form-group">
              <label class="form-label">Bot Token</label>
              <input v-model="manualBindForm.token" class="input" type="password" placeholder="iLink Bot Token" />
            </div>
            <div class="form-group">
              <label class="form-label">Account ID</label>
              <input v-model="manualBindForm.account_id" class="input" placeholder="Bot 账号 ID" />
            </div>
            <div class="form-row">
              <div class="form-group" style="flex:1;">
                <label class="form-label">微信 ID（可选）</label>
                <input v-model="manualBindForm.wxid" class="input" placeholder="用于绑定的微信标识" />
              </div>
              <div class="form-group" style="flex:1;">
                <label class="form-label">备注（可选）</label>
                <input v-model="manualBindForm.nickname" class="input" placeholder="例如: 我的微信" />
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary btn-sm" @click="submitManualBind" :disabled="!manualBindForm.token.trim() || !manualBindForm.account_id.trim() || savingManual">
                {{ savingManual ? '保存中...' : '确认绑定' }}
              </button>
              <span v-if="manualBindMsg" class="status-text" :class="{ ok: manualBindOk }">{{ manualBindMsg }}</span>
            </div>
          </div>

          <!-- 我的绑定状态 -->
          <h4 class="subsection-title" style="margin-top: 20px;">👤 我的绑定</h4>
          <div v-if="wechatBinding" class="binding-card">
            <div class="binding-info">
              <span class="binding-icon">💬</span>
              <div>
                <div class="binding-name">{{ wechatBinding.nickname || '微信用户' }}</div>
                <div class="binding-id">{{ wechatBinding.open_id }}</div>
              </div>
            </div>
            <button class="btn btn-danger btn-sm" @click="unbindWechat">解绑</button>
          </div>
          <div v-else class="binding-empty">
            <span class="muted">尚未绑定微信账号</span>
          </div>
        </div>
      </div>

      <!-- 飞书（灰掉） -->
      <div class="card card-disabled" style="margin-top: 16px;">
        <div class="card-header">🦜 飞书 <span class="badge badge-muted">即将推出</span></div>
        <div class="card-body">
          <p class="section-tip muted">飞书渠道绑定功能正在开发中，敬请期待。</p>
        </div>
      </div>
    </div>

    <!-- ──────────────────────────────────────────── -->
    <!-- Tab 3: 邮箱配置 -->
    <!-- ──────────────────────────────────────────── -->
    <div v-show="activeTab === 'email'" class="tab-content">
      <!-- 投递规则说明 -->
      <div class="card" style="margin-bottom: 16px;">
        <div class="card-header">💡 定时任务投递规则</div>
        <div class="card-body">
          <div class="delivery-rules">
            <div class="rule-item">
              <span class="rule-icon">🟢</span>
              <div class="rule-content">
                <div class="rule-title">微信投递</div>
                <div class="rule-desc">自动使用用户绑定的微信账号，无需额外配置。每个用户只能绑定一个微信账号。</div>
              </div>
            </div>
            <div class="rule-item">
              <span class="rule-icon">📧</span>
              <div class="rule-content">
                <div class="rule-title">邮箱投递</div>
                <div class="rule-desc">需要在创建定时任务时选择：<b>发件人邮箱</b>（从下方 SMTP 配置中选择）和 <b>收件人邮箱</b>（手动填写接收地址）。</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- SMTP 配置：左右结构 -->
      <div class="split-layout">
        <div class="card">
          <div class="card-header">
            <span>📧 SMTP 邮箱配置</span>
            <span v-if="!hasSystemConfig" class="badge badge-muted">需系统配置权限</span>
          </div>
          <div class="card-body">
            <p class="section-tip">可保存多条 SMTP 配置，点击「设为当前」切换。</p>
            <div v-if="emailConfigs.length === 0" class="empty-state">暂无配置，请在右侧新增</div>
            <div v-else class="config-mini-list">
              <div v-for="cfg in emailConfigs" :key="cfg.id" class="mini-item" :class="{ active: cfg.is_current }">
                <div class="mini-main">
                  <div class="mini-name">{{ cfg.config_name }} <span v-if="cfg.is_current" class="badge badge-success">当前</span></div>
                  <div class="mini-meta">{{ cfg.sender_email }} · {{ cfg.host }}:{{ cfg.port }}</div>
                </div>
                <div class="mini-actions" v-if="hasSystemConfig">
                  <button v-if="!cfg.is_current" class="btn btn-primary btn-sm" @click="setEmailActive(cfg.id)">设为当前</button>
                  <button class="btn btn-secondary btn-sm" @click="testEmail(cfg.id)" :disabled="emailTestingId === cfg.id">{{ emailTestingId === cfg.id ? '测试中' : '测试' }}</button>
                  <button class="btn btn-secondary btn-sm" @click="deleteEmail(cfg.id)">删除</button>
                </div>
              </div>
            </div>
            <div v-if="emailTestResult" class="smtp-test-result" :class="{ ok: emailTestResult.startsWith('✅'), error: emailTestResult.startsWith('❌') || emailTestResult.startsWith('⚠') }">{{ emailTestResult }}</div>
          </div>
        </div>

        <div v-if="hasSystemConfig" class="card">
          <div class="card-header">➕ 新增邮箱配置</div>
          <div class="card-body">
            <div class="form-group">
              <label class="form-label">配置名称</label>
              <input v-model="emailForm.config_name" class="input" placeholder="如：QQ邮箱" />
            </div>
            <div class="form-row">
              <div class="form-group" style="flex: 1;"><label class="form-label">SMTP 服务器</label><input v-model="emailForm.host" class="input" placeholder="smtp.qq.com" /></div>
              <div class="form-group" style="flex: 0 0 80px;"><label class="form-label">端口</label><input v-model="emailForm.port" class="input" placeholder="587" /></div>
            </div>
            <div class="form-group"><label class="form-label">发件人邮箱</label><input v-model="emailForm.sender_email" class="input" placeholder="your@qq.com" /></div>
            <div class="form-group"><label class="form-label">发件人名称</label><input v-model="emailForm.sender_name" class="input" placeholder="AgentForge" /></div>
            <div class="form-group"><label class="form-label">SMTP 密码 / 授权码</label><input v-model="emailForm.password" class="input" type="password" placeholder="QQ邮箱授权码" /></div>
            <button class="btn btn-primary" @click="addEmailConfig" :disabled="!canAddEmail" style="width:100%;margin-top:8px;">新增</button>
          </div>
        </div>
      </div>

      <!-- 个人邮箱 -->
      <div class="split-layout" style="margin-top:16px;">
        <div class="card">
          <div class="card-header">👤 我的邮箱</div>
          <div class="card-body">
            <p class="section-tip">我的接收邮箱，可添加多个，点击「设为当前」切换。</p>
            <div v-if="personalEmails.length === 0" class="empty-state">暂无邮箱</div>
            <div v-else class="config-mini-list">
              <div v-for="pe in personalEmails" :key="pe.id" class="mini-item" :class="{ active: pe.is_current }">
                <div class="mini-main"><div class="mini-name">{{ pe.email }} <span v-if="pe.is_current" class="badge badge-success">当前</span></div></div>
                <div class="mini-actions">
                  <button v-if="!pe.is_current" class="btn btn-primary btn-sm" @click="setPersonalEmailActive(pe.id)">设为当前</button>
                  <button class="btn btn-secondary btn-sm" @click="deletePersonal(pe.id)">删除</button>
                </div>
              </div>
            </div>
            <div v-if="personalEmailMsg" class="smtp-test-result" :class="{ ok: personalEmailOk, error: !personalEmailOk }" style="margin-top:8px;">{{ personalEmailMsg }}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">➕ 添加邮箱</div>
          <div class="card-body">
            <div class="form-group"><label class="form-label">邮箱地址</label><input v-model="newPersonalEmail" class="input" placeholder="your@email.com" @keyup.enter="addPersonal" /></div>
            <button class="btn btn-primary" @click="addPersonal" :disabled="!newPersonalEmail.trim().includes('@') || addingPersonalEmail" style="width:100%;margin-top:8px;">{{ addingPersonalEmail ? '添加中…' : '添加' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ──────────────────────────────────────────── -->
    <!-- Tab 4: 系统信息 -->
    <!-- ──────────────────────────────────────────── -->
    <div v-show="activeTab === 'info'" class="tab-content">
      <div class="config-grid">
        <div class="card">
          <div class="card-header">📊 服务状态</div>
          <div class="card-body">
            <div class="stat-grid">
              <div class="stat-card">
                <div class="stat-icon">💬</div>
                <div>
                  <div class="stat-value">{{ stats.sessions || '-' }}</div>
                  <div class="stat-label">活跃会话</div>
                </div>
              </div>
              <div class="stat-card">
                <div class="stat-icon">🧠</div>
                <div>
                  <div class="stat-value">{{ stats.skills || '-' }}</div>
                  <div class="stat-label">已安装技能</div>
                </div>
              </div>
              <div class="stat-card">
                <div class="stat-icon">🟢</div>
                <div>
                  <div class="stat-value">{{ stats.status || '-' }}</div>
                  <div class="stat-label">服务状态</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">📖 配置说明</div>
          <div class="card-body config-help">
            <p>所有配置通过 <code>.env</code> 文件管理。修改后需重启服务生效。</p>
            <p>生产环境推荐使用 Docker 部署，通过 <code>-e</code> 参数或 <code>docker-compose.yml</code> 注入环境变量。</p>
            <div class="help-code">
              <pre>cp .env.example .env
# 编辑 .env 填入你的配置
python main.py</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { getModelConfigs, createModelConfig, setActiveModelConfig, deleteModelConfig, updateModelConfig, testModelConfig, getEmailConfigs, createEmailConfig, setActiveEmailConfig, deleteEmailConfig, testEmailConfig, getPersonalEmails, addPersonalEmail as apiAddPersonalEmail, setActivePersonalEmail, deletePersonalEmail, getFallbackChain, saveFallbackChain, getSceneRouting, saveSceneRouting, evaluateRoute, getAvailableScenes, type ModelConfig, type TestResult, type EmailConfig, type PersonalEmail, type FallbackChainItem, type SceneRoutingItem, type SceneDefinition, type SceneCategory } from '@/api/config';
import { getPlatformConfig, savePlatformConfig, getUserBindings, createUserBinding, deleteUserBinding, startWechatQr, checkWechatQrStatus, bindWechatQr } from '@/api/platform';

const authStore = useAuthStore();
const isSuperAdmin = computed(() => authStore.userRole === 'super_admin');
// 与 :664 的 tab 过滤保持一致：走 hasPerm（super_admin 兜底），
// 避免 localStorage.userPermissions 过期时连超管都看不到邮箱配置按钮
const hasSystemConfig = computed(() => authStore.hasPerm('system.config'));

// ── Tab 状态 ──
const allTabs = [
  { key: 'model', label: '模型配置', icon: '🤖', perm: 'system.config' },
  { key: 'channel', label: '渠道绑定', icon: '🔗', perm: null },
  { key: 'email', label: '邮箱配置', icon: '📧', perm: 'system.config' },
];
const tabs = computed(() => {
  return allTabs.filter(t => !t.perm || authStore.hasPerm(t.perm));
});
const activeTab = ref(tabs.value[0]?.key || 'model');

// ── 模型配置（按分类：聊天 / Embedding / Rerank） ──
const stats = reactive({ sessions: '-', skills: '-', status: '-' });
const configs = ref<ModelConfig[]>([]);
const envConfigured = ref(false);
const modelCategories: Record<string, string> = { chat: '聊天模型', embedding: 'Embedding 模型', rerank: 'Rerank 模型' };
const modelCategory = ref<'chat' | 'embedding' | 'rerank'>('chat');
const filteredConfigs = computed(() =>
  configs.value.filter(c => (c.category || 'chat') === modelCategory.value)
);
function switchModelCategory(key: string) {
  modelCategory.value = key as 'chat' | 'embedding' | 'rerank';
  editingId.value = null;
  testResult.value = null;
  form.category = key;
}
const creating = ref(false);
const form = reactive({ config_name: '', config_type: 'URL', api_url: '', api_key: '', model_name: '', provider: '', reasoning_effort: '', category: 'chat', is_multimodal: 0, dimension: 0, send_dimensions: 0 });
const canCreate = computed(() => form.api_url.trim() && form.model_name.trim() && !creating.value);
const editingId = ref<number | null>(null);
const editForm = reactive({ config_name: '', config_type: 'URL', api_url: '', api_key: '', model_name: '', provider: '', reasoning_effort: '', category: 'chat', is_multimodal: 0, dimension: 0, send_dimensions: 0 });
const testingId = ref<number | null>(null);
const testResult = ref<TestResult | null>(null);

function startEdit(cfg: ModelConfig) {
  editingId.value = cfg.id;
  editForm.config_name = cfg.config_name;
  editForm.config_type = cfg.config_type;
  editForm.api_url = cfg.api_url;
  editForm.api_key = '';
  editForm.model_name = cfg.model_name;
  editForm.provider = cfg.provider || '';
  editForm.reasoning_effort = (cfg as any).reasoning_effort || '';
  editForm.category = (cfg as any).category || 'chat';
  editForm.is_multimodal = Number((cfg as any).is_multimodal || 0);
  editForm.dimension = Number((cfg as any).dimension || 0);
  editForm.send_dimensions = Number((cfg as any).send_dimensions || 0);
  testResult.value = null;
}

function effortLabel(effort: string): string {
  const labels: Record<string, string> = { low: 'Low', medium: 'Med', high: 'High', max: 'Max', ultra: 'Ultra' };
  return labels[effort] || effort;
}
function cancelEdit() { editingId.value = null; }

async function saveEdit(id: number) {
  if (!editForm.api_url.trim() || !editForm.model_name.trim()) return;
  try {
    await updateModelConfig(id, { ...editForm });
    editingId.value = null;
    await loadModelConfigs();
    alert(`✅ 模型配置「${editForm.config_name}」已更新`);
  } catch (e: any) { alert(e?.response?.data?.detail || '更新失败'); }
}async function testConn(id: number) {
  testingId.value = id; testResult.value = null;
  try { testResult.value = await testModelConfig(id); }
  catch (e: any) { testResult.value = { ok: false, message: e?.response?.data?.detail || '测试请求失败' }; }
  finally { testingId.value = null; }
}
async function loadModelConfigs() {
  try {
    const data = await getModelConfigs();
    configs.value = data.configs || [];
    envConfigured.value = !!data.env_configured;
  } catch (e: any) { console.error('加载模型配置失败:', e); }
}
async function create() {
  if (!canCreate.value) return; creating.value = true;
  try {
    await createModelConfig({ config_name: form.config_name, config_type: form.config_type, api_url: form.api_url, api_key: form.api_key, model_name: form.model_name, provider: form.provider, reasoning_effort: form.reasoning_effort, category: form.category, is_multimodal: form.is_multimodal, dimension: form.dimension, send_dimensions: form.send_dimensions });
    form.config_name = ''; form.api_url = ''; form.api_key = ''; form.model_name = ''; form.provider = ''; form.reasoning_effort = ''; form.is_multimodal = 0; form.dimension = 0; form.send_dimensions = 0;
    await loadModelConfigs();
    alert(`✅ ${modelCategories[modelCategory.value]}配置「${form.config_name}」已保存`);
  } catch (e: any) { alert(e?.response?.data?.detail || '保存失败'); }
  finally { creating.value = false; }
}
async function setActive(id: number) {
  try {
    await setActiveModelConfig(id);
    await loadModelConfigs();
    const cfg = configs.value.find(c => c.id === id);
    alert(`✅ 已切换为当前模型：${cfg?.config_name || id}`);
  }
  catch (e: any) { alert(e?.response?.data?.detail || '设置失败'); }
}
async function remove(cfg: ModelConfig) {
  if (!confirm(`确定删除模型配置「${cfg.config_name}」吗？`)) return;
  try {
    await deleteModelConfig(cfg.id);
    await loadModelConfigs();
    alert(`✅ 模型配置「${cfg.config_name}」已删除`);
  }
  catch (e: any) { alert(e?.response?.data?.detail || '删除失败'); }
}
async function loadStats() {
  try { const res = await fetch('/health'); if (res.ok) stats.status = '运行中'; } catch { stats.status = '离线'; }
  try { const res = await fetch('/api/skills'); if (res.ok) { const skills = await res.json(); stats.skills = skills.length; } } catch { stats.skills = '?'; }
  try { const token = localStorage.getItem('authToken') || ''; const res = await fetch('/api/history', { headers: { 'Authorization': `Bearer ${token}` } }); if (res.ok) { const data = await res.json(); stats.sessions = (Array.isArray(data?.sessions) ? data.sessions.length : 0) || 0; } } catch { stats.sessions = '?'; }
}

// ── 微信配置 ──
const wechatConfig = reactive({ token: '', account_id: '', base_url: '', bot_user_id: '' });
const wechatConfigured = ref(false);

async function loadWechatConfig() {
  try {
    const data = await getPlatformConfig('wechat');
    if (data.configured) {
      wechatConfig.account_id = data.raw_config_json?.account_id || '';
      wechatConfig.bot_user_id = data.raw_config_json?.bot_user_id || '';
      wechatConfigured.value = true;
    } else {
      wechatConfigured.value = false;
    }
  } catch (e) { console.error('加载微信配置失败:', e); }
}

// ── 手动绑定 ──
const showManualBind = ref(false);
const savingManual = ref(false);
const manualBindOk = ref(false);
const manualBindMsg = ref('');
const manualBindForm = reactive({ token: '', account_id: '', base_url: '', wxid: '', nickname: '' });

async function submitManualBind() {
  if (!manualBindForm.token.trim() || !manualBindForm.account_id.trim()) return;
  savingManual.value = true; manualBindMsg.value = ''; manualBindOk.value = false;
  try {
    if (isSuperAdmin.value) {
      await savePlatformConfig('wechat', {
        config_json: {
          token: manualBindForm.token.trim(),
          account_id: manualBindForm.account_id.trim(),
          base_url: manualBindForm.base_url.trim() || 'https://ilinkai.weixin.qq.com',
          bot_user_id: manualBindForm.wxid.trim() || manualBindForm.account_id.trim(),
        },
        enabled: true,
      });
    }
    const wxid = manualBindForm.wxid.trim() || manualBindForm.account_id.trim();
    await createUserBinding({
      platform: 'wechat',
      open_id: wxid,
      nickname: manualBindForm.nickname.trim() || `微信Bot_${manualBindForm.account_id.trim().slice(0, 8)}`,
    });
    manualBindOk.value = true;
    manualBindMsg.value = '✅ 绑定成功';
    showManualBind.value = false;
    manualBindForm.token = ''; manualBindForm.account_id = ''; manualBindForm.wxid = ''; manualBindForm.nickname = '';
    await loadWechatConfig();
    await loadWechatBinding();
  } catch (e: any) {
    manualBindOk.value = false;
    manualBindMsg.value = '❌ ' + (e?.response?.data?.detail || '保存失败');
  } finally { savingManual.value = false; }
}

// ── 微信扫码绑定（QR） ──
const qrSessionId = ref('');
const qrImage = ref('');
const qrStatus = ref('');
const qrLoading = ref(false);
let qrPollTimer: ReturnType<typeof setInterval> | null = null;

async function startQrBind() {
  qrLoading.value = true;
  try {
    const result = await startWechatQr();
    qrSessionId.value = result.session_id;
    qrImage.value = result.qr_image;
    qrStatus.value = 'wait';
    qrPollTimer = setInterval(pollQrStatus, 2000);
  } catch (e: any) {
    alert(e?.response?.data?.detail || '生成二维码失败');
    cancelQr();
  } finally { qrLoading.value = false; }
}

async function pollQrStatus() {
  if (!qrSessionId.value) return;
  try {
    const result = await checkWechatQrStatus(qrSessionId.value);
    qrStatus.value = result.status;
    if (result.status === 'wait_refreshed' && result.qr_image) {
      qrImage.value = result.qr_image;
      qrStatus.value = 'wait';
    } else if (result.status === 'confirmed') {
      clearInterval(qrPollTimer!);
      qrPollTimer = null;
      try {
        await bindWechatQr(qrSessionId.value);
        await loadWechatConfig();
        await loadWechatBinding();
        cancelQr();
      } catch (e: any) { alert(e?.response?.data?.detail || '绑定失败'); cancelQr(); }
    } else if (result.status === 'bound') {
      // 已经绑定过，直接刷新状态
      clearInterval(qrPollTimer!);
      qrPollTimer = null;
      await loadWechatConfig();
      await loadWechatBinding();
      cancelQr();
    } else if (result.status === 'expired') {
      clearInterval(qrPollTimer!);
      qrPollTimer = null;
    }
  } catch (e) { /* 轮询静默失败 */ }
}

function cancelQr() {
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
  qrSessionId.value = '';
  qrImage.value = '';
  qrStatus.value = '';
}

// ── 微信个人绑定 ──
const wechatBinding = ref<any>(null);

async function loadWechatBinding() {
  try {
    const data = await getUserBindings();
    wechatBinding.value = data.bindings.find((b: any) => b.platform === 'wechat') || null;
  } catch (e) { console.error('加载微信绑定失败:', e); }
}

async function unbindWechat() {
  if (!wechatBinding.value || !confirm('确定解绑微信账号吗？')) return;
  try {
    await deleteUserBinding(wechatBinding.value.id);
    wechatBinding.value = null;
    alert('✅ 微信账号已解绑');
  } catch (e: any) { alert(e?.response?.data?.detail || '解绑失败'); }
}

// ── 邮箱多配置 ──
const emailConfigs = ref<EmailConfig[]>([]);
const emailTestingId = ref<number | null>(null);
const emailTestResult = ref('');
const emailForm = reactive({ config_name: '', host: 'smtp.qq.com', port: '587', sender_email: '', sender_name: 'AgentForge', password: '' });
const canAddEmail = computed(() => emailForm.host.trim() && emailForm.sender_email.trim());

async function loadEmailConfigs() {
  try {
    const data = await getEmailConfigs();
    emailConfigs.value = data.configs || [];
  } catch (e) { console.error('加载邮箱配置失败:', e); }
}

async function addEmailConfig() {
  if (!canAddEmail.value) return;
  try {
    await createEmailConfig({ ...emailForm });
    const name = emailForm.config_name || emailForm.sender_email;
    emailForm.config_name = ''; emailForm.host = 'smtp.qq.com'; emailForm.port = '587';
    emailForm.sender_email = ''; emailForm.sender_name = 'AgentForge'; emailForm.password = '';
    await loadEmailConfigs();
    alert(`✅ 邮箱配置「${name}」已新增`);
  } catch (e: any) { alert(e?.response?.data?.detail || '新增失败'); }
}

async function setEmailActive(id: number) {
  try {
    await setActiveEmailConfig(id);
    await loadEmailConfigs();
    alert('✅ 已切换为当前邮箱配置');
  }
  catch (e: any) { alert(e?.response?.data?.detail || '切换失败'); }
}

async function deleteEmail(id: number) {
  if (!confirm('确定删除此邮箱配置吗？')) return;
  try {
    await deleteEmailConfig(id);
    await loadEmailConfigs();
    alert('✅ 邮箱配置已删除');
  }
  catch (e: any) { alert(e?.response?.data?.detail || '删除失败'); }
}

async function testEmail(id: number) {
  emailTestingId.value = id; emailTestResult.value = '';
  try {
    const result = await testEmailConfig(id);
    emailTestResult.value = result.ok ? (result.message || '✅ 测试通过') : ('❌ ' + result.message);
  } catch (e: any) {
    emailTestResult.value = '❌ ' + (e?.response?.data?.detail || e?.message || '测试失败');
  } finally { emailTestingId.value = null; }
}

// ── 个人邮箱（多邮箱+切换） ──
const personalEmails = ref<PersonalEmail[]>([]);
const newPersonalEmail = ref('');
const addingPersonalEmail = ref(false);
const personalEmailMsg = ref('');
const personalEmailOk = ref(false);

async function loadPersonalEmails() {
  try {
    const data = await getPersonalEmails();
    personalEmails.value = data.emails || [];
  } catch (e) { console.error('加载个人邮箱失败:', e); }
}

async function addPersonal() {
  if (!newPersonalEmail.value.trim().includes('@')) return;
  addingPersonalEmail.value = true; personalEmailMsg.value = '';
  try {
    const result = await apiAddPersonalEmail(newPersonalEmail.value.trim());
    if (result.duplicate) personalEmailMsg.value = '⚠ 已存在，已设为当前';
    else personalEmailMsg.value = '✅ 已添加';
    personalEmailOk.value = true;
    newPersonalEmail.value = '';
    await loadPersonalEmails();
  } catch (e: any) {
    personalEmailMsg.value = '❌ ' + (e?.response?.data?.detail || '添加失败');
    personalEmailOk.value = false;
  } finally { addingPersonalEmail.value = false; }
}

async function setPersonalEmailActive(id: number) {
  try {
    await setActivePersonalEmail(id);
    await loadPersonalEmails();
    alert('✅ 已切换为当前邮箱');
  }
  catch (e: any) { alert(e?.response?.data?.detail || '切换失败'); }
}

async function deletePersonal(id: number) {
  if (!confirm('确定删除此邮箱吗？')) return;
  try {
    await deletePersonalEmail(id);
    await loadPersonalEmails();
    alert('✅ 邮箱已删除');
  }
  catch (e: any) { alert(e?.response?.data?.detail || '删除失败'); }
}

// ── 降级链配置 ──
const showFallbackChain = ref(false)
const fallbackChainItems = ref<FallbackChainItem[]>([])
const fallbackChainSaving = ref(false)
const showSceneRouting = ref(false)
const sceneRouting = ref<Record<string, SceneRoutingItem>>({})
const sceneRoutingSaving = ref(false)
const newSceneKey = ref('')
const newSceneModelId = ref<number>(0)
const routeEvalResult = ref<string>('')
const routeEvalScene = ref('')

// ── 编辑场景路由 ──
const editingSceneKey = ref<string | null>(null)
const editingModelId = ref<number>(0)

function startEditScene(key: string) {
  editingSceneKey.value = key
  editingModelId.value = sceneRouting.value[key]?.model_config_id || 0
}
function saveEditScene() {
  if (!editingSceneKey.value || !editingModelId.value) return
  const cfg = configs.value.find(c => c.id === editingModelId.value)
  sceneRouting.value[editingSceneKey.value] = {
    model_config_id: editingModelId.value,
    config_name: cfg?.config_name || '',
    model_name: cfg?.model_name || '',
  }
  editingSceneKey.value = null
}
function cancelEditScene() {
  editingSceneKey.value = null
}
function getModelName(id: number): string {
  const item = sceneRouting.value && Object.values(sceneRouting.value).find((v: any) => v.model_config_id === id) as any
  if (item?.config_name && item?.model_name) {
    return formatModelLabel({ config_name: item.config_name, model_name: item.model_name })
  }
  if (item?.config_name) return item.config_name
  if (item?.model_name) return item.model_name
  const cfg = configs.value.find(c => c.id === id)
  if (cfg) return formatModelLabel({ config_name: cfg.config_name, model_name: cfg.model_name })
  return `#${id}`
}

// ── 按分类分组已配置的场景路由 ──
const groupedSceneRouting = computed(() => {
  const groups: Record<string, { name: string; icon: string; order: number; items: { key: string; model_config_id: number }[] }> = {}
  for (const [key, item] of Object.entries(sceneRouting.value)) {
    const scene = availableScenes.value.find(s => s.key === key)
    const cat = scene?.category || 'custom'
    const catDef = sceneCategories.value[cat] || { name: cat, icon: '📌', order: 99 }
    if (!groups[cat]) {
      groups[cat] = { name: catDef.name, icon: catDef.icon, order: catDef.order, items: [] }
    }
    groups[cat].items.push({ key, model_config_id: (item as any).model_config_id })
  }
  return Object.entries(groups).sort(([, a], [, b]) => a.order - b.order)
})

// ── 场景注册表（供下拉选择）──
const availableScenes = ref<SceneDefinition[]>([])
const sceneCategories = ref<Record<string, SceneCategory>>({})

// 按分类分组的场景（供下拉使用）
const groupedScenes = computed(() => {
  const groups: Record<string, { category: SceneCategory; scenes: SceneDefinition[] }> = {}
  for (const scene of availableScenes.value) {
    if (!groups[scene.category]) {
      groups[scene.category] = {
        category: sceneCategories.value[scene.category] || { name: scene.category, icon: '📌', order: 99 },
        scenes: [],
      }
    }
    groups[scene.category].scenes.push(scene)
  }
  // 按 order 排序
  return Object.entries(groups).sort(([, a], [, b]) => a.category.order - b.category.order)
})

// 获取选中场景的描述
const selectedSceneDescription = computed(() => {
  if (!newSceneKey.value) return ''
  const scene = availableScenes.value.find(s => s.key === newSceneKey.value)
  return scene ? `${scene.description}（推荐：${scene.recommended_model}）` : ''
})

const chatConfigs = computed(() => configs.value.filter(c => (c.category || 'chat') === 'chat' && c.enabled))
const availableForChain = computed(() =>
  chatConfigs.value.filter(c => !fallbackChainItems.value.some(f => f.id === c.id))
)

function addToChain(cfg: ModelConfig) {
  fallbackChainItems.value.push({ ...cfg } as FallbackChainItem)
}
function removeFromChain(index: number) {
  fallbackChainItems.value.splice(index, 1)
}
function moveChainItem(from: number, to: number) {
  if (to < 0 || to >= fallbackChainItems.value.length) return
  const [item] = fallbackChainItems.value.splice(from, 1)
  fallbackChainItems.value.splice(to, 0, item)
}

async function loadFallbackChain() {
  try {
    const data = await getFallbackChain()
    fallbackChainItems.value = data.fallback_chain || []
  } catch (e) { console.error('加载降级链失败:', e) }
}

async function saveChain() {
  fallbackChainSaving.value = true
  try {
    await saveFallbackChain(fallbackChainItems.value.map(i => i.id))
    alert('✅ 降级链已保存')
  } catch (e: any) { alert('❌ ' + (e?.response?.data?.detail || '保存失败')) }
  finally { fallbackChainSaving.value = false }
}

async function loadSceneRouting() {
  try {
    const data = await getSceneRouting()
    sceneRouting.value = data.routing || {}
  } catch (e) { console.error('加载场景路由失败:', e) }
}

async function loadAvailableScenes() {
  try {
    const data = await getAvailableScenes()
    availableScenes.value = data.scenes || []
    sceneCategories.value = data.categories || {}
  } catch (e) { console.error('加载场景列表失败:', e) }
}

async function saveSceneRoute() {
  sceneRoutingSaving.value = true
  try {
    const payload: Record<string, number> = {}
    for (const [k, v] of Object.entries(sceneRouting.value)) {
      payload[k] = v.model_config_id
    }
    await saveSceneRouting(payload)
    alert('✅ 场景路由已保存')
  } catch (e: any) { alert('❌ ' + (e?.response?.data?.detail || '保存失败')) }
  finally { sceneRoutingSaving.value = false }
}

function addSceneRoute() {
  if (!newSceneKey.value.trim() || !newSceneModelId.value) return
  const cfg = configs.value.find(c => c.id === newSceneModelId.value)
  sceneRouting.value[newSceneKey.value.trim()] = {
    model_config_id: newSceneModelId.value,
    config_name: cfg?.config_name || '',
    model_name: cfg?.model_name || '',
  }
  newSceneKey.value = ''
  newSceneModelId.value = 0
}

function removeSceneRoute(key: string) {
  delete sceneRouting.value[key]
}

function getSceneName(key: string): string {
  const scene = availableScenes.value.find(s => s.key === key)
  return scene?.name || key
}

function getSceneRecommendation(key: string): string {
  const scene = availableScenes.value.find(s => s.key === key)
  return scene?.recommended_model ? `(${scene.recommended_model})` : ''
}

function getSceneDescription(key: string): string {
  const scene = availableScenes.value.find(s => s.key === key)
  return scene?.description || ''
}

function formatModelLabel(cfg: { config_name: string; model_name: string }): string {
  if (!cfg.config_name || cfg.config_name === cfg.model_name) return cfg.model_name
  return `${cfg.config_name} (${cfg.model_name})`
}

async function doEvaluateRoute() {
  try {
    const data = await evaluateRoute(routeEvalScene.value || undefined)
    const model = data.selected_model
    routeEvalResult.value = model
      ? `场景 "${data.scene || '默认'}" → ${model.config_name} (${model.model_name})\n路由路径: ${data.route_path}`
      : `场景 "${data.scene || '默认'}" → 无可用模型`
  } catch (e: any) {
    routeEvalResult.value = '❌ ' + (e?.response?.data?.detail || '评测失败')
  }
}

function circuitLabel(state?: number): string {
  if (state === 1) return '🔴 熔断'
  if (state === 2) return '🟡 半开'
  return '🟢 正常'
}

function formatCost(val?: number): string {
  if (!val && val !== 0) return '-'
  return `$${val.toFixed(4)}`
}

function formatContext(val?: number): string {
  if (!val) return '-'
  if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`
  if (val >= 1000) return `${(val / 1000).toFixed(0)}K`
  return String(val)
}

// ── 拖拽状态 ──
const dragIndex = ref<number | null>(null)

function onDragStart(index: number) {
  dragIndex.value = index
}
function onDragOver(e: DragEvent, index: number) {
  e.preventDefault()
  if (dragIndex.value === null || dragIndex.value === index) return
}
function onDrop(e: DragEvent, index: number) {
  e.preventDefault()
  if (dragIndex.value !== null && dragIndex.value !== index) {
    moveChainItem(dragIndex.value, index)
  }
  dragIndex.value = null
}
function onDragEnd() {
  dragIndex.value = null
}

onMounted(() => {
  loadStats();
  loadModelConfigs();
  loadFallbackChain();
  loadSceneRouting();
  loadAvailableScenes();
  loadWechatConfig();
  loadWechatBinding();
  loadEmailConfigs();
  loadPersonalEmails();
});

onUnmounted(() => {
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
});
</script>

<style scoped>
.page-header { margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
.page-desc { font-size: 13px; color: var(--text-tertiary); }

/* ── Tab 导航 ── */
.config-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: 4px;
}
.tab-btn {
  flex: 1;
  padding: 10px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.tab-btn.active { background: var(--bg-card); color: var(--brand); font-weight: 600; box-shadow: var(--shadow-sm); }
.tab-icon { font-size: 16px; }
.tab-content { animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* ── 左右分栏 ── */
.split-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

/* ── 模型分类 Tab ── */
.model-cat-tabs { display: flex; gap: 6px; padding: 10px 14px 0; border-bottom: 1px solid var(--border-primary); }
.model-cat-tab {
  background: none; border: none; cursor: pointer;
  padding: 7px 14px; font-size: 13px; color: var(--text-secondary);
  border-bottom: 2px solid transparent; transition: var(--transition);
  display: inline-flex; align-items: center; gap: 6px;
}
.model-cat-tab:hover { color: var(--text-primary); }
.model-cat-tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.model-cat-count {
  font-size: 11px; background: var(--bg-hover); color: var(--text-tertiary);
  border-radius: 10px; padding: 0 7px; line-height: 16px;
}
.model-cat-tab.active .model-cat-count { background: var(--brand-light); color: var(--brand); }

/* ── 紧凑配置列表 ── */
.config-mini-list { display: flex; flex-direction: column; gap: 6px; }
.mini-item {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 10px 12px; border-radius: var(--radius-md);
  background: var(--bg-secondary); transition: background 0.15s;
}
.mini-item.active { background: var(--bg-card); border: 1px solid var(--brand-light, #e0e7ff); }
.mini-main { flex: 1; min-width: 0; }
.mini-name { font-size: 13px; font-weight: 600; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; }
.mini-meta { font-size: 11px; color: var(--text-tertiary); word-break: break-all; }
.mini-actions { display: flex; gap: 4px; flex-shrink: 0; margin-left: 8px; }
.mini-edit { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.mini-edit-actions { display: flex; gap: 6px; }

/* ── 渠道绑定 ── */
.platform-admin-section {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  border: 1px dashed var(--border-secondary);
}
.subsection-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}
.binding-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-primary);
}
.binding-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.binding-icon { font-size: 28px; }
.binding-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.binding-id { font-size: 12px; color: var(--text-tertiary); font-family: monospace; }
.binding-form {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  text-align: center;
}

.manual-bind-form {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px dashed var(--border-secondary);
  margin-bottom: 16px;
}

/* ── 扫码绑定卡片 ── */
.wechat-bind-methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.bind-method-card {
  padding: 20px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-primary);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.bind-method-card:hover { border-color: var(--brand); box-shadow: var(--shadow-sm); }
.bind-method-icon { font-size: 32px; }
.bind-method-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.bind-method-desc { font-size: 12px; color: var(--text-tertiary); }

/* ── QR 扫码区域 ── */
.qr-scan-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  margin-bottom: 16px;
}
.qr-container {
  width: 200px;
  height: 200px;
  background: #fff;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--border-primary);
  overflow: hidden;
}
.qr-image { width: 100%; height: 100%; object-fit: contain; }
.qr-loading { font-size: 14px; color: var(--text-tertiary); }
.qr-status-text { font-size: 14px; color: var(--text-secondary); text-align: center; }

.binding-empty {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  text-align: center;
}

/* ── 禁用卡片 ── */
.card-disabled { opacity: 0.55; pointer-events: none; }
.muted { color: var(--text-placeholder) !important; }
.status-text { font-size: 13px; margin-left: 12px; color: var(--text-tertiary); }
.status-text.ok { color: var(--success); }

.smtp-test-result { margin-top: 10px; padding: 10px 14px; border-radius: var(--radius-md); font-size: 13px; }
.smtp-test-result.ok { background: #e8f5e9; color: #2e7d32; }
.smtp-test-result.error { background: #fce4ec; color: #c62828; }

/* ── 复用原样式 ── */
.config-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.section-tip { font-size: 13px; color: var(--text-tertiary); margin-bottom: 16px; line-height: 1.6; }
.empty-state { text-align: center; padding: 24px 16px; color: var(--text-tertiary); font-size: 13px; background: var(--bg-secondary); border-radius: var(--radius-md); margin-bottom: 16px; }
.model-config-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }
.model-config-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border: 1px solid var(--border-primary); border-radius: var(--radius-lg); background: var(--bg-card); transition: border-color 0.2s, box-shadow 0.2s; }
.model-config-item:hover { border-color: var(--border-secondary); box-shadow: var(--shadow-sm); }
.model-config-item.active { border-color: var(--brand); background: var(--brand-light); }
.mci-main { min-width: 0; flex: 1; }
.mci-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.mci-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.mci-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; margin-bottom: 4px; }
.mci-model { color: var(--brand); font-weight: 500; }
.mci-url { color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; }
.mci-sub { display: flex; gap: 16px; font-size: 12px; color: var(--text-tertiary); }
.mci-actions { display: flex; gap: 8px; flex-shrink: 0; }
.model-config-form { padding: 18px; background: var(--bg-secondary); border-radius: var(--radius-lg); border: 1px dashed var(--border-secondary); }
.form-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }
.test-result { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: var(--radius-md); font-size: 13px; margin-top: 4px; }
.test-result.ok { background: #e8f5e9; color: #2e7d32; }
.test-result.fail { background: #fce4ec; color: #c62828; }
.config-help { font-size: 13px; color: var(--text-tertiary); line-height: 1.8; }
.config-help p { margin-bottom: 8px; }
.help-code { background: var(--bg-secondary); border-radius: var(--radius-md); padding: 12px; margin-top: 8px; overflow-x: auto; }
.help-code pre { font-size: 12px; color: var(--text-primary); font-family: 'SF Mono', 'Fira Code', monospace; }
.config-tips { margin-top: 12px; font-size: 13px; color: var(--text-tertiary); }
.input-hint { font-size: 11px; color: var(--text-tertiary); margin: 4px 0 0; line-height: 1.5; }
.input-hint code { background: var(--bg-secondary); padding: 1px 5px; border-radius: 3px; font-size: 10px; }
.stat-grid { display: flex; gap: 12px; }
.stat-card { flex: 1; display: flex; align-items: center; gap: 10px; padding: 14px; background: var(--bg-secondary); border-radius: var(--radius-md); }
.stat-icon { font-size: 24px; }
.stat-value { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-tertiary); }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 500; }
.badge-info { background: #e3f2fd; color: #1565c0; }
.badge-success { background: #e8f5e9; color: #2e7d32; }
.badge-muted { background: var(--bg-secondary); color: var(--text-placeholder); }
.badge-multimodal { background: #fff3e0; color: #e65100; }
.badge-effort { background: #e8eaf6; color: #3f51b5; }

/* ── 模型能力标签 ── */
.mini-capabilities { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.cap-tag {
  font-size: 11px; padding: 1px 7px; border-radius: 8px;
  background: var(--bg-hover, #f3f4f6); color: var(--text-secondary);
  white-space: nowrap;
}
.cap-circuit-open { background: #fce4ec; color: #c62828; }
.cap-circuit-half { background: #fff8e1; color: #f57f17; }

/* ── 折叠卡片头 ── */
.collapsible-header { cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; }
.collapsible-header:hover { color: var(--brand); }

/* ── 降级链列表 ── */
.chain-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.chain-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: var(--radius-md);
  background: var(--bg-secondary); border: 1px solid var(--border-primary);
  cursor: grab; transition: box-shadow 0.15s, opacity 0.15s;
}
.chain-item:hover { box-shadow: var(--shadow-sm); }
.chain-item:active { cursor: grabbing; }
.chain-dragging { opacity: 0.5; }
.chain-drag-handle { font-size: 18px; color: var(--text-placeholder); cursor: grab; line-height: 1; }
.chain-priority {
  font-size: 12px; font-weight: 700; color: var(--brand);
  min-width: 28px; text-align: center;
}
.chain-info { flex: 1; min-width: 0; }
.chain-name { font-size: 13px; font-weight: 600; }
.chain-meta { font-size: 11px; color: var(--text-tertiary); }
.chain-circuit { font-size: 11px; white-space: nowrap; }
.chain-add-row { margin-top: 8px; }

/* ── 场景路由 ── */
.scene-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
/* ── 场景路由分组 ── */
.scene-grouped {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 12px;
}
.scene-group {
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.scene-group-title {
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-tertiary, var(--bg-secondary));
  border-bottom: 1px solid var(--border-primary);
}
.scene-group-items {
  display: flex;
  flex-direction: column;
}
.scene-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border-primary);
  transition: background 0.15s;
}
.scene-row:last-child { border-bottom: none; }
.scene-row:hover { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.scene-row-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.scene-row-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}
.scene-row-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-tertiary, rgba(0,0,0,0.04));
  padding: 1px 6px;
  border-radius: 4px;
  cursor: help;
}
.scene-row-arrow {
  color: var(--text-placeholder);
  font-size: 12px;
}
.scene-row-model {
  font-size: 13px;
  color: var(--brand);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scene-row-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.scene-edit-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--brand-light, #e0e7ff);
  border-radius: var(--radius-md);
  margin-top: 8px;
}
.scene-edit-label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ── 编辑弹窗 ── */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-box {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  min-width: 360px;
  max-width: 480px;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}
.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover { color: var(--text-primary); }
.modal-body {
  padding: 20px;
}
.modal-field {
  margin-bottom: 16px;
}
.modal-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.modal-scene-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-scene-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-left: 8px;
}
.modal-description {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-top: 8px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-primary);
}
.scene-add-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }

/* ── 路由评测结果 ── */
.route-eval-result {
  margin-top: 8px; padding: 10px 12px;
  background: var(--bg-secondary); border-radius: var(--radius-md);
  font-size: 12px; font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-primary); white-space: pre-wrap;
  border: 1px solid var(--border-primary);
}
</style>
