---
name: system-hardening
category: 运维
author: admin
description: "Linux 服务器安全加固：防火墙、SSH、审计、内核参数"
version: 1.0.0
metadata:
  hermes:
    tags: [DevOps, Security, Linux]
    platforms: [linux]
    requires_toolsets:
      - terminal
---

# 系统安全加固

Linux 服务器安全加固检查清单与操作指南。

## 何时使用

- 新部署服务器需要加固
- 安全审计
- 等保合规检查
- 用户说 "帮我加固服务器"

## 检查清单

### 1. 账号安全
```bash
# 检查空密码账户
awk -F: '($2 == "") {print $1}' /etc/shadow

# 检查 root 权限账户
awk -F: '($3 == 0) {print $1}' /etc/passwd

# 锁定不需要登录的账户
passwd -l <username>
```

### 2. SSH 加固
```bash
# /etc/ssh/sshd_config
PermitRootLogin no          # 禁止 root 登录
PasswordAuthentication no   # 禁用密码登录（用密钥）
MaxAuthTries 3              # 最大尝试次数
Port 2222                   # 修改默认端口（可选）
AllowUsers user1 user2      # 白名单用户

systemctl restart sshd
```

### 3. 防火墙
```bash
# UFW（Ubuntu/Debian）
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp    # SSH
ufw allow 80,443/tcp  # HTTP/HTTPS
ufw enable

# firewalld（CentOS/RHEL）
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --reload
```

### 4. 审计与日志
```bash
# 查看登录失败记录
lastb | head -20

# 查看认证日志
grep "Failed password" /var/log/auth.log | tail -20

# 实时监控日志
tail -f /var/log/syslog
```

### 5. 内核参数
```bash
# /etc/sysctl.d/99-security.conf
net.ipv4.tcp_syncookies = 1          # 防 SYN flood
net.ipv4.conf.all.rp_filter = 1      # 反向路径过滤
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
kernel.kptr_restrict = 2

sysctl -p
```

### 6. 自动更新
```bash
# Ubuntu/Debian
apt install unattended-upgrades
dpkg-reconfigure unattended-upgrades

# CentOS/RHEL
yum install yum-cron
systemctl enable yum-cron
```

## 输出格式

```
## 安全加固报告

### 通过项 ✅
- [x] 禁止 root SSH 登录
- [x] 防火墙已启用

### 需修复 ❌
- [ ] 存在空密码账户: user1
- [ ] SSH 密码登录未禁用

### 加固命令
1. passwd -l user1
2. sed -i 's/PasswordAuthentication yes/no/' /etc/ssh/sshd_config
3. systemctl restart sshd
```

## 注意事项

- 修改 SSH 配置前确保有备用连接方式
- 防火墙规则先用 `--dry-run` 或测试环境验证
- 内核参数修改后需要 `sysctl -p` 立即生效
- 生产环境操作前先备份配置文件
