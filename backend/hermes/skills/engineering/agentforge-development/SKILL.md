---
name: agentforge-development
description: AgentForge 项目(Vue3+FastAPI+MySQL)开发模式、验证规则与常见陷阱。
author: AgentForge
category: AI生成
metadata:
  hermes:
    requires_toolsets:
      - file
      - terminal
---

# AgentForge 项目开发

## 项目概况

- **前端**: Vue 3 + Pinia + Vite,从 `agent_frontend/dist` 经 FastAPI 静态服务
- **后端**: FastAPI,`python main.py start 8001`,`reload=False`必须手动重启
- **数据库**: MySQL (`agentforge/agentforge123@localhost:3306`,库 `agentforge`)
- **默认管理员**: `admin/admin123`

## 验证规则（关键）

- **前端无 vitest/jest/eslint**。`package.json` 仅 `dev/build/preview/type-check`。
- **验证门禁**: `npm run build`（exit 0 即通过）+ `vue-tsc --noEmit`（只关注与改动相关的文件；`tsconfig.json` 的 `baseUrl` 弃用警告是既存的,忽略）。
- **后端无 pytest/make test/make lint**。Python 语法验证用 `ast.parse`,模块导入用 `python -c "from xxx import router"`。这就是全部。
- **不要声称能跑更深层的测试**——如实说明项目没有对应设施,给出可用的最强门禁结果。

## 前端核心模式

### Pinia Store & sessionStorage 残留
- `chatStore.currentChatId` 初始值来自 `sessionStorage.getItem('currentChatId')`。
- **陷阱**: 刚进页面时 `messages` 为空,但 `currentChatId` 可能有残留值。
- **影响**: 侧边栏误高亮;`sendMessage` 的 `isNewChat` 用了残留旧 chatId 而不开新会话。
- **修复**: 需要判断时用 `messages.length === 0` 而非只看 `!chatId`。

### chatUserId 丢失 → 会话/技能归属 admin（多层修复）
- `authStore.userId` computed 优先读 `localStorage.chatUserId` → `sessionStorage.chatUserId` → fallback `'1'`（admin）
- **login/register 会写 chatUserId**，但 **verify() 实际从未在应用启动时被调用过**（只有显式调 verify() 才写入）
- **老 session 从未存过 chatUserId**：用户用修复前版本登录后，localStorage 里没 chatUserId → 即使现在 verify() 写了，也不会触发
- **症状**：会话跑到 admin 历史 + 技能创建人变 admin，是**同一个 bug**的两面：`chatUserId` 缺失 → `authStore.userId` fallback 到 `'1'` → 会话 `thread_id='1_...'` 归 admin + 技能创建 `_CURRENT_USER_ID_CTX` 解析到 admin
- **修复（router 兜底）**：`router/index.ts` 的 `beforeEach` 守卫在已认证路由检查 chatUserId 是否存在；缺失时调 `/api/auth/me` 同步。用模块级 `chatUserIdSynced` 标志避免每次路由跳转调接口；失败时重置为 false 下次重试
- **⚠️ `useChat.ts` 构造 thread_id 必须优先用内存中的 user.id**：`const userId = authStore.user?.id || authStore.userId || '1'`。因为 `authStore.userId` 是 computed 读 localStorage，login/logout 切换时 localStorage 可能残留上一用户的值（如 qqq 残留 `2` 被 admin 读取 → admin 会话归到 qqq）。`authStore.user` 是登录接口直接写入的内存对象，最可靠。
- 详细方案、代码、相关文件地图见 `agentforge-dev/references/chatUserId-router-sync.md`

