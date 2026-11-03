# 技能分类功能实现细节

## 后端改动

### `skill_controller.py`
- `SkillUpdateRequest` 新增可选字段：`category: Optional[str]`, `description: Optional[str]`
- 新增端点 `GET /api/skills/categories` → `skill_service.list_categories()`
- `PUT /api/skills/{name}` 传递 `category`/`description` 到 service 层

### `skill_service.py`
- `list_categories()` — 从 `list_skills()` 结果中提取 `category` 字段，`Set` 去重排序
- `update_skill()` 签名扩展：`category: Optional[str] = None, description: Optional[str] = None`
- 目录移动逻辑：
  1. 先读取旧 SKILL.md，解析当前 `category`
  2. 写入新内容
  3. 若 `new_category != old_category`：`shutil.move(skill_dir, skills_dir / new_category / name)`
  4. 目标分类目录 `mkdir(parents=True, exist_ok=True)`
- 查找技能目录时递归搜索子目录（因为技能可能在 `category/name/` 下）

## 前端改动

### `skills.ts`
- `updateSkill(name, content, category?, description?)` — category/description 可选参数
- 新增 `listCategories(): Promise<string[]>` → `GET /api/skills/categories`

### `SkillView.vue`
- 新增状态：`activeCategory`（当前选中分类）、`categories`（分类列表）
- 分类标签栏：`.category-tabs` 横向排列，`.category-tab.active` 高亮
- `filteredSkills` 计算属性：先按 `activeCategory` 过滤，再按 `search` 关键词过滤
- 编辑表单：去掉 `v-if="!editMode"`，编辑时也显示分类输入框
- `openEdit`：`category` 初始值从 `skill.frontmatter?.category` 取
- `handleSave`：编辑时传递 `form.category` 和 `form.description`
- `loadSkills`：加载分类列表，404 时从技能列表兜底提取

### 兜底逻辑（关键）
```typescript
try {
  categories.value = await SkillAPI.listCategories();
} catch {
  // 后端未重启时 API 不存在，从技能列表提取分类
  const catSet = new Set();
  skills.value.forEach(s => catSet.add(s.category || '其他'));
  categories.value = Array.from(catSet).sort() as string[];
}
```
- 原因：新增的 `/api/skills/categories` 端点需要重启后端才生效
- 兜底保证前端即使在后端未重启时也能显示分类标签
