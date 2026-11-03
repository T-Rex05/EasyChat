# 微信消息后台监听器架构

`backend/controller/wechat_listener.py` 是 AgentForge 自实现的微信消息收发引擎，
用 aiohttp 长轮询 iLink `getupdates` API，不依赖 Hermes gateway 进程。

## 架构
```
微信用户发消息 → iLink API → wechat_listener._poll_loop()
                                ├─ 从 platform_config 读 Bot 凭证
                                ├─ 从 user_bindings 找到绑定的 AgentForge 用户
                                ├─ 调用 LLM（model_configs.is_current=1）生成回复
                                ├─ 写入 conversations（source='wechat'）
                                └─ 通过 iLink sendmessage 推回微信
```

## 生命周期
- **启动**: `main.py` 的 `lifespan` startup 段 → `start_wechat_listener()` → 检查 platform_config 有凭证 → `asyncio.create_task(_poll_loop())`
- ⚠️ **不能用 `@app.on_event("startup")`** — `lifespan` 存在时 on_event 永不触发，监听器静默失效 → 重启后发消息无反应
- **重启**: `restart_wechat_listener()` — 绑定/解绑/换绑时调用。先 cancel 旧 task → sleep(1s 等 DB 事务提交) → `_get_wechat_config()` 重读 → 有凭证才 create_task，无则 return
- **停止**: 解绑时 `user_binding_controller.delete_binding()` 调 `restart_wechat_listener()`，监听器检测到无凭证 → 打印日志 → task 自然退出
- **超管解绑微信**: 同步 `UPDATE platform_config SET enabled = 0 WHERE platform = 'wechat'`

## 关键子模块

### `_get_wechat_config()`
从 `platform_config` 读 `platform='wechat' AND enabled=1` 的 `config_json`。必须有 `token` 和 `account_id`。

### `_find_user_by_wechat_id(wx_user_id)`
JOIN `user_bindings` + `users`，通过微信 `from_user_id` 匹配 `open_id`。未绑定的消息静默丢弃。

### `_call_llm(user_message)`
读 `model_configs WHERE is_current=1`。**必须检测端点类型**：
- URL 含 `/anthropic` 或 `/messages` → 用 Anthropic 格式（POST `/messages`, `x-api-key` header, `anthropic-version`）
- 否则 → OpenAI 格式（POST `/v1/chat/completions`, `Bearer` header）

Anthropic 端点响应 `content[]` 可能含 `type: "thinking"` 块：
- **保留 thinking** — thinking 块加 `🧠 思考过程：\n` 标签，text 块直接拼接，`\n\n` 分隔
- 不要用 `"thinking": {"type": "disabled"}`（用户要求保留深度思考）
```python
parts = []
for block in data.get("content", []):
    if not isinstance(block, dict): continue
    if block.get("type") == "text":
        parts.append(block.get("text", ""))
    elif block.get("type") == "thinking":
        parts.append(f"🧠 思考过程：\n{block.get('thinking', '')}")
return "\n\n".join(parts).strip() if parts else fallback()
```
`choices` fallback 用于兼容非标准 Anthropic 格式。使用 `backend.utils.crypto_utils.decrypt()` 解密 api_key。

### iLink API 必须用 `json.loads(resp.text())`
iLink 返回 `Content-Type: application/octet-stream`，aiohttp 的 `.json()` 会直接抛：
```
Attempt to decode JSON with unexpected mimetype: application/octet-stream
```
所有监听器中的 iLink 调用统一用 `json.loads(await resp.text())`。

### restart 必须重新读取配置
`restart_wechat_listener()` 不能传 `{}` 给 `_poll_loop`（会 KeyError on `config["token"]`）。
正确流程：sleep(1) 等 DB 事务 → `_get_wechat_config()` 重读 → 无凭证则 return（静默停止）。

### 消息去重
`_dedup` dict 缓存 `msg_id → timestamp`，TTL 300s。同时清理过期条目。

### session_id 生成
格式: `wx_{user_id}_{wx_user_id[:12]}`，保证同一对用户+微信好友共享一个会话。
新会话: `_new_session_key()` → `wx_{user_id}_{wx_user_id[:8]}_{timestamp_suffix}`。

### 微信会话管理命令
`_handle_message` 在 LLM 调用前拦截斜杠命令（全部 `cmd = text.strip().lower()` 精确匹配）：

