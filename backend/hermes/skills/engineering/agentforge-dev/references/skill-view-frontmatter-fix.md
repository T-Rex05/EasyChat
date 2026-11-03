# Skill 详情页 YAML frontmatter 渲染修复模式

## 问题
`SkillView.vue` 中 `renderMd(selected.content)` 直接渲染完整 SKILL.md（含 YAML frontmatter），用户看到 `name: send-email category: automation ...` 等原始元数据文本。

## 修复 — 三层方案

### 1. 后端：`_strip_frontmatter()` + `body` 字段
文件：`backend/service/skill_service.py`

```python
def _strip_frontmatter(content: str) -> str:
    """去除 YAML frontmatter，返回纯 Markdown 正文。"""
    if not content.startswith("---"):
        return content
    end = content.find("---", 3)
    if end == -1:
        return content
    body = content[end + 3:]
    # 跳过结束标记后的换行符（\n 或 \r\n）
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return body
```

`get_skill()` 返回中增加 `"body": _strip_frontmatter(content)`，`SkillDetail` 模型加 `body: str = ""`。

### 2. 前端：优先用 `body`，兜底 `stripFrontmatter()`
`SkillView.vue` 中渲染行改为：
```html
<div class="detail-content" v-html="renderMd(selected.body || stripFrontmatter(selected.content))"></div>
```

```js
function stripFrontmatter(text) {
  if (!text || !text.startsWith('---')) return text;
  const end = text.indexOf('---', 3);
  if (end === -1) return text;
  let body = text.slice(end + 3);
  if (body.startsWith('\n')) body = body.slice(1);
  return body;
}
```

### 3. 元数据展示
详情区用 grid 布局展示 author/category/description/files，而非藏在被隐藏的 frontmatter 里。

```html
<div class="meta-grid">
  <div class="meta-item">
    <span class="meta-label">👤 创建者</span>
    <span class="meta-value">{{ selected.author || '未知' }}</span>
  </div>
  <!-- ... -->
</div>
```

## 创建技能时注入 author
- `POST /api/skills` 通过 `Depends(optional_user)` 获取当前用户
- `create_skill(author=user.get("username", ""))` 在自动生成的 frontmatter 中写入 `author: xxx`
- 已含 frontmatter 的内容不覆盖其 author 字段
