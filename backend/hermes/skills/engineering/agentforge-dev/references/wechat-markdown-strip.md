# 微信 ClawBot MD 兼容转换

## 核心原则：保守策略

ClawBot **能渲染**纯文本消息中的基础 MD：`**bold**`、`*italic*`、`~~strike~~`、`[link](url)`、`>quote`、`` `code` ``、列表（`-`/`1.`）、``` 代码块 ```。这些**原样保留，不做任何转换**。

**只转换 ClawBot 不支持或显示不佳的语法**：

| MD 语法 | 转换后 | 原因 |
|---------|--------|------|
| `# 标题` | `【标题】` | ClawBot 不渲染标题，【】醒目替代 |
| `## 标题` / `### 标题` | `**标题**` | 用加粗模拟标题效果 |
| `| A | B |` 表格 | `- A: value`（键值对列表） | 表格排版在微信端完全错乱 |
| `- [ ] 待办` | `☐ 待办` | 任务列表转 visual checkbox |
| `- [x] 完成` | `☑ 完成` | |
| `---` / `***` | `────────────────`（16个全角—） | 原生 `---` 显示为 3 个短横线太淡 |

## 实施位置

- 文件：`backend/controller/wechat_listener.py`
- 函数：`_strip_md(text: str) -> str`
- 调用：在 `_handle_message` 普通消息路径，`_reply_wechat_text(_strip_md(answer), ...)`
- DB 存储原始 answer（保留完整 MD），微信发送 stripped 版本。Web 端仍可看到完整格式化。

## 关键陷阱 — 错误做法总结

经历多次迭代确认的教训：

1. **不要去掉 `~~` 删除线**：ClawBot 能渲染，用户明确反馈"原来可以的被你去掉了"
2. **不要去掉 `[text](url)` 链接**：同上
3. **不要去掉 `*italic*`**：ClawBot 能渲染斜体
4. **不要去掉 `` `code` `` 行内代码**：ClawBot 能渲染
5. **不要展开无序列表为 `•`**：ClawBot 能渲染 `- item` 格式
6. **不要修改 `> 引用`**：ClawBot 能渲染引用块
7. **表格不要用 `·` 连接**：信息密度太低，应用 `- key: value` 格式
8. **标题不要用下划线**：`标题\n──` 占两行不紧凑，不如 `【标题】`

## 完整转换算法

```python
def _strip_md(text: str) -> str:
    # 1. 代码块处理：原样保留，前后加空行
    # 2. 任务列表：[-*+] [xX] → ☑/☐
    # 3. 表格检测：表头行 + 下接 |---| 分隔行 → zip 为 - key: value
    # 4. # 标题 → 【标题】
    # 5. ##+ 标题 → **标题**
    # 6. --- → ────────（16个全角）
    # 7. 其他：原样保留（**bold**, *italic*, ~~strike~~, [link](url), >quote, 列表等）
    # 8. 合并连续空行
```

## 验证断言

```python
from backend.controller.wechat_listener import _strip_md

# 标题转换
assert '【H1】' == _strip_md('# H1')
assert '**H2**' == _strip_md('## H2')

# 表格转换
assert '- A: 1\n- B: 2' == _strip_md('| A | B |\n|---|---|\n| 1 | 2 |')

# 任务列表
assert '☑ done' == _strip_md('- [x] done')
assert '☐ todo' == _strip_md('- [ ] todo')

# 以下全部原样保留
for keep in ['**bold**', '*it*', '~~del~~', '[link](url)', '> q', '- list', '1. ol', '```\ncode\n```']:
    assert keep in _strip_md(keep), f'{keep} should be preserved'
```
