# 会话记录:聊天历史点击"只有第一个能跳转"排查

AgentForge Vue 前端,用户报:"点击历史记录里的以前的会话,有蓝色框选中,但聊天内容没有跳转"(后确认具体为「第一个会话能跳转,之后点击没反应」)。

## 误诊教训(重要)

第一轮排查**错误地**把根因定位到 API:
- `getChatMessages()` 请求 `/api/data/conversations/session/{id}` 与 `/api/chat/history/{id}`,curl 均 404;后端真实端点是 `/api/history/{chat_id}` 返回 200。
- 据此改了前端 API URL + 后端时间戳字段。

但用户后续反馈"第一个能跳转、之后没反应"→ 说明 404 并不是该症状的根因(真正的持久层 404 会让第一次点击也失败)。真正的 bug 在 **`selectChat` 提前 `setCurrentChatId` 导致的守卫误判**。

**两种问题同时存在但互不导致**:端点 URL 不对(影响时间戳/字段)vs 守卫逻辑错(影响"后续点击能否切换内容")。排查时要把「持久层能否取数」与「UI 为何不刷新」当成两个独立问题分别验证。

## 坏代码

`agent_frontend/src/components/chat/ChatSidebar.vue` → `selectChat()`:
```ts
chatStore.setCurrentChatId(chatId)   // 提前改共享状态
window.dispatchEvent(new CustomEvent('chat:loadHistory', { detail: { chatId } }))
```

`agent_frontend/src/composables/useChat.ts` → `loadChatHistory()`:
```ts
if (chatStore.messages.length > 0 && chatStore.currentChatId === chatId) {
  return  // currentChatId 已被 selectChat 提前设为目标 → 恒真
}
```

=> 第一次点击 `messages.length===0` 通过;之后 `currentChatId===chatId`(被提前改)且 `messages.length>0` → 恒 return,后续所有点击被跳过。蓝色高亮 `active` 用 `chat.id===currentChatId` 故照样切换。

## 修复

1. `selectChat` 移除 `chatStore.setCurrentChatId(chatId)`,只 `dispatchEvent`。
2. `loadChatHistory` 在函数入口 `const prevChatId = chatStore.currentChatId` 捕获上一个会话,守卫改 `if (prevChatId === chatId && messages.length > 0) return`;成功路径内再 `setCurrentChatId(chatId)`。

## 验证命令(本会话实际用过)

```bash
# 后端是否运行
curl -s -m 5 http://localhost:8001/health

# 登录拿 token
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
# 拿第一个会话
curl -s "http://localhost:8001/api/data/sessions?user_id=1&limit=1" -H "Authorization: Bearer $TOKEN"
# 该会话消息(真实端点)
curl -s "http://localhost:8001/api/history/1_deepseek_test"
# 旧错误端点确认 404
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/api/chat/history/1_deepseek_test"   # → 404
```

前端重建 + 确认 dist 被后端服务:
```bash
cd agent_frontend && npm run build
grep -oE "assets/index-[A-Za-z0-9_-]+\.js" dist/index.html
curl -s http://localhost:8001/ | grep -oE "assets/index-[A-Za-z0-9_-]+\.js"   # 应与上面一致
```

## 附带修复

- `chat_controller.py` `/api/history/{chat_id}`:`get_conversations_by_session` 返回的 SQL 列是 `created_at/updated_at`,原代码读 `create_time/update_time` 导致 timestamp 空串;并补 `id: user-${conv_id}` / `assistant-${conv_id}`。
- 前端 `getChatMessages`:主请求改指向正确的 `/api/history/{chat_id}`,规范化消息兜底补 `id`,并读取 `localStorage.authToken` 附 Authorization(真实键是 `authToken`,不是 `auth`)。

## 本项目环境注意

- 无 vitest/jest/eslint;`vue-tsc --noEmit` 报 pre-existing `tsconfig.json baseUrl` 弃用错误(TS7),与本改动无关。
- 后端 `reload=False`,改 Python 必须重启进程;前端经后端从 `agent_frontend/dist` 静态服务,改源码必须 `npm run build` 重新出包。
