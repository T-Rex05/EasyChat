# 技能审核流程 (Review Pipeline)

## 两条独立链路

### 链路A — skill_manager_tool (Hermes 工具)
直接写 `HERMES_HOME/skills/{name}/SKILL.md` + 插入 `skill_meta`。

**状态逻辑（2026-08-07 修复）**:
- **前台模式（用户主动创建）**: `status="pending"`（待审核，不可用）
  - 即使当前用户是 admin/super_admin，用户通过对话请求创建的技能都走审核
  - `_create_skill` 中 `is_background_review()` 返回 `false` → `final_status="pending"`
- **后台模式（AI 自主生成）**: `status="approved"`（自动批准，立即可用）
  - AI 自己主动生成的技能（非用户请求）直接生效
  - `_create_skill` 中 `is_background_review()` 返回 `true` → `final_status="approved"`

**Author 注入（2026-08-07 修复）**:
- 优先从 DB 查询当前登录用户的 `username` 作为 `author`
- 回退：参数传入的 `author` → defaults（`_read_creator_defaults()`）
- **陷阱**: LLM 可能在 content 中硬编码 `author: AgentForge`，但 `_strip_agent_frontmatter_defaults()` 会剥掉它
- **关键代码**: `skill_manager_tool.py:967-982` 查询 `current_username`，`1008-1012` 优先级注入

**Pending 技能过滤（2026-08-07 修复）**:
- `skills_tool._filter_locked_skills()` 必须过滤 `status="pending"` 的技能
- 否则 Agent 系统会加载待审核技能，违反"审核前不可用"原则
- 过滤条件：`status != "pending"` AND `locked != 1`

### 链路B — review_service (`submit_skill_for_review` 工具 / 前端提交)
写入 `backend/pending/skills/{id}.yaml`，**前端技能管理页面不显示 pending 项**。
需管理员审核通过后才复制到 `HERMES_HOME/skills/` 并入库 `skill_meta`。

## 审核通过方式

1. **前端管理页** → 审核队列 → 点"通过"
2. **Python 直接调**（推荐快速通过）:
   ```python
   from backend.service.review_service import approve
   approve(submission_id, reviewed_by='admin', comment='...')
   ```
3. **API 方式**: `POST /api/review/approve`（需 `review.approve` 权限 + Cookie/Token 认证）

## 相关 API 端点 (`review_controller.py`)

- `GET /api/review/pending` — 列出待审核项（普通用户只看自己的）
- `POST /api/review/approve` — 审核通过
- `POST /api/review/reject` — 审核拒绝
- `GET /api/review/history` — 已审历史（已通过 + 已拒绝）

## 常见陷阱

### 用户说"为什么我在技能管理里看不到"
原因：技能还在 `backend/pending/skills/` 里，状态 `pending`。必须审核通过后才显示。
解决：用 Python 直接调 `approve()` 最快，或让用户在前端审核页操作。

### `submit_skill_for_review` 返回的 ID 是 submission_id 不是 skill name
审核时需要用 submission_id（如 `635f86a8`），不是技能名（如 `travel-guide-planner`）。

### ContextVar 用错 → 提交者显示 user_id 而非 username
- `_MEMORY_USER_CTX` 存 `str(user_id)`（如 "2"），`_CURRENT_USERNAME_CTX` 存 `username`（如 "admin"）
- `tools_decorator.py` 的 `submit_skill/agent_for_review` 之前只读 `_MEMORY_USER_CTX` → 审核页"提交者"显示数字
- **修复**: 优先 `_CURRENT_USERNAME_CTX.get()`，回退 `_MEMORY_USER_CTX.get()`，兜底 `"ai_agent"`

### 前后端字段名不匹配 → Invalid Date
- 后端 `review_service.list_pending()` 返回 `submitted_at`，不是 `created_at`
- 前端 `ReviewView.vue` 必须用 `item.submitted_at`，加 `isNaN(d.getTime())` 兜底
- `source` 是英文 key，前端需 `sourceText()` 映射（`ai_conversation` → "AI 对话"）

### AI 重复提交防护
- LLM 同一轮对话可能多次调 `submit_skill_for_review`（同 name，时间差 <1s）
- **工具层防重**: 提交前扫 `_load_index()` 同名+pending+skill，60 秒内已有则拒绝
- 历史残留重复 pending 需手动标记 rejected

### description 被工具输出污染
- LLM 把工具输出/对话历史塞进 description 参数 → 审核页显示垃圾
- **修复**: 优先从 `content` 的 YAML frontmatter 提取 `name`/`description`/`author`
- 兜底：description 超 200 字符截断
