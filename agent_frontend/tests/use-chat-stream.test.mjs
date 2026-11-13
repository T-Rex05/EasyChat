// WP-A 聊天流恢复回归：连接与清理按 chatId 归属、晚到历史不覆盖流式。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

const source = readFileSync(new URL('../src/composables/useChat.ts', import.meta.url), 'utf8')
const script = source
  .replace(/^import .*$/gm, '')
  .replace(/export /g, '')
const { outputText } = ts.transpileModule(script, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
})

function makeStore() {
  const messagesByChat = {}
  const streaming = new Map()
  const pending = new Map()
  const store = {
    currentChatId: '',
    get isStreaming() {
      const s = streaming.get(store.currentChatId)
      return s?.status === 'streaming'
    },
    get messages() { return messagesByChat[store.currentChatId] || [] },
    getMessages: (cid) => messagesByChat[cid] || [],
    setMessages: (msgs, cid) => { messagesByChat[cid || store.currentChatId] = [...msgs] },
    addMessage: (m, cid) => { (messagesByChat[cid || store.currentChatId] ||= []).push(m) },
    updateLastAssistantMessage: (content, meta, cid) => {
      const msgs = messagesByChat[cid || store.currentChatId] || []
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') last.content = content
    },
    createStreamingSession: (cid, clientMsgId) => {
      const s = { chatId: cid, clientMsgId, status: 'streaming' }
      streaming.set(cid, s)
      return s
    },
    updateStreamingSession: (cid, patch) => { const s = streaming.get(cid); if (s) Object.assign(s, patch) },
    getStreamingSession: (cid) => streaming.get(cid) || null,
    removeStreamingSession: (cid) => streaming.delete(cid),
    savePendingStreamsToStorage: (cid, payload) => pending.set(cid, payload),
    clearPendingStreamFromStorage: (cid) => pending.delete(cid),
    loadPendingStreamsFromStorage: () => Object.fromEntries(pending),
    clearMessages() { for (const k of Object.keys(messagesByChat)) delete messagesByChat[k] },
    clearPendingMessages() { pending.clear() },
    setCurrentChatId(cid) { store.currentChatId = cid },
  }
  return store
}

function makeApi() {
  const streams = []
  const api = {
    streams,
    historyGate: { release: null, lastChatId: null },
    sendMessageStream: async (text, chatId, callbacks, clientMsgId) => {
      const entry = { chatId, callbacks, closed: false, close: () => { entry.closed = true } }
      streams.push(entry)
      return { eventSource: { fake: chatId, close: entry.close }, close: entry.close }
    },
    sendMessageStreamPost: async (text, chatId, callbacks, clientMsgId) => {
      const entry = { chatId, callbacks, closed: false, close: () => { entry.closed = true } }
      streams.push(entry)
      return { close: entry.close }
    },
    getChatMessages: (cid) => new Promise((resolve) => {
      api.historyGate.release = (msgs) => resolve(msgs)
      api.historyGate.lastChatId = cid
    }),
    cancelStream: async () => {},
    uploadChatImages: async () => [],
    uploadChatFiles: async () => [],
    resolveExecApproval: async () => {},
  }
  return api
}

function makeEnv() {
  const store = makeStore()
  const api = makeApi()
  const listeners = []
  const windowStub = {
    addEventListener: (n, f) => listeners.push([n, f]),
    dispatchEvent: (e) => { for (const [, f] of listeners) f(e) },
    open: () => ({}),
    localStorage: {
      getItem: (k) => (k === 'chatUserId' ? '4' : null),
      setItem() {}, removeItem() {},
    },
  }
  globalThis.localStorage = windowStub.localStorage
  const ref = (v) => ({ value: v })
  const computed = (fn) => ({ get value() { return fn() } })
  const bindings = {
    ref, computed,
    useChatStore: () => store,
    sendMessageStream: api.sendMessageStream,
    sendMessageStreamPost: api.sendMessageStreamPost,
    uploadChatImages: api.uploadChatImages,
    uploadChatFiles: api.uploadChatFiles,
    cancelStream: api.cancelStream,
    getChatMessages: api.getChatMessages,
    resolveExecApproval: api.resolveExecApproval,
    generateUUID: () => `uuid-${Math.random().toString(16).slice(2, 10)}`,
    window: windowStub,
  }
  const { useChat } = new Function(...Object.keys(bindings), `${outputText}
return { useChat }`)(...Object.values(bindings))
  const chat = useChat('normal')
  return { chat, store, api }
}

async function send(chat, store, api, text, chatId) {
  store.setCurrentChatId(chatId)
  store.setMessages([{ id: 'seed', role: 'user', content: 'seed' }], chatId)
  await chat.sendMessage(text)
}

test('A 完成只清理自己,不误关 B 的连接(B 流继续)', async () => {
  const { chat, store, api } = makeEnv()
  await send(chat, store, api, '问题 A', 'A')
  await send(chat, store, api, '问题 B', 'B')
  assert.equal(api.streams.length, 2)
  assert.equal(api.streams[0].closed, false)
  api.streams[0].callbacks.onComplete({ final_content: 'A 的回答' })
  assert.equal(api.streams[0].closed, true, 'A 完成只关自己的连接')
  assert.equal(api.streams[1].closed, false, 'B 的连接不得被误关(缺陷①)')
  assert.equal(store.getStreamingSession('B')?.status, 'streaming', 'B 流式状态不得被清理')
  api.streams[1].callbacks.onComplete({ final_content: 'B 的回答' })
  assert.equal(api.streams[1].closed, true)
  assert.equal(store.getMessages('A').at(-1)?.content, 'A 的回答', 'A 的结果写入 A 会话')
  assert.equal(store.getMessages('B').at(-1)?.content, 'B 的回答', 'B 的结果写入 B 会话')
})

test('晚到历史不覆盖流式内容与新消息(缺陷②)', async () => {
  const { chat, store, api } = makeEnv()
  const loading = chat.loadChatHistory('A')
  await new Promise(r => setTimeout(r, 30))
  assert.equal(api.historyGate.lastChatId, 'A', '历史请求归属请求会话')
  store.createStreamingSession('A', 'cmid-1')
  store.addMessage({ id: 'user-1', role: 'user', content: '刚发的问题' }, 'A')
  store.addMessage({ id: 'assistant-1', role: 'assistant', content: '流式中间态…' }, 'A')
  api.historyGate.release([{ id: 'old-1', role: 'user', content: '三个月前的旧消息' }])
  await loading
  const msgs = store.getMessages('A')
  assert.equal(msgs.length, 2, '晚到历史不得覆盖流式内存数据')
  assert.equal(msgs[0].content, '刚发的问题')
})

test('同一会话流式期间禁止重复发送(不同会话互不影响)', async () => {
  const { chat, store, api } = makeEnv()
  await send(chat, store, api, '第一条', 'A')
  const n = api.streams.length
  store.setCurrentChatId('A')
  await chat.sendMessage('流式中再发一条')
  assert.equal(api.streams.length, n, '同会话流式期间重复发送被拒绝')
  await send(chat, store, api, 'B 的独立问题', 'B')
  assert.equal(api.streams.length, n + 1, '不同会话可并行发流')
})

test('停止只作用于当前浏览会话', async () => {
  const { chat, store, api } = makeEnv()
  await send(chat, store, api, 'A 的长任务', 'A')
  await send(chat, store, api, 'B 的长任务', 'B')
  store.setCurrentChatId('B')
  await chat.stopStream()
  assert.equal(api.streams[1].closed, true, '当前浏览会话(B)被停止')
  assert.equal(api.streams[0].closed, false, '后台会话(A)不受影响')
})