| 命令 | 触发词 | 行为 |
|------|--------|------|
| `/new` | `/new`, `/新对话`, `/新会话` | `_new_session_key()` → `_set_active_session()` |
| `/history` | `/history`, `/历史`, `/会话列表`, `/list` | `_get_user_sessions()` 查 DB，标 `← 当前` |
| `/1`..`/9` | `/` + 纯数字 | 从 history 列表按序号切换活跃会话 |
| `/rename` | `/rename <title>`, `/重命名 <title>` | `_wx_session_titles[sid] = title`，限 30 字符 |
| `/rm` | `/rm`, `/删除`, `/删除会话`, `/delete` | `UPDATE conversations SET status=0`，清除活跃会话，发送任意消息自动开启新会话 |
| `/rm 1`..`/rm 10` | `/rm <序号>`, `/删除 <序号>`, `/删除会话 <序号>` | 按序号删除指定会话（非当前也可删）。`startswith` + `isdigit()` 解析，不是 regex。若删除的是当前活跃会话则同步清除 `_wx_active_session` |
| `/rename` | `/rename <标题>`, `/重命名 <标题>` | `_wx_session_titles[sid] = title`，限 30 字符。`/history` 列表中自定义标题优先显示 |
| `/status` | `/status`, `/当前` | 显示当前 session_id |
| `/help` | `/help`, `/帮助`, `/?` | 列出所有命令 |

**系统控制命令（仅 `super_admin` 可执行）**: `/restart` / `/restart-all` / `/stop` / `/stop-all`
- 检查 `users.role == 'super_admin'`（非 admin），不满足返回"⛔ 仅超级管理员可执行此操作"
- 通过 `subprocess.Popen` 执行对应 .bat 文件
- **Windows**: 必须用 `start "title" cmd /c "cd /d {PROJECT_ROOT} && {bat_path}"` — `shell=True` 字符串形式，新 cmd 窗口执行（`creationflags=subprocess.CREATE_NEW_CONSOLE` 在 shell=True 时无效果）
- Linux/macOS: `subprocess.Popen([bat_path], shell=True, cwd=PROJECT_ROOT)`

**`/rm [序号]` 解析逻辑（关键）**:
```python
# 纯 /rm 无参数 → 删当前会话
if cmd == "/rm" or cmd == "/删除": ...
# /rm 数字 → startswith 判断
_rm_idx = 0
if cmd.startswith("/rm ") and cmd[4:].strip().isdigit():
    _rm_idx = int(cmd[4:].strip())
elif cmd.startswith("/删除 ") and cmd[4:].strip().isdigit():
    _rm_idx = int(cmd[4:].strip())
elif cmd.startswith("/删除会话 ") and cmd[6:].strip().isdigit():
    _rm_idx = int(cmd[6:].strip())
# ⚠️ /rm 与 /rename 都 startswith "/r"，/rm 必须排在 /rename 之后检查
```
**陷阱**: 不能用 regex 的 `/rm\s+(\d+)`（微信输入法可能发全角空格），`startswith + split + isdigit` 更鲁棒。

**内存状态**: `_wx_active_session: dict[str, str]` 存 `{user_id:wx_user_id} → session_id`，
`_wx_session_titles: dict[str, str]` 存 `session_id → 用户自定义标题`。服务重启丢失但不影响核心功能。

**`_reply_wechat_text()`** — 纯回复助手（不写 DB、不调 LLM），用于命令响应。普通消息走 `_call_llm()` → `_insert_conversation()` → `_reply_wechat_text()`。

**`_get_user_sessions()`** — 查询 `conversations WHERE user_id=%s AND source='wechat' AND status!=0 GROUP BY session_id ORDER BY last_time DESC LIMIT 10`，用首条 `user_question` 作标题，`_wx_session_titles` 自定义标题优先。

## 与 Hermes 原生 WeixinAdapter 的差异
| | WeixinAdapter | wechat_listener |
|---|---|---|
| 运行方式 | Hermes gateway 进程 | AgentForge FastAPI 后台 Task |
| iLink 凭证 | `.env` + `gateway.yaml` | `platform_config` 表 |
| 消息路由 | Hermes 内部 session 系统 | `user_bindings` 表匹配 |
| 绑定方式 | `hermes gateway setup` CLI | Web 配置页面 |
| 依赖 | certifi (SSL) | aiohttp + certifi (SSL) |

## 换绑场景
扫码确认时 `bind_after_qr` 检测已有绑定 → `UPDATE user_bindings` 覆盖 open_id → 调 `restart_wechat_listener()`。
旧 listener task 被 cancel，新 task 用新凭证开始轮询。微信端不需要做任何操作。
