<template>
  <div class="page-container">
    <header class="page-header">
      <div>
        <h1 class="page-title">🧠 技能管理</h1>
        <p class="page-desc">管理你的技能库，浏览和安装共享技能</p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button v-if="rejectedItems.length > 0" class="btn btn-secondary" @click="showRejected = !showRejected">
          已拒绝 ({{ rejectedItems.length }})
        </button>
        <button class="btn btn-primary" @click="openCreate">+ 创建技能</button>
      </div>
    </header>

    <!-- 已拒绝区域 -->
    <div v-if="showRejected && rejectedItems.length > 0" class="rejected-section">
      <div class="rejected-header">
        <span>已拒绝的技能</span>
        <button class="btn-icon" @click="showRejected = false">✕</button>
      </div>
      <div class="rejected-list">
        <div v-for="item in rejectedItems" :key="item.id" class="rejected-item">
          <div class="rejected-name">{{ item.content_name }}</div>
          <div class="rejected-reason">拒绝原因：{{ item.reject_reason || '无' }}</div>
          <div class="rejected-time">{{ formatTime(item.reviewed_at) }}</div>
          <button class="btn btn-sm btn-primary" @click="republishSkill(item.content_name)">重新发布</button>
        </div>
      </div>
    </div>

    <!-- Tab 导航 -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'my' }" @click="activeTab = 'my'">
        我的技能 <span class="tab-count">({{ mySkills.length }})</span>
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'pool' }" @click="activeTab = 'pool'">
        🏊 技能池 <span class="tab-count">({{ poolAvailable.length }})</span>
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'installed' }" @click="activeTab = 'installed'">
        已安装 <span class="tab-count">({{ poolInstalled.length }})</span>
      </button>
    </div>

    <!-- 我的技能 Tab -->
    <div v-if="activeTab === 'my'" class="tab-content">
      <!-- 视图切换 + 搜索框 -->
      <div class="view-switcher-row">
        <div class="view-switcher">
          <button class="view-btn" :class="{ active: viewMode === 'mine' }" @click="viewMode = 'mine'">
            👤 我的
          </button>
          <button v-if="canManageAll" class="view-btn" :class="{ active: viewMode === 'all' }" @click="viewMode = 'all'">
            👥 全部用户
          </button>
          <button v-if="canManageAll" class="view-btn" :class="{ active: viewMode === 'ai' }" @click="viewMode = 'ai'">
            🤖 AI生成 <span class="tab-count">({{ aiSkills.length }})</span>
          </button>
        </div>
        <div class="search-bar-inline">
          <input v-model="search" class="input search-input" :placeholder="viewMode === 'mine' ? '搜索我的技能...' : '搜索用户名或技能名...'" />
        </div>
      </div>

      <!-- 分类栏（仅在"我的"视图显示） -->
      <div v-if="viewMode === 'mine'" class="category-bar">
        <button class="category-tag" :class="{ active: activeCategory === '' }" @click="activeCategory = ''">
          全部
        </button>
        <div v-for="cat in userCategories" :key="cat" class="category-tag-wrap">
          <button v-if="editingCat !== cat" class="category-tag" :class="{ active: activeCategory === cat }" @click="activeCategory = cat">
            {{ cat }}
          </button>
          <input v-else v-model="editCatName" class="cat-input" @keyup.enter="handleRenameCategory(cat)" @keyup.escape="editingCat = ''; editCatName = ''" @blur="handleRenameCategory(cat)" />
          <button v-if="editingCat !== cat" class="category-tag cat-more" @click.stop="toggleCatMenu(cat)">···</button>
          <div v-if="catMenuOpen === cat" class="cat-popup" @click.stop>
            <button @click="startRenameCat(cat)">✏️ 重命名</button>
            <button class="cat-danger" @click="handleDeleteCategory(cat)">🗑️ 删除</button>
          </div>
        </div>
        <template v-if="showCatInput">
          <input v-model="newCatName" class="cat-input" placeholder="新分类名" @keyup.enter="handleCreateCategory" @keyup.escape="showCatInput = false; newCatName = ''" />
          <button class="category-tag cat-confirm" @click="handleCreateCategory">✓</button>
          <button class="category-tag cat-cancel" @click="showCatInput = false; newCatName = ''">✕</button>
        </template>
        <button class="category-tag cat-add" @click="openCatInput">+</button>
      </div>

      <!-- 技能列表 + 详情面板 -->
      <div class="skill-layout skill-layout-large">
        <div class="card skill-list-card skill-list-large">
          <div class="card-header">
            <span>{{ viewMode === 'mine' ? '我的技能' : viewMode === 'ai' ? 'AI生成' : '全部用户技能' }} ({{ filteredList.length }})</span>
          </div>
          <div class="skill-list">
            <div v-if="loading" class="card-body"><div class="spinner"></div></div>
            <div v-else-if="filteredList.length === 0" class="card-body empty">
              <p>{{ viewMode === 'mine' ? '暂无技能，点击右上角创建' : '暂无其他用户的技能' }}</p>
            </div>

            <!-- 我的/AI视图：平铺列表 -->
            <template v-if="viewMode === 'mine' || viewMode === 'ai'">
              <div v-for="skill in filteredList" :key="skill.name" class="skill-item" :class="{ active: selected?.name === skill.name }" @click="selectSkill(skill.name)">
                <div class="skill-item-name">
                  {{ skill.name }}
                  <span v-if="getPoolStatus(skill.name)" class="status-badge" :class="'status-' + getPoolStatus(skill.name)">{{ getPoolStatusText(skill.name) }}</span>
                  <span v-if="skill.locked" class="lock-badge" title="已锁定">🔒</span>
                </div>
                <div class="skill-item-desc">{{ skill.description || '无描述' }}</div>
                <div class="skill-item-actions" @click.stop>
                  <button v-if="canPublishSkill(skill)" class="btn-icon" @click="handlePublish(skill.name)" title="发布到池">📤</button>
                  <button v-if="canManageAll && !skill.locked" class="btn-icon" @click="handleLock(skill.name)" title="锁定">🔒</button>
                  <button v-if="canManageAll && skill.locked" class="btn-icon" @click="handleUnlock(skill.name)" title="解锁">🔓</button>
                  <button v-if="canManageAll || viewMode !== 'ai'" class="btn-icon" @click="openEdit(skill.name)" title="编辑">✏️</button>
                  <button v-if="canManageAll || viewMode !== 'ai'" class="btn-icon btn-danger-icon" @click="handleDelete(skill.name)" title="删除">🗑️</button>
                </div>
              </div>
            </template>

            <!-- 全部用户视图：按用户分组 -->
            <template v-else>
              <div v-for="group in groupedByUser" :key="group.name" class="user-group">
                <div class="skill-group-header">
                  👤 {{ group.name }} <span class="group-count">({{ group.count }})</span>
                </div>
                <div v-for="skill in group.skills" :key="skill.name" class="skill-item" :class="{ active: selected?.name === skill.name }" @click="selectSkill(skill.name)">
                  <div class="skill-item-name">
                    {{ skill.name }}
                    <span v-if="skill.locked" class="lock-badge" title="已锁定">🔒</span>
                  </div>
                  <div class="skill-item-desc">{{ skill.description || '无描述' }}</div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 详情面板 -->
        <div class="card skill-detail-card skill-detail-large">
          <div v-if="!selected" class="card-body detail-empty">
            <div class="empty-icon">📄</div>
            <p>选择一个技能查看详情</p>
          </div>
          <template v-else>
            <div class="card-header">
              <div class="detail-header-left">
                <span class="detail-name">{{ selected.name }}</span>
                <span v-if="selected.locked" class="badge badge-danger">🔒 已锁</span>
              </div>
              <div class="detail-header-right">
                <button v-if="canManageAll && !selected.locked" class="btn btn-sm btn-warning" @click="handleLock(selected.name)">🔒 锁定</button>
                <button v-if="canManageAll && selected.locked" class="btn btn-sm btn-success" @click="handleUnlock(selected.name)">🔓 解锁</button>
                <button class="btn btn-sm btn-secondary" @click="openEdit(selected.name)">编辑</button>
              </div>
            </div>
            <div class="card-body detail-body">
              <!-- 描述区域 -->
              <div class="detail-section" v-if="selected.description">
                <div class="section-label">📝 描述</div>
                <div class="description-text">{{ selected.description }}</div>
              </div>
              
              <!-- 元信息 -->
              <div class="detail-section meta-section">
                <div class="meta-chips">
                  <div class="meta-chip">
                    <span class="chip-icon">👤</span>
                    <span class="chip-label">创建者</span>
                    <span class="chip-value">{{ selected.owner_name || selected.author || '未知' }}</span>
                  </div>
                  <div class="meta-chip">
                    <span class="chip-icon">📂</span>
                    <span class="chip-label">分类</span>
                    <span class="chip-value">{{ selected.category || '未分类' }}</span>
                  </div>
                </div>
              </div>
              
              <!-- 依赖工具集 -->
              <div class="detail-section" v-if="skillToolsets.length > 0">
                <div class="section-label">🔧 依赖工具集</div>
                <div class="toolset-grid">
                  <div v-for="ts in skillToolsets" :key="ts.key" class="toolset-item" :class="{ 'missing': !ts.hasPermission }">
                    <div class="toolset-name">{{ ts.label }}</div>
                    <div class="toolset-desc">{{ ts.desc }}</div>
                    <div v-if="!ts.hasPermission" class="toolset-warning">⚠️ 无权限</div>
                  </div>
                </div>
              </div>
              
              <!-- 技能内容 -->
              <div class="detail-section">
                <div class="section-label">📖 技能内容</div>
                <div class="detail-content" v-html="renderMd(selected.body || stripFrontmatter(selected.content))"></div>
              </div>
              
              <!-- 附属文件区域 -->
              <div class="detail-section skill-files-section">
                <div class="files-header">
                  <span class="section-label">📎 附属文件 ({{ (selected.files || []).length }})</span>
                  <div class="files-header-actions" v-if="canManageAll || selected.owner_id === authStore.userId">
                    <select v-model="uploadTargetDir" class="input input-sm">
                      <option value="references">📚 references/</option>
                      <option value="templates">📝 templates/</option>
                      <option value="scripts">⚙️ scripts/</option>
                      <option value="assets">📦 assets/</option>
                    </select>
                    <button class="btn btn-sm btn-secondary" @click="openCreateFile">+ 新建文本</button>
                    <label class="btn btn-sm btn-primary" :class="{ disabled: isUploading }">
                      <input type="file" multiple @change="handleFileSelect" style="display: none;" :disabled="isUploading" />
                      {{ isUploading ? '上传中...' : '📤 上传文件' }}
                    </label>
                  </div>
                </div>

                <!-- 拖拽上传区域 -->
                <div
                  v-if="canManageAll || selected.owner_id === authStore.userId"
                  class="upload-drop-zone"
                  :class="{ active: isDragging }"
                  @dragover="handleDragOver"
                  @dragleave="handleDragLeave"
                  @drop="handleDrop"
                >
                  <div class="upload-hint">
                    <span class="upload-icon">📂</span>
                    <span>拖拽文件到此处上传到 <strong>{{ uploadTargetDir }}/</strong></span>
                  </div>
                </div>

                <!-- 快捷模板 -->
                <div v-if="canManageAll || selected.owner_id === authStore.userId" class="quick-templates">
                  <div class="templates-title">💡 快捷创建模板文件：</div>
                  <div class="templates-list">
                    <button v-for="t in QUICK_TEMPLATES" :key="t.path" class="template-btn" @click="createQuickTemplate(t)">
                      {{ getFileIcon(t.path) }} {{ t.path }}
                    </button>
                  </div>
                </div>

                <!-- 目录说明 -->
                <div class="directory-guide">
                  <div class="guide-title">📁 目录结构说明：</div>
                  <div class="guide-items">
                    <div class="guide-item" v-for="(info, dir) in DIRECTORY_INFO" :key="dir">
                      <span class="guide-icon">{{ info.icon }}</span>
                      <strong>{{ dir }}/</strong>
                      <span class="guide-desc">{{ info.desc }}</span>
                    </div>
                  </div>
                </div>

                <!-- 文件列表 -->
                <div v-if="selected.files && selected.files.length > 0" class="files-groups">
                  <div v-for="[dir, files] in skillFilesGrouped" :key="dir" class="file-group">
                    <div class="file-group-header">
                      <span class="file-group-icon">{{ DIRECTORY_INFO[dir]?.icon || '📄' }}</span>
                      <span class="file-group-name">{{ dir }}</span>
                      <span v-if="DIRECTORY_INFO[dir]" class="file-group-desc" :title="DIRECTORY_INFO[dir].desc">ⓘ</span>
                    </div>
                    <div class="file-list">
                      <div v-for="f in files" :key="f" class="file-item">
                        <span class="file-icon">{{ getFileIcon(f) }}</span>
                        <span class="file-name" @click="isBinaryFile(f) ? null : openViewFile(f)">
                          {{ f.split('/').pop() }}
                        </span>
                        <div class="file-actions">
                          <a v-if="isBinaryFile(f)" :href="getSkillFileDownloadUrl(selected.name, f)" target="_blank" class="btn-icon-sm" title="下载/预览">⬇️</a>
                          <button v-if="!isBinaryFile(f) && (canManageAll || selected.owner_id === authStore.userId)" class="btn-icon-sm" @click="openEditFile(f)" title="编辑">✏️</button>
                          <button v-if="canManageAll || selected.owner_id === authStore.userId" class="btn-icon-sm btn-danger-icon" @click="handleDeleteFile(f)" title="删除">🗑️</button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 空状态 -->
                <div v-else-if="!(canManageAll || selected.owner_id === authStore.userId)" class="files-empty-hint">
                  暂无附属文件
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 技能池浏览 Tab -->
    <div v-if="activeTab === 'pool'" class="tab-content">
      <div class="skill-layout skill-layout-tall">
        <div class="card skill-list-card">
          <div class="card-header">🏊 技能池 ({{ poolAvailable.length }})</div>
          <div class="skill-list">
            <div v-if="loading" class="card-body"><div class="spinner"></div></div>
            <div v-else-if="poolAvailable.length === 0" class="card-body empty"><p>技能池为空</p></div>
            <div v-for="skill in poolAvailable" :key="skill.name" class="skill-item" :class="{ active: selected?.name === skill.name }" @click="selectSkill(skill.name)">
              <div class="skill-item-name">{{ skill.name }} <span class="pool-badge">🏊</span></div>
              <div class="skill-item-desc">{{ skill.description || '无描述' }}</div>
              <div class="skill-item-actions" @click.stop>
                <button class="btn-icon" @click="handleInstallPool(skill.name)" title="安装">⭐</button>
              </div>
            </div>
          </div>
        </div>
        <div class="card skill-detail-card skill-detail-tall">
          <div v-if="!selected" class="card-body detail-empty"><div class="empty-icon">📄</div><p>选择技能查看详情</p></div>
          <template v-else>
            <div class="card-header">
              <div class="detail-header-left">
                <span class="detail-name">{{ selected.name }}</span>
              </div>
              <div class="detail-header-right">
                <button class="btn btn-sm btn-primary" @click="handleInstallPool(selected.name)">⭐ 安装</button>
              </div>
            </div>
            <div class="card-body detail-body">
              <!-- 描述区域 -->
              <div class="detail-section" v-if="selected.description">
                <div class="section-label">📝 描述</div>
                <div class="description-text">{{ selected.description }}</div>
              </div>
              
              <!-- 元信息 -->
              <div class="detail-section meta-section">
                <div class="meta-chips">
                  <div class="meta-chip">
                    <span class="chip-icon">👤</span>
                    <span class="chip-label">创建者</span>
                    <span class="chip-value">{{ selected.owner_name || selected.author || '未知' }}</span>
                  </div>
                  <div class="meta-chip">
                    <span class="chip-icon">📂</span>
                    <span class="chip-label">分类</span>
                    <span class="chip-value">{{ selected.category || '未分类' }}</span>
                  </div>
                </div>
              </div>
              
              <!-- 技能内容 -->
              <div class="detail-section">
                <div class="section-label">📖 技能内容</div>
                <div class="detail-content" v-html="renderMd(selected.body || stripFrontmatter(selected.content))"></div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 已安装 Tab -->
    <div v-if="activeTab === 'installed'" class="tab-content">
      <div class="skill-layout skill-layout-tall">
        <div class="card skill-list-card">
          <div class="card-header">已安装 ({{ poolInstalled.length }})</div>
          <div class="skill-list">
            <div v-if="loading" class="card-body"><div class="spinner"></div></div>
            <div v-else-if="poolInstalled.length === 0" class="card-body empty"><p>暂无已安装的技能</p></div>
            <div v-for="skill in poolInstalled" :key="skill.name" class="skill-item" :class="{ active: selected?.name === skill.name }" @click="selectSkill(skill.name)">
              <div class="skill-item-name">{{ skill.name }} <span class="pool-badge">📥</span></div>
              <div class="skill-item-desc">{{ skill.description || '无描述' }}</div>
              <div class="skill-item-actions" @click.stop>
                <button class="btn-icon" @click="handleUninstallPool(skill.name)" title="卸载">📥</button>
              </div>
            </div>
          </div>
        </div>
        <div class="card skill-detail-card skill-detail-tall">
          <div v-if="!selected" class="card-body detail-empty"><div class="empty-icon">📄</div><p>选择技能查看详情</p></div>
          <template v-else>
            <div class="card-header">
              <div class="detail-header-left">
                <span class="detail-name">{{ selected.name }}</span>
              </div>
              <div class="detail-header-right">
                <button class="btn btn-sm btn-danger" @click="handleUninstallPool(selected.name)">📥 卸载</button>
              </div>
            </div>
            <div class="card-body detail-body">
              <!-- 描述区域 -->
              <div class="detail-section" v-if="selected.description">
                <div class="section-label">📝 描述</div>
                <div class="description-text">{{ selected.description }}</div>
              </div>
              
              <!-- 元信息 -->
              <div class="detail-section meta-section">
                <div class="meta-chips">
                  <div class="meta-chip">
                    <span class="chip-icon">👤</span>
                    <span class="chip-label">创建者</span>
                    <span class="chip-value">{{ selected.owner_name || selected.author || '未知' }}</span>
                  </div>
                  <div class="meta-chip">
                    <span class="chip-icon">📂</span>
                    <span class="chip-label">分类</span>
                    <span class="chip-value">{{ selected.category || '未分类' }}</span>
                  </div>
                </div>
              </div>
              
              <!-- 技能内容 -->
              <div class="detail-section">
                <div class="section-label">📖 技能内容</div>
                <div class="detail-content" v-html="renderMd(selected.body || stripFrontmatter(selected.content))"></div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 创建/编辑弹窗 -->
    <teleport to="body">
      <div v-if="showEditor" class="modal-overlay" @click.self="closeEditor">
        <div class="modal" style="max-width: 1100px; width: 95vw; height: 90vh;">
          <div class="modal-header">
            <span class="modal-title">{{ editMode ? '编辑技能' : '创建技能' }}</span>
            <button class="btn-icon" @click="closeEditor">✕</button>
          </div>
          <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; height: calc(100% - 60px); overflow-y: auto;">
            <!-- 基本信息区域 -->
            <div style="display: flex; gap: 20px;">
              <div style="width: 240px; flex-shrink: 0; display: flex; flex-direction: column; gap: 14px;">
                <div class="form-group">
                  <label class="form-label">名称</label>
                  <input v-model="form.name" class="input" placeholder="my-skill" :disabled="editMode" />
                </div>
                <div class="form-group">
                  <label class="form-label">描述</label>
                  <textarea v-model="form.description" class="input" rows="4" placeholder="简短描述"></textarea>
                </div>
                <div class="form-group">
                  <label class="form-label">分类</label>
                  <select v-model="form.category" class="input">
                    <option value="">未分类</option>
                    <option v-for="cat in userCategories" :key="cat" :value="cat">{{ cat }}</option>
                  </select>
                </div>
              </div>
              <div style="flex: 1; display: flex; flex-direction: column;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                  <label class="form-label">内容（Markdown）</label>
                  <div class="tab-switch">
                    <button class="tab-btn-sm" :class="{ active: !editorPreview }" @click="editorPreview = false">源码</button>
                    <button class="tab-btn-sm" :class="{ active: editorPreview }" @click="editorPreview = true">预览</button>
                  </div>
                </div>
                <textarea v-if="!editorPreview" v-model="form.content" class="textarea" style="flex: 1; font-family: monospace; min-height: 200px;" placeholder="# 技能标题&#10;&#10;详细指令..."></textarea>
                <div v-else class="preview-pane" style="min-height: 200px;" v-html="renderMd(stripFrontmatter(form.content))"></div>
              </div>
            </div>

            <!-- 附属文件区域（仅创建模式显示） -->
            <div v-if="!editMode" class="skill-files-section" style="margin-top: 0; padding-top: 16px; border-top: 1px solid var(--border-primary);">
              <div class="files-header">
                <span class="files-title">📎 附属文件 ({{ pendingFiles.length }})</span>
                <div class="files-header-actions">
                  <select v-model="pendingFileTargetDir" class="input input-sm">
                    <option value="references">📚 references/</option>
                    <option value="templates">📝 templates/</option>
                    <option value="scripts">⚙️ scripts/</option>
                    <option value="assets">📦 assets/</option>
                  </select>
                  <button class="btn btn-sm btn-secondary" @click="addPendingFile">+ 新建文本</button>
                  <label class="btn btn-sm btn-primary" :class="{ disabled: isUploading }">
                    <input type="file" multiple @change="handlePendingFileSelect" style="display: none;" :disabled="isUploading" />
                    📤 上传文件
                  </label>
                </div>
              </div>

              <!-- 快捷模板 -->
              <div class="quick-templates">
                <div class="templates-title">💡 快捷创建模板文件：</div>
                <div class="templates-list">
                  <button v-for="t in QUICK_TEMPLATES" :key="t.path" class="template-btn" @click="addQuickTemplate(t)">
                    {{ getFileIcon(t.path) }} {{ t.path }}
                  </button>
                </div>
              </div>

              <!-- 目录说明 -->
              <div class="directory-guide">
                <div class="guide-title">📁 目录结构说明：</div>
                <div class="guide-items">
                  <div class="guide-item" v-for="(info, dir) in DIRECTORY_INFO" :key="dir">
                    <span class="guide-icon">{{ info.icon }}</span>
                    <strong>{{ dir }}/</strong>
                    <span class="guide-desc">{{ info.desc }}</span>
                  </div>
                </div>
              </div>

              <!-- 待创建的文件列表 -->
              <div v-if="pendingFiles.length > 0" class="files-groups">
                <div v-for="[dir, files] in pendingFilesGrouped" :key="dir" class="file-group">
                  <div class="file-group-header">
                    <span class="file-group-icon">{{ DIRECTORY_INFO[dir]?.icon || '📄' }}</span>
                    <span class="file-group-name">{{ dir }}</span>
                    <span v-if="DIRECTORY_INFO[dir]" class="file-group-desc" :title="DIRECTORY_INFO[dir].desc">ⓘ</span>
                  </div>
                  <div class="file-list">
                    <div v-for="f in files" :key="f.path" class="file-item">
                      <span class="file-icon">{{ getFileIcon(f.path) }}</span>
                      <span class="file-name" @click="editPendingFile(f)">{{ f.path.split('/').pop() }}</span>
                      <div class="file-actions">
                        <button class="btn-icon-sm" @click="editPendingFile(f)" title="编辑">✏️</button>
                        <button class="btn-icon-sm btn-danger-icon" @click="removePendingFile(f)" title="删除">🗑️</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="files-empty-hint">
                还没有添加附属文件，点击上方按钮或模板快速添加
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeEditor">取消</button>
            <button class="btn btn-primary" @click="handleSave" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- 附属文件编辑弹窗 -->
    <teleport to="body">
      <div v-if="showFileEditor" class="modal-overlay" @click.self="closeFileEditor">
        <div class="modal" style="max-width: 900px; width: 90vw; height: 80vh;">
          <div class="modal-header">
            <span class="modal-title">
              {{ fileEditorMode === 'create' ? '📎 新建附属文件' : fileEditorMode === 'edit' ? '📎 编辑文件' : '📎 查看文件' }}
            </span>
            <button class="btn-icon" @click="closeFileEditor">✕</button>
          </div>
          <div class="modal-body" style="display: flex; flex-direction: column; gap: 12px; padding: 16px; height: calc(100% - 60px);">
            <div class="form-group" style="margin: 0;">
              <label class="form-label">文件路径</label>
              <input
                v-model="fileEditorPath"
                class="input"
                :placeholder="'references/api-guide.md'"
                :disabled="fileEditorMode === 'view' || fileEditorMode === 'edit'"
                style="font-family: monospace;"
              />
              <div class="file-path-hints" v-if="fileEditorMode === 'create'">
                <span class="hint-label">快捷前缀：</span>
                <button class="hint-btn" @click="fileEditorPath = 'references/'">📚 references/</button>
                <button class="hint-btn" @click="fileEditorPath = 'templates/'">📝 templates/</button>
                <button class="hint-btn" @click="fileEditorPath = 'scripts/'">⚙️ scripts/</button>
                <button class="hint-btn" @click="fileEditorPath = 'assets/'">📦 assets/</button>
              </div>
            </div>
            <div style="flex: 1; display: flex; flex-direction: column; min-height: 0;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <label class="form-label" style="margin: 0;">内容</label>
                <div class="tab-switch" v-if="fileEditorMode !== 'view'">
                  <button class="tab-btn-sm" :class="{ active: !fileEditorPreview }" @click="fileEditorPreview = false">源码</button>
                  <button class="tab-btn-sm" :class="{ active: fileEditorPreview }" @click="fileEditorPreview = true">预览</button>
                </div>
              </div>
              <textarea
                v-if="!fileEditorPreview && fileEditorMode !== 'view'"
                v-model="fileEditorContent"
                class="textarea"
                style="flex: 1; font-family: monospace; resize: none;"
                placeholder="文件内容..."
              ></textarea>
              <div v-else-if="fileEditorPreview" class="preview-pane" style="flex: 1; overflow-y: auto;" v-html="renderMd(fileEditorContent)"></div>
              <div v-else style="flex: 1; display: flex; flex-direction: column; min-height: 0;">
                <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                  <div class="tab-switch">
                    <button class="tab-btn-sm" :class="{ active: !fileEditorPreview }" @click="fileEditorPreview = false">源码</button>
                    <button class="tab-btn-sm" :class="{ active: fileEditorPreview }" @click="fileEditorPreview = true">预览</button>
                  </div>
                </div>
                <pre v-if="!fileEditorPreview" class="file-view-content">{{ fileEditorContent }}</pre>
                <div v-else class="preview-pane" style="flex: 1; overflow-y: auto;" v-html="renderMd(fileEditorContent)"></div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeFileEditor">{{ fileEditorMode === 'view' ? '关闭' : '取消' }}</button>
            <button v-if="fileEditorMode !== 'view'" class="btn btn-primary" @click="handleSaveFile" :disabled="fileEditorSaving">
              {{ fileEditorSaving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- 待创建文件编辑弹窗 -->
    <teleport to="body">
      <div v-if="showPendingFileEditor" class="modal-overlay" @click.self="closePendingFileEditor">
        <div class="modal" style="max-width: 900px; width: 90vw; height: 80vh;">
          <div class="modal-header">
            <span class="modal-title">
              {{ pendingFileEditorIndex === -1 ? '📎 新建附属文件' : '📎 编辑附属文件' }}
            </span>
            <button class="btn-icon" @click="closePendingFileEditor">✕</button>
          </div>
          <div class="modal-body" style="display: flex; flex-direction: column; gap: 12px; padding: 16px; height: calc(100% - 60px);">
            <div class="form-group" style="margin: 0;">
              <label class="form-label">文件路径</label>
              <input
                v-model="fileEditorPath"
                class="input"
                :placeholder="'references/api-guide.md'"
                style="font-family: monospace;"
              />
              <div class="file-path-hints">
                <span class="hint-label">快捷前缀：</span>
                <button class="hint-btn" @click="fileEditorPath = 'references/'">📚 references/</button>
                <button class="hint-btn" @click="fileEditorPath = 'templates/'">📝 templates/</button>
                <button class="hint-btn" @click="fileEditorPath = 'scripts/'">⚙️ scripts/</button>
                <button class="hint-btn" @click="fileEditorPath = 'assets/'">📦 assets/</button>
              </div>
            </div>
            <div style="flex: 1; display: flex; flex-direction: column; min-height: 0;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <label class="form-label" style="margin: 0;">内容</label>
                <div class="tab-switch">
                  <button class="tab-btn-sm" :class="{ active: !fileEditorPreview }" @click="fileEditorPreview = false">源码</button>
                  <button class="tab-btn-sm" :class="{ active: fileEditorPreview }" @click="fileEditorPreview = true">预览</button>
                </div>
              </div>
              <textarea
                v-if="!fileEditorPreview"
                v-model="fileEditorContent"
                class="textarea"
                style="flex: 1; font-family: monospace; resize: none;"
                placeholder="文件内容..."
              ></textarea>
              <div v-else class="preview-pane" style="flex: 1; overflow-y: auto;" v-html="renderMd(fileEditorContent)"></div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closePendingFileEditor">取消</button>
            <button class="btn btn-primary" @click="savePendingFile">确定</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import * as SkillAPI from '../api/skills'
import { useAuthStore } from '../stores/auth'
import request from '../api/request'
import { errMsg } from '@/utils/err'

const authStore = useAuthStore()
const isSuperAdmin = computed(() => authStore.userRole === 'super_admin')
const canManageAll = computed(() => isSuperAdmin.value || authStore.hasPerm('skill.manage'))
const canCreate = computed(() => authStore.hasPerm('skill.create'))

// 判断用户是否可以发布技能
// 规则：有 skill.create 权限且是自己创建的技能，或管理员可以发布任何技能
function canPublishSkill(skill: any): boolean {
  if (viewMode.value === 'ai') return false  // AI 技能不能发布
  if (canManageAll.value) return true  // 管理员可以发布任何技能
  if (!canCreate.value) return false  // 没有 skill.create 权限不能发布
  // 有 skill.create 权限的用户可以发布自己的技能
  return Number(skill.owner_id) === Number(authStore.userId)
}

// Tab 状态
const activeTab = ref<'my' | 'pool' | 'installed'>('my')
const viewMode = ref<'mine' | 'all' | 'ai'>('mine')

// 数据
const loading = ref(false)
const mySkills = ref<any[]>([])
const allSkills = ref<any[]>([])
const aiSkills = ref<any[]>([])
const poolAvailable = ref<any[]>([])
const poolInstalled = ref<any[]>([])
const myPoolRecords = ref<any[]>([])
const userCategories = ref<string[]>([])
const selected = ref<any>(null)

// 搜索和过滤
const search = ref('')
const activeCategory = ref('')

// 分类编辑
const showCatInput = ref(false)
const newCatName = ref('')
const editingCat = ref('')
const editCatName = ref('')
const catMenuOpen = ref('')

// 编辑器
const showEditor = ref(false)
const editMode = ref(false)
const saving = ref(false)
const editorPreview = ref(false)
const form = ref({ name: '', description: '', content: '', category: '' })

// 拒绝相关
const showRejected = ref(false)

// 附属文件管理
const showFileEditor = ref(false)
const fileEditorMode = ref<'view' | 'edit' | 'create'>('view')
const fileEditorSaving = ref(false)
const fileEditorPath = ref('')
const fileEditorContent = ref('')
const fileEditorPreview = ref(false)

// 上传相关
const isDragging = ref(false)
const uploadTargetDir = ref('references')
const isUploading = ref(false)

// 创建技能时的待添加文件
interface PendingFile {
  path: string
  content: string
  isBinary: boolean
  file?: File  // 对于上传的二进制文件
}
const pendingFiles = ref<PendingFile[]>([])
const pendingFileTargetDir = ref('references')
const pendingFileEditorIndex = ref(-1)  // -1 表示新建，>= 0 表示编辑现有文件
const showPendingFileEditor = ref(false)

// 目录说明
const DIRECTORY_INFO: Record<string, { icon: string; desc: string }> = {
  'references': { icon: '📚', desc: '参考文档 — 按需加载的详细资料（API 文档、配置指南、最佳实践等）' },
  'templates': { icon: '📝', desc: '输出模板 — 技能生成的标准格式（报告模板、邮件模板、代码模板等）' },
  'scripts': { icon: '⚙️', desc: '功能脚本 — 可执行的 Python/Shell 脚本' },
  'assets': { icon: '📦', desc: '配置和数据 — 配置文件、数据文件、静态资源等' },
}

// 文件类型判断
function isImageFile(path: string): boolean {
  return /\.(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(path)
}

function isBinaryFile(path: string): boolean {
  return /\.(pdf|zip|tar|gz|rar|7z|exe|dll|so|dylib|bin|dat|db|sqlite)$/i.test(path) || isImageFile(path)
}

function getFileIcon(path: string): string {
  if (isImageFile(path)) return '🖼️'
  if (path.endsWith('.py')) return '🐍'
  if (path.endsWith('.js') || path.endsWith('.ts')) return '📜'
  if (path.endsWith('.json')) return '📋'
  if (path.endsWith('.md')) return '📄'
  if (path.endsWith('.pdf')) return '📕'
  if (path.endsWith('.sh') || path.endsWith('.bat')) return '⚡'
  if (isBinaryFile(path)) return '📦'
  return '📄'
}

// 快捷模板
const QUICK_TEMPLATES = [
  { path: 'references/api-guide.md', content: '# API 参考文档\n\n## 接口列表\n\n### GET /api/example\n\n**描述**: 示例接口\n\n**参数**:\n- `param1` (string, required): 参数说明\n\n**返回**:\n```json\n{\n  "code": 200,\n  "data": {}\n}\n```\n' },
  { path: 'templates/report.md', content: '# {{title}}\n\n**生成时间**: {{date}}\n**作者**: {{author}}\n\n---\n\n## 摘要\n\n{{summary}}\n\n## 详细内容\n\n{{content}}\n\n## 结论\n\n{{conclusion}}\n' },
  { path: 'scripts/example.py', content: '#!/usr/bin/env python3\n"""示例脚本"""\n\ndef main():\n    print("Hello from skill script!")\n\nif __name__ == "__main__":\n    main()\n' },
  { path: 'assets/config.json', content: '{\n  "name": "example",\n  "version": "1.0.0",\n  "settings": {\n    "debug": false,\n    "timeout": 30\n  }\n}\n' },
]

const rejectedItems = computed(() => {
  return myPoolRecords.value.filter(r => r.status === 'rejected')
})

function getPoolStatus(name: string): string {
  const record = myPoolRecords.value.find(r => r.content_name === name)
  return record?.status || ''
}

function getPoolStatusText(status: string): string {
  const map: Record<string, string> = {
    'pending': '待审核',
    'active': '已上架',
    'rejected': '已拒绝'
  }
  return map[status] || ''
}

function formatTime(date: string): string {
  if (!date) return ''
  return new Date(date).toLocaleString('zh-CN')
}

async function republishSkill(name: string) {
  if (!confirm('确定重新发布此技能？')) return
  try {
    const resp: any = await SkillAPI.publishToPool(name)
    alert(resp && resp.status === 'active' ? '✅ 已重新发布并直接上架（您拥有审核权限，无需审核）' : '已重新发布，等待审核')
    await loadSkills()
  } catch (e) {
    alert('发布失败: ' + errMsg(e))
  }
}

// 计算属性
const filteredList = computed(() => {
  if (viewMode.value === 'ai') return aiSkills.value
  let list = viewMode.value === 'mine' ? mySkills.value : allSkills.value

  // 搜索过滤
  if (search.value) {
    const q = search.value.toLowerCase()
    if (viewMode.value === 'all') {
      // 全部用户模式：搜索用户名和技能名
      list = list.filter(s =>
        s.name.toLowerCase().includes(q) ||
        (s.owner_name || '').toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q)
      )
    } else {
      // 我的模式：只搜索技能名和描述
      list = list.filter(s =>
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q)
      )
    }
  }

  // 分类过滤
  if (activeCategory.value) {
    list = list.filter(s => (s.category || '') === activeCategory.value)
  }

  return list
})

// 按用户分组（管理员视图）
const groupedByUser = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const s of filteredList.value) {
    const uname = s.owner_name || '未知'
    if (!groups[uname]) groups[uname] = []
    groups[uname].push(s)
  }
  return Object.entries(groups)
    .sort((a, b) => b[1].length - a[1].length)
    .map(([name, skills]) => ({ name, count: skills.length, skills }))
})