### ChatSidebar & loadChatHistory
- `selectChat` **绝不能**在触发 `chat:loadHistory` 事件前调 `setCurrentChatId`。若提前设置,`loadChatHistory` 里的守卫 `currentChatId === chatId` 会恒成立 → 第二次点击永远跳过。
- 正确做法: 在 `loadChatHistory` 里用 `prevChatId`(进入函数时的值) 做守卫基准。
- **历史选中去重**: 模板高亮和点击去重必须都用 `selectedChatId`(= `messages.length > 0 ? currentChatId : ''`),**不能**用 `currentChatId`。原因: 刚进页面时 `currentChatId` 从 sessionStorage 恢复残留值,若碰巧等于历史第一条的 id,点击第一条时去重 `chatId === currentChatId` 为真 → 直接 return,什么都不做。必须等消息加载后才能让去重判断有意义。
- **历史加载后滚动到底部**: `ChatView.vue` 的 `handleLoadHistory` 必须 `await loadChatHistory(chatId)` 然后 `await nextTick()` + `requestAnimationFrame(() => { scrollToBottom(false); refreshNavState(); })`。**不能**用 `setTimeout(..., 100)`——消息多、含 Markdown/代码块时 Vue DOM 批处理 + 浏览器布局时间远超 100ms，此时 `scrollHeight` 不准确，`scrollTo` 滚不到真正的底部 → 时而底部时而顶部（用户报的 bug）。`nextTick` 等 Vue 更新、`requestAnimationFrame` 等浏览器布局完成，双重保障。`scrollToBottom(false)` 用即时滚动(smooth 会让视觉上有延迟)。注意需要 `import { nextTick } from 'vue'`。

## 技能管理后端 API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/skills` | GET | 列出所有技能（含 category/author/enabled） |
| `/api/skills/categories` | GET | 列出所有分类（去重排序） |
| `/api/skills/{name}` | GET | 技能详情 |
| `/api/skills` | POST | 创建（name/content/description/category） |
| `/api/skills/{name}` | PUT | 更新（content + 可选 category/description；改分类时自动移动目录） |
| `/api/skills/{name}` | DELETE | 删除 |
| `/api/skills/{name}/toggle` | PUT | 启用/禁用 |
| `/api/skills/categories` | POST | 创建空分类目录（超级管理员） |
| `/api/skills/categories/{name}/rename` | PUT | 重命名分类（超级管理员） |
| `/api/skills/categories/{name}` | DELETE | 删除空分类（超级管理员） |
| `/api/skills/pending` | GET | 列出待审核技能（admin+） |
| `/api/skills/{name}/approve` | PUT | 审核通过（admin+） |
| `/api/skills/{name}/reject` | PUT | 审核拒绝（admin+） |
| `/api/skills/{name}/lock` | PUT | 锁定技能（超级管理员） |
| `/api/skills/{name}/unlock` | PUT | 解锁技能（超级管理员） |

### skill_meta 表 — 权限/审核/锁定

```sql
CREATE TABLE skill_meta (
    name        VARCHAR(100) NOT NULL UNIQUE,
    owner_id    BIGINT NOT NULL,       -- 创建者 user_id（AI 创建 = 1）
    category    VARCHAR(50) DEFAULT '其他',
    status      VARCHAR(20) DEFAULT 'approved',  -- pending/approved/rejected
    locked      TINYINT DEFAULT 0,
    reviewed_by BIGINT DEFAULT NULL,
    reviewed_at DATETIME DEFAULT NULL,
    ...
);
```

- **list_skills 过滤规则**: super_admin 看到全部；普通用户只看到 `owner_id == user_id OR owner_id == 1` 且隐藏 `category='AI生成'`。
- **create_skill 状态决策**: AI 创建（`from_agent=True` 或 `category='AI生成'`）→ `approved`；admin/super_admin 用户 → `approved`；普通用户 → `pending`。
- **锁定**: 超级管理员锁定后，非超管用户无法查看该技能详情。
- **审核流**: GET `/pending` 列出待审核；PUT `approve`/`reject` 由管理员操作。
- **分类管理**: 仅超级管理员可创建/重命名/删除分类（`require_super_admin`）。非超管看不到"AI生成"分类。
- **list_skills 与 get_skill 可见性必须一致**: `get_skill` 的权限判断必须和 `list_skills` 完全一致，否则用户看到列表但点不开详情。正确实现：`is_owner = (owner == user_id)` 或 `is_public = (owner == 1 and category != _AI_CATEGORY)`。
- **update_skill / delete_skill 带 user_id/role 参数**: 只能改/删自己的；super_admin 除外。
- **Hermes 内核锁定过滤必须在缓存返回后执行**: `backend/hermes/tools/skills_tool.py` 的 `_find_all_skills` 有文件系统缓存，锁定状态变更不改变文件系统，所以锁过滤不能放在扫描循环里。正确做法：抽出 `_filter_locked_skills()` 辅助函数，在 `return [dict(s) for s in cached[2]]` 和 `return [dict(s) for s in skills]` 两处都调用，确保每次返回前都实时查 `skill_meta` 过滤。`skill_view` 也要在函数入口检查 `locked` 并拒绝。

