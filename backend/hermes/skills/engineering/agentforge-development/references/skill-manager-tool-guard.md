# skill_manager_tool.py — Auto-Inject & Tool-Docstring Enforcement

## 架构决策

`skill_manage(action='create')` 的 `_create_skill()` 是**注入器**而非校验器。职责：自动补默认值 +  保持已有值不变。

## 注入链

```
_create_skill()
  → _read_creator_defaults()
      → 读取 agent-skill-creator/SKILL.md frontmatter
      → 找到 → 用文件中的 author/category
      → 没找到 → 降级硬编码 {"author": "AgentForge", "category": "AI生成"}
  → 检查 content frontmatter 是否已有 author/category
      → 缺 author → 注入
      → 缺 category → 注入
      → 都有 → 不覆盖（尊重用户手动设定的值）
```

## 路径搜索

```python
def _read_creator_defaults():
    # Strategy 1: _skills_dir() / "agent-skill-creator" / "SKILL.md"
    # Strategy 2: _skills_dir().rglob("agent-skill-creator/SKILL.md")
    # Fallback: {"author": "AgentForge", "category": "AI生成"}
```

两层搜索，覆盖分类子目录场景。找不到时降级硬编码保证创建不中断。

## 为什么删除了后端校验

`_validate_against_creator_rules()` 被主动删除（2026-08-07）。原因：

- 后端无法执行"发现→设计→实现→验证"工作流——只有 LLM 能做到
- 在校验层拦截会导致 `skill_manage(create)` 返回错误，LLM 不知道为什么会失败
- 正确的约束点：`skill_manage()` 的 **docstring**，写明调用前必须 `skill_view('agent-skill-creator')`

## Docstring 约束

```python
"""
**IMPORTANT for 'create'**: Before calling this with action='create', you MUST
first load the `agent-skill-creator` skill with skill_view(name='agent-skill-creator')
and follow its discovery→design→implementation→validation workflow.
"""
```

LLM 读到工具描述时才触发——比记忆或技能内容中的软提醒更可靠。

## 版本演进

| 版本 | 做法 | 问题 |
|---|---|---|
| v1 | 硬编码值 | 不可配置 |
| v2 | 后端校验 `_validate_against_creator_rules()` | 误拦截，LLM 不理解 |
| v3（当前） | `_read_creator_defaults()` 读取 + docstring 约束 | 职责分离，注入和约束各在其位 |
