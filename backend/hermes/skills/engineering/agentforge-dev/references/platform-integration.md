# 多渠道（微信/飞书）集成模式

## Hermes 原生微信支持

Hermes 自带完整的微信个人号 Bot 能力，通过腾讯官方的 **iLink Bot API** (`https://ilinkai.weixin.qq.com`) 实现：

- **网关适配器**: `backend/hermes/gateway/platforms/weixin.py` — 长轮询收消息、发文本/图片/语音/文件、二维码扫码登录
- **发送工具**: `backend/hermes/tools/send_message_tool.py` — `_WEIXIN_TARGET_RE` 匹配微信 ID（`wxid_xxx` 等），第 417-434 行支持纯 `.env` 配置无需 gateway.yaml
- **环境变量**: `WEIXIN_TOKEN`、`WEIXIN_ACCOUNT_ID`、`WEIXIN_BASE_URL`、`WEIXIN_CDN_BASE_URL`、`WEIXIN_HOME_CHANNEL`

## 数据模型

### platform_config 表（系统级平台凭证）
```sql
CREATE TABLE platform_config (
    platform    VARCHAR(20) NOT NULL UNIQUE,   -- wechat/feishu/email
    config_json JSON NOT NULL,                  -- {token, account_id, base_url, ...}
    enabled     TINYINT DEFAULT 0
);
```

### user_bindings 表（用户↔平台账号映射）
```sql
CREATE TABLE user_bindings (
    user_id     BIGINT NOT NULL,
    platform    VARCHAR(20) NOT NULL,           -- wechat/feishu
    open_id     VARCHAR(128) NOT NULL,          -- 微信ID / 飞书open_id
    nickname    VARCHAR(128) DEFAULT '',
    UNIQUE KEY uk_platform_openid (platform, open_id),
    UNIQUE KEY uk_user_platform (user_id, platform)
);
```

### conversations.source 列（消息来源标记）
```sql
ALTER TABLE conversations ADD COLUMN source VARCHAR(20) DEFAULT 'web';  -- web/wechat/feishu
```

## 后端控制器注册模式

1. 新建 `backend/controller/platform_config_controller.py`，定义 `router = APIRouter(prefix="/api/platform-config")`
2. 新建 `backend/controller/user_binding_controller.py`，定义 `router = APIRouter(prefix="/api/user-bindings")`
3. 在 `main.py` 的 `create_app()` 中注册：
```python
from backend.controller.platform_config_controller import router as pcfg_router
app.include_router(pcfg_router)
```

## iLink QR 扫码绑定流程

### 关键陷阱：`qrcode_img_content` 不是图片 ⚠️

iLink API `GET /ilink/bot/get_bot_qrcode?bot_type=3` 返回的 `qrcode_img_content` **是 liteapp 协议 URL 字符串**（如 `https://ilinkai.weixin.qq.com/...`），不是图片二进制或图片 URL。**不能**作为 `<img src>` 直接渲染——会导致前端显示空白。

**正确做法**：服务端用 `qrcode` 库把 `qrcode_img_content`（或 fallback `qrcode` hex token）生成真正的 PNG 二维码，返回 base64 data URI：

```python
def _generate_qr_image(data: str) -> str:
    import qrcode as qrcode_lib
    qr = qrcode_lib.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
```

微信扫的是 **liteapp URL**（不是 hex token），所以 `qr_scan_data = qrcode_url if qrcode_url else qrcode_value`。

### 完整扫码流程

```
用户点击「扫码绑定微信 Bot」
  → POST /api/platform-config/wechat/qr/start
    → 后端 GET https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3
    → 拿到 qrcode_value（hex token）+ qrcode_img_content（liteapp URL）
    → 用 qrcode 库生成 PNG → base64 data URI
    → 返回 { session_id, qr_image: "data:image/png;base64,...", status: "wait" }
  → 前端显示 <img :src="qr_image" />

前端每 2s 轮询 GET /api/platform-config/wechat/qr/{sid}/status
  → 后端 GET https://ilinkai.weixin.qq.com/ilink/bot/get_qrcode_status?qrcode={hex_token}
  → status 状态机: wait → scaned → confirmed / expired
  
微信扫码确认后:
  → status = "confirmed" → 返回 credentials { account_id, token, base_url, user_id }
  → 前端自动调 POST /api/platform-config/wechat/qr/{sid}/bind
    → 保存 platform_config (wechat) + user_bindings (user_id ↔ wechat user_id)
```

轮询中的 `status` 状态：
- `wait` — 等待扫码
- `scaned` — 已扫码，等待确认
- `confirmed` — 已确认，返回凭证
- `expired` — 过期（自动刷新最多 3 次）
- `wait_refreshed` — 二维码过期后成功刷新，需重新渲染

### 超时与阻塞防护 ⚠️

iLink API 国内直连可能慢/不可达。两层防护：
1. 请求超时设 10-15s（不要 35s），快速失败让前端知道
2. 所有 HTTP 调用通过 `asyncio.to_thread()` 包装，**绝不在 async 端点中直接调同步 I/O**

## 前端渠道绑定布局

ConfigView.vue 采用 **Tab 切换式** 布局：

```typescript
const activeTab = ref('model');
const tabs = [
  { key: 'model',   label: '模型配置', icon: '🤖' },
  { key: 'channel', label: '渠道绑定', icon: '🔗' },
  { key: 'email',   label: '邮箱配置', icon: '📧' },
  { key: 'info',    label: '系统信息', icon: '📊' },
];
```

渠道绑定 Tab 内布局结构：
```
🟢 微信 [已配置]
  ├── Bot 操作区：「📱 扫码绑定微信 Bot」按钮
  ├── QR 扫码区域（扫码时显示）：二维码图片 + 状态文字 + 取消按钮
  ├── Bot 配置信息（已配置时显示）：Account ID / Bot User ID
  └── 我的绑定：已绑定微信ID / 「尚未绑定」
🦜 飞书 [即将推出]（灰掉）
```

## 消息来源标记全栈流转

1. **DB**: `conversations.source = 'wechat'/'web'`
2. **ConversationStore**: `insert_conversation(..., source=...)`, `get_conversations_by_session` SELECT 加 `source` 列
3. **chat_controller**: `GET /api/history/{chat_id}` 返回消息时注入 `"source": source`
4. **前端类型**: `Message` 接口加 `source?: string`
5. **MessageBubble**: `v-if="message.source && message.source !== 'web'"` → 显示 `💬 微信` / `🦜 飞书` 徽章

徽章 CSS：
```css
.source-badge { font-size: 11px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.source-wechat, .source-weixin { background: #e8f5e9; color: #2e7d32; }   /* 绿色 */
.source-feishu { background: #e3f2fd; color: #1565c0; }                   /* 蓝色 */
```

## API 端点汇总

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/platform-config/{platform}` | GET | 获取平台配置（脱敏） |
| `/api/platform-config/{platform}` | PUT | 保存配置（超管） |
| `/api/platform-config/{platform}/bindings` | GET | 绑定列表 |
| `/api/platform-config/wechat/qr/start` | POST | 发起微信扫码，返回 base64 PNG |
| `/api/platform-config/wechat/qr/{sid}/status` | GET | 查询扫码状态 |
| `/api/platform-config/wechat/qr/{sid}/bind` | POST | 确认绑定 |
| `/api/user-bindings` | GET | 当前用户绑定 |
| `/api/user-bindings` | POST | 添加绑定（手动输入微信ID） |
| `/api/user-bindings/{id}` | DELETE | 删除绑定 |
