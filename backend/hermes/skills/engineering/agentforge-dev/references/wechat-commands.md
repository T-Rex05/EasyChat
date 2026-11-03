# 微信聊天命令系统

`wechat_listener.py` 的 `_handle_message()` 中通过前缀/精确匹配实现命令路由。命令在 LLM 调用之前拦截，不产生 LLM 费用。

## 命令列表

| 命令 | 别名 | 功能 | 权限 |
|------|------|------|------|
| `/new` | `/新对话`, `/新会话` | 创建新会话（时间戳 ID） | 所有 |
| `/history` | `/历史`, `/会话列表`, `/list` | 列出最近 10 个会话（编号列表） | 所有 |
| `/1` ~ `/10` | — | 切换到序号对应的会话 | 所有 |
| `/rename <标题>` | `/重命名 <标题>` | 重命名当前会话（最多 30 字） | 所有 |
| `/rm` | `/删除`, `/删除会话`, `/delete` | 删除当前会话（软删除 status=0） | 所有 |
| `/rm <序号>` | `/删除 <序号>` | 按序号删除指定会话 | 所有 |
| `/status` | `/当前` | 查看当前会话 ID | 所有 |
| `/help` | `/帮助`, `/?` | 显示命令列表 | 所有 |
| `/restart` | — | 执行 `restart.bat` | 超管 |
| `/restart-all` | — | 执行 `restart-all.bat` | 超管 |
| `/stop` | — | 执行 `stop.bat` | 超管 |
| `/stop-all` | — | 执行 `stop-all.bat` | 超管 |

## 实现细节

### 会话管理
- `_wx_active_session` dict: `{(user_id, wx_user_id): session_id}` — 内存中存当前活跃会话
- `_wx_session_titles` dict: `{session_id: "自定义标题"}` — 内存中存重命名标题
- 默认会话 ID: `wx_{user_id}_{wx_user_id[:12]}` — 同一对用户+微信好友固定
- 新会话 ID: `wx_{user_id}_{wx_user_id[:8]}_{timestamp后8位}`
- 服务重启后 `_wx_active_session` 和 `_wx_session_titles` 丢失（内存），会话恢复默认

### 命令匹配策略
- **所有命令先 `strip().lower()`** — 微信输入可能自带空格
- `/rm`（无参数）：`cmd == "/rm"` **精确匹配**，不能用 `in`，否则 `/rm 1` 被拦截
- `/rm 1`（带序号）：`cmd.startswith("/rm ") and cmd[4:].strip().isdigit()` — 用 `startswith` 不用 regex（微信全角空格导致 regex `\s+` 可能不匹配）
- `/rename abc`：`cmd.startswith("/rename ")`，从原始 `text`（未 lower）取空格后部分作为标题
- `/rename` 必须在 `/rm` 之前检查，避免 `startswith("/r")` 冲突

### 系统控制命令
- `subprocess.Popen` Windows 下用 `start "title" cmd /c "cd /d PROJECT_ROOT && bat_path"`，新窗口执行不卡主进程
- 权限检查：`SELECT role FROM users WHERE id = uid`，必须 `role == "super_admin"`

### `/history` 响应格式
```
📋 微信对话列表：
1. 你好 ← 当前
2. 技术支持
3. 闲聊话题

回复序号切换，如 /1
```

### `/rm` 删除逻辑
- `UPDATE conversations SET status = 0 WHERE session_id = ?`
- 同时清理 `_wx_session_titles` + 如果是当前会话则清理 `_wx_active_session`
- 返回被删会话标题和消息数量

## 相关文件
- `backend/controller/wechat_listener.py` — 全部命令逻辑在 `_handle_message()`
- `backend/controller/platform_config_controller.py` — 绑定/解绑触发 `restart_wechat_listener()`
- 系统控制脚本：`E:\PythonCode\AgentForge\restart.bat`, `restart-all.bat`, `stop.bat`, `stop-all.bat`
