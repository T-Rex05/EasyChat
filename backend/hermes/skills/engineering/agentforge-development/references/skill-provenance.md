# Skill Provenance — 前台 vs 后台区分

## 问题背景

`skill_manager_tool._create_skill()` 原先统一注入 `author: AgentForge` + `category: AI生成`，
导致用户通过 LLM 创建的技能在管理界面中不可见（`list_skills` 对非超管隐藏 `category='AI生成'` 的技能）。

## 解决方案

利用已有的 `skill_provenance.py` ContextVar 机制区分调用来源：

- **前台（foreground）**：用户直接要求 LLM 创建 → 返回空默认值，不注入 agent 标记。技能对普通用户可见。
- **后台（background_review）**：自主 curator 生成 → 注入 `author: AgentForge` + `category: AI生成`。仅超级管理员可见。

## 修改的文件

### 1. `backend/hermes/tools/skill_manager_tool.py`

#### `_read_creator_defaults()` — 新增前台/后台分支

```python
def _read_creator_defaults() -> Dict[str, str]:
    from tools.skill_provenance import is_background_review

    if not is_background_review():
        return {"author": "", "category": ""}

    defaults = {"author": "AgentForge", "category": "AI生成"}
    # ... 读取 agent-skill-creator SKILL.md 覆盖（后台模式）
```

#### `_create_skill()` — 仅注入非空默认值

```python
if not has_author and defaults.get("author"):
    fm_lines.append(f"author: {defaults['author']}")
if not has_category and defaults.get("category"):
    fm_lines.append(f"category: {defaults['category']}")
```

#### `_create_skill()` — 前台模式下剥离 agent 默认值

LLM 按照 `agent-skill-creator` 的约定输出 frontmatter 时，总是包含 `author: AgentForge` 和 `category: AI生成`。
前台模式下调用 `_strip_agent_frontmatter_defaults(content)` 精确移除这两行。

```python
if not is_background_review():
    content = _strip_agent_frontmatter_defaults(content)
```

#### `_strip_agent_frontmatter_defaults()` — 新增辅助函数

精确匹配并移除 `author: AgentForge` 和 `category: AI生成` 行（保留其他字段不变，含 `author: SWQ` 或 `category: devops` 等用户自定义值）。

#### `_create_skill()` — final_category 逻辑

```python
if is_background_review():
    final_category = category or fm.get("category", "") or "AI生成"
else:
    final_category = category or fm.get("category", "") or ""
```

#### `skill_manage()` docstring 更新

描述从"author: AgentForge, category: AI生成"改为说明前台剥离、后台保留的区分机制。

### 2. `backend/service/skill_service.py`

#### `create_skill()` — final_category 默认值

```python
# 旧: final_category = category or fm.get("category", "其他")
# 新:
final_category = category or fm.get("category", "")
```

不再默认 `"其他"`，改为空字符串。`is_ai` 基于实际 `"AI生成"` 匹配判断。

## 关键函数调用链

```
skill_manage(action='create')
  └─ _read_creator_defaults()
       └─ is_background_review()  ← ContextVar 判断
            ├─ foreground → {"author": "", "category": ""}
            └─ background → {"author": "AgentForge", "category": "AI生成"}
  └─ _create_skill(name, content, category)
       ├─ 仅注入非空的 author/category
       ├─ foreground: _strip_agent_frontmatter_defaults(content)
       └─ final_category: foreground="" / background="AI生成"
```

## 可见性对照

| 场景 | author | category | 普通用户可见 | 超管可见 |
|------|--------|----------|-------------|---------|
| 前台用户请求 | (空) | (空) | ✅ | ✅ |
| 后台自主生成 | AgentForge | AI生成 | ❌ | ✅ |
| 用户指定分类 | 用户 | devops等 | ✅ | ✅ |