// 工具集定义（与后端 TOOLSET_DEFINITIONS 同步）
const TOOLSET_DEFINITIONS = [
  { key: 'terminal', label: '终端执行', desc: '执行 Shell 命令' },
  { key: 'file', label: '文件读写', desc: '读写文件' },
  { key: 'web', label: '网络搜索', desc: '搜索网页和抓取 URL' },
  { key: 'email', label: '邮件收发', desc: '发送/接收邮件' },
  { key: 'data', label: '数据查询', desc: '数据库查询操作' },
  { key: 'notification', label: '通知推送', desc: '消息通知推送' },
  { key: 'schedule', label: '定时任务', desc: '定时任务管理' },
]

// 选中技能的依赖工具集
const skillToolsets = computed(() => {
  if (!selected.value) return []
  
  // 从 frontmatter 获取 requires_toolsets
  const frontmatter = selected.value.frontmatter || {}
  const hermesMeta = (frontmatter.metadata || {}).hermes || {}
  const requiresToolsets: string[] = hermesMeta.requires_toolsets || []
  
  // 获取用户当前拥有的 toolset 权限
  const userToolsets: string[] = JSON.parse(localStorage.getItem('userToolsets') || '[]')
  const userRole = localStorage.getItem('userRole') || ''
  // utility 已改为 __always_available__，所有用户自动可用
  const ALWAYS_AVAILABLE = new Set(['utility'])

  return requiresToolsets.map(key => {
    const def = TOOLSET_DEFINITIONS.find(t => t.key === key) || { key, label: key, desc: '' }
    return {
      ...def,
      hasPermission: ALWAYS_AVAILABLE.has(key) || userRole === 'super_admin' || userToolsets.includes(key)
    }
  })
})

