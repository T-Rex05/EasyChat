---
name: agentforge-dev
description: 修改 AgentForge 项目时加载。包含前后端约定、已知陷阱、验证门禁和用户偏好。
author: AgentForge
category: AI生成
metadata:
  hermes:
    requires_toolsets:
      - file
      - terminal
---

# AgentForge 开发指南

## 触发条件
- 修改 `E:\PythonCode\AgentForge` 中任意前端/后端/数据库代码
- 排查 AgentForge 前端的交互 bug（点击无反应、状态残留、渲染异常）
- 新增功能（API 端点、数据库表、前端组件、第三方依赖）

## 项目结构
- `agent_frontend/` — Vue3+Pinia TS 前端, `dist/` 为 vite build 产物(后端静态服务)
- `backend/controller/` — FastAPI 路由; `backend/db/` — schema/MySQL 适配器; `backend/service/` — auth/权限
- `main.py` — FastAPI 入口+路由注册, `reload=False`, 改 Python 必须重启 `python main.py start 8001`
- `backend/controller/wechat_listener.py` — 微信消息后台监听器（aiohttp 长轮询 iLink getupdates，启动/重启/停止生命周期）
- 并发架构/瓶颈分析见 `references/concurrency-architecture.md`
- **多渠道集成（微信/飞书）** — 数据模型、API、前端 Tab 布局、消息来源标记、微信后台监听器，全栈参考见：
  - `references/wechat-ilink-integration.md` — QR 扫码/手动绑定 & 关键陷阱
  - `references/multi-channel-architecture.md` — 数据模型 & 前端改造
  - `references/wechat-listener-architecture.md` — 后台监听器架构 & 生命周期
  - `references/wechat-commands.md` — 微信内聊天命令系统（/new /history /rename /rm /restart 等）
  - `references/wechat-markdown-strip.md` — 微信 MD→纯文本转换（`_strip_md` 正则规则）
- **多模态图片问答** — 模型检测、图片上传、ChatInput 粘贴/拖拽、微信图片识别，全栈实现参考见：
  - `references/multimodal-image-support.md` — 架构总览、双路 SSE 流式、数据流、关键陷阱

## 验证门禁
- 前端: `npm run build`(exit 0 通过) + `npx vue-tsc --noEmit`(tsconfig baseUrl 弃用是既有警告)
- 后端: `ast.parse` 语法检查; 无 pytest/make test — build+type-check 是最强可用门禁,不以此为由宣称无法验证

## 关键陷阱

### sessionStorage 残留 currentChatId
- `chatStore.currentChatId` 恢复 sessionStorage 旧值, 进入页面时 messages 为空却误高亮历史或新消息发到旧会话
- 修复: 用 `selectedChatId`(需 `messages.length>0` 才返回 chatId)判断 active 和去重; `sendMessage` 里 `isNewChat = !chatId || messages.value.length === 0`

### chatUserId 存 sessionStorage → 新对话刷新后丢失
- `authStore.userId` 优先读 `sessionStorage.getItem('chatUserId')`，sessionStorage 按标签页隔离，打开新标签页/某些场景被清空 → fallback `'0'`
- `'0'` 作为 fallback → 新对话 `thread_id = '0_...'` → `user_id=0` 入库 → 刷新后 `/api/data/sessions` 通过 Token 取到 `user_id=1`，查 `WHERE user_id=1` 看不到 user_id=0 的会话 → 历史列表只剩旧会话
- **修复 1**：`auth.ts` userId computed 改为 `localStorage` 优先 → `sessionStorage` 回退 → fallback `'1'`（不是 `'0'`）
- **修复 2**：login/register 同时写 `localStorage.setItem('chatUserId', uid)`
- **修复 3**：已存在的 user_id=0 数据需 SQL 修正：`UPDATE conversations SET user_id=1, session_id=REPLACE(session_id,'0_','1_') WHERE user_id=0`
- **修复 4（verify 未回写 chatUserId）**：`verify()` (token 刷新时调用) 必须回写 `chatUserId`。用户通过旧 token 自动恢复登录态时，如果 localStorage 里没有 chatUserId（比如换浏览器/清缓存后），userId 会 fallback 到 `'1'`（admin），新建会话全部挂在 admin 名下。修复：verify() 拿到 userData 后 `if (userData.id) { localStorage.setItem('chatUserId', String(userData.id)); sessionStorage.setItem('chatUserId', String(userData.id)) }`
- **修复 5（logout 未清理 chatUserId）**：`logout()` 必须 `localStorage.removeItem('chatUserId')`，否则切换用户后新用户继承上一个用户的 ID，新对话继续挂旧用户名下
- **修复 6（router 兜底同步 — 老 session 从未存过 chatUserId）**：即便修复 1-5 全到位，**已经存在的旧 session**（在修复前登录的）可能 localStorage 里根本没存过 chatUserId，且 `verify()` 实际**从未在应用启动时被调用**过。这种情况下 userId computed 仍然 fallback 到 `'1'` (admin)。**修复**：`router/index.ts` 的 `beforeEach` 守卫在遇到已认证路由时，检查 localStorage/sessionStorage 是否已有 chatUserId；若缺失，调用 `/api/auth/me` 拿到 `userData.id` 并写入。用模块级 `chatUserIdSynced` 标志避免每次路由跳转都调接口。
  ```typescript
  // router/index.ts
  let chatUserIdSynced = false
  router.beforeEach(async (to, from, next) => {
    const token = localStorage.getItem('authToken')
    // ... requiresAuth check ...
    if (token && !chatUserIdSynced) {
      chatUserIdSynced = true
      const existingUid = localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId')
      if (!existingUid) {
        try {
          const { default: request } = await import('../api/request')
          const resp = await request.get('/api/auth/me')
          if (resp.data?.id) {
            const uid = String(resp.data.id)
            localStorage.setItem('chatUserId', uid)
            sessionStorage.setItem('chatUserId', uid)
          }
        } catch { chatUserIdSynced = false }  // 失败则下次重试
      }
    }
    // ... permission check ...
  })
  ```