### update_skill 目录移动逻辑
- `skill_service.update_skill()` 接受可选 `category` 参数
- 若新 category 与旧 category 不同，用 `shutil.move()` 将技能目录移动到新分类子目录
- 目标分类目录自动创建（`mkdir(parents=True)`）

### skill_manager_tool.py — auto-inject + 前台/后台区分

- `_read_creator_defaults()` 根据 `is_background_review()` 返回不同默认值：
  - 前台（用户请求）→ `{"author": "", "category": ""}`（技能对普通用户可见）
  - 后台（自动生成）→ `{"author": "AgentForge", "category": "AI生成"}`
- `_create_skill()` 中仅注入非空的默认值（`defaults.get("author")` / `defaults.get("category")` 判空后才注入）。
- 前台模式下调用 `_strip_agent_frontmatter_defaults(content)` 清理 LLM 输出的 agent 默认值行。
- `final_category` 逻辑：前台为空字符串，后台为 `"AI生成"`。
- **降级**：找不到 `agent-skill-creator` 时，后台回退硬编码 `{"author": "AgentForge", "category": "AI生成"}`，前台回退空字符串。
- **不要在 `_create_skill` 里加后端校验拦截 `skill_manage(create)`**——后端只能读规则注入默认值，不能要求 LLM 走工作流。
- **陷阱**: `_create_skill` 中 `owner_id` 现在从 `_CURRENT_USER_ID_CTX.get() or 1` 获取，`author` 优先从 `_CURRENT_USERNAME_CTX.get()` 获取（`hermes_adapter` 在对话流程中已设置），fallback 到 DB 查询 users 表。
- **⚠️ ContextVar 为空导致 author 注入失效**：如果 `_CURRENT_USERNAME_CTX.get()` 返回空字符串（例如技能创建发生在非对话上下文），`current_username` 为空 → strip+re-inject 逻辑不触发 → frontmatter 缺 author → 前端显示"未知"。**排查时必须验证 ContextVar 是否被正确设置**。DB fallback 路径 `get_conn().cursor()` 会静默失败（`_MySQLAdapter` 没有 `.cursor()` 方法），`except Exception: pass` 吞掉错误后 `current_username` 保持空。正确做法：用 `get_conn().execute("SELECT username FROM users WHERE id = %s", (current_user_id,)).fetchone()` 直接查询。
- **陷阱**: 用户通过对话请求创建技能时，`skill_manage(create)` 已经写入 `skill_meta` 并设置 `status='approved'`，AI **不应该**再调用 `submit_skill_for_review`——这会产生冗余的待审核记录。只有 AI 自己主动生成技能时才需要提交审核。
- 详见 `references/skill-manager-tool-guard.md` 和 `references/skill-provenance.md`

### 两条审核路径（关键差异）

**审核管理页面** vs **技能管理页面** 走的是两条不同的审核代码路径：

| 入口 | 端点 | 处理函数 | 行为 |
|---|---|---|---|
| 审核管理 → 通过 | `/api/review/approve` | `review_service.approve()` | ✅ 从 pending YAML 读取 content，调用 `_inject_author_to_frontmatter()` 注入 author 到 SKILL.md，然后写入 `~/.hermes/skills/` |
| 技能管理 → 审核通过 | `/api/skills/{name}/approve` | `skill_service.approve_skill()` | ❌ **只更新 `skill_meta` 表的 status 字段为 approved，不修改 SKILL.md 文件** |

**影响**：如果 LLM 创建 skill 时 SKILL.md 缺少 author 字段（因为 ContextVar 为空），通过「技能管理」页面审核通过后，SKILL.md 仍然没有 author → 前端显示「未知」。通过「审核管理」页面审核则会注入 author（从 pending YAML 的 `submitted_by` 字段读取）。

**修复**：`_create_skill()` 现在优先从 `_CURRENT_USERNAME_CTX` 读取 username，确保创建时就写入 author。

### 审核逻辑 — 基于权限而非角色

- **旧逻辑（已废弃）**: `role in ['super_admin', 'admin']` → 硬编码角色判断
- **新逻辑**: `has_permission(current_user_id, "skill.direct")` → 检查 `Perm.SKILL_DIRECT` 权限（"直接创建技能，跳过审核"）
- 有 `skill.direct` 权限 → `need_review=False`，无则 `need_review=True`
- 权限检查失败（如 DB 不可用）时静默降级为 `need_review=True`，不阻断创建流程
- 权限定义在 `backend/db/schema.py` 的 `class Perm` 中