// 待创建文件按目录分组
const pendingFilesGrouped = computed(() => {
  const groups: Record<string, PendingFile[]> = {}
  for (const f of pendingFiles.value) {
    const parts = f.path.split('/')
    const dir = parts.length > 1 ? parts[0] : '(根目录)'
    if (!groups[dir]) groups[dir] = []
    groups[dir].push(f)
  }
  // 按目录说明顺序排序
  const order = ['references', 'templates', 'scripts', 'assets']
  const sorted = Object.entries(groups).sort((a, b) => {
    const ai = order.indexOf(a[0])
    const bi = order.indexOf(b[0])
    if (ai >= 0 && bi >= 0) return ai - bi
    if (ai >= 0) return -1
    if (bi >= 0) return 1
    return a[0].localeCompare(b[0])
  })
  return sorted
})

// 方法
async function loadSkills() {
  loading.value = true
  try {
    const data = await SkillAPI.listSkills()
    mySkills.value = data.my_skills || []
    allSkills.value = data.all_skills || []
    aiSkills.value = data.ai_skills || []
    poolAvailable.value = data.pool_available || []
    poolInstalled.value = data.pool_installed || []
    myPoolRecords.value = data.my_pool_records || []
    userCategories.value = data.categories || []
    
    // 调试：打印当前用户 ID 和技能所有者 ID
    console.log('[loadSkills] userId:', authStore.userId, 'mySkills:', mySkills.value.map(s => ({ name: s.name, owner_id: s.owner_id })))
  } catch (e) {
    console.error('加载技能失败:', e)
  } finally {
    loading.value = false
  }
}