- **陷阱 — 两个症状其实同源**：会话跑到 admin 历史 + 技能创建人变成 admin，是**同一个 bug**的不同表现：都是 `chatUserId` 缺失 → `authStore.userId` fallback 到 `'1'`。会话端 `thread_id = '1_...'` 归 admin；技能创建端 `_CURRENT_USER_ID_CTX` 从 token 解析到的也是 admin 的 user_id。排查时**两个症状必须一起看**，修一个修不到另一个。
- 详细诊断流程见 `references/chat-user-id-mismatch.md`

### loadChatHistory 守卫误判
- `selectChat` 提前 `setCurrentChatId` → 守卫 `messages.length>0 && currentChatId===chatId` 恒成立 → 跳过加载
- 修复: 用 `prevChatId`(进入函数时捕获)判断; `selectChat` 不再提前 set

### details 折叠被 Vue 覆盖
- `:open="!message.content"` 是受控组件,手动展开会被 content 更新覆写
- 修复: 本地 `isOpen` ref + `@toggle` + `userToggled` 标志,仅未干预时自动跟随

### SKILL.md 渲染 — YAML frontmatter 陷阱
- `skill_service.get_skill()` 返回 `content`(完整 SKILL.md 含 `---...---`) + `body`(`_strip_frontmatter` 去除了 frontmatter 的纯 Markdown)
- 前端 `SkillView.vue` 渲染时必须用 `body`(优先) 或客户端 `stripFrontmatter(content)` 兜底,直接用 `content` 会把 `name: xxx\ndescription: xxx\n---` 当作文本显示
- 列表/详情接口返回 `author`/`version`/`category`,来自 frontmatter 解析;创建技能时 `POST /api/skills` 通过 `optional_user` 注入当前用户为 author

### API 函数名不匹配 — "X is not a function"
- Vue 组件中 `import * as XAPI from '../api/xxx'` 时,调用的函数名必须与 API 模块导出的函数名完全一致
- 典型案例: `SkillView.vue` 调用 `SkillAPI.get(name)` 报错,因为 `skills.ts` 导出的是 `getSkill`(不是 `get`)
- 排查方法: 打开对应的 `../api/*.ts` 文件,逐一对齐 `XAPI.xxx()` 调用与 `export async function xxx` 声明

### 模型配置链路
- 聊天流: `get_current_model_config(user_id)` → `model_configs.is_current=1`(表不存在需自己建且加列) → `user_configs` → env 兜底
- `ModelConfigMapperImpl` 依赖不存在的 `user_info` 表,不可直接用

### 新建表/加列
- 先 `ALTER TABLE` 直接执行, 再同步 `schema.py` + `mysql_impl.py` 建表语句
- MySQL 连接: `pymysql.connect(host='localhost', user='agentforge', password='agentforge123', database='agentforge', charset='utf8mb4')`
- 新增控制器注册到 `main.py` 后做两件事：`ast.parse` 语法检查 + `from backend.controller.xxx import router` 模块导入验证

### 邮箱多配置模式（可复用的 CRUD + 激活切换）

仿照 `model_configs`，实现了 `email_configs`（SMTP，超管）+ `personal_emails`（个人邮箱，所有用户）。通用模式：

1. **建表**：`id/user_id/.../is_current/enabled/created_at/updated_at`，带 `INDEX idx_xxx_current (user_id, is_current)`。从旧 `platform_config`/`user_configs` 迁数据
2. **后端控制器**：`GET` 列表 + `POST` 创建（首次自动 `is_current=1`）+ `PUT {id}` 更新 + `PUT {id}/active` 切换（先清零全表再设新）+ `DELETE {id}` 软删除 + `POST {id}/test` 测试连接。所有端点带 `user: dict = Depends(get_current_user)` 鉴权，增删改查超管检查
3. **注册**：`main.py` 中 `app.include_router(router)`，然后 `ast.parse` + 模块导入验证
4. **前端 API** (`config.ts`)：导出 `getXxxConfigs/createXxxConfig/setActiveXxxConfig/deleteXxxConfig/testXxxConfig` + TypeScript 接口
5. **前端 UI**：左右分栏 — 左列表卡片 + 右新增表单卡片（`.split-layout` grid）

**QQ 邮箱**：服务器 `smtp.qq.com`，端口 `465`(SSL) 或 `587`(STARTTLS)，密码用授权码（QQ邮箱设置→账户→开启SMTP→获取16位码）

**SMTP 测试**：`POST /api/platform-config/email/test` 支持 `to_email` 参数；`POST /api/email-configs/{id}/test` 从 DB 读配置发测试邮件

**文件地图**：
- `backend/controller/email_config_controller.py` — 6 路由（SMTP CRUD+test）
- `backend/controller/personal_email_controller.py` — 4 路由（个人邮箱 CRUD）
- `agent_frontend/src/api/config.ts` — `EmailConfig`/`PersonalEmail` 接口 + API 函数
- `agent_frontend/src/views/ConfigView.vue` — 邮箱 Tab 左右分栏布局

