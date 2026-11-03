---
name: test-driven-development
category: AI生成
author: AgentForge
description: "测试驱动开发 — 先写测试再写代码，红→绿→重构"
metadata:
  hermes:
    requires_toolsets:
      - terminal
---

# 测试驱动开发（TDD）

**核心原则：没看到测试失败，就不知道它测对了没有。**

## 红-绿-重构

1. **红** — 写一个最小失败测试
2. **验证红** — 确认失败原因正确（功能缺失，不是笔误）
3. **绿** — 写最少代码让测试通过
4. **验证绿** — 确认通过 + 无回归
5. **重构** — 清理代码，保持绿色
6. **重复** — 下一个测试

## AgentForge 约束

- 前端无 vitest/jest，只能用 `npm run build` + `vue-tsc --noEmit` 作为测试替代
- 后端无 pytest，用 `ast.parse` + 模块导入验证
- 在能力范围内做最强的验证即可

## 红牌

代码写在测试之前 → 删掉重来。测试第一次就通过 → 你在测已有行为，修正测试。
