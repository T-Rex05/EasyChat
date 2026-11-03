<template>
  <div class="graph-page">
    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="search-section">
        <div class="search-box">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="M21 21l-4.35-4.35"></path>
          </svg>
          <input 
            v-model="searchQuery" 
            placeholder="搜索实体名称..." 
            @keyup.enter="searchEntity"
            class="search-input"
          />
        </div>
        <button @click="searchEntity" class="btn-primary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="M21 21l-4.35-4.35"></path>
          </svg>
          搜索
        </button>
        <button @click="resetView" class="btn-secondary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
            <path d="M3 3v5h5"></path>
          </svg>
          重置
        </button>
      </div>
      
      <div class="filter-section">
        <select v-model="selectedEntityType" @change="filterByType" class="type-select">
          <option value="">全部类型</option>
          <option value="person">👤 人物</option>
          <option value="org">🏢 组织</option>
          <option value="location">📍 地点</option>
          <option value="concept">💡 概念</option>
          <option value="event">📅 事件</option>
          <option value="skill">⚙️ 技能</option>
          <option value="project">📁 项目</option>
        </select>
        
        <select v-model="selectedRelationType" @change="filterByRelation" class="relation-select">
          <option value="">全部关系</option>
          <option value="knows">认识</option>
          <option value="works_at">工作于</option>
          <option value="founded">创立</option>
          <option value="uses">使用</option>
          <option value="prefers">偏好</option>
          <option value="related_to">相关</option>
        </select>
      </div>
    </div>
    
    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 图谱可视化区域 -->
      <div class="graph-container" ref="graphContainer">
        <!-- 服务不可用 -->
        <div v-if="!graphAvailable" class="unavailable-message">
          <div class="icon">📊</div>
          <h3>知识图谱服务不可用</h3>
          <p>请检查 Neo4j 连接配置</p>
        </div>
        
        <!-- 加载中 -->
        <div v-else-if="loading" class="loading-overlay">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>
        
        <!-- 图谱容器 - 已渲染图谱时显示 -->
        <div 
          v-else-if="graphRendered"
          ref="networkContainer" 
          class="network-container"
        ></div>
        
        <!-- 空状态引导 - 未渲染图谱时显示 -->
        <div v-else class="empty-state">
          <div class="empty-content">
            <div class="empty-icon">🕸️</div>
            <h3>知识图谱</h3>
            <p>探索实体之间的关系网络</p>
            <p v-if="stats.entityCount > 0" class="entity-count-hint">共 {{ stats.entityCount }} 个实体</p>
            <div class="empty-actions">
              <button @click="loadGraphWithLimit(stats.entityCount || 9999)" class="load-btn primary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polygon points="10 8 16 12 10 16 10 8"></polygon>
                </svg>
                加载全部图谱
              </button>
            </div>
            <div class="quick-tips">
              <div class="tip">
                <span class="tip-icon">💡</span>
                <span>搜索实体名称快速定位</span>
              </div>
              <div class="tip">
                <span class="tip-icon">🖱️</span>
                <span>双击节点展开关联子图</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 右侧面板：Tab 切换 -->
      <div class="right-panel">
        <!-- Tab 按钮 -->
        <div class="tab-buttons">
          <button :class="{ active: rightPanelTab === 'stats' }" @click="rightPanelTab = 'stats'">📊 统计</button>
          <button :class="{ active: rightPanelTab === 'entities' }" @click="rightPanelTab = 'entities'">📋 实体</button>
          <button :class="{ active: rightPanelTab === 'history' }" @click="switchToHistoryTab">📜 历史</button>
        </div>
        
        <!-- 统计 Tab -->
        <div v-show="rightPanelTab === 'stats'" class="tab-content">
          <!-- 加载更多按钮 -->
          <div v-if="graphRendered" class="load-more-section">
            <button @click="forceRefreshLayout" class="load-more-btn" :disabled="loading">
              <span v-if="loading" class="spinner-small"></span>
              <span v-else>🔄 刷新布局</span>
            </button>
            <span class="current-count">图谱中: {{ displayNodeCount }} 个节点（布局已缓存）</span>
          </div>
          
          <div class="stats-card">
            <h4>📊 统计信息</h4>
            <div class="stats-grid">
              <div class="stat-item">
                <span class="stat-value">{{ displayNodeCount }}</span>
                <span class="stat-label">{{ hasFilter ? '可见节点' : '图谱节点' }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ displayEdgeCount }}</span>
                <span class="stat-label">{{ hasFilter ? '可见关系' : '图谱关系' }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ stats.memoryCount }}</span>
                <span class="stat-label">记忆</span>
              </div>
            </div>
          </div>
          
          <!-- 图例 -->
          <div class="legend-card">
            <h4>🎨 实体类型</h4>
            <div class="legend-list">
              <div class="legend-item" v-for="type in entityTypes" :key="type.value">
                <span class="legend-color" :style="{ backgroundColor: type.color }"></span>
                <span class="legend-label">{{ type.label }}</span>
              </div>
            </div>
          </div>
          
          <!-- 操作提示 - 简化版 -->
          <div class="tips-card compact">
            <h4>💡 快捷操作</h4>
            <div class="tips-grid">
              <span>🖱️ 拖拽移动</span>
              <span>🔍 滚轮缩放</span>
              <span>👆 点击详情</span>
              <span>⚡ 双击展开</span>
            </div>
          </div>
        </div>
        
        <!-- 实体列表 Tab -->
        <div v-show="rightPanelTab === 'entities'" class="tab-content entity-tab">
          <input 
            v-model="entityListSearch" 
            type="text" 
            placeholder="搜索实体..." 
            class="entity-search"
          />
          <div class="entity-list">
            <div 
              v-for="entity in paginatedEntities" 
              :key="entity.id" 
              class="entity-list-item"
              @click="focusAndSelectEntity(entity)"
            >
              <span class="entity-name">{{ entity.label }}</span>
              <span class="entity-type-badge" :style="{ backgroundColor: getTypeColor(entity.group) }">
                {{ getTypeLabel(entity.group) }}
              </span>
            </div>
            <div v-if="filteredEntityList.length === 0" class="empty-list">未找到匹配实体</div>
          </div>
          <div v-if="filteredEntityList.length > entityPageSize" class="pagination">
            <button @click="entityPage--" :disabled="entityPage <= 1">上一页</button>
            <span>{{ entityPage }} / {{ totalEntityPages }}</span>
            <button @click="entityPage++" :disabled="entityPage >= totalEntityPages">下一页</button>
          </div>
        </div>

        <!-- 操作历史 Tab -->
        <div v-show="rightPanelTab === 'history'" class="tab-content history-tab">
          <div class="history-header">
            <select v-model="historyFilter" @change="loadChangeLogs" class="history-filter">
              <option value="">全部操作</option>
              <option value="entity_created">创建实体</option>
              <option value="entity_updated">编辑实体</option>
              <option value="entity_deleted">删除实体</option>
              <option value="entity_restored">恢复实体</option>
              <option value="relation_created">创建关系</option>
              <option value="relation_updated">编辑关系</option>
              <option value="relation_deleted">删除关系</option>
              <option value="relation_flipped">翻转关系</option>
              <option value="rollback">⏪ 回滚</option>
            </select>
            <button @click="loadChangeLogs" class="refresh-btn" title="刷新">🔄</button>
          </div>

          <div v-if="historyLoading" class="history-loading">
            <div class="spinner-small"></div>
            <span>加载中...</span>
          </div>

          <div v-else class="history-list">
            <div
              v-for="log in changeLogs"
              :key="log.id"
              class="history-item"
              :class="'event-' + log.event_type"
            >
              <div class="history-icon">
                <span v-if="log.event_type.includes('entity')">📦</span>
                <span v-else>🔗</span>
              </div>
              <div class="history-content">
                <div class="history-title">
                  <span class="event-label">{{ getEventLabel(log.event_type) }}</span>
                  <span class="entity-name">{{ log.entity_name || log.entity_id }}</span>
                </div>
                <div class="history-time">{{ formatTime(log.created_at) }}</div>
                <div v-if="log.before_json || log.after_json" class="history-actions">
                  <button @click="showLogDetail(log)" class="detail-btn">查看详情</button>
                </div>
              </div>
            </div>
            <div v-if="changeLogs.length === 0" class="empty-history">
              <span>暂无操作记录</span>
            </div>
          </div>

          <div v-if="changeLogs.length > 0" class="history-pagination">
            <button @click="historyPage--" :disabled="historyPage <= 1">上一页</button>
            <span>{{ historyPage }} / {{ totalHistoryPages }}</span>
            <button @click="historyPage++" :disabled="historyPage >= totalHistoryPages">下一页</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 侧边详情面板 -->
    <div class="detail-panel" :class="{ 'show': selectedNode }">
      <div v-if="selectedNode" class="panel-content">
        <div class="panel-header">
          <h3>{{ selectedNode.name }}</h3>
          <span class="entity-type" :class="selectedNode.type">
            {{ getTypeLabel(selectedNode.type) }}
          </span>
          <button v-if="hasGraphManage && !entityEditing" @click="startEditEntity" class="header-action-btn edit-btn" title="编辑实体">✏️</button>
          <button v-if="hasGraphManage && !entityEditing" @click="deleteEntity" class="header-action-btn delete-btn" title="删除实体">🗑️</button>
          <button @click="closePanel" class="close-btn">&times;</button>
        </div>

        <div class="panel-body">
          <!-- 实体信息 / 编辑表单 -->
          <div class="info-section entity-info-section">
            <template v-if="entityEditing">
              <h4>编辑实体</h4>
              <div class="edit-form">
                <label class="edit-label">名称</label>
                <input v-model="entityForm.name" class="edit-input" placeholder="实体名称" />
                <label class="edit-label">描述</label>
                <textarea v-model="entityForm.description" class="edit-textarea" rows="3" placeholder="实体描述"></textarea>
                <label class="edit-label">别名（逗号分隔）</label>
                <input v-model="entityForm.aliasesStr" class="edit-input" placeholder="别名1, 别名2, ..." />
                <div class="edit-actions">
                  <button class="action-btn save" @click="saveEntity">💾 保存</button>
                  <button class="action-btn" @click="cancelEditEntity">取消</button>
                </div>
              </div>
            </template>
            <template v-else>
              <div v-if="selectedNode.description" class="entity-desc">
                <span class="desc-text">{{ selectedNode.description }}</span>
              </div>
              <div v-if="selectedNode.aliases && selectedNode.aliases.length" class="entity-aliases">
                <span class="aliases-label">别名：</span>
                <span v-for="(alias, i) in selectedNode.aliases" :key="i" class="alias-tag">{{ alias }}</span>
              </div>
            </template>
          </div>

          <div class="info-section">
            <h4>关联记忆 <span v-if="relatedMemories.length" class="count-badge">{{ relatedMemories.length }}</span></h4>
            <ul class="memory-list">
              <li
                v-for="mem in relatedMemories"
                :key="mem.id"
                @click="viewMemory(mem.id)"
                :title="mem.content ? '点击查看完整记忆' : ''"
                class="memory-item"
              >
                <span class="memory-text">{{ mem.content || '(无内容)' }}</span>
                <span class="memory-action">→</span>
              </li>
              <li v-if="relatedMemories.length === 0" class="empty">暂无关联记忆</li>
            </ul>
          </div>

          <div class="info-section">
            <div class="section-header">
              <h4>关联关系 <span v-if="relatedRelations.length" class="count-badge">{{ relatedRelations.length }}</span></h4>
              <button v-if="hasGraphManage && !showAddRelation" @click="openAddRelation" class="section-action-btn" title="添加关系">+ 添加</button>
            </div>

            <!-- 添加关系表单 -->
            <div v-if="showAddRelation" class="add-relation-form">
              <label class="edit-label">搜索目标实体</label>
              <div class="add-relation-search-row">
                <input
                  v-model="addRelationForm.targetSearch"
                  @input="searchAddRelationTarget"
                  class="edit-input"
                  placeholder="输入实体名称搜索..."
                />
              </div>
              <div v-if="addRelationCandidates.length" class="add-relation-candidates">
                <div
                  v-for="c in addRelationCandidates"
                  :key="c.id"
                  class="candidate-item"
                  :class="{ selected: addRelationForm.targetId === c.id }"
                  @click="addRelationForm.targetId = c.id; addRelationForm.targetSearch = c.name"
                >
                  <span class="candidate-type-dot" :style="{ backgroundColor: getTypeColor(c.group || c.type) }"></span>
                  <span class="candidate-name">{{ c.name }}</span>
                  <span class="candidate-type">{{ getTypeLabel(c.group || c.type) }}</span>
                </div>
              </div>
              <label class="edit-label">关系类型</label>
              <select v-model="addRelationForm.relationType" class="edit-select">
                <option v-for="opt in relationTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
              <label class="edit-label">描述</label>
              <input v-model="addRelationForm.description" class="edit-input" placeholder="关系描述（可选）" />
              <div class="edit-actions">
                <button class="action-btn save" @click="submitAddRelation" :disabled="!addRelationForm.targetId">✅ 添加</button>
                <button class="action-btn" @click="cancelAddRelation">取消</button>
              </div>
            </div>

            <input
              v-if="!showAddRelation"
              v-model="relatedSearchQuery"
              type="text"
              placeholder="搜索关联实体/关系..."
              class="related-search"
            />
            <div class="relation-list">
              <div
                v-for="rel in filteredRelatedRelations"
                :key="rel.entityId + '-' + rel.relationId"
                class="relation-item"
              >
                <div class="relation-header">
                  <span class="relation-dir" :class="rel.direction">
                    {{ rel.direction === 'out' ? '→' : '←' }}
                  </span>
                  <span class="relation-type-tag">{{ rel.relationType }}</span>
                  <span
                    class="relation-entity-name"
                    :class="rel.entityType"
                    @click="focusEntity(rel.entityName)"
                    :title="`定位: ${rel.entityName}`"
                  >{{ rel.entityName }}</span>
                  <div class="relation-actions" v-if="hasGraphManage">
                    <button
                      v-if="editingRelationId !== rel.relationId"
                      @click="startEditRelation(rel)"
                      class="rel-action-btn"
                      title="编辑描述"
                    >✏️</button>
                    <button
                      v-if="rel.relationId"
                      @click="flipRelation(rel)"
                      class="rel-action-btn"
                      title="翻转方向"
                    >🔄</button>
                    <button
                      v-if="rel.relationId"
                      @click="deleteRelation(rel)"
                      class="rel-action-btn delete"
                      title="删除关系"
                    >🗑️</button>
                  </div>
                </div>
                <!-- 内联编辑关系描述 -->
                <div v-if="editingRelationId === rel.relationId" class="relation-edit">
                  <textarea v-model="editingRelationDesc" class="edit-textarea small" rows="2" placeholder="关系描述"></textarea>
                  <div class="edit-actions">
                    <button class="action-btn save" @click="saveRelation(rel)">💾 保存</button>
                    <button class="action-btn" @click="cancelEditRelation">取消</button>
                  </div>
                </div>
                <div v-else-if="rel.relationDesc" class="relation-desc">{{ rel.relationDesc }}</div>
              </div>
              <div v-if="filteredRelatedRelations.length === 0 && relatedRelations.length > 0" class="empty">未找到匹配关系</div>
              <div v-if="relatedRelations.length === 0" class="empty">暂无关联关系</div>
            </div>
          </div>

          <!-- 间接关系（路径发现） -->
          <div class="info-section">
            <h4>间接关系（路径发现）</h4>
            <div class="path-query">
              <select v-model="pathTargetId" class="path-target-select" :disabled="reachableLoading">
                <option value="">
                  {{ reachableLoading ? '加载可达实体中...' : '选择目标实体...' }}
                </option>
                <option
                  v-for="node in pathTargetCandidates"
                  :key="node.id"
                  :value="node.id"
                >
                  {{ node.label }}
                </option>
              </select>
              <button
                @click="loadPaths"
                :disabled="!pathTargetId || pathsLoading"
                class="path-query-btn"
              >
                {{ pathsLoading ? '查找中...' : '查找路径' }}
              </button>
            </div>
            <div v-if="!reachableLoading && pathTargetCandidates.length === 0" class="empty path-hint">
              无可达的其他实体
            </div>

            <!-- 路径结果 -->
            <div v-if="paths.length > 0" class="path-results">
              <div v-for="(path, idx) in paths" :key="idx" class="path-card">
                <span class="path-hops">{{ path.hops }} 跳</span>
                <div class="path-chain">
                  <template v-for="(node, i) in path.nodes" :key="'n' + i">
                    <span
                      class="path-node"
                      :class="{ 'is-source': i === 0, 'is-target': i === path.nodes.length - 1 }"
                      @click="focusEntity(node.name)"
                      :title="`点击定位: ${node.name}`"
                    >
                      {{ node.name }}
                    </span>
                    <span v-if="i < path.edges.length" class="path-edge">
                      →{{ path.edges[i].type }}→
                    </span>
                  </template>
                </div>
              </div>
            </div>
            <div v-else-if="pathsQueried && !pathsLoading" class="empty">
              未找到间接路径（最大 {{ pathMaxHops }} 跳内）
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志详情弹窗 -->
    <div v-if="showLogDetailModal" class="log-detail-modal" @click.self="showLogDetailModal = false">
      <div class="log-detail-content">
        <div class="log-detail-header">
          <h3>操作详情</h3>
          <button @click="showLogDetailModal = false" class="close-modal-btn">&times;</button>
        </div>
        <div class="log-detail-body" v-if="selectedLog">
          <div class="log-info-row">
            <span class="log-label">操作类型：</span>
            <span class="log-value">{{ getEventLabel(selectedLog.event_type) }}</span>
          </div>
          <div class="log-info-row">
            <span class="log-label">操作时间：</span>
            <span class="log-value">{{ formatTime(selectedLog.created_at) }}</span>
          </div>
          <div class="log-info-row">
            <span class="log-label">实体名称：</span>
            <span class="log-value">{{ selectedLog.entity_name || selectedLog.entity_id || '-' }}</span>
          </div>
          <div class="log-info-row" v-if="selectedLog.entity_type">
            <span class="log-label">实体类型：</span>
            <span class="log-value">{{ selectedLog.entity_type }}</span>
          </div>

          <div v-if="selectedLog.before_json" class="log-diff-section">
            <h4>修改前</h4>
            <pre class="log-json">{{ JSON.stringify(selectedLog.before_json, null, 2) }}</pre>
          </div>
          <div v-if="selectedLog.after_json" class="log-diff-section">
            <h4>修改后</h4>
            <pre class="log-json">{{ JSON.stringify(selectedLog.after_json, null, 2) }}</pre>
          </div>

          <!-- 回滚按钮 -->
          <div v-if="hasGraphManage && selectedLog.event_type !== 'rollback'" class="rollback-section">
            <div class="rollback-hint">
              <span>💡</span>
              <span>回滚将撤销此操作，恢复到修改前的状态</span>
            </div>
            <button
              @click="confirmRollback"
              class="rollback-btn"
              :disabled="rollbackLoading"
            >
              <span v-if="rollbackLoading" class="spinner-small"></span>
              <span v-else>⏪ 回滚到此版本</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 回滚确认弹窗 -->
    <div v-if="showRollbackConfirm" class="log-detail-modal" @click.self="showRollbackConfirm = false">
      <div class="rollback-confirm-content">
        <div class="rollback-confirm-icon">⚠️</div>
        <h3>确认回滚</h3>
        <p class="rollback-confirm-text">
          确定要将 <strong>{{ selectedLog?.entity_name || selectedLog?.entity_id }}</strong>
          恢复到 <strong>{{ formatTime(selectedLog?.created_at) }}</strong> 之前的状态吗？
        </p>
        <p class="rollback-confirm-detail">{{ getRollbackDescription(selectedLog?.event_type) }}</p>
        <div class="rollback-confirm-actions">
          <button @click="showRollbackConfirm = false" class="confirm-cancel-btn">取消</button>
          <button @click="executeRollback" class="confirm-rollback-btn" :disabled="rollbackLoading">
            <span v-if="rollbackLoading" class="spinner-small"></span>
            <span v-else>确认回滚</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import request from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import Graph from 'graphology'
