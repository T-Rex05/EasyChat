# chatUserId 同步陷阱 — router 兜底方案

## 问题链路（完整）

1. **`authStore.userId` computed 的 fallback 链**: `localStorage.getItem('chatUserId') || sessionStorage.getItem('chatUserId') || '1'`
2. **login/register 会写 chatUserId**: 正常登录流程下 localStorage 和 sessionStorage 都有
3. **verify() 不写 chatUserId**: token 刷新（页面刷新时恢复登录态）不会回写
4. **verify() 从未在启动时被调用**: 应用启动时 `router.beforeEach` 只检查 `localStorage.getItem('authToken')` 是否存在，**不触发** `authStore.verify()`
5. **老 session 从未存过 chatUserId**: 用户用旧版本（修复前）登录后，localStorage 里没有 chatUserId，即使现在修复了 verify() 也不会触发

## 症状

两个看似不同的 bug 其实是**同一个根因**：

| 症状 | 表面原因 | 实际根因 |
|---|---|---|
| 会话跑到 admin 历史 | `thread_id = '1_...'` | `authStore.userId` fallback 到 '1' |
| 技能创建人变 admin | `_CURRENT_USER_ID_CTX` 解析到 admin 的 user_id | 同上 |
| 前端 `selected.author` 显示 "未知" | SKILL.md 缺 author 字段 | AI 写 `author: AgentForge` → 被 strip → 无 author（**另一条路径**，见 SKILL.md）|

## 解决方案（router 兜底同步）

在 `router/index.ts` 的 `beforeEach` 守卫中，遇到已认证路由时检查 chatUserId 是否存在；若缺失，调用 `/api/auth/me` 同步：

```typescript
// router/index.ts
let chatUserIdSynced = false  // 模块级标志，避免每次路由跳转都调接口

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem('authToken')
  // ... requiresAuth check ...

  // token 存在但 chatUserId 缺失时，调用 /api/auth/me 同步用户信息
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
      } catch (e) {
        chatUserIdSynced = false  // 失败则下次路由跳转时重试
      }
    }
  }

  // ... permission check ...
})
```

## 关键要点

- **不要依赖 verify()**: verify() 只在显式调用时写 chatUserId，但应用启动时根本不会调它
- **两个症状一起看**: 会话跑到 admin + 技能创建人变 admin = 同一个 bug，修一个修不到另一个
- **chatUserIdSynced 标志**: 用模块级变量避免每次路由跳转都调接口；失败时重置为 false，下次重试
- **动态导入 request**: 避免循环依赖，只在需要时导入

## 相关文件

- `agent_frontend/src/router/index.ts` — beforeEach 守卫
- `agent_frontend/src/stores/auth.ts` — userId computed、verify()、login()、logout()
- `agent_frontend/src/composables/useChat.ts` — 生成 thread_id = `${userId}_${Date.now()}`
- `backend/controller/chat_controller.py` — 从 thread_id 第一段解析 user_id