### ConfigView 左右分栏布局

紧凑 UI 模式，适用于"列表 + 新增表单"场景：

```css
.split-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.config-mini-list { display: flex; flex-direction: column; gap: 6px; }
.mini-item {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 10px 12px; border-radius: var(--radius-md);
  background: var(--bg-secondary);
}
.mini-item.active { background: var(--bg-card); border: 1px solid var(--brand-light); }
.mini-main { flex: 1; min-width: 0; }
.mini-name { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.mini-meta { font-size: 11px; color: var(--text-tertiary); word-break: break-all; }
.mini-actions { display: flex; gap: 4px; flex-shrink: 0; margin-left: 8px; }
```

左侧卡片放 `.config-mini-list`（紧凑列表），右侧卡片放新增表单。模型配置 Tab、邮箱配置 Tab 均采用此布局。表单按钮 `style="width:100%;margin-top:8px;"` 全宽。非超管用户右侧卡片不渲染（`v-if="isSuperAdmin"`）。

### 微信命令系统
详见 `references/wechat-ilink-integration.md`、`references/multi-channel-architecture.md`、`references/wechat-listener-architecture.md`。**13 个关键陷阱**，必须逐条检查：

1. **同步 I/O 阻塞事件循环** — `urllib.request.urlopen()` 必须 `asyncio.to_thread()`，否则全部卡死
2. **`qrcode` + `Pillow` 运行时依赖** — `pip install qrcode Pillow`，iLink 返回 liteapp URL 不是图片
3. **scaned_but_redirect** — 扫码后必须切换 base_url，否则微信显示"暂时无法连接" ⚠️ 最常见根因
4. **bot_type 只有 3 有效** — 0/1/2/4/5 全返回空
5. **iLink Content-Type 是 application/octet-stream** — 必须 `json.loads(await resp.text())` 不能 `.json()`
6. **QR 后台轮询架构** — 前端 `/status` 只读内存，后台 asyncio.Task 轮询 iLink。前端直调 → 35s 长轮询堆叠卡死
7. **DeepSeek Anthropic thinking 块** — `content[0]` 可能是 thinking，遍历找 `type="text"`
8. **restart_wechat_listener 不能传 {}** — 先 `sleep(1)` 等事务，再重读 DB，无配置直接 return
9. **LLM URL 端点类型判定** — Anthropic 用 `/messages` + `x-api-key`，OpenAI 用 `/v1/chat/completions` + `Bearer`
10. **`@app.on_event("startup")` 与 `lifespan` 冲突** — lifespan 存在时 on_event 永不触发，监听器放 lifespan 内
11. **换绑不拒绝** — 已绑定用户扫码直接 UPDATE 覆盖
12. **QR 会话生命周期** — 绑定后标记 `bound` 不删除，允许前端后续查询
13. **`conversations` 表需 ALTER ADD source 列** — 新增 `platform_config` + `user_bindings` 两张表
14. **`_handle_message` / `_reply_wechat_text` 缺 `import aiohttp`** — 函数内部用 `aiohttp.ClientTimeout(total=15)` 但没有 root-level import → `NameError: name 'aiohttp' is not defined`。必须在函数体开头加 `import aiohttp`。
15. **`/rm` 与 `/rename` 前缀冲突 + 命令匹配策略** — `/rename` 必须排在 `/rm` 之前检查（两者 `startswith("/r")`）。`/rm`（无参数）用 `cmd == "/rm"` 精确匹配，不能用 `cmd in ("/rm", ...)`，否则 `/rm 1` 被提前拦截；`/rm <序号>` 用 `startswith` 判断，不要用 regex（微信输入法可能全角空格，`\\s+` 不匹配）。同样 `/rename` 的标题从原始 `text`（未 lower）取。所有命令先 `strip().lower()`。详见 `references/wechat-commands.md`。
16. **微信回复必须走 `_strip_md` — 保守策略** — LLM 返回含 `# 标题`、表格等 MD。ClawBot **能渲染** `**bold**`、`*italic*`、`~~strike~~`、`[link](url)`、`>quote`、列表、`` `code` ``、``` 代码块 ``` —— 这些**原样保留不转换**。只转换 ClawBot 不支持的：`#` → `【】`、`##+` → `**加粗**`、表格 → `- key: value` 键值对、`---` → 全角长划线、`- [ ]` → `☐`/`☑`。在 `_reply_wechat_text(_strip_md(answer), ...)` 中调用。DB 存原始 answer（保留 MD 给 Web 端看），发微信用 stripped 版本。详见 `references/wechat-markdown-strip.md`。
17. **`wx_` 前缀 thread_id 解析** — 微信会话的 `thread_id` 格式为 `wx_{user_id}_{openid*}`，chat_controller 的 `token_stream_events` 按 `thread_id.split('_')[0]` 取 user_id 会拿到 `'wx'` → 类型错误。必须先行检测 `thread_id.startswith("wx_")` → `split("_", 2)[1]` 取 user_id。同时 `/api/data/sessions` 查询需加 `MAX(c.source) as source`，微信会话标题加 `💬` 前缀。
18. **sendtyping 用 `ilink_user_id` 而非 `user_id`** — iLink sendtyping 端点要求的字段名是 `ilink_user_id`，传 `user_id` 返回 `errcode=-2, errmsg="ilink_user_id required"`。`getconfig` 端点在当前设置下不返回 `typing_ticket`（仅 `ret/errmsg`），因此不需要先调 getconfig 获取 ticket，直接发 `{"ilink_user_id": to_user_id, "status": 1或2}`。
19. **消息分块 (_split_text_for_weixin)** — iLink 单条消息上限 ~2048 字符，按 `_WEIXIN_MAX_CHARS=1800` 在段落+代码块边界拆分，代码块保持完整不拆。单块超限时在最后一个换行处硬截断。块间 `asyncio.sleep(1.2)`。入口：`_reply_wechat_chunks(chunks, ...)`。
20. **微信图片 URL 在 `media.full_url` 嵌套中** — iLink 图片消息的 `item_list` 中 `image_item` 结构为 `{aeskey, media: {full_url, ...}, ...}`，不是顶层 `url`/`cdn_url`。提取时必须检查嵌套路径：`img_data.get("url") or img_data.get("cdn_url") or img_data.get("full_url") or (img_data.get("media") or {}).get("full_url")`。
21. **微信图片是 AES-128-ECB 加密的（不是 AES-CBC）** — iLink 返回的图片数据不是原始图片，是 AES-128-ECB + PKCS#7 填充加密的。文件头不会是标准 JPEG/PNG 魔数（如 `ffd8ff` 或 `89504e47`），而是随机字节。**必须先解密**：
    - 从 `image_item` 提取 `aeskey`（32 字符 hex 字符串，如 `4ada6213e741ed9a5f591ba6c21df862`）
    - 用 `pycryptodome` 解密：
      ```python
      from Crypto.Cipher import AES
      from Crypto.Util.Padding import unpad
      key = bytes.fromhex(aeskey)  # 16 bytes = AES-128
      cipher = AES.new(key, AES.MODE_ECB)  # ⚠️ ECB 模式，无 IV
      decrypted = cipher.decrypt(img_content)
      img_content = unpad(decrypted, AES.block_size)  # PKCS#7 去填充
      ```
    - **依赖**：`pip install pycryptodome`
    - **调试技巧**：打印前 20 字节 hex（`img_content[:20].hex()`），解密后应该是 `ffd8ff`（JPEG）或 `89504e47`（PNG）开头
    - **⚠️ 常见错误**：不要用 AES-CBC（无论 IV=0 还是 IV=key[:16]），解密后前两个字节碰巧是 `ffd8` 但实际数据损坏，API 会报 "The image format is illegal and cannot be opened"
    - **排查顺序**：下载成功 → 检查文件头 → 发现非标准格式 → 检查是否有 `aeskey` → AES-128-ECB 解密 → 去 PKCS#7 填充 → 再检测 MIME → base64 编码