### ContextVar 缓存污染 — username 为空导致用户串号

- **症状**: admin 创建 skill 显示为 qqq 创建；会话也归属到 qqq
- **根因**: `chat_controller.py` 查询 `username` 可能失败返回 `None` → `hermes_adapter.py` 第 753 行 `if self.username: _CURRENT_USERNAME_CTX.set(...)` 为 False，跳过更新 → ContextVar 保留上一個用户（qqq）的值
- **修复**: 在 `chat_controller.py` 查询 username 后加 fallback：`if not username: username = f"user_{user_id}"`。确保 `get_runtime()` 始终收到非空 username

### 侧边栏会话排序

- `stores/sidebar.ts` 的 `sortedHistory` 使用 `localeCompare` 排序
- 升序 = 最新在底部 → `timeA.localeCompare(timeB)`
- 降序 = 最新在顶部 → `timeB.localeCompare(timeA)`
- **用户偏好：最新会话在顶部（降序，`timeB.localeCompare(timeA)`）**
- **陷阱**：不要为了"点击会话后聊天区滚动到底部"而去改排序方向。这是两个独立需求——排序控制侧边栏列表顺序，`scrollToBottom` 控制点击后聊天区定位

### 重启命令

- `E:\PythonCode\AgentForge\restart.bat` — 重启前后端
- `E:\PythonCode\AgentForge\restart-all.bat` — 重启前后端 + MySQL

### 多渠道会话展示（微信/飞书/Web）

`conversations` 表有 `source` 列（`web`/`wechat`/`feishu`），多渠道消息统一存入。
- **后端** (`data_controller.py`): 会话列表查询需加 `MAX(c.source) as source`（聚合列，兼容 `ONLY_FULL_GROUP_BY`），标题加前缀 `if source == 'wechat': display_title = '💬 ' + display_title`
- **前端**: `ChatSession` 接口加 `source?: string` 字段，`ChatSidebar` 直接渲染带前缀的标题
- 微信消息由 `wechat_listener.py` 写入，session_id 格式 `wx_{user_id}_{wx_user_id[:12]}`

### API 端点对齐（聊天/会话）
- `/api/history/{chat_id}` — `chat_controller.py`,返回 `{messages: [...]}`
- `/api/data/sessions` — `data_controller.py`,返回 `{sessions: [...], has_more}`
- **常见错误**: 前端 `getChatMessages` 可能请求 `/api/chat/history/` 或 `/api/data/conversations/session/`——这两条后端都**不存在**,返回 404。

### Vue 组件模式
- `<details :open="!message.content">` 是**受控组件**——用户手动 toggle 会被 Vue 响应式覆盖。改用本地 ref `isOpen` + `@toggle` 同步,`userToggled` 标志区分用户操作和 content 变化。
- M-form 消息溢出: `.markdown-body` 需要 `max-width:100%、overflow-x:auto、word-break:break-word`;`.markdown-body pre` 用 `white-space:pre-wrap` 防代码块撑破。

### 技能创建规则（来自 agent-skill-creator）

- **前台用户请求创建**: `author` 和 `category` 字段被自动清空（`_strip_agent_frontmatter_defaults()` 移除 LLM 输出的 `author: AgentForge` / `category: AI生成`）。技能在管理界面对普通用户可见，无强制分类。
- **后台自动生成（background_review）**: `author: AgentForge`、`category: AI生成`。这些技能仅超级管理员可见。
- `_read_creator_defaults()` 根据 `is_background_review()` 决定返回值：前台 → `{"author": "", "category": ""}`；后台 → `{"author": "AgentForge", "category": "AI生成"}`。
- `_create_skill()` 仅注入非空的默认值（`defaults.get("author")` / `defaults.get("category")` 判空后才写入 frontmatter）。
- **网络拉取的 skill**（GitHub、网页、API 文档等）: `author` 写来源 URL，保留出处可追溯。
- 创建技能前必须先 `skill_view('agent-skill-creator')` 走发现→设计→实现→验证工作流。
- **陷阱**: `submit_skill_for_review` 工具 (`tools_decorator.py`) 解析 frontmatter `author` 时，若存在会覆盖 `_CURRENT_USERNAME_CTX` 的真实用户名。已修复为 `if not real_username and fm.get('author')` —— 仅当无登录用户上下文时才用 frontmatter author 作为 fallback。
- 详见 `references/skill-provenance.md`