import Sigma from 'sigma'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import noverlap from 'graphology-layout-noverlap'

export default {
  name: 'GraphView',
  setup() {
    // 状态
    const searchQuery = ref('')
    const relatedSearchQuery = ref('')  // 关联实体搜索
    const selectedEntityType = ref('')
    const selectedRelationType = ref('')
    const graphAvailable = ref(true)
    const loading = ref(false)
    const loadingMore = ref(false)  // 加载更多节点时的状态
    const selectedNode = ref(null)
    const relatedMemories = ref([])
    const relatedEntities = ref([])
    const networkContainer = ref(null)
    const graphContainer = ref(null)

    // ── 编辑相关状态 ──
    const authStore = useAuthStore()
    const hasGraphManage = computed(() => {
      const role = authStore.userRole
      return role === 'super_admin' || role === 'admin' || authStore.permissions.includes('graph.manage')
    })
    const entityEditing = ref(false)
    const entityForm = ref({ name: '', description: '', aliasesStr: '' })
    const relatedRelations = ref([])  // 完整关系数据（含 relation ID、描述、方向）
    const editingRelationId = ref(null)  // 正在编辑的关系 ID
    const editingRelationDesc = ref('')  // 正在编辑的关系描述
    // 添加关系
    const showAddRelation = ref(false)
    const addRelationForm = ref({ targetSearch: '', targetId: '', relationType: 'related_to', description: '' })
    const addRelationCandidates = ref([])
    const addRelationSearching = ref(false)
    const relationTypeOptions = [
      { value: 'related_to', label: '相关' },
      { value: 'knows', label: '认识' },
      { value: 'works_at', label: '工作于' },
      { value: 'founded', label: '创立' },
      { value: 'uses', label: '使用' },
      { value: 'prefers', label: '偏好' },
      { value: 'located_in', label: '位于' },
      { value: 'participates', label: '参与' },
    ]

    // 间接关系（路径发现）
    const pathTargetId = ref('')
    const paths = ref([])
    const pathsLoading = ref(false)
    const pathsQueried = ref(false)
    const pathMaxHops = 4
    const reachableEntities = ref([])  // 从选中实体出发可达的实体列表
    const reachableLoading = ref(false)
    
    // 统计
    const stats = ref({
      entityCount: 0,
      relationCount: 0,
      memoryCount: 0
    })
    
    // 右侧面板 Tab
    const rightPanelTab = ref('stats')

    // ── 操作历史相关状态 ──
    const changeLogs = ref([])
    const historyLoading = ref(false)
    const historyPage = ref(1)
    const historyPageSize = 20
    const historyTotal = ref(0)
    const historyFilter = ref('')
    const showLogDetailModal = ref(false)
    const selectedLog = ref(null)
    const showRollbackConfirm = ref(false)
    const rollbackLoading = ref(false)

    // 总页数
    const totalHistoryPages = computed(() => {
      return Math.ceil(historyTotal.value / historyPageSize) || 1
    })

    // 切换到历史 Tab 时加载数据
    const switchToHistoryTab = () => {
      rightPanelTab.value = 'history'
      if (changeLogs.value.length === 0) {
        loadChangeLogs()
      }
    }

    // 加载变更日志
    const loadChangeLogs = async () => {
      historyLoading.value = true
      try {
        const params = {
          limit: historyPageSize,
          offset: (historyPage.value - 1) * historyPageSize,
        }
        if (historyFilter.value) {
          params.event_type = historyFilter.value
        }
        const res = await request.get('/api/graph/change-logs', { params })
        changeLogs.value = res.data.logs || []
        historyTotal.value = res.data.total || 0
      } catch (e) {
        console.error('[Graph] loadChangeLogs failed:', e)
      } finally {
        historyLoading.value = false
      }
    }

    // 获取事件类型标签
    const getEventLabel = (eventType) => {
      const labels = {
        'entity_created': '创建实体',
        'entity_updated': '编辑实体',
        'entity_deleted': '删除实体',
        'entity_restored': '恢复实体',
        'relation_created': '创建关系',
        'relation_updated': '编辑关系',
        'relation_deleted': '删除关系',
        'relation_flipped': '翻转关系',
        'rollback': '⏪ 回滚',
      }
      return labels[eventType] || eventType
    }

    // 格式化时间
    const formatTime = (timeStr) => {
      if (!timeStr) return ''
      const d = new Date(timeStr)
      const now = new Date()
      const diffMs = now - d
      const diffMins = Math.floor(diffMs / 60000)
      const diffHours = Math.floor(diffMs / 3600000)
      const diffDays = Math.floor(diffMs / 86400000)

      if (diffMins < 1) return '刚刚'
      if (diffMins < 60) return `${diffMins}分钟前`
      if (diffHours < 24) return `${diffHours}小时前`
      if (diffDays < 7) return `${diffDays}天前`
      return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    }

    // 显示日志详情
    const showLogDetail = (log) => {
      selectedLog.value = log
      showLogDetailModal.value = true
    }

    // 获取回滚操作描述
    const getRollbackDescription = (eventType) => {
      const descriptions = {
        'entity_created': '将删除该实体（因为此操作创建了它）',
        'entity_deleted': '将恢复该实体（因为此操作删除了它）',
        'entity_updated': '将恢复实体属性到修改前的值',
        'entity_restored': '将重新删除该实体（因为此操作恢复了它）',
        'relation_created': '将删除该关系（因为此操作创建了它）',
        'relation_deleted': '将恢复该关系（因为此操作删除了它）',
        'relation_updated': '将恢复关系属性到修改前的值',
        'relation_flipped': '将恢复关系方向（再次翻转）',
      }
      return descriptions[eventType] || '将撤销此操作'
    }

    // 确认回滚
    const confirmRollback = () => {
      showRollbackConfirm.value = true
    }

    // 执行回滚
    const executeRollback = async () => {
      if (!selectedLog.value) return
      rollbackLoading.value = true
      try {
        await request.post(`/api/graph/change-logs/${selectedLog.value.id}/rollback`)
        // 成功提示
        alert('✅ 回滚成功！图谱已恢复到修改前的状态。')
        // 关闭弹窗
        showRollbackConfirm.value = false
        showLogDetailModal.value = false
        // 刷新历史列表
        await loadChangeLogs()
        // 刷新图谱
        forceRefreshLayout()
      } catch (e) {
        console.error('[Graph] Rollback failed:', e)
        alert('❌ 回滚失败：' + (e?.response?.data?.detail || e.message))
      } finally {
        rollbackLoading.value = false
      }
    }

    // 监听页码变化
    watch(historyPage, () => {
      loadChangeLogs()
    })

    // 实体列表
    const entityListSearch = ref('')
    const entityPage = ref(1)
    const entityPageSize = 20
    const allEntities = ref([])
    
    // 过滤后的实体列表
    const filteredEntityList = computed(() => {
      if (!entityListSearch.value.trim()) {
        return allEntities.value
      }
      const query = entityListSearch.value.toLowerCase()
      return allEntities.value.filter(e => 
        e.label.toLowerCase().includes(query)
      )
    })
    
    // 分页后的实体列表
    const paginatedEntities = computed(() => {
      const start = (entityPage.value - 1) * entityPageSize
      const end = start + entityPageSize
      return filteredEntityList.value.slice(start, end)
    })
    
    // 总页数
    const totalEntityPages = computed(() => {
      return Math.ceil(filteredEntityList.value.length / entityPageSize)
    })
    
    // 当前图谱中的节点数量（响应式）
    const currentGraphNodes = computed(() => graphStats.value.nodes)
    
    // 当前图谱中的边数量（响应式）
    const currentGraphEdges = computed(() => graphStats.value.edges)
    
    // 是否有筛选条件
    const hasFilter = computed(() => 
      selectedEntityType.value || selectedRelationType.value
    )
    
    // 显示的节点数（有筛选时显示可见数，否则显示总数）
    const displayNodeCount = computed(() => 
      hasFilter.value ? filteredStats.value.visibleNodes : currentGraphNodes.value
    )
    
    // 显示的边数（有筛选时显示可见数，否则显示总数）
    const displayEdgeCount = computed(() => 
      hasFilter.value ? filteredStats.value.visibleEdges : currentGraphEdges.value
    )
    
    // 聚焦并选中实体
    const focusAndSelectEntity = async (entity) => {
      console.log('[Graph] focusAndSelectEntity:', entity.label, 'id:', entity.id)

      // 如果 sigma 还没准备好，直接加载子图
      if (!sigma || !graph) {
        console.log('[Graph] Sigma not ready, loading subgraph directly')
        loading.value = true
        try {
          const subgraph = await request.get(`/api/graph/subgraph/${entity.id}`, {
            params: { depth: 1 }
          })

          console.log('[Graph] Subgraph loaded, nodes:', subgraph.data.nodes?.length)

          if (subgraph.data.nodes?.length > 0) {
            graphData.value = subgraph.data

            // 第一步：设置 graphRendered（loading 还是 true）
            graphRendered.value = true
            await nextTick()

            // 第二步：关闭 loading
            loading.value = false
            await nextTick()

            await new Promise(resolve => setTimeout(resolve, 100))

            if (networkContainer.value) {
              await renderGraph(graphData.value)
              console.log('[Graph] Subgraph rendered')
            }
          } else {
            loading.value = false
            console.log('[Graph] No nodes in subgraph')
          }
        } catch (e) {
          console.error('[Graph] Failed to load subgraph:', e)
          loading.value = false
        }
        return
      }

      // sigma 已准备好，检查节点是否在图谱中
      const hasNode = graph.hasNode(entity.id)
      console.log('[Graph] Sigma ready, node count:', graph.order)

      if (hasNode) {
        // 节点在图谱中，直接聚焦
        console.log('[Graph] Node found in graph, focusing')
        try {
          // 获取相机并设置动画聚焦
          const camera = sigma.getCamera()
          camera.animate(
            {
              x: graph.getNodeAttribute(entity.id, 'x'),
              y: graph.getNodeAttribute(entity.id, 'y'),
              ratio: 0.5
            },
            { duration: 300 }
          )
          selectNode(entity.id)
        } catch (e) {
          console.error('[Graph] Focus/select failed:', e)
        }
      } else {
        // 节点不在图谱中，加载子图
        console.log('[Graph] Node not in graph, loading subgraph')
        loading.value = true
        try {
          const subgraph = await request.get(`/api/graph/subgraph/${entity.id}`, {
            params: { depth: 1 }
          })

          if (subgraph.data.nodes?.length > 0) {
            graphData.value = subgraph.data

            // 第一步：设置 graphRendered（loading 还是 true）
            graphRendered.value = true
            await nextTick()

            // 第二步：关闭 loading
            loading.value = false
            await nextTick()

            await new Promise(resolve => setTimeout(resolve, 100))
            await renderGraph(graphData.value)
          } else {
            loading.value = false
          }
        } catch (e) {
          console.error('[Graph] Failed to load subgraph:', e)
          loading.value = false
        }
      }
    }
    
    // Sigma.js 实例 - 使用模块级变量
    let sigma = null
    let graph = null
    const graphRendered = ref(false)  // 改为响应式 ref
    
    // 图谱节点/边数量（响应式，用于界面显示）
    const graphStats = ref({
      nodes: 0,
      edges: 0
    })
    
    // 实体类型配置
    const entityTypes = [
      { value: 'person', label: '人物', color: '#4CAF50' },
      { value: 'org', label: '组织', color: '#2196F3' },
      { value: 'location', label: '地点', color: '#FF9800' },
      { value: 'concept', label: '概念', color: '#9C27B0' },
      { value: 'event', label: '事件', color: '#F44336' },
      { value: 'skill', label: '技能', color: '#00BCD4' },
      { value: 'preference', label: '偏好', color: '#E91E63' },
      { value: 'fact', label: '事实', color: '#795548' },
      { value: 'project', label: '项目', color: '#3F51B5' },
      { value: 'tool', label: '工具', color: '#607D8B' }
    ]
    
    // 获取类型颜色
    const getTypeColor = (type) => {
      const found = entityTypes.find(t => t.value === type)
      return found ? found.color : '#9E9E9E'
    }
    
    // 获取类型标签
    const getTypeLabel = (type) => {
      const found = entityTypes.find(t => t.value === type)
      return found ? found.label : type
    }
    
    // 检查图谱可用性
    const checkAvailability = async () => {
      try {
        const resp = await request.get('/api/graph/stats')
        graphAvailable.value = true
        stats.value = {
          entityCount: resp.data.entity_count || 0,
          relationCount: resp.data.relation_count || 0,
          memoryCount: resp.data.memory_count || 0
        }
      } catch (error) {
        if (error.response?.status === 503) {
          graphAvailable.value = false
        }
      }
    }

    // ── 图谱布局缓存 ──
    const GRAPH_CACHE_KEY = 'agentforge_graph_layout_v1'

    // 获取缓存的布局数据
    const getCachedLayout = () => {
      try {
        const cached = localStorage.getItem(GRAPH_CACHE_KEY)
        if (!cached) return null
        const data = JSON.parse(cached)
        // 验证缓存有效性（节点数 + 关系数匹配）
        const versionMatch = data.entityCount === stats.value.entityCount &&
                             data.relationCount === stats.value.relationCount
        if (versionMatch && data.nodes?.length > 0) {
          console.log('[Graph] Using cached layout, nodes:', data.nodes.length)
          return data
        }
        console.log('[Graph] Cache invalid (structure changed)')
        return null
      } catch (e) {
        console.warn('[Graph] Failed to read cache:', e)
        return null
      }
    }

    // 保存布局到缓存
    const saveCachedLayout = (nodes, edges) => {
      try {
        const data = {
          nodes: nodes,  // 带坐标的节点
          edges: edges,
          entityCount: stats.value.entityCount,
          relationCount: stats.value.relationCount,
          timestamp: Date.now()
        }
        localStorage.setItem(GRAPH_CACHE_KEY, JSON.stringify(data))
        console.log('[Graph] Layout cached, nodes:', nodes.length)
      } catch (e) {
        console.warn('[Graph] Failed to save cache:', e)
      }
    }

    // 强制刷新布局缓存
    const forceRefreshLayout = () => {
      localStorage.removeItem(GRAPH_CACHE_KEY)
      console.log('[Graph] Layout cache cleared')
      loadUserGraph()
    }

    // 加载用户图谱
    const loadUserGraph = async (limit) => {
      return loadGraphWithLimit(limit || stats.value.entityCount || 9999)
    }

    // 加载指定数量的图谱
    const loadGraphWithLimit = async (nodeLimit = 9999) => {
      loading.value = true
      try {
        console.log('[Graph] Loading graph with limit:', nodeLimit)
        const resp = await request.get('/api/graph/user-graph', {
          params: { limit: nodeLimit }
        })
        
        console.log('[Graph] API response:', resp.data)
        console.log('[Graph] Nodes count:', resp.data.nodes?.length)
        console.log('[Graph] Edges count:', resp.data.edges?.length)
        
        // 保存所有实体到列表
        allEntities.value = resp.data.nodes || []
        console.log('[Graph] allEntities saved:', allEntities.value.length)
        
        if (!resp.data.nodes?.length) {
          loading.value = false
          // 显示空状态提示
          return
        }
        
        // 保存数据
        graphData.value = resp.data
        
        // 第一步：先设置 graphRendered 为 true
        // 此时 loading 还是 true，所以会继续显示加载中
        graphRendered.value = true
        
        // 等待 Vue 更新 DOM（创建 networkContainer）
        await nextTick()
        
        // 第二步：关闭 loading，显示图谱容器
        loading.value = false
        
        // 再次等待 DOM 更新
        await nextTick()
        
        // 额外等待确保容器完全准备好
        await new Promise(resolve => setTimeout(resolve, 100))
        
        if (!networkContainer.value) {
          console.error('[Graph] networkContainer still null')
          graphRendered.value = false
          return
        }
        
        console.log('[Graph] networkContainer ready, rendering...')
        await renderGraph(graphData.value)
        console.log('[Graph] renderGraph completed, sigma ready:', !!sigma)
        
      } catch (error) {
        console.error('[Graph] Failed to load graph:', error)
        loading.value = false
        // 渲染失败时保持 graphRendered 为 true，让用户看到错误信息
        // 而不是回到空状态
        if (!graphRendered.value) {
          graphRendered.value = false
        }
      }
    }
    
    // 加载更多节点（增量加载）
    const loadMoreNodes = async () => {
      if (loadingMore.value || !sigma || !graph) return

      loadingMore.value = true
      try {
        // 计算当前加载的节点数，请求更多
        const currentCount = allEntities.value.length
        const additionalLimit = 50

        console.log('[Graph] Loading more nodes, current:', currentCount)

        const resp = await request.get('/api/graph/user-graph', {
          params: { limit: currentCount + additionalLimit }
        })

        if (!resp.data.nodes?.length) {
          console.log('[Graph] No more nodes to load')
          loadingMore.value = false
          return
        }

        // 更新实体列表
        allEntities.value = resp.data.nodes || []

        // 找出新节点（当前图谱中不存在的）
        const newNodes = (resp.data.nodes || []).filter(
          node => !graph.hasNode(node.id)
        )

        // 找出新边
        const existingEdgeKeys = new Set()
        graph.forEachEdge((edge, attrs, src, tgt) => {
          existingEdgeKeys.add(`${src}-${tgt}`)
        })

        const newEdges = (resp.data.edges || []).filter(edge => {
          return !existingEdgeKeys.has(`${edge.from}-${edge.to}`)
        })

        console.log('[Graph] New nodes:', newNodes.length, 'New edges:', newEdges.length)

        if (newNodes.length > 0) {
          // 获取当前图形的边界来给新节点合理的位置
          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
          graph.forEachNode((node, attrs) => {
            if (attrs.x < minX) minX = attrs.x
            if (attrs.x > maxX) maxX = attrs.x
            if (attrs.y < minY) minY = attrs.y
            if (attrs.y > maxY) maxY = attrs.y
          })

          const rangeX = maxX - minX || 100
          const rangeY = maxY - minY || 100

          // 添加新节点
          newNodes.forEach(node => {
            const nodeType = node.group || node.type || 'other'
            graph.addNode(node.id, {
              label: node.name || node.label || node.id,
              x: maxX + Math.random() * rangeX * 0.3,
              y: minY + Math.random() * rangeY,
              size: 8,
              color: getTypeColor(nodeType),
              entityType: nodeType,
              originalLabel: node.name || node.label,
            })
          })
        }

        // 添加新边
        let edgeIndex = graph.size
        newEdges.forEach(edge => {
          if (graph.hasNode(edge.from) && graph.hasNode(edge.to)) {
            graph.addEdgeWithKey(`edge_${edgeIndex++}`, edge.from, edge.to, {
              label: edge.label || edge.type || '',
              size: 1,
              color: '#ccc',
              edgeType: edge.type || '',
            })
          }
        })

        // 重新运行布局算法（少量迭代调整新节点位置）
        if (newNodes.length > 0) {
          forceAtlas2.assign(graph, {
            iterations: 50,
            settings: {
              gravity: 1,
              scalingRatio: 500,
              strongGravityMode: true,
              barnesHutOptimize: graph.order > 200,
              adjustSizes: true,
              edgeWeightInfluence: 2,
              linLogMode: true,
            }
          })
        }

        // 更新统计
        updateFilteredStats()

        // 更新图谱统计（响应式）
        graphStats.value.nodes = graph.order
        graphStats.value.edges = graph.size

        console.log('[Graph] Loaded more nodes, total:', allEntities.value.length, 'graph nodes:', graphStats.value.nodes)

      } catch (error) {
        console.error('[Graph] Failed to load more nodes:', error)
      } finally {
        loadingMore.value = false
      }
    }
    
    // 保存图谱数据
    const graphData = ref(null)
    
    // 搜索实体
    const searchEntity = async () => {
      if (!searchQuery.value.trim()) {
        loadUserGraph(stats.value.entityCount || 9999)
        return
      }
      
      loading.value = true
      try {
        console.log('[Graph] Searching for:', searchQuery.value)
        
        const resp = await request.get('/api/graph/entities/search', {
          params: {
            query: searchQuery.value,
            entity_type: selectedEntityType.value || undefined,
            limit: 20
          }
        })
        
        console.log('[Graph] Search response:', resp.data)
        console.log('[Graph] Entities found:', resp.data.entities?.length || 0)
        
        // 获取每个实体的子图
        const allNodes = []
        const allEdges = []
        
        for (const entity of resp.data.entities || []) {
          try {
            const subgraph = await request.get(`/api/graph/subgraph/${entity.id}`, {
              params: { depth: 2 }
            })
            console.log('[Graph] Subgraph for', entity.name, ':', subgraph.data.nodes?.length, 'nodes')
            allNodes.push(...(subgraph.data.nodes || []))
            allEdges.push(...(subgraph.data.edges || []))
          } catch (e) {
            console.warn('[Graph] Failed to get subgraph for', entity.name, e)
          }
        }
        
        console.log('[Graph] Total nodes:', allNodes.length, 'edges:', allEdges.length)
        
        // 去重
        const uniqueNodes = [...new Map(allNodes.map(n => [n.id, n])).values()]
        const uniqueEdges = [...new Map(allEdges.map(e => [`${e.from}-${e.to}`, e])).values()]
        
        console.log('[Graph] Unique nodes:', uniqueNodes.length, 'edges:', uniqueEdges.length)
        
        if (uniqueNodes.length === 0) {
          alert('搜索结果为空')
          loading.value = false
          return
        }
        
        // 保存数据
        graphData.value = { nodes: uniqueNodes, edges: uniqueEdges }
        
        // 第一步：先设置 graphRendered 为 true（loading 还是 true）
        graphRendered.value = true
        await nextTick()
        
        // 第二步：关闭 loading，显示图谱容器
        loading.value = false
        await nextTick()
        
        // 额外等待确保容器完全准备好
        await new Promise(resolve => setTimeout(resolve, 100))
        
        if (!networkContainer.value) {
          console.error('[Graph] networkContainer still null after nextTick')
          graphRendered.value = false
          return
        }
        console.log('[Graph] networkContainer ready, rendering...')
        renderGraph(graphData.value)
      } catch (error) {
        console.error('Search failed:', error)
        loading.value = false
        graphRendered.value = false
      }
    }
    
    // 渲染图谱 - 使用 Sigma.js + graphology
    const renderGraph = async (data) => {
      console.log('[Graph] renderGraph called, nodes:', data.nodes?.length, 'edges:', data.edges?.length)
      console.log('[Graph] networkContainer:', networkContainer.value)

      if (!networkContainer.value) {
        console.error('[Graph] networkContainer is null, cannot render')
        return
      }

      try {
        // 清理旧的 Sigma 实例
        if (sigma) {
          sigma.kill()
          sigma = null
        }
        if (graph) {
          graph.clear()
          graph = null
        }

        // 创建新的 graphology 图
        graph = new Graph()

        // 获取容器尺寸
        const containerRect = networkContainer.value.getBoundingClientRect()
        const width = containerRect.width || 800
        const height = containerRect.height || 600

        // 检查缓存
        const cached = getCachedLayout()
        const cachedNodeMap = new Map()
        if (cached) {
          cached.nodes.forEach(n => cachedNodeMap.set(n.id, { x: n.x, y: n.y }))
        }

        // 节点去重并添加到图
        const nodeMap = new Map()
        const nodesForCache = []
        ;(data.nodes || []).forEach((node, index) => {
          if (!nodeMap.has(node.id) && !graph.hasNode(node.id)) {
            const nodeType = node.group || node.type || 'other'
            const nodeColor = getTypeColor(nodeType)

            // 优先使用缓存坐标，否则螺旋分布
            let x, y
            if (cachedNodeMap.has(node.id)) {
              const cached = cachedNodeMap.get(node.id)
              x = cached.x
              y = cached.y
            } else {
              const angle = (index / (data.nodes?.length || 1)) * 2 * Math.PI
              const radius = Math.min(width, height) * 0.35 * (0.5 + Math.random() * 0.5)
              x = radius * Math.cos(angle) + (Math.random() - 0.5) * 100
              y = radius * Math.sin(angle) + (Math.random() - 0.5) * 100
            }

            graph.addNode(node.id, {
              label: node.name || node.label || node.id,
              x, y,
              size: 8,
              color: nodeColor,
              entityType: nodeType,
              originalLabel: node.name || node.label,
            })
            nodeMap.set(node.id, true)
            nodesForCache.push({ id: node.id, x, y })
          }
        })
        console.log('[Graph] graphology nodes added:', graph.order, cached ? '(from cache)' : '(new layout)')

        // 边去重并添加到图（相同 from-to 只保留一条）
        const edgeSet = new Set()
        let edgeIndex = 0
        ;(data.edges || []).forEach((edge) => {
          const key = `${edge.from}-${edge.to}`
          if (!edgeSet.has(key) && graph.hasNode(edge.from) && graph.hasNode(edge.to)) {
            const edgeLabel = edge.label || edge.type || ''
            graph.addEdgeWithKey(`edge_${edgeIndex}`, edge.from, edge.to, {
              label: edgeLabel,
              size: 1,
              color: '#ccc',
              edgeType: edge.type || '',
            })
            edgeSet.add(key)
            edgeIndex++
          } else if (edgeSet.has(key)) {
            // 合并重复边的标签
            const existingEdgeKey = graph.edges().find(k => {
              const e = graph.getEdgeAttributes(k)
              return graph.source(k) === edge.from && graph.target(k) === edge.to
            })
            if (existingEdgeKey) {
              const attrs = graph.getEdgeAttributes(existingEdgeKey)
              const newLabel = edge.label || edge.type
              if (newLabel && !attrs.label.includes(newLabel)) {
                graph.setEdgeAttribute(existingEdgeKey, 'label', `${attrs.label}, ${newLabel}`)
              }
            }
          }
        })
        console.log('[Graph] graphology edges added:', graph.size)

        // 运行 ForceAtlas2 布局算法（有缓存则跳过）
        if (!cached) {
          console.log('[Graph] No cache, running ForceAtlas2 layout...')
          // 目标：有关系的节点聚集，孤节点分散在外围
          forceAtlas2.assign(graph, {
            iterations: 500,  // 增加迭代次数，布局更充分
            settings: {
              gravity: 1.5,         // 中心引力（让主连通分量聚集）
              scalingRatio: 1000,   // 排斥力（增大，让不相关节点距离更远）
              strongGravityMode: true,  // 强引力模式，连通分量更紧密
              barnesHutOptimize: graph.order > 200,  // 节点多时启用优化
              barnesHutTheta: 0.9,  // 精度（越小越精确，但更慢）
              adjustSizes: true,    // 避免节点重叠
              edgeWeightInfluence: 3,  // 边权重影响力（增大，让有关系节点更紧密）
              linLogMode: true,     // LinLog 模式，聚类效果更明显
            }
          })

          // 运行 noverlap 避免节点重叠
          noverlap.assign(graph, {
            settings: {
              margin: 4,    // 节点间距
              ratio: 1.5,   // 扩展比例
            }
          })

          console.log('[Graph] ForceAtlas2 layout completed')

          // 保存布局到缓存
          const nodesForCache = []
          graph.forEachNode((nodeKey, attrs) => {
            nodesForCache.push({ id: nodeKey, x: attrs.x, y: attrs.y })
          })
          saveCachedLayout(nodesForCache, data.edges)
        } else {
          console.log('[Graph] Using cached layout, skipping ForceAtlas2')
        }

        // 创建 Sigma 渲染器
        sigma = new Sigma(graph, networkContainer.value, {
          renderLabels: true,
          renderEdgeLabels: false,
          labelSize: 12,
          labelColor: { color: '#333' },
          labelWeight: '500',
          nodeReducer(nodeKey, attrs) {
            return attrs
          },
          edgeReducer(edgeKey, attrs) {
            return { ...attrs, color: '#999', size: 1.5 }
          },
          settings: {
            defaultNodeType: 'circle',
            defaultEdgeType: 'arrow',
            defaultNodeColor: '#999',
            defaultEdgeColor: '#999',
            labelFont: 'Arial, sans-serif',
            minCameraRatio: 0.001,
            maxCameraRatio: 10,
          }
        })

        graphRendered.value = true
        console.log('[Graph] Sigma created:', !!sigma, 'graphRendered:', graphRendered.value)

        // 初始化筛选统计
        updateFilteredStats()

        // 更新图谱统计（响应式）
        graphStats.value.nodes = graph.order
        graphStats.value.edges = graph.size
        console.log('[Graph] Graph stats updated:', graphStats.value)

        // 点击节点事件
        sigma.on('clickNode', ({ node }) => {
          selectNode(node)
        })

        // 双击展开子图
        sigma.on('doubleClickNode', ({ node }) => {
          focusSubgraph(node)
        })

        // 鼠标悬停高亮
        sigma.on('enterNode', ({ node }) => {
          if (sigma) {
            sigma.setSetting('nodeReducer', (n, attrs) => {
              // 保持 hidden 状态
              if (attrs.hidden) {
                return { ...attrs, hidden: true, size: 0, label: '' }
              }
              if (n === node) {
                return { ...attrs, size: 12, borderColor: '#fff', borderWidth: 2 }
              }
              // 高亮相连节点
              if (graph && (graph.hasEdge(node, n) || graph.hasEdge(n, node))) {
                return { ...attrs, size: 10 }
              }
              return attrs
            })
            sigma.setSetting('edgeReducer', (e, attrs) => {
              const src = graph.source(e)
              const tgt = graph.target(e)
              const srcHidden = graph.getNodeAttribute(src, 'hidden')
              const tgtHidden = graph.getNodeAttribute(tgt, 'hidden')
              // 保持 hidden 状态
              if (srcHidden || tgtHidden || attrs.hidden) {
                return { ...attrs, hidden: true }
              }
              if (src === node || tgt === node) {
                return { ...attrs, color: '#6366f1', size: 2 }
              }
              return { ...attrs, color: '#eee', size: 0.5 }
            })
            sigma.refresh()
          }
        })

        sigma.on('leaveNode', () => {
          // 恢复到 filter 设置的样式（通过重新触发 filter）
          if (sigma && selectedEntityType.value) {
            filterByType()
          } else if (sigma && selectedRelationType.value) {
            filterByRelation()
          } else if (sigma) {
            // 没有 filter，恢复默认
            sigma.setSetting('nodeReducer', (n, attrs) => attrs)
            sigma.setSetting('edgeReducer', (e, attrs) => ({ ...attrs, color: '#ddd', size: 1 }))
            sigma.refresh()
          }
        })

      } catch (error) {
        console.error('[Graph] renderGraph error:', error)
        throw error
      }
    }
    
    // 选择节点
    const selectNode = async (nodeId) => {
      try {
        const resp = await request.get(`/api/graph/entities/${nodeId}`)
        selectedNode.value = resp.data.entity
        entityEditing.value = false  // 重置编辑状态

        // 关联实体：使用 related 数据
        relatedEntities.value = resp.data.related?.map(r => ({
          id: r.entity?.id,
          name: r.entity?.name,
          type: r.entity?.group || 'other'
        })) || []

        // 关联关系：完整数据（含关系 ID、描述、方向）
        relatedRelations.value = resp.data.related?.map(r => ({
          entityId: r.entity?.id,
          entityName: r.entity?.name,
          entityType: r.entity?.group || 'other',
          relationType: r.relation_type,
          relationId: r.relation?.id || '',
          relationDesc: r.relation?.description || '',
          direction: r.relation?.direction || 'out',
        })) || []

        // 关联记忆：使用后端返回的 related_memories
        relatedMemories.value = resp.data.related_memories?.map(m => ({
          id: m.id,
          content: m.content || ''
        })) || []
      } catch (error) {
        console.error('Failed to get node details:', error)
      }
    }
    
    // 聚焦子图
    const focusSubgraph = async (nodeId) => {
      try {
        const resp = await request.get(`/api/graph/subgraph/${nodeId}`, { params: { depth: 2 } })
        await nextTick()
        renderGraph(resp.data)
      } catch (error) {
        console.error('Failed to focus subgraph:', error)
      }
    }
    
    // 关闭面板
    const closePanel = () => {
      selectedNode.value = null
      relatedMemories.value = []
      relatedEntities.value = []
      relatedRelations.value = []
      relatedSearchQuery.value = ''
      pathTargetId.value = ''
      paths.value = []
      pathsQueried.value = false
      reachableEntities.value = []
      entityEditing.value = false
      editingRelationId.value = null
    }

    // ── 实体编辑 ──
    const startEditEntity = () => {
      const node = selectedNode.value
      if (!node) return
      entityForm.value = {
        name: node.name || '',
        description: node.description || '',
        aliasesStr: (node.aliases || []).join(', ')
      }
      entityEditing.value = true
    }

    const cancelEditEntity = () => {
      entityEditing.value = false
    }

    const saveEntity = async () => {
      if (!selectedNode.value) return
      try {
        const body = {}
        if (entityForm.value.name !== (selectedNode.value.name || '')) {
          body.name = entityForm.value.name
        }
        if (entityForm.value.description !== (selectedNode.value.description || '')) {
          body.description = entityForm.value.description
        }
        const newAliases = entityForm.value.aliasesStr.split(/[,，]/).map(s => s.trim()).filter(Boolean)
        const oldAliases = selectedNode.value.aliases || []
        if (JSON.stringify(newAliases) !== JSON.stringify(oldAliases)) {
          body.aliases = newAliases
        }
        if (Object.keys(body).length === 0) {
          entityEditing.value = false
          return
        }
        await request.put(`/api/graph/entities/${selectedNode.value.id}`, body)
        // 更新本地数据
        if (body.name) selectedNode.value.name = body.name
        if (body.description !== undefined) selectedNode.value.description = body.description
        if (body.aliases) selectedNode.value.aliases = body.aliases
        entityEditing.value = false
        // 刷新图谱中节点的标签
        if (sigma && graph && body.name && graph.hasNode(selectedNode.value.id)) {
          graph.setNodeAttribute(selectedNode.value.id, 'label', body.name)
          graph.setNodeAttribute(selectedNode.value.id, 'originalLabel', body.name)
        }
      } catch (e) {
        alert('编辑失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    const deleteEntity = async () => {
      if (!selectedNode.value) return
      if (!confirm(`确定删除实体「${selectedNode.value.name}」？\n删除后其所有关系也会被移除，此操作不可撤销。`)) return
      try {
        await request.delete(`/api/graph/entities/${selectedNode.value.id}`)
        // 从图谱中移除节点
        if (sigma && graph && graph.hasNode(selectedNode.value.id)) {
          graph.dropNode(selectedNode.value.id)
        }
        closePanel()
      } catch (e) {
        alert('删除失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    // ── 关系编辑 ──
    const startEditRelation = (rel) => {
      editingRelationId.value = rel.relationId
      editingRelationDesc.value = rel.relationDesc
    }

    const cancelEditRelation = () => {
      editingRelationId.value = null
      editingRelationDesc.value = ''
    }

    const saveRelation = async (rel) => {
      if (!rel.relationId) {
        alert('该关系没有 ID，无法编辑')
        return
      }
      try {
        await request.put(`/api/graph/relations/${rel.relationId}`, {
          description: editingRelationDesc.value
        })
        // 更新本地数据
        rel.relationDesc = editingRelationDesc.value
        editingRelationId.value = null
      } catch (e) {
        alert('编辑关系失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    const flipRelation = async (rel) => {
      if (!rel.relationId) {
        alert('该关系没有 ID，无法翻转')
        return
      }
      const arrow = rel.direction === 'out' ? '→' : '←'
      if (!confirm(`确认翻转「${selectedNode.value.name} ${arrow} ${rel.entityName}」的方向？`)) return
      try {
        await request.post(`/api/graph/relations/${rel.relationId}/flip`)
        // 翻转方向
        rel.direction = rel.direction === 'out' ? 'in' : 'out'
      } catch (e) {
        alert('翻转失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    const deleteRelation = async (rel) => {
      if (!rel.relationId) {
        alert('该关系没有 ID，无法删除')
        return
      }
      if (!confirm(`确认删除「${selectedNode.value.name}」与「${rel.entityName}」之间的关系？`)) return
      try {
        await request.delete(`/api/graph/relations/${rel.relationId}`)
        // 从列表中移除
        const idx = relatedRelations.value.indexOf(rel)
        if (idx >= 0) relatedRelations.value.splice(idx, 1)
      } catch (e) {
        alert('删除失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    // ── 添加关系 ──
    const searchAddRelationTarget = async () => {
      const q = addRelationForm.value.targetSearch.trim()
      if (!q) { addRelationCandidates.value = []; return }
      addRelationSearching.value = true
      try {
        const resp = await request.get('/api/graph/entities/search', {
          params: { query: q, limit: 10 }
        })
        addRelationCandidates.value = (resp.data.entities || [])
          .filter(e => e.id !== selectedNode.value?.id)
      } catch (e) {
        console.error('Search failed:', e)
        addRelationCandidates.value = []
      } finally {
        addRelationSearching.value = false
      }
    }

    const openAddRelation = () => {
      showAddRelation.value = true
      addRelationForm.value = { targetSearch: '', targetId: '', relationType: 'related_to', description: '' }
      addRelationCandidates.value = []
    }

    const cancelAddRelation = () => {
      showAddRelation.value = false
    }

    const submitAddRelation = async () => {
      const form = addRelationForm.value
      if (!form.targetId) { alert('请选择目标实体'); return }
      try {
        await request.post('/api/graph/relations', {
          source_id: selectedNode.value.id,
          target_id: form.targetId,
          relation_type: form.relationType,
          description: form.description || ''
        })
        showAddRelation.value = false
        // 刷新详情
        await selectNode(selectedNode.value.id)
      } catch (e) {
        alert('添加关系失败: ' + (e.response?.data?.detail || e.message))
      }
    }
    
    // 过滤关联实体
    const filteredRelatedEntities = computed(() => {
      if (!relatedSearchQuery.value.trim()) {
        return relatedEntities.value
      }
      const query = relatedSearchQuery.value.toLowerCase()
      return relatedEntities.value.filter(e =>
        e.name.toLowerCase().includes(query)
      )
    })

    // 过滤关联关系（按实体名或关系类型搜索）
    const filteredRelatedRelations = computed(() => {
      if (!relatedSearchQuery.value.trim()) {
        return relatedRelations.value
      }
      const query = relatedSearchQuery.value.toLowerCase()
      return relatedRelations.value.filter(r =>
        r.entityName.toLowerCase().includes(query) ||
        (r.relationType || '').toLowerCase().includes(query) ||
        (r.relationDesc || '').toLowerCase().includes(query)
      )
    })

    // 间接关系：目标实体候选列表（只显示从当前节点可达的实体）
    const pathTargetCandidates = computed(() => {
      if (!reachableEntities.value.length) return []
      // 构建 id → graph 节点的映射，用于获取 label 等展示信息
      const graphNodeMap = {}
      if (graphData.value && graphData.value.nodes) {
        for (const n of graphData.value.nodes) {
          graphNodeMap[n.id] = n
        }
      }
      return reachableEntities.value
        .map(e => {
          const gn = graphNodeMap[e.id]
          return {
            id: e.id,
            label: (gn && (gn.label || gn.name)) || e.name || e.id,
            type: e.type
          }
        })
        .sort((a, b) => (a.label || '').localeCompare(b.label || ''))
    })

    // 加载从某实体出发可达的所有实体
    const loadReachable = async (sourceId) => {
      if (!sourceId) {
        reachableEntities.value = []
        return
      }
      reachableLoading.value = true
      try {
        const resp = await request.get('/api/graph/reachable', {
          params: { source_id: sourceId, max_hops: pathMaxHops }
        })
        reachableEntities.value = resp.data.entities || []
      } catch (error) {
        console.error('[Graph] Failed to load reachable entities:', error)
        reachableEntities.value = []
      } finally {
        reachableLoading.value = false
      }
    }

    // 查找两个实体之间的路径
    const loadPaths = async () => {
      if (!selectedNode.value || !pathTargetId.value) return
      pathsLoading.value = true
      pathsQueried.value = true
      paths.value = []
      try {
        const resp = await request.get('/api/graph/paths', {
          params: {
            source_id: selectedNode.value.id,
            target_id: pathTargetId.value,
            max_hops: pathMaxHops
          }
        })
        paths.value = resp.data.paths || []
      } catch (error) {
        console.error('[Graph] Failed to load paths:', error)
      } finally {
        pathsLoading.value = false
      }
    }

    // 切换选中节点时重置路径状态，并加载可达实体
    watch(selectedNode, (newNode) => {
      pathTargetId.value = ''
      paths.value = []
      pathsQueried.value = false
      reachableEntities.value = []
      if (newNode) {
        loadReachable(newNode.id)
      }
    })


    // 聚焦实体 - 优化动画速度，支持加载子图
    const focusEntity = async (name) => {
      console.log('[Graph] focusEntity called:', name)

      if (sigma && graph) {
        // 先在当前图谱中查找
        let foundNodeKey = null
        graph.forEachNode((nodeKey, attrs) => {
          if (attrs.label === name || nodeKey === name || attrs.originalLabel === name) {
            foundNodeKey = nodeKey
          }
        })

        if (foundNodeKey) {
          // 节点存在，直接聚焦
          console.log('[Graph] Node found in graph:', foundNodeKey)
          const camera = sigma.getCamera()
          camera.animate(
            {
              x: graph.getNodeAttribute(foundNodeKey, 'x'),
              y: graph.getNodeAttribute(foundNodeKey, 'y'),
              ratio: 0.5
            },
            { duration: 300 }
          )
          await selectNode(foundNodeKey)
        } else {
          // 节点不存在，尝试搜索并加载
          console.log('[Graph] Node not in graph, searching...')
          try {
            const resp = await request.get('/api/graph/entities/search', {
              params: { query: name, limit: 1 }
            })

            if (resp.data.entities?.length > 0) {
              const entity = resp.data.entities[0]
              console.log('[Graph] Found entity:', entity.id, entity.name)

              // 加载子图
              loading.value = true
              const subgraph = await request.get(`/api/graph/subgraph/${entity.id}`, {
                params: { depth: 1 }
              })

              if (subgraph.data.nodes?.length > 0) {
                graphData.value = subgraph.data

                // 第一步：设置 graphRendered（loading 还是 true）
                graphRendered.value = true
                await nextTick()

                // 第二步：关闭 loading
                loading.value = false
                await nextTick()

                await new Promise(resolve => setTimeout(resolve, 100))
                await renderGraph(graphData.value)

                // 渲染完成后聚焦
                if (sigma && graph) {
                  let newFoundKey = null
                  graph.forEachNode((nodeKey, attrs) => {
                    if (attrs.label === name || nodeKey === entity.id || attrs.originalLabel === name) {
                      newFoundKey = nodeKey
                    }
                  })
                  if (newFoundKey) {
                    const camera = sigma.getCamera()
                    camera.animate(
                      {
                        x: graph.getNodeAttribute(newFoundKey, 'x'),
                        y: graph.getNodeAttribute(newFoundKey, 'y'),
                        ratio: 0.5
                      },
                      { duration: 300 }
                    )
                    await selectNode(newFoundKey)
                  }
                }
              } else {
                loading.value = false
                console.log('[Graph] No nodes in subgraph')
              }
            } else {
              console.log('[Graph] Entity not found:', name)
            }
          } catch (e) {
            console.error('[Graph] Failed to focus entity:', e)
            loading.value = false
          }
        }
      }
    }
    
    // 重置视图
    const resetView = () => {
      searchQuery.value = ''
      selectedEntityType.value = ''
      selectedRelationType.value = ''
      closePanel()
      loadUserGraph(stats.value.entityCount || 9999)
    }
    
    // 筛选统计
    const filteredStats = ref({
      visibleNodes: 0,
      visibleEdges: 0
    })
    
    // 按类型过滤 - 使用 Sigma.js nodeReducer
    const filterByType = () => {
      if (!graph || !sigma) return

      const type = selectedEntityType.value
      let visibleNodeCount = 0

      console.log('[Graph] 筛选类型:', type)

      // 为节点设置 hidden 属性
      graph.forEachNode((nodeKey, attrs) => {
        const nodeType = (attrs.entityType || '').toLowerCase()
        const shouldShow = !type || nodeType === type.toLowerCase()
        graph.setNodeAttribute(nodeKey, 'hidden', !shouldShow)
        if (shouldShow) {
          visibleNodeCount++
        }
      })

      console.log('[Graph] 筛选结果 - 可见节点数:', visibleNodeCount)

      // 更新边的可见性
      updateEdgeVisibility()

      // 更新统计
      updateFilteredStats()

      // 应用 nodeReducer 实现隐藏
      sigma.setSetting('nodeReducer', (nodeKey, attrs) => {
        if (attrs.hidden) {
          return { ...attrs, hidden: true, size: 0, label: '' }
        }
        return attrs
      })

      sigma.setSetting('edgeReducer', (edgeKey, attrs) => {
        const src = graph.source(edgeKey)
        const tgt = graph.target(edgeKey)
        const srcHidden = graph.getNodeAttribute(src, 'hidden')
        const tgtHidden = graph.getNodeAttribute(tgt, 'hidden')
        if (srcHidden || tgtHidden) {
          return { ...attrs, hidden: true }
        }
        return attrs
      })

      sigma.refresh()
    }

    // 按关系过滤
    const filterByRelation = () => {
      if (!graph || !sigma) return

      const relType = selectedRelationType.value
      let visibleEdgeCount = 0

      graph.forEachEdge((edgeKey, attrs) => {
        const label = (attrs.label || '').toLowerCase().replace(/_/g, ' ')
        const target = relType.toLowerCase().replace(/_/g, ' ')
        const shouldShow = !relType || label.includes(target)
        graph.setEdgeAttribute(edgeKey, 'hidden', !shouldShow)
        if (shouldShow) visibleEdgeCount++
      })

      // 更新统计
      updateFilteredStats()

      sigma.setSetting('edgeReducer', (edgeKey, attrs) => {
        const src = graph.source(edgeKey)
        const tgt = graph.target(edgeKey)
        const srcHidden = graph.getNodeAttribute(src, 'hidden')
        const tgtHidden = graph.getNodeAttribute(tgt, 'hidden')
        if (srcHidden || tgtHidden || attrs.hidden) {
          return { ...attrs, hidden: true }
        }
        return attrs
      })

      sigma.refresh()
    }

    // 更新边的可见性
    const updateEdgeVisibility = () => {
      if (!graph || !sigma) return

      graph.forEachEdge((edgeKey) => {
        const src = graph.source(edgeKey)
        const tgt = graph.target(edgeKey)
        const srcHidden = graph.getNodeAttribute(src, 'hidden')
        const tgtHidden = graph.getNodeAttribute(tgt, 'hidden')
        graph.setEdgeAttribute(edgeKey, 'hidden', srcHidden || tgtHidden)
      })
    }

    // 更新筛选统计
    const updateFilteredStats = () => {
      if (!graph) return

      let visibleNodes = 0
      let visibleEdges = 0

      graph.forEachNode((nodeKey, attrs) => {
        if (!attrs.hidden) visibleNodes++
      })

      graph.forEachEdge((edgeKey, attrs) => {
        if (!attrs.hidden) visibleEdges++
      })

      console.log('[Graph] 更新筛选统计 - 可见节点:', visibleNodes, '可见边:', visibleEdges)

      filteredStats.value = {
        visibleNodes,
        visibleEdges
      }
    }
    
    // 查看记忆 - 跳转到记忆页面
    const viewMemory = (memoryId) => {
      console.log('[Graph] viewMemory:', memoryId)
      // 跳转到记忆页面并高亮该记忆
      // 使用 router 跳转（如果有的话）或者打开新窗口
      if (memoryId) {
        // 方案1: 如果页面在 iframe 中，发送消息给父窗口
        if (window.parent !== window) {
          window.parent.postMessage({
            type: 'navigateToMemory',
            memoryId: memoryId
          }, '*')
        }
        // 方案2: 尝试使用 Vue Router
        try {
          // 动态获取 router
          import('vue-router').then(({ useRouter }) => {
            const router = useRouter()
            if (router) {
              router.push({ name: 'Memory', params: { id: memoryId } })
            }
          })
        } catch (e) {
          // Router 不可用，使用备用方案
          console.log('[Graph] Router not available, using fallback')
        }
      }
    }
    
    // 生命周期
    onMounted(async () => {
      await checkAvailability()
      console.log('[Graph] onMounted: graphAvailable=', graphAvailable.value, 'entityCount=', stats.value.entityCount)
      // WebGL 渲染性能足够，自动全量加载所有节点
      if (graphAvailable.value && stats.value.entityCount > 0) {
        console.log('[Graph] Auto loading all entities:', stats.value.entityCount)
        await loadGraphWithLimit(stats.value.entityCount)
      }
    })

    onUnmounted(() => {
      if (sigma) {
        sigma.kill()
        sigma = null
      }
      if (graph) {
        graph.clear()
        graph = null
      }
    })
    
    return {
      searchQuery,
      relatedSearchQuery,
      selectedEntityType,
      selectedRelationType,
      graphAvailable,
      loading,
      loadingMore,
      selectedNode,
      relatedMemories,
      relatedEntities,
      relatedRelations,
      filteredRelatedEntities,
      filteredRelatedRelations,
      // 编辑相关
      hasGraphManage,
      entityEditing,
      entityForm,
      editingRelationId,
      editingRelationDesc,
      startEditEntity,
      cancelEditEntity,
      saveEntity,
      deleteEntity,
      startEditRelation,
      cancelEditRelation,
      saveRelation,
      flipRelation,
      deleteRelation,
      showAddRelation,
      addRelationForm,
      addRelationCandidates,
      addRelationSearching,
      relationTypeOptions,
      searchAddRelationTarget,
      openAddRelation,
      cancelAddRelation,
      submitAddRelation,
      // 间接关系（路径发现）
      pathTargetId,
      paths,
      pathsLoading,
      pathsQueried,
      pathMaxHops,
      pathTargetCandidates,
      reachableLoading,
      loadPaths,
      networkContainer,
      graphContainer,
      stats,
      filteredStats,
      entityTypes,
      graphData,
      graphRendered,
      currentGraphNodes,
      currentGraphEdges,
      hasFilter,
      displayNodeCount,
      displayEdgeCount,
      getTypeLabel,
      getTypeColor,
      searchEntity,
      resetView,
      closePanel,
      focusEntity,
      focusAndSelectEntity,
      filterByType,
      filterByRelation,
      viewMemory,
      loadGraphWithLimit,
      loadMoreNodes,
      forceRefreshLayout,
      // 实体列表相关
      rightPanelTab,
      entityListSearch,
      entityPage,
      entityPageSize,
      allEntities,
      filteredEntityList,
      paginatedEntities,
      totalEntityPages,
      // 操作历史相关
      changeLogs,
      historyLoading,
      historyPage,
      historyPageSize,
      historyTotal,
      historyFilter,
      totalHistoryPages,
      switchToHistoryTab,
      loadChangeLogs,
      getEventLabel,
      formatTime,
      showLogDetailModal,
      selectedLog,
      showLogDetail,
      showRollbackConfirm,
      rollbackLoading,
      getRollbackDescription,
      confirmRollback,
      executeRollback
    }
  }
}
</script>

<style scoped>
.graph-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f0 100%);
}

/* 工具栏 */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: white;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  flex-shrink: 0;
}

.search-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  color: #9ca3af;
  pointer-events: none;
}

.search-input {
  padding: 10px 16px 10px 38px;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  width: 280px;
  font-size: 14px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: #f9fafb;
}

.search-input:focus {
  outline: none;
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.search-input::placeholder {
  color: #9ca3af;
}

.filter-section {
  display: flex;
  gap: 12px;
}

.type-select, .relation-select {
  padding: 10px 16px;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  font-size: 14px;
  background: #f9fafb;
  cursor: pointer;
  min-width: 130px;
  transition: all 0.3s;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239ca3af'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 16px;
  padding-right: 40px;
}

.type-select:focus, .relation-select:focus {
  outline: none;
  border-color: #6366f1;
  background-color: white;
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}

.btn-primary:active {
  transform: translateY(0);
}

.btn-secondary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #6b7280;
  transition: all 0.3s;
}

.btn-secondary:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #faf5ff;
}

/* 主内容区 */
.main-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 图谱容器 */
.graph-container {
  flex: 1;
  position: relative;
  background: white;
  margin: 16px;
  margin-right: 0;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.network-container {
  width: 100%;
  height: 100%;
}

.unavailable-message, .loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
}

.unavailable-message .icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.unavailable-message h3 {
  margin: 0 0 8px;
  color: #374151;
  font-weight: 600;
}

.spinner {
  width: 44px;
  height: 44px;
  border: 3px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态引导 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: linear-gradient(180deg, #fafbfc 0%, #f0f4f8 100%);
}

.empty-content {
  text-align: center;
  padding: 40px;
}

.empty-icon {
  font-size: 72px;
  margin-bottom: 16px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.empty-content h3 {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px;
}

.empty-content p {
  font-size: 16px;
  color: #6b7280;
  margin: 0 0 32px;
}

.empty-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 40px;
}

.load-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
  border: 2px solid #e5e7eb;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: white;
  color: #374151;
}

.load-btn:hover {
  border-color: #6366f1;
  background: #faf5ff;
  color: #6366f1;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}

.load-btn.primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  color: white;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35);
}

.load-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.45);
}

.quick-tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 280px;
  margin: 0 auto;
}

.tip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: rgba(99, 102, 241, 0.05);
  border-radius: 10px;
  font-size: 13px;
  color: #6b7280;
}

.tip-icon {
  font-size: 16px;
}

/* 右侧面板 */
.right-panel {
  width: 280px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
  overflow-y: auto;
  background: #fafbfc;
}

/* Tab 按钮 */
.tab-buttons {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  background: #e5e7eb;
  padding: 4px;
  border-radius: 10px;
}

.tab-buttons button {
  flex: 1;
  padding: 8px 12px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  transition: all 0.2s;
}

.tab-buttons button.active {
  background: white;
  color: #374151;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.tab-buttons button:hover:not(.active) {
  color: #374151;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 加载更多按钮区域 */
.load-more-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #f0f4ff 0%, #faf5ff 100%);
  border-radius: 12px;
  border: 1px solid #e0e7ff;
}

.load-more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.load-more-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

.load-more-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.current-count {
  font-size: 12px;
  color: #6b7280;
  text-align: center;
}

/* 实体列表 Tab 特殊样式 */
.tab-content.entity-tab {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.tab-content.entity-tab .entity-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 实体列表 */
.entity-search {
  width: 100%;
  padding: 10px 14px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  font-size: 13px;
  outline: none;
  background: white;
  transition: all 0.2s;
}

.entity-search:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.entity-list {
  flex: 1;
  min-height: 100px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.entity-list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: white;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.entity-list-item:hover {
  background: #faf5ff;
  border-color: #c4b5fd;
  transform: translateX(4px);
}

.entity-name {
  font-size: 13px;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  font-weight: 500;
}

.entity-type-badge {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 6px;
  color: white;
  margin-left: 8px;
  flex-shrink: 0;
  font-weight: 500;
}

.empty-list {
  text-align: center;
  color: #9ca3af;
  padding: 24px;
  font-size: 13px;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.pagination button {
  padding: 6px 14px;
  border: 2px solid #e5e7eb;
  background: white;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: #6b7280;
  transition: all 0.2s;
}

.pagination button:hover:not(:disabled) {
  border-color: #6366f1;
  color: #6366f1;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination span {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.stats-card, .legend-card, .tips-card {
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  border: 1px solid #f0f0f0;
}

.stats-card h4, .legend-card h4, .tips-card h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #374151;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(50px, 1fr));
  gap: 8px;
  text-align: center;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 6px;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f4f8 100%);
  border-radius: 10px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-label {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 4px;
  font-weight: 500;
}

/* 筛选统计 */
.filtered-stats {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #e5e7eb;
}

.filtered-stats h5 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #6b7280;
  font-weight: 500;
}

.stats-grid.small .stat-item {
  padding: 8px 4px;
}

.stats-grid.small .stat-value {
  font-size: 18px;
}

.legend-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.legend-color {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
}

.legend-label {
  font-size: 12px;
  color: #4b5563;
  font-weight: 500;
}

.tips-card ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #6b7280;
}

.tips-card li {
  margin-bottom: 8px;
}

.tips-card.compact h4 {
  margin-bottom: 8px;
}

.tips-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  font-size: 12px;
  color: #6b7280;
}

.tips-grid span {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 详情面板 */
.detail-panel {
  position: fixed;
  top: 60px;
  right: 0;
  width: 340px;
  height: calc(100vh - 60px);
  background: white;
  border-left: 1px solid #e5e7eb;
  transform: translateX(100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow-y: auto;
  z-index: 100;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
}

.detail-panel.show {
  transform: translateX(0);
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #f0f0f0;
  position: sticky;
  top: 0;
  background: white;
  z-index: 1;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  flex: 1;
  color: #1f2937;
  font-weight: 600;
}

.entity-type {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  color: white;
  margin-right: 12px;
  font-weight: 500;
}

.entity-type.person { background: #4CAF50; }
.entity-type.org { background: #2196F3; }
.entity-type.location { background: #FF9800; }
.entity-type.concept { background: #9C27B0; }
.entity-type.event { background: #F44336; }
.entity-type.skill { background: #00BCD4; }
.entity-type.preference { background: #E91E63; }
.entity-type.fact { background: #795548; }
.entity-type.project { background: #3F51B5; }
.entity-type.tool { background: #607D8B; }

.close-btn {
  background: #f3f4f6;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6b7280;
  padding: 8px;
  line-height: 1;
  border-radius: 8px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.panel-body {
  padding: 20px;
}

.info-section {
  margin-bottom: 24px;
}

.info-section h4 {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.count-badge {
  font-size: 11px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  padding: 3px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.memory-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.memory-list li {
  padding: 12px 14px;
  background: #f9fafb;
  border-radius: 10px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #4b5563;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.memory-list li.memory-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.memory-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-action {
  color: #9ca3af;
  font-size: 16px;
  margin-left: 10px;
  transition: all 0.2s;
}

.memory-list li:hover {
  background: #faf5ff;
  border-color: #c4b5fd;
  color: #374151;
}

.memory-list li:hover .memory-action {
  color: #6366f1;
}

.memory-list li.empty {
  color: #9ca3af;
  cursor: default;
  text-align: center;
}

.memory-list li.empty:hover {
  background: #f9fafb;
  border-color: transparent;
  color: #9ca3af;
}

.related-search {
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  font-size: 13px;
  outline: none;
  background: #f9fafb;
  transition: all 0.2s;
}

.related-search:focus {
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.related-entities {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  padding: 6px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.entity-tag:hover {
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.entity-tag.empty {
  color: #9ca3af;
  background: #f3f4f6;
  cursor: default;
  font-weight: 400;
  box-shadow: none;
}

.entity-tag.empty:hover {
  transform: none;
}

/* 实体类型颜色 */
.entity-tag.project { background: linear-gradient(135deg, #3F51B5 0%, #5c6bc0 100%); }
.entity-tag.concept { background: linear-gradient(135deg, #9C27B0 0%, #ab47bc 100%); }
.entity-tag.tool { background: linear-gradient(135deg, #607D8B 0%, #78909c 100%); }
.entity-tag.skill { background: linear-gradient(135deg, #00BCD4 0%, #26c6da 100%); }
.entity-tag.person { background: linear-gradient(135deg, #4CAF50 0%, #66bb6a 100%); }
.entity-tag.org { background: linear-gradient(135deg, #2196F3 0%, #42a5f5 100%); }
.entity-tag.organization { background: linear-gradient(135deg, #2196F3 0%, #42a5f5 100%); }
.entity-tag.location { background: linear-gradient(135deg, #FF9800 0%, #ffa726 100%); }
.entity-tag.event { background: linear-gradient(135deg, #F44336 0%, #ef5350 100%); }
.entity-tag.preference { background: linear-gradient(135deg, #E91E63 0%, #ec407a 100%); }
.entity-tag.fact { background: linear-gradient(135deg, #795548 0%, #8d6e63 100%); }
.entity-tag.other { background: linear-gradient(135deg, #9E9E9E 0%, #bdbdbd 100%); }
.entity-tag.book { background: linear-gradient(135deg, #8D6E63 0%, #a1887f 100%); }
.entity-tag.place { background: linear-gradient(135deg, #FF9800 0%, #ffa726 100%); }
.entity-tag.item { background: linear-gradient(135deg, #78909C 0%, #90a4ae 100%); }

/* 间接关系（路径发现） */
.path-query {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.path-target-select {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;
  background: white;
  outline: none;
}

.path-target-select:focus {
  border-color: #2196F3;
}

.path-query-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.path-query-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.path-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-card {
  padding: 10px 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
  border-radius: 8px;
  border-left: 3px solid #667eea;
}

.path-hops {
  display: inline-block;
  padding: 2px 8px;
  background: #667eea;
  color: white;
  border-radius: 10px;
  font-size: 11px;
  margin-bottom: 6px;
}

.path-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  line-height: 1.8;
}

.path-node {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  background: white;
  border: 1px solid #ddd;
}

.path-node:hover {
  border-color: #2196F3;
  color: #2196F3;
}

.path-node.is-source {
  background: #e3f2fd;
  border-color: #2196F3;
  font-weight: 600;
}

.path-node.is-target {
  background: #e8f5e9;
  border-color: #4caf50;
  font-weight: 600;
}

.path-edge {
  color: #999;
  font-size: 11px;
  white-space: nowrap;
}

.path-hint {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

/* ── 实体编辑按钮 ── */
.header-action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 6px;
  border-radius: 6px;
  transition: all 0.2s;
  margin-left: 4px;
}

.header-action-btn:hover {
  background: #f3f4f6;
  transform: scale(1.1);
}

.header-action-btn.delete-btn:hover {
  background: #fee2e2;
}

/* ── 实体信息区 ── */
.entity-desc {
  margin-bottom: 10px;
}

.desc-text {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
}

.entity-aliases {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.aliases-label {
  font-size: 12px;
  color: #9ca3af;
  font-weight: 500;
}

.alias-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: #f0f4ff;
  color: #4e6ef2;
  border-radius: 10px;
  border: 1px solid #e0e7ff;
}

/* ── 编辑表单 ── */
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.edit-label {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.edit-input, .edit-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
  background: #fafbfc;
  box-sizing: border-box;
}

.edit-input:focus, .edit-textarea:focus {
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.edit-textarea.small {
  font-size: 12px;
  padding: 6px 10px;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.action-btn {
  padding: 6px 14px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  background: white;
  color: #374151;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f9fafb;
  border-color: #d1d5db;
}

.action-btn.save {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
}

.action-btn.save:hover {
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

/* ── 关系列表 ── */
.relation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.relation-item {
  padding: 8px 10px;
  background: #f9fafb;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  transition: all 0.15s;
}

.relation-item:hover {
  background: #faf5ff;
  border-color: #e0e7ff;
}

.relation-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.relation-dir {
  font-size: 14px;
  font-weight: 700;
  min-width: 16px;
  text-align: center;
}

.relation-dir.out {
  color: #6366f1;
}

.relation-dir.in {
  color: #f59e0b;
}

.relation-type-tag {
  font-size: 10px;
  padding: 2px 6px;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 4px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

.relation-entity-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.relation-entity-name:hover {
  color: #6366f1;
}

.relation-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.rel-action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
  transition: all 0.15s;
  opacity: 0.6;
}

.relation-item:hover .rel-action-btn {
  opacity: 1;
}

.rel-action-btn:hover {
  background: #e5e7eb;
  transform: scale(1.15);
}

.relation-desc {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  padding-left: 22px;
  line-height: 1.4;
}

.relation-edit {
  margin-top: 6px;
  padding-left: 22px;
}

/* ── 区域头部（标题 + 操作按钮） ── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
}

.section-action-btn {
  font-size: 12px;
  padding: 3px 10px;
  border: 1.5px solid #c4b5fd;
  background: #faf5ff;
  color: #6366f1;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.section-action-btn:hover {
  background: #ede9fe;
  border-color: #8b5cf6;
}

/* ── 添加关系表单 ── */
.add-relation-form {
  padding: 12px;
  background: #f5f3ff;
  border: 1.5px solid #e0e7ff;
  border-radius: 10px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.add-relation-search-row {
  position: relative;
}

.add-relation-candidates {
  max-height: 150px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: white;
}

.candidate-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
  border-bottom: 1px solid #f3f4f6;
}

.candidate-item:last-child {
  border-bottom: none;
}

.candidate-item:hover {
  background: #faf5ff;
}

.candidate-item.selected {
  background: #ede9fe;
  font-weight: 500;
}

.candidate-type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.candidate-name {
  flex: 1;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-type {
  font-size: 11px;
  color: #9ca3af;
  flex-shrink: 0;
}

.edit-select {
  width: 100%;
  padding: 8px 12px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  background: #fafbfc;
  cursor: pointer;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.edit-select:focus {
  border-color: #6366f1;
  background: white;
}

/* ── 删除关系按钮 ── */
.rel-action-btn.delete:hover {
  background: #fee2e2;
}

/* ── 操作历史 Tab ── */
.history-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-header {
  display: flex;
  gap: 8px;
  align-items: center;
}

.history-filter {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  background: white;
}

.history-filter:focus {
  outline: none;
  border-color: #6366f1;
}

.refresh-btn {
  padding: 8px 12px;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: #e5e7eb;
}

.history-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #6b7280;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.history-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  transition: all 0.2s;
}

.history-item:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.history-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border-radius: 8px;
  font-size: 18px;
  flex-shrink: 0;
}

.history-content {
  flex: 1;
  min-width: 0;
}

.history-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.event-label {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e0e7ff;
  color: #4338ca;
}

.event-entity_created .event-label { background: #d1fae5; color: #065f46; }
.event-entity_updated .event-label { background: #fef3c7; color: #92400e; }
.event-entity_deleted .event-label { background: #fee2e2; color: #991b1b; }
.event-entity_restored .event-label { background: #dbeafe; color: #1e40af; }
.event-relation_created .event-label { background: #e0e7ff; color: #4338ca; }
.event-relation_updated .event-label { background: #fef3c7; color: #92400e; }
.event-relation_deleted .event-label { background: #fee2e2; color: #991b1b; }
.event-relation_flipped .event-label { background: #f3e8ff; color: #6b21a8; }

.history-title .entity-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-time {
  font-size: 12px;
  color: #6b7280;
}

.history-actions {
  margin-top: 8px;
}

.detail-btn {
  padding: 4px 10px;
  font-size: 12px;
  background: white;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-btn:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.empty-history {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: #9ca3af;
  font-size: 14px;
}

.history-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.history-pagination button {
  padding: 6px 12px;
  font-size: 12px;
  background: white;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.history-pagination button:hover:not(:disabled) {
  background: #f3f4f6;
}

.history-pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.history-pagination span {
  font-size: 12px;
  color: #6b7280;
}

/* ── 日志详情弹窗 ── */
.log-detail-modal {
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

.log-detail-content {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.log-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.log-detail-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-modal-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border: none;
  border-radius: 8px;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.close-modal-btn:hover {
  background: #e5e7eb;
}

.log-detail-body {
  padding: 20px;
  overflow-y: auto;
}

.log-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f3f4f6;
}

.log-label {
  font-size: 13px;
  color: #6b7280;
  min-width: 80px;
}

.log-value {
  font-size: 13px;
  color: #111827;
  font-weight: 500;
}

.log-diff-section {
  margin-top: 16px;
}

.log-diff-section h4 {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin: 0 0 8px 0;
}

.log-json {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  font-family: 'Monaco', 'Menlo', monospace;
  color: #374151;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

/* ── 回滚按钮区域 ── */
.rollback-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.rollback-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 8px;
  font-size: 13px;
  color: #92400e;
  margin-bottom: 12px;
}

.rollback-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}

.rollback-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}

.rollback-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* ── 回滚确认弹窗 ── */
.rollback-confirm-content {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 420px;
  padding: 28px;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.rollback-confirm-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.rollback-confirm-content h3 {
  margin: 0 0 12px 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.rollback-confirm-text {
  font-size: 14px;
  color: #374151;
  line-height: 1.6;
  margin: 0 0 8px 0;
}

.rollback-confirm-detail {
  font-size: 13px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 10px 14px;
  border-radius: 8px;
  margin: 12px 0 20px 0;
}

.rollback-confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.confirm-cancel-btn {
  padding: 10px 24px;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.confirm-cancel-btn:hover {
  background: #e5e7eb;
}

.confirm-rollback-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
}

.confirm-rollback-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(239, 68, 68, 0.4);
}

.confirm-rollback-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* ── 回滚事件标签 ── */
.event-rollback .event-label {
  background: #fce7f3;
  color: #9d174d;
}
</style>