22. **微信多模态检测三层优先级** — `wechat_listener._handle_message` 检查模型是否支持图片时，按优先级检查：
    - **探测结果**（`probe_ok`）：测试连接时的图片探测结果（最权威）
    - **自动检测**（`is_multimodal_model(model_name)`）：基于模型名的正则匹配
    - **数据库字段**（`db_multimodal`）：手动设置的标记
    - 判定逻辑：`is_multi = probe_ok or is_multimodal_model(model_name) or bool(db_multimodal)`
    - **⚠️ 陷阱**：不能只查数据库字段，因为用户可能没有手动设置，或者数据库未同步

23. **微信 iLink 图片解密 — AES-128-ECB 完整流程** — 参见陷阱 21。密钥格式：hex 32 字符（16 bytes）或 base64。模式：ECB（无 IV）。填充：PKCS#7。解密后检测魔数确认格式正确，再 base64 编码发给 LLM。
    - **排查顺序**: 下载成功 → 检查文件头 → 发现非标准格式 → 检查是否有 `aeskey` → AES-128-ECB 解密 → 去 PKCS#7 填充 → 再检测 MIME

24. **微信图片缓存+文字合并机制** — 微信不能同时发图片和文字，用户先发图片后发文字描述。架构：
    - 收到纯图片（无文字）→ 下载+解密+base64 → 缓存到 `_pending_images[pending_key]` → 回复"📷 已收到 N 张图片，请在 30 秒内发送文字描述，或发送 /send 直接发送"
    - 收到纯文字（无图片）→ 检查 `_pending_images` 是否有缓存 → 有则合并（`images_for_llm = pending.pop("images", [])`）→ 调多模态 LLM
    - 超时 30 秒 → 清理缓存
    - **⚠️ 关键陷阱**：`_pending_images` 初始化必须在合并逻辑之后，不能在合并前 `images_for_llm = []` 覆盖已合并的值
    - **⚠️ 默认文本检测**：微信可能在图片消息中附带默认文本（如 `[图片]`、`image`），需要过滤：`default_texts = ["[图片]", "[image]", "图片", "image"]`，`if not text or text.lower() in default_texts:` 视为纯图片

25. **模型名标签剥离 — 所有 LLM 调用函数都需要** — 数据库 `model_name` 可能含 `[1m]`、`[32k]` 等上下文标签（如 `qwen3.7-plus[1m]`），API 不识别会报 400。**所有**调用 LLM 的函数都必须剥离：
    ```python
    if "[" in model:
        model = model.split("[")[0]
    ```
    受影响函数：`_call_llm()`、`_call_llm_multimodal()`、`chat_controller.token_stream_events()` 等。Hermes adapter 内部已处理，但微信监听器的独立 LLM 调用需要自己处理。