### SkillView.vue 常见 Bug
- **`SkillAPI.get` vs `SkillAPI.getSkill` 命名不一致**: `skills.ts` 导出的是 `getSkill`，但 `SkillView.vue` 的 `openEdit()` 里写成 `SkillAPI.get(name)` → 报 "SkillAPI.get is not a function"。**一律用 `getSkill`**。
- **详情区不可滚动**: `.skill-detail-card.card-body` 必须加 `overflow-y: auto; flex: 1;`，否则内容溢出被裁掉。
- **分类显示为"其他"**: `get_skill()` 返回 dict 和 `SkillDetail` 模型都缺 `category` 字段 → 前端 `selected.category` 取不到 → fallback 到 `'其他'`。修复：controller 模型和 service 的 return dict 都加 `category: fm.get("category", "其他")`。前端双保险 `selected.frontmatter?.category || selected.category || '其他'`。
- **登录/登出 → 聊天状态残留**: `auth.ts` logout 未清聊天状态 → 切换用户后 `chatStore` 仍保留上一用户的对话。修复：`chat.ts` 新增 `resetAll()`；`auth.ts` logout 中调用 `useChatStore().resetAll()`。
- **SkillView 权限感知**: 用 `useAuthStore()` 引入 `isSuperAdmin` 和 `isAdmin`。锁定标签、分类管理按钮、`…` 菜单均用 `v-if="isSuperAdmin"` 控制。
- **`vue-tsc` exit code 2 是正常的**: `tsconfig.json` 的 `baseUrl` 弃用是 TS5101 ERROR，vue-tsc 永远 exit 2。这就是"仅预存错误，无新增回归"的表现。
- **分类编辑时 `category` 取值**: `openEdit` 中取 `skill.frontmatter?.category` 而非空字符串，否则编辑保存后 `category` 丢失。
- **编辑表单分类字段**: 不要用 `v-if="!editMode"` 限制——编辑时也需要允许修改分类。placeholder 改为"修改分类将移动目录"提示用户。
- **编辑模态框左右分栏布局**: 左侧 240px 表单字段（名称/描述/分类），右侧 flex:1 Markdown 编辑器 + 源码/预览切换。`.modal` 改为 `max-width: 1000px; width: 90vw; height: 85vh`。
- **源码 ↔ 预览切换保持滚动位置**: 用 `nextTick` + 百分比换算恢复 `scrollTop`。切换时记录当前面板 `scrollTop / (scrollHeight - clientHeight)`，切到新面板后 `nextTick` 内设置同等百分比位置。

### 技能分类系统
- 前端在 header 下方独立的 `.category-bar`（不在左侧卡片内），胶囊标签 + 末尾"+"按钮。
- 点击"+" → 内联输入框 + ✓/✕ 确认 → `POST /api/skills/categories` 创建空分类目录（含 `.gitkeep`）。
- 切换分类标签过滤左侧列表，`filteredSkills` 同时受 `activeCategory` + `search` 影响。
- 前端 `listCategories` 兜底：API 不可用时（后端未重启），从技能列表自动提取分类去重。
- `list_categories()` 同时扫描空分类目录（无 `SKILL.md` 的纯目录），确保新创建的空分类可见。

### SKILL.md 渲染 — YAML frontmatter 陷阱
- `backend/service/skill_service.py` 的 `get_skill()` 返回 `content`(完整 SKILL.md) + `body`(`_strip_frontmatter` 去除 `---` 包裹的 YAML frontmatter)
- **陷阱**: 前端 `SkillView.vue` 直接用 `renderMd(selected.content)` 会把 `name: / description: / author: / ---` 等 raw frontmatter 文本显示出来
- **修复**: 渲染用 `selected.body || clientStripFrontmatter(selected.content)`；详情 meta 区展示 `author`/`category`/`version` 而非藏在被隐藏的 frontmatter 里
- `create_skill()` 通过 `optional_user` 注入当前用户为 `author`（已有 frontmatter 的内容不覆盖）

