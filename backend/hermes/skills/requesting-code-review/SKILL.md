---
name: requesting-code-review
category: AI生成
author: AgentForge
description: "请求代码审查 — 完成重要功能或合并前，验证工作质量"
metadata:
  hermes:
    requires_toolsets:
      - file
---

# 请求代码审查

**核心原则：早审查，常审查。**

## 何时

- 完成主要功能后
- 修完复杂 bug 后
- 合并到主分支前

## 方法

用 `code-review` skill 自审，按安全→性能→可读性→最佳实践四维度走一遍。逐项确认后输出审查报告。

## AgentForge 项目特殊点

- 前端：`npm run build` (exit 0) + `vue-tsc --noEmit` (仅看新增报错)
- 后端：`ast.parse` + 模块导入
- Monaco chunk >500KB 为正常，非回归
