---
name: git-workflow
category: 工程
author: admin
description: "Git 分支管理、提交规范、代码审查工作流"
version: 1.0.0
metadata:
  hermes:
    tags: [Engineering, DevOps, Git]
    requires_toolsets:
      - terminal
---

# Git 工作流

标准化的 Git 操作流程，涵盖分支管理、提交规范和 PR 流程。

## 何时使用

- 创建新分支、提交代码
- 解决合并冲突
- 发起 Pull Request
- 查看 Git 历史和差异
- 回滚错误提交

## 分支命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 功能 | `feat/<描述>` | `feat/add-search` |
| 修复 | `fix/<描述>` | `fix/login-error` |
| 重构 | `refactor/<描述>` | `refactor/auth-module` |
| 文档 | `docs/<描述>` | `docs/api-guide` |

## 提交信息规范

```
<type>: <简短描述>

<详细说明（可选）>

示例：
feat: 添加技能管理 CRUD API

- GET /api/skills 列出所有技能
- POST /api/skills 创建技能
- PUT /api/skills/{name} 更新技能
```

常用 type：`feat` `fix` `refactor` `docs` `style` `test` `chore`

## 常用操作

### 创建功能分支
```bash
git checkout -b feat/my-feature
git add .
git commit -m "feat: 简短描述"
git push origin feat/my-feature
```

### 查看状态和历史
```bash
git status           # 查看工作区状态
git log --oneline    # 紧凑日志
git diff HEAD~1      # 上次提交的变更
```

### 撤销操作
```bash
git reset --soft HEAD~1   # 撤销上次提交（保留变更）
git checkout -- <file>    # 撤销文件修改
git revert HEAD           # 创建新提交来撤销
```

## 代码审查检查项

- [ ] 代码逻辑正确，无明显bug
- [ ] 命名规范，注释完整
- [ ] 没有硬编码密钥/IP
- [ ] 异常处理完善
- [ ] 测试通过
