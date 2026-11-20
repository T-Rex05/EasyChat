// WP-C 回归：GET 聊天流真实 HTTP 失败可见 + error.message 读取 + 恢复互斥/代次/终态关闭。
// GET 流已从 EventSource 改为 fetch SSE（HTTP 状态可读、Last-Event-ID/last_seq 续传保留）。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

const raw = readFileSync(new URL('../src/api/chat.ts', import.meta.url), 'utf8')
const script = raw
  .replace(/^import .*$/gm, '')
  .replace(/import\.meta\.env/g, '(globalThis.__env || {})')
  .replace(/export /g, '')
const EXPORTED = ts.transpileModule(script, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
  + '\nexports.sendMessageStream = sendMessageStream;'
  + '\nexports.sendMessageStreamPost = sendMessageStreamPost;'

const flush = async () => {
  for (let i = 0; i < 10; i++) await new Promise((r) => setImmediate(r))
}

const enc = new TextEncoder()

function sseBody(frames) {
  // frames: [{id?, data}] → SSE 文本
  let out = ''
  for (const f of frames) {
    if (f.id !== undefined) out += `id: ${f.id}\n`
    out += `data: ${JSON.stringify(f.data)}\n\n`
  }
  return out
}

function makeMod(fetchImpl, stubs = {}) {
  globalThis.__env = {}
  const store = { authToken: 'JWT-1', ...(stubs.store || {}) }
  const local = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
  }
  const win = { location: { pathname: stubs.pathname || '/chat', href: '', hash: stubs.hash ?? '#/chat' } }
  const exports = {}
  new Function(
    'fetch', 'EventSource', 'localStorage', 'window', 'useAuthStore', 'module', 'exports', EXPORTED,
  )(fetchImpl, function FakeES() { this.close = () => {} }, local, win,
    () => ({ token: null }), { exports }, exports)
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

function okStream(frames) {
  const text = sseBody(frames)
  return new ReadableStream({
    start(controller) {
      controller.enqueue(enc.encode(text))
      controller.close()
    },
  })
}

const AUTH_OK = { ok: true, status: 200, json: async () => ({ id: 1 }) }

test('流请求 503：真实状态可见，不清 token，不建立读取循环', async () => {
  const calls = []
  const { exports, local } = makeMod(async (url) => {
    calls.push(String(url))
    if (String(url).includes('auth/me')) return AUTH_OK
    return { ok: false, status: 503, json: async () => ({ detail: 'assistant 未就绪' }), body: null }
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.equal(errors.length, 1)
  assert.match(errors[0], /503|暂时不可用|未就绪/)
  assert.doesNotMatch(errors[0], /请先登录|登录已过期/)
  assert.equal(local.getItem('authToken'), 'JWT-1')
})

test('流请求 409：服务繁忙原因可见且不做无效重试', async () => {
  let streamCalls = 0
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('auth/me')) return AUTH_OK
    if (String(url).includes('/chat/stream')) { streamCalls += 1; return { ok: false, status: 409, json: async () => ({ error: 'busy', message: '已有正在执行的任务' }), body: null } }
    throw new Error('未预期请求 ' + url)
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.match(errors[0], /繁忙|正在执行/)
  assert.doesNotMatch(errors[0], /登录/)
  assert.ok(streamCalls <= 2, `409 不得反复重试，实际 ${streamCalls} 次`)
})

test('流请求 401：在 /login#/chat 清 token 并返回登录路由', async () => {
  const { exports, local, win } = makeMod(async (url) => {
    if (String(url).includes('auth/me')) return { ok: false, status: 401, json: async () => ({ detail: 'expired' }) }
    return { ok: false, status: 401, json: async () => ({ detail: 'expired' }), body: null }
  }, { pathname: '/login' })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.equal(local.getItem('authToken'), null)
  assert.equal(win.location.hash, '#/login')
  assert.match(errors[0], /登录/)
})

test('后端 error 帧读取 message 字段（此前只读 error 显示未知错误）', async () => {
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('/chat/stream')) {
      return { ok: true, status: 200, body: okStream([{ id: 1, data: { type: 'error', message: '模型调用超时，请稍后重试' } }]) }
    }
    if (String(url).includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.deepEqual(errors, ['模型调用超时，请稍后重试'])
})

test('完成事件后正常关闭：无假错误、无重连', async () => {
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('/chat/stream')) {
      return { ok: true, status: 200, body: okStream([
        { id: 1, data: { type: 'token', content: '答' } },
        { data: { type: 'chat_complete', final_content: '答案' } },
      ]) }
    }
    if (String(url).includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  const chunks = []
  callbacks.onChunk = (_d, full) => chunks.push(full)
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.deepEqual(errors, [])
  assert.equal(chunks.join(''), '答')
})

test('输出后断流：携带原 client_msg_id 与游标重连，不重复上报用户消息', async () => {
  const streamBodies = [
    okStream([{ id: 42, data: { type: 'token', content: '部分' } }]),
    okStream([
      { id: 43, data: { type: 'token', content: '后续' } },
      { data: { type: 'chat_complete', final_content: '部分后续' } },
    ]),
  ]
  const streamCalls = []
  let failOnce = true
  const { exports } = makeMod(async (url) => {
    const u = String(url)
    if (u.includes('/chat/stream')) {
      streamCalls.push(u)
      if (failOnce) {
        failOnce = false
        return { ok: true, status: 200, body: new ReadableStream({
          start(c) { c.enqueue(enc.encode('id: 42\ndata: {"type":"token","content":"部分"}\n\n')); c.close() },
        }) }
      }
      return { ok: true, status: 200, body: streamBodies[1] }
    }
    if (u.includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-9')
  await flush()
  assert.deepEqual(errors, [])
  assert.ok(streamCalls.length >= 2, '断流后应自动重连一次')
  const second = streamCalls[1]
  assert.match(second, /client_msg_id=cm-9/, '重连携带原逻辑请求标识')
  assert.match(second, /last_seq=42/, '重连携带已收游标')
})

test('恢复中手动停止：不再发起新连接，晚到数据丢弃且无错误', async () => {
  let streamCalls = 0
  let hold = null
  const { exports } = makeMod(async (url) => {
    const u = String(url)
    if (u.includes('/chat/stream')) {
      streamCalls += 1
      return { ok: true, status: 200, body: new ReadableStream({
        start(c) {
          hold = c
          c.enqueue(enc.encode('id: 1\ndata: {"type":"token","content":"x"}\n\n'))
        },
      }) }
    }
    if (u.includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const chunks = []
  const { callbacks, errors } = cb()
  callbacks.onChunk = (_d, full) => chunks.push(full)
  const handle = await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  const beforeClose = streamCalls
  handle.close() // 用户停止：推进代次 + abort
  // 停止后旧连接再推数据（模拟已在途字节）：必须按代次丢弃
  try { hold.enqueue(enc.encode('id: 2\ndata: {"type":"token","content":"迟到"}\n\n')) } catch { /* 已关闭 */ }
  await flush()
  assert.equal(chunks.join(''), 'x', '停止前的数据保留，停止后的迟到数据丢弃')
  assert.equal(streamCalls, beforeClose, '停止后不得发起新连接')
  assert.deepEqual(errors, [])
})

test('重试有界：持续断流最终给出连接异常提示且停止恢复', async () => {
  let streamCalls = 0
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('/chat/stream')) {
      streamCalls += 1
      return { ok: true, status: 200, body: new ReadableStream({
        start(c) { c.enqueue(enc.encode('id: 1\ndata: {"type":"token","content":"x"}\n\n')); c.close() },
        // 提前 close 且无终态 → 读取循环正常结束但流未完成 → 视为断流
      }) }
    }
    if (String(url).includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.ok(streamCalls <= 3, `恢复有界，实际 ${streamCalls}`)
  assert.ok(errors.length >= 1)
  assert.match(errors[errors.length - 1], /断开|连接|重试/)
  assert.doesNotMatch(errors[errors.length - 1], /登录/)
})

test('完成后返回值可安全停止：无错误无副作用', async () => {
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('/chat/stream')) {
      return { ok: true, status: 200, body: okStream([{ data: { type: 'chat_complete', final_content: 'ok' } }]) }
    }
    if (String(url).includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  const handle = await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  handle.close() // 终态后 close 幂等
  await flush()
  assert.deepEqual(errors, [])
})

test('重连 URL 保留 Authorization 不落 ticket/token 于查询串', async () => {
  const urls = []
  const { exports } = makeMod(async (url) => {
    const u = String(url)
    urls.push(u)
    if (u.includes('/chat/stream')) return { ok: true, status: 200, body: okStream([{ data: { type: 'chat_complete', final_content: 'ok' } }]) }
    if (u.includes('auth/me')) return AUTH_OK
    throw new Error('未预期请求')
  })
  const { callbacks, errors } = cb()
  await exports.sendMessageStream('你好', 'c1', callbacks, 'cm-1')
  await flush()
  assert.deepEqual(errors, [])
  for (const u of urls) {
    if (u.includes('/chat/stream')) {
      assert.doesNotMatch(u, /ticket=|token=/, '长效凭据不得进 URL（审计 #3）')
    }
  }
})

test('旧服务的推理帧被忽略，工具名称和最终回复按序可见', async () => {
  const { exports } = makeMod(async (url) => {
    if (String(url).includes('auth/me')) return AUTH_OK
    return { ok: true, status: 200, body: okStream([
      { id: 1, data: { type: 'thinking_step', content: 'private' } },
      { id: 2, data: { type: 'tool_activity', tools: ['search', 'lookup'] } },
      { id: 3, data: { type: 'token', content: '你好' } },
      { data: { type: 'chat_complete', final_content: '你好！' } },
    ]) }
  })
  const events = []
  await exports.sendMessageStream('hello', 'c1', {
    onThinkingStep: (text) => events.push(text),
    onToolCall: (name) => events.push(name),
    onChunk: (_chunk, full) => events.push(full),
    onComplete: (data) => events.push(data.final_content),
  }, 'cm-1')
  await flush()
  assert.deepEqual(events, ['search', 'lookup', '你好', '你好！'])
})