async function selectSkill(name: string) {
  try {
    selected.value = await SkillAPI.getSkill(name)
  } catch (e) {
    console.error('加载技能详情失败:', e)
  }
}

function renderMd(text: string) {
  if (!text) return ''
  // marked v15 无异步扩展时 parse 同步返回 string（类型为 string | Promise<string>，运行时恒为 string）
  return DOMPurify.sanitize(marked.parse(text) as string)
}

function stripFrontmatter(text: string) {
  if (!text || !text.startsWith('---')) return text
  const end = text.indexOf('---', 3)
  if (end === -1) return text
  let body = text.slice(end + 3)
  if (body.startsWith('\n')) body = body.slice(1)
  return body
}

// 技能操作
function openCreate() {
  editMode.value = false
  editorPreview.value = false
  form.value = { name: '', description: '', content: '', category: '' }
  pendingFiles.value = []  // 重置待创建文件
  pendingFileTargetDir.value = 'references'
  showEditor.value = true
}

async function openEdit(name: string) {
  editMode.value = true
  editorPreview.value = false
  try {
    const skill = await SkillAPI.getSkill(name)
    form.value = {
      name: skill.name,
      description: skill.description,
      content: skill.content,
      category: skill.frontmatter?.category || skill.category || ''
    }
    showEditor.value = true
  } catch (e) {
    alert('加载技能失败: ' + (e as Error).message)
  }
}

