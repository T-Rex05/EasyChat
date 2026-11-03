# 微信 iLink Bot 集成

AgentForge 通过 Hermes 原生 `gateway/platforms/weixin.py` 接入腾讯 iLink Bot API。

## 架构
```
微信用户 → iLink API (ilinkai.weixin.qq.com) → WeixinAdapter 长轮询
                                                   ↓
                                             platform_config DB
                                             user_bindings DB
                                             conversations.source='wechat'
```

## 数据库表

### platform_config
```sql
CREATE TABLE platform_config (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform VARCHAR(20) NOT NULL UNIQUE,  -- 'wechat'/'feishu'/'email'
    config_json JSON NOT NULL,             -- {token, account_id, base_url, bot_user_id}
    enabled TINYINT DEFAULT 0,
    ...
);
```

### user_bindings
```sql
CREATE TABLE user_bindings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    platform VARCHAR(20) NOT NULL,         -- 'wechat'/'feishu'
    open_id VARCHAR(128) NOT NULL,         -- 微信ID
    UNIQUE KEY uk_platform_openid (platform, open_id),
    UNIQUE KEY uk_user_platform (user_id, platform),
    ...
);
```

### conversations 加 source 列
```sql
ALTER TABLE conversations ADD COLUMN source VARCHAR(20) DEFAULT 'web';
```
值: `web` / `wechat` / `feishu`

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/platform-config/{platform}` | GET | 获取平台配置（脱敏） |
| `/api/platform-config/{platform}` | PUT | 保存平台配置（超管） |
| `/api/user-bindings` | GET/POST | 用户绑定管理 |
| `/api/user-bindings/{id}` | DELETE | 删除绑定 |
| `/api/platform-config/wechat/qr/start` | POST | 发起扫码 |
| `/api/platform-config/wechat/qr/{sid}/status` | GET | 轮询扫码状态 |
| `/api/platform-config/wechat/qr/{sid}/bind` | POST | 确认绑定 |

## QR 扫码流程关键陷阱

### 1. `urllib.request.urlopen()` 同步阻塞事件循环
FastAPI async 端点里直接调同步 HTTP 会卡死整个服务。
**修复**: 用 `asyncio.to_thread()` 把同步调用丢进线程池。

### 2. `qrcode` + `Pillow` 依赖
iLink 返回的 `qrcode_img_content` 是 liteapp URL（不是图片），需服务端用 `qrcode` 库生成 PNG 二维码。
```bash
pip install qrcode Pillow
```

### 3. scaned_but_redirect — 扫码后 iLink 要求切换轮询主机（关键！）
扫码后 iLink 可能返回 `status='scaned_but_redirect'` + 一个 `redirect_host`。
此时**必须把后续轮询的 base_url 切到这个新 host**，否则：
- 继续轮询 `ilinkai.weixin.qq.com` → iLink 不认这个会话 → 微信端显示"暂时无法连接"

Hermes 的 `qr_login()` 中正确处理了此状态（第 1105-1108 行）：
```python
elif status == "scaned_but_redirect":
    redirect_host = str(status_resp.get("redirect_host") or "")
    if redirect_host:
        current_base_url = f"https://{redirect_host}"
```
自部署的 AgentForge 实现时**必须**在 `_poll_qr_session_async` 中同样处理，
会话需要维护 `current_base_url` 字段并在每次轮询时使用它。
忽略此状态是导致扫码失败的最常见根因。

### 4. iLink API 可达性
`ilinkai.weixin.qq.com` 是腾讯国内服务器，VPN 反而绕路更慢。直连实测 ~0.3s。

### 5. bot_type 参数
`get_bot_qrcode` 的 `bot_type` 参数实测：**只有 `3` 返回有效数据**（`qrcode` 字段和 `qrcode_img_content` 字段均非空）。`0/1/2/4/5` 全部返回空字段。

### 6. iLink API 返回 `Content-Type: application/octet-stream` — aiohttp `.json()` 报错
iLink 的 `getupdates` 和 `sendmessage` 端点返回 `Content-Type: application/octet-stream`。
aiohttp 的 `resp.json()` 遇到非 JSON Content-Type 会直接抛异常：
```
Attempt to decode JSON with unexpected mimetype: application/octet-stream
```
**修复**: 所有 iLink API 调用必须改用 `json.loads(await resp.text())` 代替 `resp.json()`：
```python
import json
# ❌ 错误 — 内容明明是 JSON 但 Content-Type 不对，.json() 拒绝解析
data = await resp.json()
# ✅ 正确 — 手动读取文本后用标准 json 库解析
data = json.loads(await resp.text())
```
同时影响 getupdates（轮询收消息）和 sendmessage（发送回复）两个端点。

### 7. QR 后台轮询架构 — 前端不能直接调 iLink（长轮询卡死）

`get_qrcode_status` 是**长轮询**（block ~35 秒），如果前端每 2 秒调一次 `/status` 端点，
会堆叠大量并发阻塞请求 → 卡死整个服务。

**正确架构**:
1. `/wechat/qr/start` — 获取二维码 + **启动后台 `asyncio.Task`**（`_background_qr_poll`）
2. 后台任务每 `QR_POLL_INTERVAL`(3s) 交替轮询 iLink，更新 `_qr_sessions` 内存 dict
3. `/wechat/qr/{sid}/status` — **只读内存状态**，不调 iLink
4. 前端每 2s 调 `/status` 获取内存快照，极快

```python
# start 端点中启动后台任务
loop = asyncio.get_event_loop()
task = loop.create_task(_background_qr_poll(sid))
_qr_tasks[sid] = task
task.add_done_callback(lambda _: _qr_tasks.pop(sid, None))
```

忽略这一点会直接导致**用户点击扫码 → 全部功能卡死**（事件循环被长轮询占满）。

### 9. DeepSeek Anthropic 端点返回 thinking 块 — content[0] 不是文本
DeepSeek 的 Anthropic 兼容端点 `content[0]` 可能是 `type: "thinking"` 的推理块，
真正的回复在 `content[1]`（`type: "text"`）。直接取 `content[0].text` 会报 `KeyError: 'text'`。
**修复**: 遍历 content 数组，thinking 块加 `🧠 思考过程：\n` 标签，text 块直接拼接：
```python
parts = []
for block in data.get("content", []):
    if not isinstance(block, dict): continue
    if block.get("type") == "text":
        parts.append(block.get("text", ""))
    elif block.get("type") == "thinking":
        parts.append(f"🧠 思考过程：\n{block.get('thinking', '')}")
