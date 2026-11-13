// P1 回归：SSE 登录过期误报修复——ticket 错误分类、移除 3 秒启发式、
// 认证判定走显式状态接口、断线重连用新 ticket+原 client_msg_id+游标。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

const raw = readFileSync(new URL('../src/api/chat.ts', import.meta.url), 'utf8')
const script = raw
  .replace(/^import .*$/gm, '')
  .replace(/import\.meta\.env/g, '(globalThis.__env || {})')
  .replace(/export /g, '')
const transpiled = ts.transpileModule(script, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
})
const EXPORTED = transpiled.outputText
  + '\nexports.sendMessageStream = sendMessageStream;'
  + '\nexports.sendMessageStreamPost = sendMessageStreamPost;'

class FakeEventSource {
  constructor(url) {
    this.url = String(url)
    this.listeners = {}
    this.readyState = 0
    FakeEventSource.instances.push(this)
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn) }
  close() { this.readyState = 2 }
  emit(type, ev = {}) {
    for (const fn of this.listeners[type] || []) fn(ev)
  }
}
FakeEventSource.instances = []

const flush = async () => {
  for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r))
}

function makeMod(fetchImpl, stubs = {}) {
  globalThis.__env = {}
  const store = { authToken: 'JWT-1', ...(stubs.store || {}) }
  const local = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
  }
  const win = { location: { pathname: stubs.pathname || '/chat', href: '' } }
  FakeEventSource.instances = []
  const exports = {}
  new Function(
    'fetch', 'EventSource', 'localStorage', 'window', 'useAuthStore', 'module', 'exports', EXPORTED,
  )(fetchImpl, FakeEventSource, local, win, () => ({ token: null }), { exports }, exports)
  return { exports, local, win }
}

function cb() {
  const errors = []
  return {
    errors,
    callbacks: {
      onError: (m) => errors.push(String(m)),
      onChunk: () => {},
      onComplete: () => {},
    },
  }
}

// 常规 fetch 桩：ticket 依次 T1,T2,...；auth 探测默认 200
function normalFetch(authStatus = 200) {
  let ticketSeq = 0
  return async (url) => {
    const u = String(url)
    if (u.includes('sse-ticket')) {
      return { ok: true, status: 200, json: async () => ({ ticket: `T${++ticketSeq}` }) }
    }
    if (u.includes('auth/me')) {
      return authStatus === 200
        ? { ok: true, status: 200, json: async () => ({ id: 1 }) }
        : { ok: false, status: authStatus, json: async () => ({ detail: 'expired' }) }
    }
    throw new Error('未预期请求 ' + u)
  }
}

test('ticket 503 显示服务不可用而非"请先登录"，且不清 token、不建连接', async () => {
  const { exports, local } = makeMod(async () => ({
    ok: false, status: 503, json: async () => ({ detail: 'maintenance' }),
  }))
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  assert.equal(errors.length, 1)
  assert.match(errors[0], /服务|503|暂时不可用/)
  assert.doesNotMatch(errors[0], /请先登录|登录已过期/)
  assert.equal(local.getItem('authToken'), 'JWT-1', '服务不可用不得清除有效 token')
  assert.ok(
    FakeEventSource.instances.every((s) => s.url.startsWith('data:')),
    '未获得 ticket 不得建立真实流连接',
  )
})

test('ticket 网络异常提示无法连接，不判登录失效', async () => {
  const { exports } = makeMod(async () => { throw new TypeError('Failed to fetch') })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  assert.equal(errors.length, 1)
  assert.match(errors[0], /网络|无法连接|连不上|服务/)
  assert.doesNotMatch(errors[0], /请先登录|登录已过期/)
})

test('ticket 401 走现有登录机制：清 token 并跳转登录页', async () => {
  const { exports, local, win } = makeMod(async () => ({
    ok: false, status: 401, json: async () => ({ detail: 'expired' }),
  }))
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  assert.equal(local.getItem('authToken'), null, '真实 401 必须清除 token')
  assert.equal(win.location.href, '/login', '真实 401 必须走登录跳转')
  assert.equal(errors.length, 1)
  assert.match(errors[0], /登录/)
})