function closeEditor() {
  showEditor.value = false
}

// ── 待创建文件处理 ──

function addPendingFile() {
  pendingFileEditorIndex.value = -1
  fileEditorPath.value = pendingFileTargetDir.value + '/'
  fileEditorContent.value = ''
  fileEditorPreview.value = false
  showPendingFileEditor.value = true
}

function addQuickTemplate(template: { path: string; content: string }) {
  // 检查是否已存在
  if (pendingFiles.value.some(f => f.path === template.path)) {
    alert(`文件 ${template.path} 已存在`)
    return
  }
  pendingFiles.value.push({
    path: template.path,
    content: template.content,
    isBinary: false
  })
}

function editPendingFile(file: PendingFile) {
  const index = pendingFiles.value.findIndex(f => f.path === file.path)
  if (index === -1) return
  
  pendingFileEditorIndex.value = index
  fileEditorPath.value = file.path
  fileEditorContent.value = file.content
  fileEditorPreview.value = false
  showPendingFileEditor.value = true
}

function removePendingFile(file: PendingFile) {
  if (!confirm(`确定删除文件 "${file.path}"？`)) return
  pendingFiles.value = pendingFiles.value.filter(f => f.path !== file.path)
}

async function handlePendingFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  
  for (const file of Array.from(files)) {
    const path = pendingFileTargetDir.value + '/' + file.name
    // 检查是否已存在
    if (pendingFiles.value.some(f => f.path === path)) {
      alert(`文件 ${path} 已存在，跳过`)
      continue
    }
    
    // 读取文件内容
    const isBinary = isBinaryFile(file.name)
    if (isBinary) {
      pendingFiles.value.push({
        path,
        content: '',
        isBinary: true,
        file
      })
    } else {
      const content = await file.text()
      pendingFiles.value.push({
        path,
        content,
        isBinary: false
      })
    }
  }
  
  input.value = ''  // 重置以便可以再次选择同一文件
}

function savePendingFile() {
  if (!fileEditorPath.value.trim()) {
    alert('请输入文件路径')
    return
  }
  
  // 检查路径是否已存在（编辑时排除自己）
  const existingIndex = pendingFiles.value.findIndex(f => f.path === fileEditorPath.value)
  if (existingIndex !== -1 && existingIndex !== pendingFileEditorIndex.value) {
    alert(`文件 ${fileEditorPath.value} 已存在`)
    return
  }
  
  if (pendingFileEditorIndex.value === -1) {
    // 新建
    pendingFiles.value.push({
      path: fileEditorPath.value,
      content: fileEditorContent.value,
      isBinary: false
    })
  } else {
    // 编辑
    pendingFiles.value[pendingFileEditorIndex.value] = {
      path: fileEditorPath.value,
      content: fileEditorContent.value,
      isBinary: false
    }
  }
  
  showPendingFileEditor.value = false
}