26. **前端等待动画位置 — 在气泡内而非外部独立元素** — 等待 LLM 首 token 的"思考中..."动画必须在 `MessageBubble.vue` 内部渲染（`v-else-if="isThinking"`），不能在 `ChatView.vue` 中创建独立的 `.message-bubble.assistant` 元素。外部独立气泡与聊天区白框分离，视觉上难看。
    - `isThinking` computed：`message.role === 'assistant' && !message.content && !message.thinkingProcesses?.length`
    - 动画：三个跳动圆点 + "思考中..." 文字，在助手气泡内显示
    - **⚠️ 陷阱**：如果 ChatView 中有独立的流式加载动画 div，必须删除，否则出现两个气泡（白框内一个、白框外一个）

### 前端 API 调用必须带认证 Token
- `ConfigView.vue` 中的 `savePersonalEmail` 原用裸 `fetch('/api/config', ...)` → 401 未授权无响应
- **修复**: `import request from '@/api/request'` 然后用 `request.post('/api/config', {key, value})`，Axios 拦截器自动带 Bearer token
- **后端权限**: `config_controller.py` 的 POST 端点原用 `require_perm("config.view")`，对于 `personal_email` 这类所有用户都要用的 key 会 403。改为 `get_current_user`，手动判断：`req.key != "personal_email" and role != "super_admin"` 才 403

### FastAPI 异步端点中同步 I/O 会卡死整个事件循环 ⚠️
- **症状**: 点击一个按钮后，整个应用所有请求全部卡住转圈，刷新无效
- **根因**: 在 `async def` 端点中直接调用同步阻塞函数（如 `urllib.request.urlopen()`），阻塞了 FastAPI 唯一的 event loop 线程，所有后续请求排队等待
- **修复**: 将同步 I/O 调用包装为 `await asyncio.to_thread(sync_func, *args)` —— 把阻塞操作丢进线程池，释放事件循环
  ```python
  # ❌ 错误：同步 HTTP 调用阻塞事件循环
  @router.get("/api/xxx")
  async def handler():
      resp = urllib.request.urlopen("https://...")  # 卡死！
  
  # ✅ 正确：异步包装
  def _sync_get(url):
      return json.loads(urllib.request.urlopen(url).read())
  
  async def _async_get(url):
      return await asyncio.to_thread(_sync_get, url)
  
  @router.get("/api/xxx")
  async def handler():
      resp = await _async_get("https://...")  # 不阻塞
  ```
- 适用场景：`urllib`、`requests`、`pymysql` 同步查询、文件 I/O 等任何同步阻塞操作

### Monaco Editor 初始化
- `monaco.editor.create` 需容器有高度(offsetHeight>0), splitpanes 内布局可能延迟,需 `setTimeout` 重试
- 切换 Tab 或文件时先 `editor.dispose()` 再重建
- 不要用 `vite-plugin-monaco-editor`（Monaco 0.56 + Vite 6 下 `?worker` 导入解析失败），直接 `import * as monaco from 'monaco-editor'` 即可
- IDE 模式全栈开发模式详见 `references/ide-mode-patterns.md`

### 模型配置测试连接的 Anthropic 端点坑
- DeepSeek Anthropic 兼容端点（`https://api.deepseek.com/anthropic`）只接受 POST，GET 一律 404
- 检测 URL 含 `/anthropic` 则走 Anthropic 分支：POST 到 `{base}/v1/messages`（自动补全路径，已有 `/v1/messages` 或 `/v1` 后缀则不重复追加）
- Anthropic 用 `x-api-key` header + `anthropic-version: 2023-06-01` header
- **404 返回必须判 `ok: False`**（仅 2xx 算成功），不能跟 2xx 一样判成功
- 测试连接返回需带 `is_multimodal` 字段，**自动检测优先于数据库字段**：
  - **三层检测体系**：① 静态规则（模型名正则匹配，零开销）→ ② 厂商元数据接口（预留）→ ③ 图片探测预检（7天缓存）
  - **静态规则覆盖范围**：GPT-4o/4.1/o 系列、Claude 3+/4 系列、Gemini 全系列、Qwen-VL/Qwen3 系列（含 qwen3.7-plus）、GLM-4V/5 系列、DeepSeek VL 系列
  - **判定逻辑**：`detected = is_multimodal_model(model_name) or stored_multimodal`，任一为 true 即判为多模态
  - 前端展示「🖼️ 多模态」badge，测试连接失败时也显示检测结果
- 多模态自动检测见 `backend/utils/multimodal_detect.py`，详见 `references/model-config-multimodal.md`
- 前端模型配置表单有 URL 提示：填根域名即可，系统自动补全 `/v1/models` 或 `/v1/messages`
- 详见 `references/model-config-api.md`

### 消息气泡布局模式 — 用户靠右，助手靠左，居中限宽 1100px

聊天界面标准布局：用户消息右对齐（蓝色渐变气泡），助手消息左对齐（白色边框气泡）。

**实现方式**：使用 `data-role` 属性选择器控制对齐，而非在组件内部判断 role：

```css
/* ChatView.vue */
.message-anchor {
  max-width: 1100px;  /* ⚠️ 用户偏好：不要太窄（860px 太中间），1100px 刚好 */
  width: 100%;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
}

.message-anchor[data-role="user"] {
  justify-content: flex-end;  /* 用户消息靠右 */
}

.message-anchor[data-role="assistant"] {
  justify-content: flex-start;  /* 助手消息靠左 */
}
```

