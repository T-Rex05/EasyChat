---
name: event-driven-state-debugging
author: AgentForge
category: AI生成
description: "调试点击只有第一次生效的守卫型状态 bug。触发：Vue/Pinia dispatchEvent 选中不刷新。"
version: 1.0.0
metadata:
  hermes:
    tags: [Debugging, Frontend, Vue, StateManagement]
    requires_toolsets:
      - file
---

# 事件驱动 UI 状态守卫型 Bug 调试

AgentForge 的聊天前端用 Vue 3 + Pinia，并通过 `window.dispatchEvent(new CustomEvent(...))` / `window.addEventListener(...)` 在「侧边栏组件」和「主聊天视图/composable」之间传事件。这类架构下最隐蔽的一类 bug 是**状态守卫在事件消费者里基于已被提前改写的外部状态做判断**。

## 触发条件 / 何时使用

- UI 点击/选中的行为「**只有第一次操作生效，后续操作无反应**」，但高亮/选中态照样切换。
- 某个 `select`/`load` 函数开头有「已在当前目标则跳过」的守卫（guard / early-return）。
- 事件分发者（dispatcher）在 `dispatchEvent` **之前**就改动了一个共享 store 或闭包状态。

「第一次能生效、之后全部失效」几乎是**守卫/early-return 误判**的标志，而不是网络/端点类的问题——一个真实且持续的 404 会连第一次点击都失败。

## 核心坑：守卫比较了"已被提前改写的状态"

典型坏代码（确曾发生在本项目 `agent_frontend`）：

```ts
// 事件分发者 —— 错误：dispatch 前先 setCurrentChatId
async function selectChat(chatId: string) {
  ...
  chatStore.setCurrentChatId(chatId)                       // ❌ 提前改写共享状态
  window.dispatchEvent(new CustomEvent('chat:loadHistory', { detail: { chatId } }))
}
```

```ts
// 事件消费者 —— 错误：用 currentChatId === chatId 判断"同一会话"
async function loadChatHistory(chatId: string) {
  if (chatStore.messages.length > 0 && chatStore.currentChatId === chatId) {
    return   // ❌ 恒成立，导致后续点击全部被跳过
  }
  ...
}
```

**根因**：`selectChat` 先把 `currentChatId` 设成了目标 `chatId`，等事件传到 `loadChatHistory` 时，守卫里的 `currentChatId === chatId` 恒为真；又因首次加载后 `messages.length > 0`，第二个条件也为真 → 守卫误判"已加载" → `return`。第一次点击时 `messages` 为空所以正常。

## 正确修法

1. **由事件消费者统一负责 `setCurrentChatId`**，分发者只 `dispatchEvent`，不再提前改状态。
2. 守卫的对比基准改成**进入 handler 时捕获的上一个值**，而不是会被改写掉的当前值：

```ts
async function loadChatHistory(chatId: string) {
  const prevChatId = chatStore.currentChatId            // 进入时捕获"上一个会话"
  if (chatStore.isStreaming) return
  if (prevChatId === chatId && chatStore.messages.length > 0) {
    return   // 只有"上一个会话 === 目标会话"才跳过
  }
  chatStore.setCurrentChatId(chatId)
  const msgs = await getChatMessages(chatId)
  chatStore.setMessages(msgs)
}
```

## 另一相关坑：持久化的选中态在无数据时仍高亮

**症状**：刚进页面（聊天区是欢迎屏、`messages` 为空），历史侧边栏却把一个会话标成 active（蓝色）。

**根因**：`currentChatId` 初始化自 `sessionStorage`（存过就会残留）：
```ts
const currentChatId = ref<string>(sessionStorage.getItem('currentChatId') || '')
```
侧边栏 active 判断 `chat.id === currentChatId` 直接用了这个持久化 id。页面刷新后 messages 是空的，但残留的 id 仍让某个历史项高亮，造成「选中了会话、聊天区却是欢迎屏」的矛盾观感。

**修法**：UI 的「选中态」要从**实际已加载的数据**派生，而不是从持久化 id 派生：
```ts
// 只有聊天区确实加载了消息，才算"选中了一个会话"
const selectedChatId = computed(() =>
  chatStore.messages.length > 0 ? chatStore.currentChatId : '',
)
```
模板用 `selectedChatId` 做 active，`messages` 空时自然不高亮任何项；点了历史项、`loadChatHistory` 填充 messages 后自动亮起。

**可迁移原则**：凡持久化（sessionStorage/localStorage/URL 参数）驱动的选中/高亮状态，都要先问一句「这个状态对应的数据现在加载了吗」。数据未加载时，UI 应显示为"未选中"，而不是回放旧的持久化值。

## 同一根因的另一面：残留 currentChatId 会吞掉"新会话"

**症状**：刚进聊天页（欢迎屏、`messages` 为空）点一个快捷问题 / 发消息，**历史列表没有新增会话**，消息被发进了上次那个（旧的）会话里，显示倒也正常——但因为它没走 `chat:newSession`，历史侧边栏不会出现新条目。

**根因**：`sendMessage` 判定新会话用的是 `isNewChat = !chatId`，而 `currentChatId` 由 `sessionStorage` 初始化（上次残留非空）→ `isNewChat = false`，于是不生成新 chatId、不 dispatch `chat:newSession` → 历史不新增。这与上面"持久化高亮"是**同一根因**（残留 `currentChatId`），只是坏在「新会话检测」而非「选中高亮」。