### Monaco Editor / 重型第三方组件初始化
- Monaco Editor **不能** `v-show` + `onMounted` 初始化——`v-show` 只是隐藏，容器可能仍未 layout（`offsetHeight === 0`），编辑器会静默创建出空白。
- **正确模式**: 用 `v-if` + `editorReady` ref 控制容器渲染;`nextTick` → `setTimeout(createEditor, 100)` 确保浏览器完成 layout 再调 `monaco.editor.create`。
- **须有重试兜底**: `createEditor()` 内检测 `container.offsetHeight === 0` → `setTimeout(() => createEditor(), 100)` 再试。
- **切换 Tab**: 先 `editor.dispose()` → `editorReady=false` → `nextTick` 设 `true` → `setTimeout` 重建。
- **Web Workers**: Vite 直接 `import * as monaco from 'monaco-editor'` 即可，**不需要** `vite-plugin-monaco-editor`（会报 "Rollup failed to resolve" 错误）。基础语法高亮不需要 workers；workers 可选后配。

### splitpanes IDE 布局
- `npm install splitpanes` → `import { Splitpanes, Pane } from 'splitpanes'` + `import 'splitpanes/dist/splitpanes.css'`
- 三面板: `<Pane :min-size="15" :size="20">` 文件树 / `<Pane :min-size="30" :size="45">` 编辑器 / `<Pane :min-size="20" :size="35">` 聊天
- 分隔线主题: `.splitpanes.default-theme .splitpanes__splitter { background: var(--border-primary) }; :hover { background: var(--brand) }`
- `.ide-layout { height: 100%; width: 100%; position: relative; }` — `position:relative` 必须且用于悬浮退出按钮的定位容器
- 退出按钮通过 `<slot />` 传入 IdeLayout，用 `position:absolute; top:10px; right:14px; z-index:50` 悬浮在右上角

### Monaco Editor — 主题切换
- `.code-editor-wrap` 背景与 `.editor-tabs` 需与 `theme` 参数同步：`'vs'`(白色) → `background: #fff` + tabs `background: #f3f3f3`；`'vs-dark'` → `background: #1e1e1e` + tabs `background: #252526`
- IDE 切换按钮如果放在 `v-if="!ideMode"` 的 DOM **内部**，进入 IDE 模式后整块不渲染，退出按钮消失。
- **正确做法**: 退出按钮必须放在 `IdeLayout` 组件的最外层（通过 slot 传入），用 `position:absolute; top:10px; right:14px` 悬浮在右上角。进入按钮留在普通模式的头部栏里。

### MD 预览 ↔ 源码切换
- 用 `mdPreview` ref + `v-if="!mdPreview && editorReady"` 控制 Monaco 容器；MD 预览时用 `v-if="mdPreview"` 显示 `<div v-html="renderedMd">`
- 切回源码时：`watch(mdPreview, val => { if (!val) { editorReady=true; setTimeout(createEditor,100) } })` 重建编辑器（预览模式销毁了容器）
- `renderedMd` 用 `computed()` 从 `openFiles[activeIndex].content` 渲染 `renderMarkdown(content)`
- 预览区域 CSS：`overflow-y:auto; padding:16px 24px; line-height:1.7`，复用 `.markdown-body` 样式

### 文件树递归组件（TreeNode.vue）
- **不要在主组件内写递归 inline 模板**——必须独立 `TreeNode.vue` 文件，用 `defineComponent` + `PropType` 声明 props
- 根目录 `loadTree()` → 一级 `items` → 点文件夹 → `expandedDirs.add(path)` + `loadTree(path)` → `updateChildren()` 注入 `item.children` → TreeNode 自递归渲染
- 目录变更：头部「更改」按钮和路径行均可重新 `prompt()` 触发 `setIdeRoot`

### 消息导航圆点过多
- `.msg-nav-dots { max-height: 360px; overflow-y: auto; scrollbar-width: none; gap: 8px; padding: 10px 7px; }`
- 圆点尺寸：10×10px、当前 12×12px + `box-shadow: 0 0 0 2px var(--brand-light)`、最新 11×11px；`flex-shrink: 0` 防止被压缩
- `.msg-nav-dots::-webkit-scrollbar { display: none }` 隐藏滚动条但保留滚动手势
- 到顶/到底按钮 40×40px(默认 34px 太小),边框 2px,字号 18px + font-weight 700 让箭头更粗;默认 `opacity:0` + `transform:scale(0.8)`,scroll 到顶部/底部时加 `.is-visible { opacity:1; transform:scale(1) }`