**关键点**：
- 在消息列表的 `v-for` 容器上设置 `:data-role="message.role"`
- 气泡组件（`MessageBubble.vue`）内部不需要处理对齐逻辑
- **用户偏好**：`max-width: 1100px`，不要 860px（太窄太中间），也不要完全贴边
- 助手气泡的"思考中..."动画必须在气泡内部渲染（见陷阱 26），不能创建独立的外部加载指示器

### 输入区按钮布局 — 操作按钮右对齐

输入框下方的操作栏（上传图片、发送/停止按钮）必须右对齐：

```css
/* ChatView.vue */
.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;  /* ⚠️ 关键：按钮放右边 */
}
```

**用户偏好**：发送按钮和图片上传按钮放在输入框右侧，不要左侧。这是现代聊天界面的标准布局（类似微信、ChatGPT）。

### 打开历史会话后自动滚动到底部
- `handleLoadHistory` 改为 `async`，`await loadChatHistory(chatId)` 后 `scrollToBottom(false)`（false=立即跳转非平滑）
- 需从 `useAutoScroll` 同时解构 `scrollToBottom` 和 `smartScrollToBottom`
- `setTimeout(() => { scrollToBottom(false); refreshNavState(); }, 100)` 确保 DOM 更新完成

### 详情卡片不可滚动
- `.card` + `display:flex; flex-direction:column` + 固定高度布局中，`.card-body` 不会自动滚动
- 修复：`.skill-detail-card .card-body { overflow-y: auto; flex: 1; }`
- 通用模式：任何 flex-column 卡片内的 body 区域，显式加 `overflow-y: auto` + `flex: 1`

### 技能分类功能
- 后端：`GET /api/skills/categories` 返回去重排序的分类列表；`PUT /api/skills/{name}` 接受可选 `category` + `description`
- `update_skill` 改分类时用 `shutil.move()` 移动目录到新分类子目录，自动 `mkdir(parents=True)`
- 前端：分类标签筛选（`activeCategory` ref + `filteredSkills` computed）+ 编辑时显示/修改分类字段
- 新 API 兜底：`listCategories()` 404 时从 `skills` 列表提取分类（`Set` 去重），保证后端未重启也能显示标签

### 技能创建人（author）显示问题
- **症状**：技能管理页面点击技能详情，"👤 创建者"显示"未知"
- **根因链路**：AI 生成的 content 含 `author: AgentForge`（从 agent-skill-creator frontmatter 继承）→ `_create_skill` 检测 frontmatter 已有 author 不注入真实用户 → `_strip_agent_frontmatter_defaults()` 移除 `author: AgentForge` → SKILL.md 没有 author 字段 → 前端 fallback 显示"未知"
- **修复**：`_create_skill` 在 `_strip_agent_frontmatter_defaults()` 之后追加一步：如果 strip 后 frontmatter 缺少 author 字段，用 `current_username`（优先从 `_CURRENT_USERNAME_CTX.get()` 获取，fallback 到 DB 查 users 表）重新注入
- **⚠️ 关键陷阱 — ContextVar 为空导致修复失效**：即使 strip+re-inject 逻辑写对了，如果 `_CURRENT_USERNAME_CTX.get()` 返回空字符串，`current_username` 为空，后续的 `if current_username:` 判断不通过，author 仍然不会被注入。**排查时必须验证 ContextVar 是否被正确设置**。`hermes_adapter` 在对话流程中会设置 `_CURRENT_USERNAME_CTX`，但如果技能创建发生在其他上下文（如审核通过、批量导入），ContextVar 可能未被初始化。
- **诊断步骤**：
  1. 在 `_create_skill` 开头打印 `current_username = _CURRENT_USERNAME_CTX.get()` 确认是否为空
  2. 如果为空，检查调用链上游是否设置了该 ContextVar
  3. 如果 ContextVar 确实为空，fallback 到 DB 查询：`get_conn().execute("SELECT username FROM users WHERE id = %s", (current_user_id,)).fetchone()`
- **陷阱**：strip 后 frontmatter 开头可能有空行（`---\n\nname: t\n...`），正则要用 `\n---\s*\n` 匹配，不能用 `^---$`；frontmatter 解析必须容忍 leading `\n`
- **相关文件**：
  - `backend/hermes/tools/skill_manager_tool.py` — `_create_skill` (strip + re-inject) 和 `_strip_agent_frontmatter_defaults`
  - `backend/hermes_adapter.py` — `_CURRENT_USERNAME_CTX` ContextVar 定义和设置
  - `backend/service/skill_service.py` — `list_skills/get_skill` 从 SKILL.md frontmatter 读 author
  - `agent_frontend/src/views/SkillView.vue:128` — `selected.author || '未知'`
- **⚠️ 双路径陷阱**: 技能创建有两条完全独立的代码路径：
  - **路径 A（前端 UI "创建技能"按钮）**: `POST /api/skills` → `skill_controller.create_skill()` → `skill_service.create_skill(name, content, ..., author=user.username, user_id=user.user_id)`. Controller 从 auth token 的 user dict 提取 author 和 owner_id.
  - **路径 B（AI 对话 `skill_manage(create)`）**: `skill_manager_tool._create_skill()` 从 `_CURRENT_USERNAME_CTX` 获取当前用户名，自己做 strip + re-inject author.
  - 两条路径的 author/owner_id 逻辑**完全独立**,修一条不等于修另一条.排查"创建者显示未知"时必须同时检查两条路径.
