# 技能分类管理系统

## 架构概览

### 后端

| 端点 | 方法 | 说明 |
|---|---|---|
| `GET /api/skills/categories` | GET | 列出所有分类（从技能 frontmatter + 空分类目录扫描） |
| `POST /api/skills/categories` | POST | 创建空分类目录（含 `.gitkeep`） |
| `PUT /api/skills/{name}` | PUT | 更新技能，新增可选 `category`/`description` 参数 |

### `skill_manager_tool.py` 自动注入

`_create_skill()` 在 `skill_manage(action='create')` 时自动检测 frontmatter：

- **缺 `author`** → 注入 `author: AgentForge`
- **缺 `category`** → 注入 `category: AI生成`
- **已有值** → 不覆盖，用户指定优先

这确保无论通过 `skill_manage` 还是 `agent-skill-creator` 创建技能，都会带上统一标识。

### update_skill 目录移动

`skill_service.update_skill()` 接受 `category` 参数：
1. 读取旧 SKILL.md → 提取旧 category
2. 写入新内容
3. 若新 category ≠ 旧 category → `shutil.move()` 移到新分类子目录
4. 目标目录自动 `mkdir(parents=True)`

### 前端

- **分类栏**：在页面 header 下方独立一行，圆角标签 + 全部/各分类 + 虚线"+"按钮
- **创建分类**：点击"+" → 内联输入框 → Enter/✓ 确认 → 调 `POST /api/skills/categories`
- **编辑技能**：表单始终显示分类字段（不区分 create/edit），`openEdit` 从 `frontmatter.category` 预填
- **API 兜底**：`listCategories()` 失败时从技能列表的 `category` 字段 fallback 提取

### 验证门禁

- 前端：`npm run build` + `vue-tsc --noEmit`
- 后端：`ast.parse` + 模块导入
- 注入逻辑：3 场景测试（缺 author/category、仅有 author、两者都有）