### Markdown 渲染溢出
- `.message-content { overflow-wrap: break-word; min-width: 0; }`
- `.markdown-body { max-width: 100%; overflow-x: auto; }`
- `.markdown-body pre { white-space: pre-wrap; word-break: break-all; max-width: 100%; }`
- `.markdown-body :not(pre) > code { word-break: break-word; white-space: pre-wrap; }`
- li/p/h1-h3/table/img 全加 `max-width: 100%`

### 测试模型连接端点
- `POST /api/model-configs/{id}/test` 分阶段：Anthropic 端点（路径含 `/anthropic`）用 POST 最小消息测试；OpenAI 端点先后试 `/v1/models` → `/models` → 根路径
- 失败时返回 `tested_urls` 列表帮助诊断；Anthropic 端点额外带 `x-api-key` header
- **⚠️ 陷阱**：Anthropic 分支 HTTP 错误处理仅 2xx 算成功；404/500/503 等必须返回 `ok: False`。详见 `references/model-config-api.md`

### 多模态图片问答（新增功能）
- `model_configs` 新增 `is_multimodal` 列，创建/更新时自动通过名称模式检测（`backend/utils/multimodal_detect.py`）
- 图片上传端点 `POST /api/chat/upload-images`：接收 multipart 文件，转 base64 data_url 返回
- SSE 双路架构：GET `/chat/stream`(文本 EventSource) + POST `/chat/stream`(图片+文本 fetch ReadableStream)
- 微信图片：iLink type=2/3 → CDN 下载 → 多模态 LLM 调用 → `_strip_md` 回复
- 完整实现见 `agentforge-dev/references/multimodal-image-support.md`

### 微信图片缓存+文字合并机制
微信不能同时发图片和文字，用户先发图片后发文字描述。架构：
- 收到纯图片（无文字）→ 下载+解密+base64 → 缓存到 `_pending_images[pending_key]` → 回复"📷 已收到 N 张图片，请在 30 秒内发送文字描述，或发送 /send 直接发送"
- 收到纯文字（无图片）→ 检查 `_pending_images` 是否有缓存 → 有则合并（`images_for_llm = pending.pop("images", [])`）→ 调多模态 LLM
- 超时 30 秒 → 清理缓存
- **⚠️ 关键陷阱**：`_pending_images` 初始化必须在合并逻辑之后，不能在合并前 `images_for_llm = []` 覆盖已合并的值
- **⚠️ 默认文本检测**：微信可能在图片消息中附带默认文本（如 `[图片]`、`image`），需要过滤：`default_texts = ["[图片]", "[image]", "图片", "image"]`，`if not text or text.lower() in default_texts:` 视为纯图片
- **⚠️ 微信图片解密**：iLink 返回的图片数据是加密的，必须使用 **AES-128-ECB** 模式解密（不是 CBC）：
  ```python
  from Crypto.Cipher import AES
  from Crypto.Util.Padding import unpad
  key = bytes.fromhex(aeskey)  # 16 bytes = AES-128
  cipher = AES.new(key, AES.MODE_ECB)  # ⚠️ ECB 模式，无 IV
  decrypted = cipher.decrypt(img_content)
  img_content = unpad(decrypted, AES.block_size)  # PKCS#7 去填充
  ```
- **⚠️ 微信图片 URL 位置**：不在顶层 `url`/`cdn_url`，而在 `media.full_url` 嵌套中：
  ```python
  img_url = (
      img_data.get("url") 
      or img_data.get("cdn_url") 
      or img_data.get("full_url") 
      or (img_data.get("media") or {}).get("full_url")  # ⚠️ 实际位置
  )
  ```

### 模型名标签剥离 — 所有 LLM 调用函数都需要
数据库 `model_name` 可能含 `[1m]`、`[32k]` 等上下文标签（如 `qwen3.7-plus[1m]`），API 不识别会报 400。**所有**调用 LLM 的函数都必须剥离：
```python
if "[" in model:
    model = model.split("[")[0]
```
受影响函数：`_call_llm()`、`_call_llm_multimodal()`、`chat_controller.token_stream_events()` 等。Hermes adapter 内部已处理，但微信监听器的独立 LLM 调用需要自己处理。