- **⚠️ 已有数据不会自动修正**: 修复创建代码后,在修复之前创建的技能仍保留错误的 author/owner_id.需手动定位修补: `find HERMES_HOME/skills -name SKILL.md -exec grep -L "author:" {} \;` 找到缺 author 的文件并补上; 会话数据需 `UPDATE conversations SET user_id=<correct_id> WHERE ...`.

### 技能权限/审核/锁定系统

**skill_meta 表**: `id/name/owner_id/category/status(pending|approved|rejected)/locked(0|1)/reviewed_by/reviewed_at/created_at/updated_at`。MySQL 建表 + 迁移现有技能 INSERT。

**核心规则**:
- 普通用户只能看到 owner_id 匹配或 `owner_id=1` 且非 AI生成 分类的技能；AI生成 对普通用户完全隐藏
- 超级管理员看到全部技能 + 可锁定/解锁 + 只有超管可管理分类（创建/重命名/删除，`require_super_admin`）
- 锁定技能：Hermes `skills_tool._find_all_skills` 输出前 `_filter_locked_skills` + `skill_view` 检查 locked → Agent 不加载；API `get_skill` 拒绝非超管
- 审核流：**前台模式（用户主动创建）**所有技能一律 `status=pending`（包括 admin/super_admin）；**后台模式（AI 自主生成）**自动 `approved`
- `skill_manager_tool._create_skill` 调用 `_meta_insert(name, owner_id=<真实user_id>, category, status=final_status)`
- **owner_id 已从上下文获取**: `_CURRENT_USER_ID_CTX.get() or 1`，不再硬编码 `1`
- **author 从 ContextVar 获取（优先）**: `_create_skill` 先调 `_CURRENT_USERNAME_CTX.get()` 获取当前登录用户名（在对话流程中已由 `hermes_adapter` 设置），fallback 到 DB 查询 users 表。**⚠️ 陷阱**: DB fallback 路径 `get_conn().cursor()` **会静默失败**——AgentForge 用的 `_MySQLAdapter` 没有 `.cursor()` 方法（它提供 `.execute()` 直接查询），`except Exception: pass` 吞掉错误后 `current_username` 保持空字符串 → strip+re-inject 逻辑不触发 → frontmatter 缺 author → 前端显示"未知"。**必须把 ContextVar 作为主路径**，DB 查询只作兜底。
- **pending 技能不可用**: `skills_tool._filter_locked_skills()` 同时过滤 `status=pending` + `locked=1`，Agent 系统不加载待审核技能

**用户主动创建的技能一律走审核**:
- `skill_manager_tool._create_skill` 前台模式下设置 `status='pending'`（包括 admin/super_admin）
- AI **应该**在 `skill_manage(create)` 之后调用 `submit_skill_for_review`（因为返回 `need_review: true`）
- 审核通过后技能从 `pending` 变为 `approved`，在技能管理页面可见且可被 Agent 使用
- **AI 自主生成的技能**（后台模式，`is_background_review()=true`）才直接 `approved`，不走审核
- **审核通过方式**: ① 前端管理页→审核队列→点"通过"；② Python 直接调 `from backend.service.review_service import approve; approve(submission_id, reviewed_by='admin')`；③ API `POST /api/review/approve`
- **owner_id 硬编码问题**：`skill_manager_tool._create_skill` 第 1026 行硬编码 `owner_id=1`，导致技能管理页面"创建人"显示"未知"（前端用 owner_id 反查 users 表，但 id=1 不是当前登录用户）
- **修复方向**：`_create_skill` 需要从调用上下文获取真实 user_id（通过 `_CURRENT_USER_ID_CTX` 或从 users 表查 username 对应的 id）

**两条审核链路**:
- **skill_manager_tool**: 直接写 `HERMES_HOME/skills/` + 插入 `skill_meta`，`status` 由调用方 role 决定（AI 直接 `approved`）
- **review_service** (`submit_skill_for_review` 工具 / 前端提交): 写入 `backend/pending/skills/{id}.yaml`，前端技能管理**不显示** pending 项，需管理员审核通过后才复制到 `HERMES_HOME/skills/`
  - **陷阱**: `submit_skill_for_review` (`tools_decorator.py`) 会从 frontmatter 提取 `author`。若 AI 写了 `author: AgentForge`，会覆盖 `_CURRENT_USERNAME_CTX` 获取的真实用户名 → `submitted_by` 变成 "AgentForge" 而非登录用户。修复后逻辑：`if not real_username and fm.get('author')` —— 只有无真实登录用户时才用 frontmatter author
- **审核通过方式**: ① 前端管理页→审核队列→点"通过"；② Python 直接调 `from backend.service.review_service import approve; approve(submission_id, reviewed_by='admin')`；③ API `POST /api/review/approve`（需 `review.approve` 权限）
- **相关端点** (`review_controller.py`): `GET /api/review/pending`, `POST /api/review/approve`, `POST /api/review/reject`, `GET /api/review/history`

**关键文件**:
- `backend/db/schema.py` — skill_meta 建表 + `Perm.SKILL_DIRECT/SKILL_LOCK`
- `backend/service/skill_service.py` — `list_skills/get_skill` RBAC；`lock/unlock/approve/reject`；metadata helper `_meta_all/_meta_get/_meta_insert/_meta_update`
- `backend/controller/skill_controller.py` — `GET /pending`, `PUT /{name}/lock|unlock|approve|reject`；categories 需 `require_super_admin`
- `backend/hermes/tools/skills_tool.py` — `_filter_locked_skills` 在缓存返回和新扫描时都过滤