return "\n\n".join(parts).strip()
```
不要用 `"thinking": {"type": "disabled"}` — 用户要求保留深度思考。

### 10. restart_wechat_listener 不能传 {} — 必须重新读取配置
绑定后调用 `restart_wechat_listener()` 时，如果旧监听器已停止但新配置未在 DB 中生效
（事务提交延迟），传入空 dict `{}` 会导致 `_poll_loop(config)` 访问 `config["token"]` 时报 `KeyError`。
**修复**: restart 中先 `time.sleep(1)` 等事务提交，再 `_get_wechat_config()` 读取，无配置则直接 return 不启动。

### 12. `@app.on_event("startup")` 与 `lifespan` 冲突 — 监听器不启动

AgentForge 的 `main.py` 已使用 `@asynccontextmanager async def lifespan(app)`。**此时 `@app.on_event("startup")` 被 lifespan 覆盖，永远不会触发**。微信监听器的启动代码放在 `on_event` 中将静默失效 → 重启服务后发消息无反应。

**修复**: 将监听器启动代码**直接放入 `lifespan` 的 startup 段**，与其他初始化逻辑（sweeper、Hermes 预热）并列。

### 13. 换绑支持 — 不要拒绝已绑定用户的扫码

用户扫码时如果已是绑定状态（`is_rebind=True`），原实现硬拒绝 → 用户先解绑再重新扫码 → 流程复杂。正确做法：直接 `UPDATE` 覆盖现有记录，返回 `is_rebind: true` 让前端知道是换绑。

### 11. LLM URL 端点类型判定
Anthropic 兼容端点（URL 含 `/anthropic` 或 `/messages`）用 `/messages` 端点 + `x-api-key` header；
OpenAI 兼容端点用 `/v1/chat/completions` + `Bearer` token。
误判 → HTTP 404。必须在请求前检测 URL 特征选择正确端点。

## 微信消息监听器 (wechat_listener.py)
```python
# 后台模块：持续长轮询 iLink getupdates → 查绑定 → LLM 回复 → sendmessage
backend/controller/wechat_listener.py
```
启动时机：
- 应用启动 (`main.py` 的 `lifespan` startup 段)
- 绑定后 (`bind_after_qr` 调 `restart_wechat_listener()`) 
- 解绑后 (`delete_binding` 调 `restart_wechat_listener()`，检测无配置自动停)

关键实现细节：
- 使用 `aiohttp.ClientSession` 长轮询（`Content-Length` + iLink headers）
- `g` 响应用 `json.loads(await resp.text())`（iLink Content-Type 是 `application/octet-stream`）
- Dedup：`_dedup` dict，5 分钟 TTL
`urllib.request.urlopen()` 在 async 端点中直接调用时（即未用 `asyncio.to_thread` 包装），用户侧症状为：
- 点击按钮后"一直显示生成二维码中，半天没结果"
- 接着"其他功能全部卡住一直转圈，加载不出来，点击也没反应"
- **刷新也无效** — 因为服务端 event loop 被阻塞，不响应任何新请求

诊断方法：用 `curl`/`python -c` 从服务端本机直接调 iLink API 验证可达性，排除网络问题后锁定代码层面的同步阻塞。

## 消息来源标记

- `Message` 类型增加可选 `source?: string` 字段
- `MessageBubble.vue` 头部显示渠道徽章：`💬 微信` / `🦜 飞书`
- 后端 `chat_controller.py` `/api/history/{chat_id}` 返回消息带 `source` 字段
- `conversation_store.py` `insert_conversation()` 接受 `source` 参数

## 相关文件
- `backend/controller/platform_config_controller.py` — 平台配置 + QR 扫码 API
- `backend/controller/user_binding_controller.py` — 用户绑定 CRUD
- `backend/db/conversation_store.py` — 含 source 字段
- `backend/db/schema.py` — platform_config + user_bindings 建表
- `backend/controller/chat_controller.py` — 消息历史返回 source
- `agent_frontend/src/views/ConfigView.vue` — 渠道绑定 Tab（扫码 + 手动）
- `agent_frontend/src/api/platform.ts` — 前端 API 封装
- `agent_frontend/src/components/chat/MessageBubble.vue` — 消息来源徽章
- `agent_frontend/src/types/chat.ts` — Message.source 字段
- `backend/controller/wechat_listener.py` — 微信消息后台监听器（长轮询 → LLM → 回复）
- `backend/hermes/tools/send_message_tool.py` — Hermes 原生 send_message 工具（weixin 平台支持）
