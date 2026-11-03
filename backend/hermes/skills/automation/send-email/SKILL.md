---
name: send-email
category: automation
description: "发送邮件 - 使用 Python 发送纯文本/HTML 邮件，支持附件、抄送、密送。触发：当用户需要发送邮件、通知邮件、报告邮件时。"
version: 2.0.0
author: admin
metadata:
  hermes:
    requires_toolsets:
      - email
---

# /send-email — 邮件发送技能

## 触发条件
- 用户需要发送邮件（通知、报告、提醒等）
- 用户提到"发邮件"、"email"、"通知某人"
- 自动化工作流需要邮件通知

## 核心能力
1. 发送纯文本 / HTML 格式邮件
2. 支持多收件人、抄送 (CC)、密送 (BCC)
3. 支持多附件（自动检测 MIME 类型）
4. 支持内嵌图片（HTML 邮件中引用本地图片）
5. 自动根据发件人域名匹配 SMTP 服务器
6. 支持 SSL (465) 和 TLS (587) 两种加密方式

## 环境准备

### 必需环境变量
```bash
# Windows (bash/git-bash)
export EMAIL_USER="your_email@example.com"
export EMAIL_PASSWORD="your_app_password"

# Windows PowerShell
$env:EMAIL_USER="your_email@example.com"
$env:EMAIL_PASSWORD="your_app_password"

# Linux/Mac
export EMAIL_USER="your_email@example.com"
export EMAIL_PASSWORD="your_app_password"
```

### 可选环境变量（覆盖自动检测）
```bash
export SMTP_HOST="smtp.example.com"    # SMTP 服务器地址
export SMTP_PORT="587"                 # SMTP 端口（默认 587）
export SMTP_USE_SSL="false"            # 是否使用 SSL（默认 false，即使用 TLS）
```

## 使用方式

### 方式一：直接调用脚本（推荐）

```bash
# 发送简单文本邮件
python scripts/send_email.py --to "recipient@example.com" --subject "测试" --body "你好"

# 发送 HTML 邮件
python scripts/send_email.py --to "user@example.com" --subject "报告" --html "<h1>周报</h1><p>内容...</p>"

# 发送带附件的邮件
python scripts/send_email.py --to "boss@example.com" --subject "月度报告" --body "请查收" --attach report.pdf data.xlsx

# 多人 + 抄送
python scripts/send_email.py --to "a@x.com" "b@x.com" --cc "c@x.com" --subject "会议通知" --body "明天下午3点"
```

### 方式二：在 Python 代码中导入

```python
from send_email import EmailSender

sender = EmailSender()  # 自动从环境变量读取凭据

# 简单邮件
sender.send(
    to="recipient@example.com",
    subject="测试邮件",
    body="纯文本内容"
)

# HTML 邮件 + 附件
sender.send(
    to=["user1@example.com", "user2@example.com"],
    subject="月度报告",
    body="请查看附件中的报告。",
    html="<h1>月度报告</h1><p>详见附件。</p>",
    attachments=["report.pdf", "data.xlsx"],
    cc=["manager@example.com"]
)

# 带内嵌图片的 HTML 邮件
sender.send(
    to="client@example.com",
    subject="产品截图",
    html='<h1>产品</h1><img src="cid:product.png">',
    inline_images=["product.png"]
)
```

## SMTP 自动检测

脚本会根据 `EMAIL_USER` 的域名自动匹配 SMTP 服务器：

| 域名 | SMTP 服务器 | 端口 | 加密 |
|------|------------|------|------|
| gmail.com | smtp.gmail.com | 587 | TLS |
| outlook.com / hotmail.com | smtp.office365.com | 587 | TLS |
| qq.com | smtp.qq.com | 465 | SSL |
| 163.com / 126.com | smtp.163.com | 465 | SSL |
| 126.com | smtp.126.com | 465 | SSL |
| yahoo.com | smtp.mail.yahoo.com | 465 | SSL |
| sina.com | smtp.sina.com | 465 | SSL |
| aliyun.com | smtp.aliyun.com | 465 | SSL |
| foxmail.com | smtp.qq.com | 465 | SSL |

未匹配的域名默认使用 `smtp.<domain>:587` (TLS)。

## 常见邮箱配置指南

详细配置见 `references/smtp-setup.md`，包含：
- Gmail 应用专用密码生成步骤
- QQ 邮箱授权码获取方法
- Outlook / Office365 配置
- 企业邮箱配置

## 邮件模板

常用邮件模板见 `templates/` 目录：
- `report.html` — 数据报告邮件模板
- `notification.html` — 系统通知邮件模板
- `weekly-summary.html` — 周报邮件模板

## 陷阱与注意事项

1. **Gmail 必须用应用专用密码**：普通密码无法登录，需开启两步验证后生成
2. **QQ/163 邮箱用授权码**：不是登录密码，需在邮箱设置中开启 SMTP 并获取
3. **附件路径必须是绝对路径或相对于运行目录的路径**
4. **HTML 邮件必须同时提供纯文本 body**（作为 fallback）
5. **大量发送时注意频率限制**：Gmail 每天限制约 500 封，QQ 邮箱更少
6. **SSL vs TLS**：QQ/163 用 SSL(465)，Gmail/Outlook 用 TLS(587)，脚本已自动处理

## 验证步骤

1. 确认环境变量已设置：`echo $EMAIL_USER`
2. 运行测试：`python scripts/send_email.py --to "your@test.com" --subject "test" --body "hello"`
3. 检查收件箱是否收到邮件
4. 验证 HTML 渲染和附件是否正确
