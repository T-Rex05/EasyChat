# selectChat 去重判断与高亮判断用不同状态源 → 首次点击第一条无反应

## 症状

刚进入智能对话页面（聊天区是欢迎屏、messages 为空），点击历史列表里**第一条会话无效**（不跳转、不加载消息），但点击第二条会话就立即生效，之后第一条也能正常点击。

## 根因

`ChatSidebar` 的两个判断用了**两张牌**：

- **去重判断**：`selectChat` 里 `if (chatId === currentChatId.value) return` — 用的是 `chatStore.currentChatId`
- **高亮判断**：模板里 `:class="{ active: chat.id === selectedChatId }"` — 用的是 `selectedChatId`（仅在 `messages.length > 0` 时有值）

`currentChatId` 由 `sessionStorage` 初始化（可能残留上次会话的 id），而 `selectedChatId` 在 messages 为空时返回空串。所以：

- 如果残留的 `currentChatId` 恰好等于历史列表第一条的 id → `selectChat` 去重判断命中了 `chatId === currentChatId` → **直接 return，什么都不做**
- 但高亮没亮（`selectedChatId` 为空），用户看到的是"第一条没高亮，点了也没反应"

点击第二条不会触发去重（因为第二条 id 不等于残留值），它正常执行 → `loadChatHistory` 填充 messages → `selectedChatId` 和 `currentChatId` 同步更新。之后再点第一条就正常了。

## 修复

```ts
// 去重判断必须和高亮判断用同一个状态基准
async function selectChat(chatId: string) {
  if (chatId === selectedChatId.value) return   // ✅ 用 selectedChatId，而非 currentChatId
  ...
}
```

## 可迁移原则

同一视图内的**去重**和**高亮**必须从**同一份派生状态**出发。如果去重用裸 store 值、高亮用 computed 派生值，新进入/无数据态下的不一致会导致"点不动但看起来没选中"的诡异行为。