function closePendingFileEditor() {
  showPendingFileEditor.value = false
}

async function handleSave() {
  if (!form.value.name || !form.value.content) {
    alert('名称和内容不能为空')
    return
  }
  saving.value = true
  try {
    if (editMode.value) {
      await SkillAPI.updateSkill(form.value.name, form.value.content, form.value.category || undefined, form.value.description || undefined)
      alert(`✅ 技能「${form.value.name}」已更新`)
    } else {
      // 创建技能
      await SkillAPI.createSkill(form.value)
      const newSkillName = form.value.name
      
      // 创建待添加的附属文件
      if (pendingFiles.value.length > 0) {
        let successCount = 0
        let errorCount = 0
        
        for (const file of pendingFiles.value) {
          try {
            if (file.isBinary && file.file) {
              // 上传二进制文件
              await SkillAPI.uploadSkillFiles(newSkillName, [file.file], file.path.split('/')[0])
            } else {
              // 创建文本文件
              await SkillAPI.writeSkillFile(newSkillName, file.path, file.content)
            }
            successCount++
          } catch (e) {
            console.error(`创建文件 ${file.path} 失败:`, e)
            errorCount++
          }
        }
        
        if (errorCount > 0) {
          alert(`✅ 技能「${newSkillName}」已创建\n\n附属文件: ${successCount} 个成功, ${errorCount} 个失败`)
        } else {
          alert(`✅ 技能「${newSkillName}」已创建\n\n成功创建 ${successCount} 个附属文件`)
        }
      } else {
        alert(`✅ 技能「${newSkillName}」已创建`)
      }
      
      // 加载并选中新技能
      await loadSkills()
      closeEditor()
      const allSkillsList = [...mySkills.value, ...allSkills.value]
      const newSkill = allSkillsList.find(s => s.name === newSkillName)
      if (newSkill) {
        await selectSkill(newSkillName)
      }
      return
    }
    closeEditor()
    await loadSkills()
  } catch (e) {
    alert('保存失败: ' + (e as Error).message)
  } finally {
    saving.value = false
  }
}

async function handleDelete(name: string) {
  if (!confirm(`确定删除技能 "${name}"？此操作不可恢复。`)) return
  try {
    await SkillAPI.deleteSkill(name)
    if (selected.value?.name === name) selected.value = null
    await loadSkills()
    alert(`✅ 技能「${name}」已删除`)
  } catch (e) {
    alert('删除失败: ' + (e as Error).message)
  }
}

// ── 附属文件管理 ──

// 将文件列表按目录分组
const skillFilesGrouped = computed(() => {
  const files: string[] = selected.value?.files || []
  const groups: Record<string, string[]> = {}
  for (const f of files) {
    const parts = f.split('/')
    const dir = parts.length > 1 ? parts[0] : '(根目录)'
    if (!groups[dir]) groups[dir] = []
    groups[dir].push(f)
  }
  // 按目录说明顺序排序：references > templates > scripts > assets > 其他
  const order = ['references', 'templates', 'scripts', 'assets']
  const sorted = Object.entries(groups).sort((a, b) => {
    const ai = order.indexOf(a[0])
    const bi = order.indexOf(b[0])
    if (ai >= 0 && bi >= 0) return ai - bi
    if (ai >= 0) return -1
    if (bi >= 0) return 1
    return a[0].localeCompare(b[0])
  })
  return sorted
})

async function openViewFile(filePath: string) {
  if (!selected.value) return
  try {
    const resp = await SkillAPI.getSkillFile(selected.value.name, filePath)
    fileEditorMode.value = 'view'
    fileEditorPath.value = filePath
    fileEditorContent.value = resp.content
    fileEditorPreview.value = false
    showFileEditor.value = true
  } catch (e) {
    alert('读取文件失败: ' + (e as Error).message)
  }
}

async function openEditFile(filePath: string) {
  if (!selected.value) return
  try {
    const resp = await SkillAPI.getSkillFile(selected.value.name, filePath)
    fileEditorMode.value = 'edit'
    fileEditorPath.value = filePath
    fileEditorContent.value = resp.content
    fileEditorPreview.value = false
    showFileEditor.value = true
  } catch (e) {
    alert('读取文件失败: ' + (e as Error).message)
  }
}

function openCreateFile() {
  fileEditorMode.value = 'create'
  fileEditorPath.value = 'references/'
  fileEditorContent.value = ''
  fileEditorPreview.value = false
  showFileEditor.value = true
}

function closeFileEditor() {
  showFileEditor.value = false
}

async function handleSaveFile() {
  if (!selected.value) return
  if (!fileEditorPath.value.trim()) {
    alert('请输入文件路径')
    return
  }
  fileEditorSaving.value = true
  try {
    await SkillAPI.writeSkillFile(selected.value.name, fileEditorPath.value, fileEditorContent.value)
    alert(`✅ 文件已${fileEditorMode.value === 'create' ? '创建' : '保存'}`)
    closeFileEditor()
    // 刷新技能详情以更新文件列表
    await selectSkill(selected.value.name)
  } catch (e) {
    alert('保存失败: ' + (e as Error).message)
  } finally {
    fileEditorSaving.value = false
  }
}

async function handleDeleteFile(filePath: string) {
  if (!selected.value) return
  if (!confirm(`确定删除文件 "${filePath}"？此操作不可恢复。`)) return
  try {
    await SkillAPI.deleteSkillFile(selected.value.name, filePath)
    alert(`✅ 文件已删除`)
    // 刷新技能详情
    await selectSkill(selected.value.name)
  } catch (e) {
    alert('删除失败: ' + (e as Error).message)
  }
}

// ── 文件上传 ──

function handleDragOver(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = true
}

function handleDragLeave(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = false
}

async function handleDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = false
  
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
}

async function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  input.value = '' // 重置以便可以再次选择同一文件
}

async function uploadFiles(files: File[]) {
  if (!selected.value) return
  isUploading.value = true
  try {
    const result = await SkillAPI.uploadSkillFiles(selected.value.name, files, uploadTargetDir.value)
    if (result.errors.length > 0) {
      alert(`⚠️ 部分文件上传失败:\n${result.errors.join('\n')}`)
    } else {
      alert(`✅ 成功上传 ${result.uploaded.length} 个文件`)
    }
    // 刷新技能详情
    await selectSkill(selected.value.name)
  } catch (e) {
    alert('上传失败: ' + (e as Error).message)
  } finally {
    isUploading.value = false
  }
}

async function createQuickTemplate(template: typeof QUICK_TEMPLATES[0]) {
  if (!selected.value) return
  try {
    await SkillAPI.writeSkillFile(selected.value.name, template.path, template.content)
    alert(`✅ 已创建模板文件: ${template.path}`)
    await selectSkill(selected.value.name)
  } catch (e) {
    alert('创建失败: ' + (e as Error).message)
  }
}

function getSkillFileDownloadUrl(name: string, filePath: string): string {
  return SkillAPI.getSkillFileDownloadUrl(name, filePath)
}

async function handleLock(name: string) {
  try {
    await SkillAPI.lockSkill(name)
    if (selected.value?.name === name) selected.value.locked = true
    alert(`✅ 技能 "${name}" 已锁定`)
    await loadSkills()
  } catch (e) {
    alert('锁定失败: ' + (e as Error).message)
  }
}

async function handleUnlock(name: string) {
  try {
    await SkillAPI.unlockSkill(name)
    if (selected.value?.name === name) selected.value.locked = false
    alert(`✅ 技能 "${name}" 已解锁`)
    await loadSkills()
  } catch (e) {
    alert('解锁失败: ' + (e as Error).message)
  }
}

async function handlePublish(name: string) {
  if (!confirm(`确定将技能 "${name}" 发布到技能池？`)) return
  try {
    const resp: any = await SkillAPI.publishToPool(name)
    alert(resp && resp.status === 'active'
      ? `✅ 技能 "${name}" 已发布并直接上架（您拥有审核权限，无需审核）`
      : `技能 "${name}" 已发布到技能池，等待管理员审核`)
  } catch (e) {
    alert('发布失败: ' + errMsg(e))
  }
}

// 池操作
async function handleInstallPool(name: string) {
  try {
    await SkillAPI.installFromPool(name)
    alert(`技能 "${name}" 已安装`)
    await loadSkills()
  } catch (e) {
    alert('安装失败: ' + (e as Error).message)
  }
}

async function handleUninstallPool(name: string) {
  if (!confirm(`确定卸载技能 "${name}"？`)) return
  try {
    await SkillAPI.uninstallFromPool(name)
    alert(`技能 "${name}" 已卸载`)
    await loadSkills()
  } catch (e) {
    alert('卸载失败: ' + (e as Error).message)
  }
}