### 前端等待动画位置 — 在气泡内而非外部独立元素
等待 LLM 首 token 的"思考中..."动画必须在 `MessageBubble.vue` 内部渲染（`v-else-if="isThinking"`），不能在 `ChatView.vue` 中创建独立的 `.message-bubble.assistant` 元素。外部独立气泡与聊天区白框分离，视觉上难看。
- `isThinking` computed：`message.role === 'assistant' && !message.content && !message.thinkingProcesses?.length`
- 动画：三个跳动圆点 + "思考中..." 文字，在助手气泡内显示
- **⚠️ 陷阱**：如果 ChatView 中有独立的流式加载动画 div，必须删除，否则出现两个气泡（白框内一个、白框外一个）

## 后端核心模式

### MySQL 操作
- `pymysql.connect(host=..., user=..., cursorclass=pymysql.cursors.DictCursor, autocommit=True)` — **必须用 `DictCursor`** 否则字段名键访问不生效。
- `ONLY_FULL_GROUP_BY` 模式下,`ORDER BY` 只能用聚合列(如 `MIN(created_at)`)。
- 加密: `backend.utils.crypto_utils.encrypt()` / `decrypt()` — AES-256-GCM,密钥从 `JWT_SECRET` 派生。

### API 控制器结构
- FastAPI `APIRouter`,prefix 在创建时指定
- 鉴权: `Depends(get_current_user)` → user dict 含 `user_id`,`username`,`role`
- `require_perm("config.manage")` / `require_perm("config.view")`
- 在 `main.py` 中 `app.include_router(router)` 注册

### 数据库迁移
- 建表语句在两个地方同步: `backend/db/schema.py`(文档/重建用) + `backend/db/mysql_impl.py`(运行时)
- 新增列: `ALTER TABLE` 后同时更新两个文件的建表语句

## 用户交互偏好

- 中文回复,少解释多行动
- UI 改动前先出方案菜单给用户选范围,不要上来就大改
- 前端交互 bug("点不开/不显示/没反应")→ 先修再讲,讲完给 Ctrl+F5 复验提示
- 后端由用户自己 `python main.py start 8001` 重启;改了 Python 必须提醒重启

## AgentForge 技能自动加载规则

**修改 AgentForge 项目时必须遵守的加载顺序：**

- 每次加载 `agentforge-development` 后，自动按需加载以下技能：
- **Bug 修复完成后** → 加载 `code-review`，走四维度审查
- **任何改动完成准备交付时** → 加载 `verification-before-completion`，跑门禁验证
- **遇到 Bug 需要定位时** → 加载 `systematic-debugging`，先找根因再修复
- **同时修改前后端时** → 加载 `event-driven-state-debugging`（Vue/Pinia 状态问题）或 `mysql-backend-extension`（数据库扩展）

## IDE Web 模式（重大功能）

聊天界面顶部"IDE 模式"按钮可切换至三面板(splitpanes)布局:
- **文件树** (`components/ide/FileTree.vue`) — 后端 `ide_controller.py` 提供 `/api/ide/tree` / `/api/ide/file` API
- **代码编辑器** (`components/ide/CodeEditor.vue`) — Monaco Editor,多 Tab,Ctrl+S 保存回写
- **IDE 聊天** (`components/ide/IdeChatPanel.vue`) — 复用 `useChat('ide')`,会话标记 `chat_mode='ide'` 与普通聊天隔离
- 目录选择通过 `POST /api/ide/root` 设置根路径,文件操作有 `_safe_join` 路径穿越防护
- IDE 对话历史在聊天面板右上角 📋 按钮展开,后端 `/api/data/sessions?session_type=ide` 按 `chat_mode` 筛选
- 详见: `mysql-backend-extension/references/ide-web-api-pattern.md`

## 关键组件文件地图

| 功能 | 前端文件 | 后端文件 |
|---|---|---|
| 聊天主界面 | `views/ChatView.vue` | `controller/chat_controller.py` |
| 历史侧边栏 | `components/chat/ChatSidebar.vue` | `controller/data_controller.py` |
| 消息气泡 | `components/chat/MessageBubble.vue` | — |
| 聊天状态 | `composables/useChat.ts` + `stores/chat.ts` | — |
| 会话持久化 | — | `db/conversation_store.py` |
| IDE 模式 | `components/ide/IdeLayout.vue` + 子组件 | `controller/ide_controller.py` |
| 模型配置 | `views/ConfigView.vue` | `controller/model_config_controller.py` |
| 多模态检测 | — | `utils/multimodal_detect.py` |
| 主导航 | `components/AppSidebar.vue` | — |
| 技能管理 | `views/SkillView.vue` + `api/skills.ts` | `controller/skill_controller.py` + `service/skill_service.py` |
