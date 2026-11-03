# 多渠道消息架构（微信/飞书/Web）

## 数据模型

### conversations 表新增字段
```sql
ALTER TABLE conversations ADD COLUMN source VARCHAR(20) DEFAULT 'web' COMMENT 'web/wechat/feishu';
```

### 新表 platform_config
```sql
CREATE TABLE IF NOT EXISTS platform_config (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform    VARCHAR(20) NOT NULL UNIQUE COMMENT 'wechat/feishu/email',
    config_json JSON NOT NULL COMMENT '平台配置 JSON',
    enabled     TINYINT DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```
存储平台级凭证（Token、Account ID 等），`config_json` 用 JSON 列灵活适配不同平台。

### 新表 user_bindings
```sql
CREATE TABLE IF NOT EXISTS user_bindings (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    platform    VARCHAR(20) NOT NULL COMMENT 'wechat/feishu',
    open_id     VARCHAR(128) NOT NULL COMMENT '微信 wxid / 飞书 open_id',
    nickname    VARCHAR(128) DEFAULT '',
    enabled     TINYINT DEFAULT 1,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform_openid (platform, open_id),
    UNIQUE KEY uk_user_platform (user_id, platform)
);
```
每个用户每个平台只能绑定一个账号（`uk_user_platform`），每个 open_id 只能被绑定一次（`uk_platform_openid`）。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/platform-config/{platform}` | GET | 获取平台配置（敏感字段脱敏） |
| `/api/platform-config/{platform}` | PUT | 保存平台配置（超管） |
| `/api/platform-config/{platform}/bindings` | GET | 获取绑定列表 |
| `/api/user-bindings` | GET | 当前用户的绑定列表 |
| `/api/user-bindings` | POST | 创建绑定 |
| `/api/user-bindings/{id}` | DELETE | 删除绑定 |

## 前端改造点

### ConfigView.vue 改为 Tab 式布局
- Tab: 模型配置 / 渠道绑定 / 邮箱配置 / 系统信息
- 微信绑定面板：手动输入 Bot Token + Account ID
- 超管可配系统级 SMTP，普通用户配个人邮箱

### MessageBubble.vue 渠道标记
```typescript
function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    wechat: '💬 微信',
    weixin: '💬 微信',
    feishu: '🦜 飞书',
  }
  return map[source] || '🌐 ' + source
}
```
消息 header 中显示带颜色的小徽章：微信绿色底 `#e8f5e9`，飞书蓝色底 `#e3f2fd`。

### Message 类型新增 source 字段
```typescript
export interface Message {
  // ...existing fields...
  source?: string  // 'web' | 'wechat' | 'feishu'
}
```

### chat_controller.py get_chat_messages 返回 source
从 `conversations.source` 读取，消息历史 `/api/history/{chat_id}` 返回中带上。

## Hermes 原生支持

Hermes 的 `gateway/platforms/weixin.py` 完整实现了腾讯 iLink Bot API：
- 长轮询收消息（`getupdates`）
- 发文本/图片/视频/语音/文件
- 二维码扫码登录（`qr_login`）
- AES 加密 CDN 媒体传输

`send_message_tool.py` 中 weixin 是完整支持的平台，配置方式：
```bash
WEIXIN_TOKEN=<bot_token>
WEIXIN_ACCOUNT_ID=<account_id>
WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com
```
即使没有 gateway.yaml 也能通过纯 `.env` 配置工作。

## 关键陷阱

### iLink 扫码 QR 的 scaned_but_redirect 状态（关键）
扫码后 iLink 可能返回 `status='scaned_but_redirect'` + `redirect_host`，此时必须切换后续轮询的 base_url。
若忽略此状态继续轮询原地址 → iLink 不认会话 → 微信端显示"暂时无法连接"。
详见 `wechat-ilink-integration.md` 陷阱 #3。

### qrcode_img_content 不是图片 URL
iLink API 返回的 `qrcode_img_content` 是微信 liteapp 链接（如 `https://liteapp.weixin.qq.com/q/...`），**不是**可渲染的图片 URL。用它作为 `<img src>` 会显示空白。

如需生成真正的二维码图片，用 `qrcode` + `Pillow` 库：
```python
import qrcode
from io import BytesIO
import base64

qr = qrcode.QRCode(box_size=6, border=2)
qr.add_data(liteapp_url)  # 微信扫的是 liteapp URL，不是 hex token
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
buf = BytesIO()
img.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode()
return f"data:image/png;base64,{b64}"
```