// 分类操作
function openCatInput() {
  showCatInput.value = true
  newCatName.value = ''
  nextTick(() => {
    const input = document.querySelector('.cat-input') as HTMLInputElement
    input?.focus()
  })
}

async function handleCreateCategory() {
  const name = newCatName.value.trim()
  if (!name) {
    showCatInput.value = false
    return
  }
  try {
    await request.post('/api/skills/my-categories', { category: name })
    userCategories.value.push(name)
    userCategories.value.sort()
    activeCategory.value = name
    showCatInput.value = false
    newCatName.value = ''
    alert(`✅ 分类「${name}」已创建`)
  } catch (e) {
    alert('创建分类失败: ' + errMsg(e))
  }
}

function toggleCatMenu(cat: string) {
  catMenuOpen.value = catMenuOpen.value === cat ? '' : cat
}

function startRenameCat(cat: string) {
  catMenuOpen.value = ''
  editingCat.value = cat
  editCatName.value = cat
  nextTick(() => {
    const input = document.querySelector('.cat-input') as HTMLInputElement
    input?.focus()
  })
}

async function handleRenameCategory(oldName: string) {
  const newName = editCatName.value.trim()
  if (!newName || newName === oldName) {
    editingCat.value = ''
    editCatName.value = ''
    return
  }
  try {
    await request.put(`/api/skills/my-categories/${encodeURIComponent(oldName)}/rename`, { new_name: newName })
    const idx = userCategories.value.indexOf(oldName)
    if (idx !== -1) userCategories.value[idx] = newName
    userCategories.value.sort()
    if (activeCategory.value === oldName) activeCategory.value = newName
    editingCat.value = ''
    editCatName.value = ''
    alert(`✅ 分类已重命名为「${newName}」`)
  } catch (e) {
    alert('重命名失败: ' + errMsg(e))
    editingCat.value = ''
  }
}

async function handleDeleteCategory(cat: string) {
  catMenuOpen.value = ''
  if (!confirm(`确定删除分类 "${cat}"？（不会删除技能，只移除分类标签）`)) return
  try {
    await request.delete(`/api/skills/my-categories/${encodeURIComponent(cat)}`)
    userCategories.value = userCategories.value.filter(c => c !== cat)
    if (activeCategory.value === cat) activeCategory.value = ''
    alert(`✅ 分类「${cat}」已删除`)
  } catch (e) {
    alert('删除失败: ' + errMsg(e))
  }
}

onMounted(loadSkills)
</script>