test('连接立即断开不再误报登录过期：认证探测 200 → 新 ticket 原标识重连', async () => {
  const { exports, local } = makeMod(normalFetch())
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-9')
  assert.equal(FakeEventSource.instances.length, 1)
  // 模拟：连接建立后立刻 CLOSED、未收到任何消息（旧实现此处误报登录过期）
  const first = FakeEventSource.instances[0]
  first.readyState = 2
  first.emit('error')
  await flush()
  assert.deepEqual(errors, [], '认证仍有效时不得报错文案')
  assert.equal(FakeEventSource.instances.length, 2, '应自动重连一次')
  const second = FakeEventSource.instances[1]
  assert.match(second.url, /client_msg_id=cm-9/, '重连必须携带原逻辑请求标识')
  assert.match(second.url, /ticket=T2/, '重连必须使用新 ticket')
  assert.doesNotMatch(second.url, /ticket=T1[^0-9]/, '旧 ticket 已单次消费，禁止复用')
  assert.equal(local.getItem('authToken'), 'JWT-1', '非认证失效不得清 token')
})

test('重连带回事件游标：last_seq 使用最后收到的 lastEventId', async () => {
  const { exports } = makeMod(normalFetch())
  const { callbacks } = cb()
  const chunks = []
  callbacks.onChunk = (_d, full) => chunks.push(full)
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-5')
  const first = FakeEventSource.instances[0]
  first.emit('message', {
    data: JSON.stringify({ type: 'token', content: '部分' }),
    lastEventId: '42',
  })
  first.readyState = 2
  first.emit('error')
  await flush()
  const second = FakeEventSource.instances[1]
  assert.match(second.url, /last_seq=42/, '重连必须带已有游标防止重复回放')
})

test('认证探测 401 → 按现有登录机制处理（清 token+跳转，不盲目重连）', async () => {
  const { exports, local, win } = makeMod(normalFetch(401))
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  FakeEventSource.instances[0].readyState = 2
  FakeEventSource.instances[0].emit('error')
  await flush()
  assert.equal(local.getItem('authToken'), null)
  assert.equal(win.location.href, '/login')
  assert.equal(FakeEventSource.instances.length, 1, '认证失效不得盲目重连')
  assert.equal(errors.length, 1)
  assert.match(errors[0], /登录/)
})

test('重连有界：认证正常但持续断开，两次重连后给出连接异常提示', async () => {
  const { exports } = makeMod(normalFetch())
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  for (let i = 0; i < 4; i++) {
    const last = FakeEventSource.instances[FakeEventSource.instances.length - 1]
    last.readyState = 2
    last.emit('error')
    await flush()
  }
  assert.ok(
    FakeEventSource.instances.length <= 3,
    `重连必须有上限，实际连接数 ${FakeEventSource.instances.length}`,
  )
  assert.ok(errors.length >= 1)
  assert.match(errors[errors.length - 1], /断开|连接|重试/)
  assert.doesNotMatch(errors[errors.length - 1], /登录/)
})

test('chat_complete 之后的正常关闭不报错不重连', async () => {
  const { exports } = makeMod(normalFetch())
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  const es = FakeEventSource.instances[0]
  es.emit('message', { data: JSON.stringify({ type: 'chat_complete', final_content: '好' }) })
  es.readyState = 2
  es.emit('error')
  await flush()
  assert.deepEqual(errors, [])
  assert.equal(FakeEventSource.instances.length, 1)
})

test('手动 close 后的 error 事件被忽略（用户主动停止）', async () => {
  const { exports } = makeMod(normalFetch())
  const { callbacks, errors } = cb()
  const { close } = await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  const es = FakeEventSource.instances[0]
  close()
  es.readyState = 2
  es.emit('error')
  await flush()
  assert.deepEqual(errors, [])
  assert.equal(FakeEventSource.instances.length, 1)
})