### 技能所有权检查
- `update_skill(name, ..., user_id, role)` 和 `delete_skill(name, user_id, role)` 必须接收 `user_id` 和 `role` 参数
- Controller 必须从 `get_current_user` 取 `user_id`/`role` 传入 service；不传则权限检查形同虚设
- 权限规则：`role=='super_admin'` → 放行；否则 `meta.owner_id==user_id` → 放行；否则 `ValueError` → controller 映射为 HTTP 403
- **陷阱**：`delete_skill` 中 `skill_dir = skills_dir / name` 找不到就 raise，但技能实际在 `skills/<category>/<name>/SKILL.md` 子目录 → 必须先搜根目录再搜子分类目录
- **陷阱**：`get_skill` 的可见性逻辑必须与 `list_skills` 一致，否则用户能在列表中看到技能但点击后报 404；"普通用户看得到公开技能"条件：`owner_id==1` 且 `category!='AI生成'`

### get_skill 返回缺少 category 字段
- `SkillDetail` Pydantic 模型未声明 `category` → 前端 `selected.category` 为 `undefined` → fallback `'其他'`
- 修复：模型 + `get_skill()` 返回 dict 都加 `"category": fm.get("category", "其他")`
- 前端双保险：`selected.frontmatter?.category || selected.category || '其他'`

### 登录/登出 → 聊天状态残留
- 切换用户后 `chatStore` 仍保留上一用户的 `currentChatId` 和 `messages` → 新用户看到旧对话
- 修复：`auth.ts` logout 中调用 `useChatStore().resetAll()`；`chat.ts` 新增 `resetAll()` 清空状态 + `sessionStorage.removeItem('currentChatId')`

### SSE yield 中 f-string 转义陷阱 — 前端卡住无响应 ⚠️
- **症状**：发送消息后前端一直转圈，SSE 流无任何数据返回，后端日志显示已走到对应代码路径（如 warning 已打出）
- **根因**：`chat_controller.py` 的 SSE yield 语句中误用 `\\\\n\\\\n`（双反斜杠，字节 `5c 5c 6e 5c 5c 6e`）代替 `\\n\\n`（字节 `5c 6e 5c 6e`）。Python f-string 求值时 `\\\\n` 输出字面量文本 `\n`（两个字符 `0x5c 0x6e`），而 SSE 协议要求每条消息以**真正的** `\n\n`（两个 `0x0A` 字节）结尾。前端 EventSource 收不到正确终止符就一直挂起
- **诊断方法**：用 `xxd` 字节级对比正确行和 bug 行
  ```bash
  # 正确: 字节尾部 5c 6e 5c 6e → f-string 解析为真正换行
  sed -n '358p' chat_controller.py | xxd | tail -1
  # Bug: 字节尾部 5c 5c 6e 5c 5c 6e → f-string 输出字面量 \n\n 文本
  sed -n '373p' chat_controller.py | xxd | tail -1
  ```
- **修复**：用 Python 字节级替换
  ```python
  old = bytes([0x5c, 0x5c, 0x6e, 0x5c, 0x5c, 0x6e])  # 6 bytes: \\n\\n
  new = bytes([0x5c, 0x6e, 0x5c, 0x6e])               # 4 bytes: \n\n
  for pos in reversed(positions):
      data = data[:pos] + new + data[pos+6:]
  ```
- **预防**：新增 SSE yield 语句时，复制已有的正确 yield 行（如 358 行的 `fallback_msg` 路径）作为模板，写完立即用 `grep -n '\\\\\\\\n\\\\\\\\n' chat_controller.py` 扫描是否有残留的双反斜杠

## 用户偏好
- 中文回复
- 直接动手, 不空谈方案; UI 大改前给 A/B/C 菜单让用户选
- 交互 bug 先修再解释, 然后提示 Ctrl+F5 复核
- **排查要仔细**：不要遗漏明显的代码路径（如所有 LLM 调用函数都要剥离模型标签），不要重复犯同样的错误
- **不要卡在验证循环**：如果项目没有 pytest/lint 配置，build 通过就可以提交，不要反复尝试运行不存在的测试命令
- **UI 视觉改动要主动确认效果**：完成前端样式修改后，先让用户 Ctrl+F5 看效果，满意再提交；不要在无 lint 配置时反复尝试运行不存在的验证命令
- **排查要仔细**：不要遗漏明显的代码路径（如所有 LLM 调用函数都要剥离模型标签），不要重复犯同样的错误
- **不要卡在验证循环**：如果项目没有 pytest/lint 配置，build 通过就可以提交，不要反复尝试运行不存在的测试命令
- **UI 视觉改动要主动确认效果**：完成前端样式修改后，先让用户 Ctrl+F5 看效果，满意再提交；不要在无 lint 配置时反复尝试运行不存在的验证命令
- **排查要仔细**：不要遗漏明显的代码路径（如所有 LLM 调用函数都要剥离模型标签），不要重复犯同样的错误
- **不要卡在验证循环**：如果项目没有 pytest/lint 配置，build 通过就可以提交，不要反复尝试运行不存在的测试命令
- **UI 视觉改动要主动确认效果**：完成前端样式修改后，先让用户 Ctrl+F5 看效果，满意再提交；不要在无 lint 配置时反复尝试运行不存在的验证命令