<style scoped>
.page-container { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-title { margin: 0 0 4px 0; font-size: 24px; font-weight: 600; }
.page-desc { margin: 0; color: var(--text-tertiary); font-size: 13px; }

/* 已拒绝区域 */
.rejected-section { margin-bottom: 20px; padding: 16px; background: #fff5f5; border: 1px solid #ffcdd2; border-radius: 8px; }
.rejected-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-weight: 600; color: #c62828; }
.rejected-list { max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.rejected-item { padding: 12px; background: white; border-radius: 6px; display: flex; align-items: center; gap: 12px; }
.rejected-name { font-weight: 600; min-width: 120px; }
.rejected-reason { flex: 1; color: var(--text-secondary); font-size: 13px; }
.rejected-time { color: var(--text-tertiary); font-size: 12px; }

/* 状态徽章 */
.status-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-left: 6px; }
.status-pending { background: #fff3e0; color: #e65100; }
.status-active { background: #e8f5e9; color: #2e7d32; }
.status-rejected { background: #ffebee; color: #c62828; }

/* Tab 导航 */
.tab-bar { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border-primary); }
.tab-btn { padding: 10px 20px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-secondary); font-size: 14px; cursor: pointer; transition: all 0.15s; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { color: var(--brand); border-bottom-color: var(--brand); }
.tab-count { font-size: 12px; color: var(--text-tertiary); }

/* Tab 内容 */
.tab-content { }

/* 视图切换 */
.view-switcher-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.view-switcher { display: flex; gap: 4px; }
.view-btn { padding: 6px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; font-size: 13px; cursor: pointer; transition: all 0.15s; }
.view-btn:hover { background: var(--bg-hover); }
.view-btn.active { background: var(--brand); color: white; border-color: var(--brand); }

/* 搜索 */
.search-bar-inline { flex: 1; max-width: 360px; }
.search-bar-inline .search-input { 
  padding: 8px 14px; 
  font-size: 14px; 
  border: 1px solid var(--border-primary); 
  border-radius: 8px; 
  background: var(--bg-primary); 
  transition: var(--transition);
}
.search-bar-inline .search-input:focus { 
  outline: none; 
  border-color: var(--brand); 
  box-shadow: 0 0 0 3px rgba(var(--brand-rgb, 59, 130, 246), 0.15);
}
.search-bar-inline .search-input::placeholder { 
  color: var(--text-tertiary); 
}
.search-bar { margin-bottom: 12px; }
.search-input { width: 100%; }

/* 分类栏 */
.category-bar { display: flex; gap: 6px; padding: 10px 0 16px; flex-wrap: wrap; }
.category-tag { padding: 5px 14px; border: 1px solid var(--border-primary); border-radius: 20px; background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: var(--transition); }
.category-tag:hover { background: var(--bg-hover); }
.category-tag.active { background: var(--brand); color: #fff; border-color: var(--brand); }
.category-tag-wrap { position: relative; display: flex; align-items: center; }
.cat-more { padding: 5px 8px; font-size: 14px; font-weight: 700; border-radius: 0 20px 20px 0; border-left: none; margin-left: -1px; }
.cat-input { padding: 5px 10px; border: 1px solid var(--brand); border-radius: 20px; background: transparent; color: var(--text-primary); font-size: 12px; width: 100px; outline: none; }
.cat-confirm { color: var(--success, #22c55e); border-color: var(--success, #22c55e); }
.cat-cancel { color: var(--text-tertiary); }
.cat-add { border-style: dashed; opacity: 0.6; }
.cat-popup { position: absolute; top: 100%; left: 0; margin-top: 4px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); z-index: 100; min-width: 120px; padding: 4px; }
.cat-popup button { display: block; width: 100%; padding: 6px 12px; border: none; background: transparent; color: var(--text-primary); font-size: 12px; text-align: left; cursor: pointer; border-radius: 4px; }
.cat-popup button:hover { background: var(--bg-hover); }
.cat-danger { color: var(--danger, #ef4444); }

/* 技能布局 */
.skill-layout { display: grid; grid-template-columns: 320px 1fr; gap: 20px; height: calc(100vh - 360px); min-height: 400px; }
.skill-layout-large { grid-template-columns: 380px 1fr; height: calc(100vh - 280px); min-height: 500px; }
.skill-layout-tall { height: calc(100vh - 240px); min-height: 550px; }
.card { background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
.skill-list-card { }
.skill-list-large { }
.skill-detail-card { }
.skill-detail-large { }
.skill-detail-tall { }
.card-header { padding: 12px 16px; border-bottom: 1px solid var(--border-primary); font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.card-body { padding: 16px; flex: 1; overflow-y: auto; }

/* 技能列表 */
.skill-list { flex: 1; overflow-y: auto; }
.skill-item { padding: 12px 16px; border-bottom: 1px solid var(--border-primary); cursor: pointer; transition: var(--transition); }
.skill-item:hover { background: var(--bg-hover); }
.skill-item.active { background: var(--brand-light); border-left: 3px solid var(--brand); }
.skill-item-name { font-size: 13px; font-weight: 500; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; }
.skill-item-desc { font-size: 12px; color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.skill-item-actions { display: flex; gap: 4px; margin-top: 4px; opacity: 0; transition: opacity 0.15s; }
.skill-item:hover .skill-item-actions { opacity: 1; }

/* 用户分组 */
.user-group { }
.skill-group-header { padding: 8px 16px; font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); position: sticky; top: 0; z-index: 1; }
.group-count { font-size: 11px; color: var(--text-tertiary); font-weight: 400; text-transform: none; letter-spacing: 0; }

/* 徽章 */
.lock-badge { margin-left: 4px; font-size: 11px; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-danger { background: #ffebee; color: #c62828; }

/* 按钮 */
.btn { padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid var(--border-primary); transition: var(--transition); }
.btn-primary { background: var(--brand-gradient); color: white; border: none; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg-secondary); color: var(--text-primary); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-warning { background: #fff3e0; color: #e65100; border-color: #ffe0b2; }
.btn-success { background: #e8f5e9; color: #2e7d32; border-color: #c8e6c9; }
.btn-danger { background: #ffebee; color: #c62828; border-color: #ffcdd2; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px 6px; border-radius: 4px; font-size: 14px; transition: var(--transition); }
.btn-icon:hover { background: var(--bg-hover); }
.btn-danger-icon:hover { background: var(--bg-danger) !important; }

/* 详情 */
.detail-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; color: var(--text-tertiary); }
.empty-icon { font-size: 36px; }
.detail-header-left { display: flex; align-items: center; gap: 8px; }
.detail-name { font-size: 15px; font-weight: 600; }
.detail-header-right { display: flex; gap: 8px; }

/* 详情主体 */
.detail-body { padding: 0 4px; }
.detail-section { margin-bottom: 20px; }
.section-label { 
  font-size: 13px; 
  font-weight: 600; 
  color: var(--text-primary); 
  margin-bottom: 10px; 
  display: flex; 
  align-items: center; 
  gap: 6px; 
}

/* 描述区域 */
.description-text { 
  font-size: 14px; 
  color: var(--text-secondary); 
  line-height: 1.6; 
  background: var(--bg-secondary); 
  padding: 12px 16px; 
  border-radius: 8px; 
  border-left: 3px solid var(--brand); 
}

/* 元信息标签 */
.meta-section { margin-bottom: 16px; }
.meta-chips { display: flex; flex-wrap: wrap; gap: 12px; }
.meta-chip { 
  display: flex; 
  align-items: center; 
  gap: 8px; 
  background: var(--bg-secondary); 
  padding: 8px 14px; 
  border-radius: 20px; 
  border: 1px solid var(--border-primary);
}
.chip-icon { font-size: 14px; }
.chip-label { font-size: 12px; color: var(--text-tertiary); }
.chip-value { font-size: 13px; color: var(--text-primary); font-weight: 500; }

/* 工具集区域 */
.toolset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.toolset-item { 
  background: var(--bg-secondary); 
  border: 1px solid var(--border-primary); 
  border-radius: 8px; 
  padding: 10px 12px; 
  transition: var(--transition);
}
.toolset-item:hover { border-color: var(--brand); }
.toolset-item.missing { 
  border-color: #ffcdd2; 
  background: #fff5f5; 
}
.toolset-name { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.toolset-desc { font-size: 11px; color: var(--text-tertiary); }
.toolset-warning { font-size: 11px; color: #c62828; margin-top: 6px; font-weight: 500; }

/* 技能内容 */
.detail-content { 
  line-height: 1.7; 
  background: var(--bg-secondary); 
  border: 1px solid var(--border-primary); 
  border-radius: 8px; 
  padding: 16px; 
  max-height: 400px; 
  overflow-y: auto; 
}
.detail-content :deep(h1), .detail-content :deep(h2), .detail-content :deep(h3) { 
  margin-top: 0; 
  margin-bottom: 12px; 
  color: var(--text-primary); 
}
.detail-content :deep(h1) { font-size: 18px; }
.detail-content :deep(h2) { font-size: 16px; }
.detail-content :deep(h3) { font-size: 14px; }
.detail-content :deep(p) { margin: 0 0 10px 0; }
.detail-content :deep(ul), .detail-content :deep(ol) { margin: 0 0 10px 0; padding-left: 20px; }
.detail-content :deep(pre) { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0; }
.detail-content :deep(code) { background: var(--bg-code); padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.detail-content :deep(pre code) { background: none; padding: 0; }
.detail-content :deep(blockquote) { 
  border-left: 3px solid var(--brand); 
  padding-left: 12px; 
  margin: 10px 0; 
  color: var(--text-secondary); 
}

/* 池卡片 */
.pool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.pool-card { background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 12px; padding: 16px; }
.pool-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.pool-card-header h3 { margin: 0; font-size: 15px; }
.pool-author { font-size: 12px; color: var(--text-tertiary); }
.pool-desc { font-size: 13px; color: var(--text-secondary); margin: 0 0 12px 0; }
.pool-actions { display: flex; gap: 8px; }

/* 状态 */
.loading-state, .empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary); }
.spinner { width: 32px; height: 32px; border: 3px solid var(--border-primary); border-top-color: var(--brand); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty { text-align: center; color: var(--text-tertiary); padding: 40px; }

/* 弹窗 */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-primary); border-radius: 12px; width: 90%; max-height: 90vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-primary); }
.modal-title { font-size: 16px; font-weight: 600; }
.modal-body { padding: 20px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 20px; border-top: 1px solid var(--border-primary); }

/* 表单 */
.form-group { margin-bottom: 14px; }
.form-label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; font-weight: 500; }
.input { width: 100%; padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; }
.input:focus { outline: none; border-color: var(--brand); }
.textarea { width: 100%; padding: 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; resize: none; }
.textarea:focus { outline: none; border-color: var(--brand); }
.preview-pane { flex: 1; overflow-y: auto; padding: 14px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-primary); line-height: 1.7; }
.preview-pane :deep(pre) { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 8px; overflow-x: auto; }
.preview-pane :deep(code) { background: var(--bg-code); padding: 2px 6px; border-radius: 4px; }
.preview-pane :deep(pre code) { background: none; padding: 0; }

/* Tab 切换 */
.tab-switch { display: flex; border: 1px solid var(--border-primary); border-radius: 6px; overflow: hidden; }
.tab-btn-sm { padding: 4px 12px; border: none; background: transparent; color: var(--text-tertiary); font-size: 12px; cursor: pointer; transition: var(--transition); }
.tab-btn-sm.active { background: var(--brand); color: #fff; }

/* 附属文件区域 */
.skill-files-section { 
  margin-top: 20px; 
  padding-top: 20px; 
  border-top: 1px solid var(--border-primary); 
}
.files-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.files-header .section-label { margin-bottom: 0; }
.files-header-actions { display: flex; align-items: center; gap: 8px; }
.input-sm { padding: 4px 8px; font-size: 12px; width: auto; }
.files-groups { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.file-group { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 12px 14px; }
.file-group-header { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border-secondary); }
.file-group-icon { font-size: 14px; }
.file-group-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.file-group-desc { font-size: 11px; color: var(--brand); cursor: help; margin-left: auto; }
.file-list { display: flex; flex-direction: column; gap: 4px; }
.file-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; transition: var(--transition); background: var(--bg-primary); }
.file-item:hover { background: var(--bg-hover); }
.file-icon { font-size: 14px; flex-shrink: 0; }
.file-name { font-size: 13px; color: var(--brand); cursor: pointer; font-family: 'Consolas', 'Monaco', monospace; flex: 1; }
.file-name:hover { text-decoration: underline; }
.file-actions { display: flex; gap: 4px; margin-left: auto; opacity: 0; transition: var(--transition); }
.file-item:hover .file-actions { opacity: 1; }
.btn-icon-sm { background: none; border: none; cursor: pointer; font-size: 12px; padding: 2px 6px; border-radius: 4px; transition: var(--transition); text-decoration: none; display: inline-flex; align-items: center; }
.btn-icon-sm:hover { background: var(--bg-secondary); }
.btn-danger-icon:hover { background: rgba(220, 53, 69, 0.1); }

/* 拖拽上传区域 */
.upload-drop-zone { border: 2px dashed var(--border-primary); border-radius: 8px; padding: 16px; text-align: center; margin-bottom: 12px; transition: var(--transition); cursor: pointer; }
.upload-drop-zone:hover, .upload-drop-zone.active { border-color: var(--brand); background: rgba(var(--brand-rgb, 59, 130, 246), 0.05); }
.upload-hint { display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--text-secondary); font-size: 13px; }
.upload-icon { font-size: 20px; }

/* 快捷模板 */
.quick-templates { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.templates-title { font-size: 13px; font-weight: 500; color: var(--text-primary); margin-bottom: 8px; }
.templates-list { display: flex; flex-wrap: wrap; gap: 8px; }
.template-btn { padding: 6px 12px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-primary); color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: var(--transition); font-family: monospace; }
.template-btn:hover { border-color: var(--brand); color: var(--brand); }

/* 目录说明 */
.directory-guide { background: var(--bg-tertiary, #f5f5f5); border: 1px solid var(--border-primary); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.guide-title { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; }
.guide-items { display: flex; flex-direction: column; gap: 4px; }
.guide-item { font-size: 12px; color: var(--text-primary); display: flex; align-items: baseline; gap: 6px; }
.guide-icon { font-size: 14px; flex-shrink: 0; }
.guide-item strong { color: var(--brand); font-family: monospace; }
.guide-desc { color: var(--text-secondary); }

/* 空状态 */
.files-empty-hint { text-align: center; padding: 20px; color: var(--text-tertiary); font-size: 13px; }

/* 文件编辑弹窗 */
.file-path-hints { display: flex; align-items: center; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.hint-label { font-size: 11px; color: var(--text-tertiary); }
.hint-btn { padding: 2px 8px; border: 1px solid var(--border-primary); border-radius: 4px; background: var(--bg-secondary); color: var(--text-secondary); font-size: 11px; cursor: pointer; transition: var(--transition); }
.hint-btn:hover { border-color: var(--brand); color: var(--brand); }
.file-view-content { flex: 1; overflow-y: auto; padding: 12px; background: #1e1e1e; color: #d4d4d4; border-radius: 6px; font-family: monospace; font-size: 13px; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