**判定新会话要看数据，不能只看 `!chatId`**：
```ts
const isNewChat = !chatId || messages.value.length === 0
```
`messages` 为空（欢迎屏/新对话）时强制当作新会话：生成 `user_id_timestamp` 新 chatId + dispatch `chat:newSession`，即使 `currentChatId` 有残留值也不被劫持。

**升级迁移原则**：凡「判断是否新开/新建/切换」的逻辑，基准应从"当前是否有数据"出发，而不是"某个持久化 ID 是否为空"。持久化 ID 非空但数据为空 = 该被视为全新开始。排查"点了没新增 / 消息发到别处"类 bug，先确认这个 ID 是不是持久化残留。

## 另一变体：去重与高亮用不同状态源 → 第一条点不中

**症状**：刚进页面（欢迎屏、无消息），历史列表第一条点不动，但第二条正常，之后再点第一条也行。第一条也没有蓝色高亮。

**根因**：`selectChat` 去重 `chatId === currentChatId.value` 和高亮 `chatId === selectedChatId` 用了**两张牌**。`selectedChatId` 在 messages 为空时回空串，第一条不高亮；但 `currentChatId` 从 `sessionStorage` 残留，若恰等于第一条 id → 去重命中 → `return`。用户看到「没高亮的一项点了没用」。

**修法**：去重与高亮用同一源 — `selectedChatId`：
```ts
// ❌ 旧：去重用 currentChatId，高亮用 selectedChatId — 不同步
if (chatId === currentChatId.value) return
// ✅ 修复：统一用 selectedChatId
if (chatId === selectedChatId.value) return
```

详案见 `references/selectchat-dedup-mismatch.md`。

## 排查步骤（按序）

1. **复现并界定范围**：是"全部失败"还是"只有第一个成功"？"第一个成功"→ 强烈指向守卫/early-return，不是端点问题。
2. **沿事件链读代码**：找到 `dispatchEvent` 分发点与 `addEventListener` 消费点，把**执行顺序**逐行走一遍（先 set 再 dispatch？）。
3. **审查守卫条件**：所有 `x === target && ...` 的 early-return，判断 `x` 在进入时是否已被改写。
4. **别急着怪 API**：`curl` 验证端点 200/404 只能证明"持久层通不通"，**不能**证明"UI 为什么点击不刷新"。两者是独立问题，别混为一谈。
5. **修完重建验证**：dist 页面 `npm run build` 通过 + 后端 `/api/...` 返回正确字段，只能覆盖"能编译、能取数"，点击交互仍要人工按 `Ctrl+F5` 硬刷新验证。

## 本项目的关键文件（改到谁身上）

- `agent_frontend/src/components/chat/ChatSidebar.vue` — `selectChat()` 分发 `chat:loadHistory`
- `agent_frontend/src/composables/useChat.ts` — `loadChatHistory()` 消费该事件、含守卫
- `agent_frontend/src/stores/chat.ts` — `setCurrentChatId/currentChatId` 共享状态
- `agent_frontend/src/api/chat.ts` — `getChatMessages()`（真实后端端点为 `GET /api/history/{chat_id}`，旧 `/api/data/conversations/session/` 与 `/api/chat/history/` 均 404）

## 验证注意

- 本项目**没有** vitest/jest/eslint，只有 `dev/build/preview/type-check`；`vue-tsc --noEmit` 会报一个 pre-existing 的 `tsconfig.json` `baseUrl` 弃用错误（TS 6/7 迁移），与业务代码无关，别误判为自己的改动。
- 前端经后端从 `agent_frontend/dist` 静态服务，改源码后要 `npm run build` 重新出包，改后端 Python 要重启后端进程（`reload=False` 不会自动热加载）。
- AgentForge 时间戳类字段：`get_conversations_by_session` 返回 `created_at/updated_at`（SQL 列名），不是 `create_time/update_time`，二者混用会导致展示为空串。

## 相关参考

- `references/chat-history-click-session.md` — 守卫被提前改写状态误判（第一次生效、之后全失效）。
- `references/selectchat-dedup-mismatch.md` — 去重与高亮用不同状态源（第一条点不动、第二条后才通）。
- `references/controlled-details-collapse.md` — `<details :open>` 受控状态被覆盖。
- `references/sidebar-collapse-overflow.md` — 折叠侧边栏按钮被裁。

## 边界:本技能 vs 其他同类坑

本技能聚焦「守卫/early-return 基于被提前改写的外部状态」+「dispatchEvent → addEventListener 事件链」这两类的点击/选中类 bug。**不属于**本技能范围的 Vue 状态问题:
- 受控组件(`<details>`、受控 input)手动操作被 reactive 覆盖 → 见 `references/controlled-details-collapse.md`
- 消息锚点滚动定位、首个用户消息高亮、到顶/到底悬浮按钮 → UI 增强类,不在此列
- 同一视图内去重判断与高亮判断用不同状态源 → 见 `references/selectchat-dedup-mismatch.md`

**后端(数据库/SQL)相关坑** → 见 `mysql-backend-extension`(加列双写、ONLY_FULL_GROUP_BY、Windows 中文 JSON 测试、会话重命名端到端)。排查时把「前端状态」与「后端持久层」当两个独立问题分别验证。

