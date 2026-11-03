# SMTP 邮箱配置指南

## Gmail

### 前提条件
- 必须开启两步验证
- 必须使用应用专用密码（普通密码无法登录）

### 配置步骤
1. 访问 https://myaccount.google.com/security
2. 开启「两步验证」
3. 进入 https://myaccount.google.com/apppasswords
4. 选择「邮件」→ 生成密码
5. 使用生成的 16 位密码作为 `EMAIL_PASSWORD`

### SMTP 参数
| 参数 | 值 |
|------|-----|
| 服务器 | smtp.gmail.com |
| 端口 | 587 (TLS) |
| 加密 | TLS |

---

## QQ 邮箱

### 前提条件
- 必须在网页版开启 SMTP 服务
- 使用授权码（不是登录密码）

### 配置步骤
1. 登录 https://mail.qq.com
2. 设置 → 账户
3. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务」
4. 开启「IMAP/SMTP 服务」
5. 按提示用手机发短信验证
6. 获得 16 位授权码
7. 使用授权码作为 `EMAIL_PASSWORD`

### SMTP 参数
| 参数 | 值 |
|------|-----|
| 服务器 | smtp.qq.com |
| 端口 | 465 (SSL) |
| 加密 | SSL |

---

## 163 邮箱

### 前提条件
- 必须在网页版开启 SMTP 服务
- 使用授权码（不是登录密码）

### 配置步骤
1. 登录 https://mail.163.com
2. 设置 → POP3/SMTP/IMAP
3. 开启「SMTP 服务」
4. 设置授权码（自定义密码）
5. 使用授权码作为 `EMAIL_PASSWORD`

### SMTP 参数
| 参数 | 值 |
|------|-----|
| 服务器 | smtp.163.com |
| 端口 | 465 (SSL) |
| 加密 | SSL |

---

## Outlook / Office365

### 配置步骤
1. 使用你的 Outlook 邮箱密码
2. 如果启用了两步验证，需要生成应用密码

### SMTP 参数
| 参数 | 值 |
|------|-----|
| 服务器 | smtp.office365.com |
| 端口 | 587 (TLS) |
| 加密 | TLS |

---

## 企业邮箱（通用配置）

大多数企业邮箱遵循相同模式：
- SMTP 服务器：`smtp.yourdomain.com`
- 端口：587 (TLS) 或 465 (SSL)
- 向 IT 部门确认具体参数

---

## 故障排查

### 认证失败
- 确认使用的是应用专用密码/授权码，不是登录密码
- 确认环境变量没有多余空格或引号

### 连接超时
- 检查端口是否正确（SSL=465, TLS=587）
- 检查防火墙是否阻止了出站连接
- 尝试切换 SSL/TLS

### 频率限制
| 服务商 | 每日限制 |
|--------|---------|
| Gmail | ~500 封 |
| QQ 邮箱 | ~50 封 |
| 163 邮箱 | ~50 封 |
| Outlook | ~300 封 |
