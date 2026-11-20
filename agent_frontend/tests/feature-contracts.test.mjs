import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { isAxiosError } from 'axios'
import ts from 'typescript'
import { computed, reactive, ref, watch } from 'vue'

function readSource(path) {
  return readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
}

// Exercise the view handlers directly, without mounting a browser or making HTTP calls.
function evaluate(source, bindings, exposed) {
  const script = source.includes('<script setup')
    ? source.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)[1]
    : source
  const parsed = ts.createSourceFile('view.ts', script, ts.ScriptTarget.Latest, true)
  let withoutImports = script
  for (const statement of [...parsed.statements].reverse()) {
    if (ts.isImportDeclaration(statement)) {
      withoutImports = withoutImports.slice(0, statement.getStart(parsed)) + withoutImports.slice(statement.end)
    }
  }
  const { outputText } = ts.transpileModule(withoutImports, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  return new Function(...Object.keys(bindings), 'exports', `${outputText}\nreturn { ${exposed.join(', ')} }`)(
    ...Object.values(bindings), {},
  )
}

function view(path, request, exposed, auth = {}) {
  return evaluate(readSource(`views/${path}.vue`), {
    request, ref, reactive, computed, watch, isAxiosError, onMounted() {}, useAuthStore: () => auth,
  }, exposed)
}

test('login, verification, refresh and logout update the active user identity', async () => {
  const storage = () => {
    const items = new Map()
    return {
      getItem: key => items.get(key) ?? null,
      setItem: (key, value) => items.set(key, String(value)),
      removeItem: key => items.delete(key),
      clear: () => items.clear(),
    }
  }
  const localStorage = storage()
  const sessionStorage = storage()
  const { useAuthStore } = evaluate(readSource('stores/auth.ts'), {
    defineStore: (_name, setup) => setup,
    ref, computed, localStorage, sessionStorage,
    apiLogin: async () => ({ token: 'fixture', user_id: 7 }),
    verifyToken: async () => ({ id: 7 }),
    refreshToken: async () => ({ token: 'fixture-refreshed', user_id: 7 }),
    useChatStore: () => ({ resetAll() {} }),
  }, ['useAuthStore: exports.useAuthStore'])
  const auth = useAuthStore()
  assert.equal(auth.userId.value, '')
  await auth.login('fixture', 'fixture-password')
  assert.equal(auth.userId.value, '7')
  await auth.verify()
  await auth.tryRefresh()
  assert.equal(auth.userId.value, '7')
  assert.equal(localStorage.getItem('chatUserId'), '7')
  assert.equal(sessionStorage.getItem('chatUserId'), '7')
  auth.logout()
  assert.equal(auth.userId.value, '')
  assert.equal(localStorage.getItem('chatUserId'), null)
  assert.equal(sessionStorage.getItem('chatUserId'), null)
})

test('manual memory uses a supported, user-confirmed source type', async () => {
  let submitted
  const { rememberMemory } = evaluate(readSource('api/memoryManagement.ts'), {
    request: { async post(url, body) { submitted = { url, body } } },
  }, ['rememberMemory'])
  await rememberMemory({ kind: 'preference', content: '偏好茶', pinned: true, is_shared: false,
    source_refs: [{ kind: 'manual', ref: 'chat:42', quote: '记住我喜欢茶' }],
  })
  assert.equal(submitted.url, '/api/memory/remember')
  assert.equal(submitted.body.source_type, 'user_confirmed')
  assert.deepEqual(submitted.body.source_refs, [{ kind: 'manual', ref: 'chat:42', quote: '记住我喜欢茶' }])
  assert.equal(submitted.body.pinned, true)
})

const skillOwner = { userId: '7', ready: true, permissions: ['skill.create'] }

test('successive skill activations submit the latest expected active version', async () => {
  let active = null
  const activations = []
  const skill = () => ({ skill_id: 'skill-1', owner_id: 7, name: 'demo', active_version_id: active })
  const skills = view('SkillsView', {
    async post(url, body) {
      activations.push(body)
      assert.equal(body.expected_active_version_id, active)
      active = body.version_id
      return { data: { skill: skill() } }
    },
    async get(url) {
      return { data: url === '/api/skills' ? { skills: [skill()] } : { skill: skill(), versions: [], content: '' } }
    },
  }, ['activate', 'openSkill', 'error'], skillOwner)
  await skills.openSkill('skill-1')
  await skills.activate('v1')
  assert.equal(skills.error.value, '')
  await skills.activate('v2')
  assert.equal(skills.error.value, '')
  await skills.activate('v1')
  assert.equal(skills.error.value, '')
  assert.deepEqual(activations.map(body => body.expected_active_version_id), [null, 'v1', 'v2'])
})

test('stale skill activation keeps the conflict visible and preserves local version', async () => {
  const skills = view('SkillsView', {
    async post(url, body) {
      assert.equal(body.expected_active_version_id, 'stale-v1')
      throw new Error('技能激活指针已变化')
    },
  }, ['activate', 'selected', 'historyDialog', 'comparisonError'], skillOwner)
  skills.selected.value = { skill_id: 'skill-1', owner_id: 7, active_version_id: 'stale-v1' }
  skills.historyDialog.value = { open: true }
  await skills.activate('v2')
  assert.equal(skills.comparisonError.value, '技能激活指针已变化')
  assert.equal(skills.selected.value.active_version_id, 'stale-v1')
})

test('revoked skill management clears previously visible foreign content and reloads only personal skills', async () => {
  const refresh = deferred()
  const auth = reactive({
    ...skillOwner,
    permissions: ['skill.create', 'skill.manage'],
    async verify() {
      await refresh.promise
      auth.permissions = ['skill.create']
    },
  })
  const foreignSkill = { skill_id: 'foreign', owner_id: 12, name: 'other', active_version_id: 'v1' }
  const requests = []
  const skills = view('SkillsView', {
    async get(url, config) {
      if (url === '/api/skills') {
        requests.push(config.params.all_owners)
        return { data: { skills: config.params.all_owners ? [foreignSkill] : [] } }
      }
      return { data: { skill: foreignSkill, versions: [], content: '# Private content' } }
    },
    async patch() {
      throw Object.assign(new Error('无权访问该技能'), { isAxiosError: true, response: { status: 403 } })
    },
  }, ['changeScope', 'openSkill', 'patch', 'selected', 'persistedContent', 'canManageSkills'], auth)
  skills.changeScope({ target: { value: 'all' } })
  await skills.openSkill('foreign')
  assert.equal(skills.persistedContent.value, '# Private content')

  await skills.patch({ pinned: true })
  assert.equal(skills.selected.value, null)
  assert.equal(skills.persistedContent.value, '')
  assert.equal(skills.canManageSkills.value, false)

  refresh.resolve()
  await settle()
  assert.deepEqual(requests, [false, true, false])
  assert.equal(skills.canManageSkills.value, false)
})

function platformApi(request) {
  return evaluate(readSource('api/platform.ts'), { request }, ['savePlatformConfig', 'createUserBinding'])
}

test('platform configuration preserves the custom service URL', async () => {
  let submitted
  const api = platformApi({ async post(url, body) { submitted = { url, body }; return { data: { account: { id: 'pk' } } } } })
  await api.savePlatformConfig('wechat', {
    config_json: { account_id: ' account-1 ', token: ' token ', base_url: ' https://wechat.example/api ' },
    enabled: true,
  })
  assert.equal(submitted.url, '/api/channels/accounts')
  assert.equal(submitted.body.base_url, 'https://wechat.example/api')
  assert.equal(submitted.body.account_id, 'account-1')
  assert.equal(submitted.body.token, 'token')
})

test('user binding sends the bot account separately from the external user', async () => {
  let submitted
  const api = platformApi({
    async post(url, body) { submitted = { url, body }; return { data: { binding: { id: 'binding-1' } } } },
  })
  const result = await api.createUserBinding({ platform: 'wechat', account_id: 'bot-1', open_id: 'user-2', nickname: '用户' })
  assert.equal(submitted.url, '/api/channels/bindings')
  assert.deepEqual(submitted.body, { platform: 'wechat', account_id: 'bot-1', external_user_id: 'user-2' })
  assert.deepEqual(result, { ok: true, id: 'binding-1' })
})

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

const settle = () => new Promise(resolve => setImmediate(resolve))

function channelView({ manage = true, handle } = {}) {
  const calls = []
  async function respond(method, url, body) {
    calls.push({ method, url, body })
    const override = await handle?.(method, url, body)
    if (override !== undefined) return { data: override }
    if (url === '/api/system/module-status') return { data: { channels: { assembled: true, state: 'ready', reason: '' } } }
    if (url.endsWith('/accounts') && method === 'POST') return { data: { account: { id: 'pk' } } }
    if (url.endsWith('/bindings') && method === 'POST') return { data: { binding: { id: 'binding-1' } } }
    if (url.endsWith('/accounts/pk/start')) return { data: { listener: { status: 'starting' } } }
    if (url.endsWith('/qr/start')) return { data: { qr: { session_id: 'qr-1', status: 'wait' } } }
    if (url.endsWith('/accounts')) return { data: { accounts: [] } }
    if (url.endsWith('/bindings')) return { data: { bindings: [] } }
    throw new Error('Unexpected request ' + url)
  }
  const request = {
    get: url => respond('GET', url),
    post: (url, body) => respond('POST', url, body),
  }
  const api = evaluate(readSource('api/platform.ts'), { request }, ['...exports'])
  const timers = new Set()
  function schedule(fn, repeat) {
    const tick = () => {
      if (!repeat) timers.delete(tick)
      return fn()
    }
    timers.add(tick)
    return tick
  }
  let mounted, unmounted
  const empty = async () => ({})
  const ui = evaluate(readSource('views/ConfigView.vue'), {
    ...api, computed, ref, reactive, watch,
    onMounted(fn) { mounted = fn }, onUnmounted(fn) { unmounted = fn },
    useAuthStore: () => ({ ready: true, user: { id: 7 }, userId: '7', hasPerm: perm => manage && perm === 'system.manage' }),
    getModelConfigs: empty, getFallbackChain: empty, getAvailableScenes: empty, getSceneRouting: empty,
    getEmailConfigs: empty, getPersonalEmails: empty, fetch: empty,
    alert() {}, localStorage: { getItem() { return '' } },
    setInterval: fn => schedule(fn, true), clearInterval: fn => timers.delete(fn),
    setTimeout: fn => schedule(fn, false), clearTimeout: fn => timers.delete(fn),
  }, ['manualBindForm', 'submitManualBind', 'retryListener', 'startQrBind', 'qrStatus', 'wechatBinding', 'channelActionMsg'])
  mounted()
  return { ui, calls, timers, unmount: () => unmounted() }
}

test('channel mount waits for module status and disabled actions send no channel requests', async () => {
  const status = deferred()
  const { ui, calls } = channelView({ handle: (_, url) => url.endsWith('/module-status') ? status.promise : undefined })
  await settle()
  assert.deepEqual(calls.map(c => c.url), ['/api/system/module-status'])
  status.resolve({ channels: { assembled: false, state: 'disabled', reason: '管理员未开启' } })
  await settle()
  Object.assign(ui.manualBindForm, { token: 'token', account_id: 'bot', wxid: 'user' })
  await ui.submitManualBind()
  await ui.startQrBind()
  assert.deepEqual(calls.map(c => c.url), ['/api/system/module-status'])
})

test('member loads own binding without accessing accounts or management APIs', async () => {
  const { calls, ui } = channelView({ manage: false, handle: (_, url) => {
    if (url.endsWith('/bindings')) return { bindings: [{ user_id: 7, id: 'mine', external_user_id: 'self', platform: 'wechat', status: 'active' }] }
  } })
  await settle()
  assert.equal(ui.wechatBinding.value?.open_id, 'self')
  await ui.startQrBind()
  assert.deepEqual(calls.map(c => c.url), ['/api/system/module-status', '/api/channels/bindings'])
})

test('manual binding requires the sender ID, binds that sender, then starts the saved account', async () => {
  const { calls, ui } = channelView({ handle: (method, url) => {
    if (url.endsWith('/bindings') && method === 'GET') return { bindings: [{ user_id: 8, external_user_id: 'other-owner', platform: 'wechat', status: 'active' }] }
  } })
  await settle()
  assert.equal(ui.wechatBinding.value, null)
  Object.assign(ui.manualBindForm, { token: ' token ', account_id: ' bot-1 ', base_url: 'https://wechat.example' })
  await ui.submitManualBind()
  assert.equal(calls.filter(c => c.method === 'POST').length, 0)
  ui.manualBindForm.wxid = ' user-2 '
  await ui.submitManualBind()
  const posts = calls.filter(c => c.method === 'POST')
  assert.deepEqual(posts.map(c => c.url), ['/api/channels/accounts', '/api/channels/bindings', '/api/channels/accounts/pk/start'])
  assert.equal(posts[0].body.base_url, 'https://wechat.example')
  assert.equal(posts[1].body.account_id, 'bot-1')
  assert.equal(posts[1].body.external_user_id, 'user-2')
})

test('QR polls serially and ignores an in-flight confirmation after leaving the page', async () => {
  const pending = deferred()
  const { calls, ui, timers, unmount } = channelView({ handle: (_, url) => url.endsWith('/qr/qr-1') ? pending.promise : undefined })
  await settle()
  await ui.startQrBind()
  assert.equal(timers.size, 1)
  const tick = [...timers][0]
  const poll = tick()
  await settle()
  assert.equal(timers.size, 0)
  unmount()
  pending.resolve({ qr: { status: 'confirmed' } })
  await poll
  await settle()
  assert.ok(!calls.some(c => c.url.endsWith('/bind')))
  assert.equal(timers.size, 0)
})

test('listener failure keeps the binding visible and retry only starts the listener', async () => {
  let starts = 0
  let bound = false
  const { calls, ui } = channelView({ handle(method, url) {
    if (method === 'POST' && url.endsWith('/bindings')) bound = true
    if (method === 'GET' && url.endsWith('/bindings') && bound) {
      return { bindings: [{ user_id: 7, external_user_id: 'user', platform: 'wechat', status: 'active' }] }
    }
    if (url.endsWith('/pk/start') && ++starts === 1) return { listener: { status: 'error', last_error: '无法建立连接' } }
  } })
  await settle()
  Object.assign(ui.manualBindForm, { token: 'token', account_id: 'bot', wxid: 'user' })
  await ui.submitManualBind()
  assert.equal(ui.wechatBinding.value?.open_id, 'user')
  assert.match(ui.channelActionMsg.value, /无法建立连接/)
  const count = calls.length
  await ui.retryListener()
  assert.deepEqual(calls.slice(count).map(c => c.url), ['/api/channels/accounts/pk/start'])
})

test('QR displays scanned status and reports a saved bot without a user binding', async () => {
  let polls = 0
  const { calls, ui, timers } = channelView({ handle(_, url) {
    if (url.endsWith('/qr/qr-1')) return { qr: { status: ++polls === 1 ? 'scanned' : 'confirmed' } }
    if (url.endsWith('/bind')) return { account: { id: 'pk', has_credentials: true }, binding: null, listener: { status: 'running' } }
  } })
  await settle()
  await ui.startQrBind()
  await [...timers][0]()
  assert.equal(ui.qrStatus.value, 'scanned')
  await [...timers][0]()
  assert.equal(calls.filter(c => c.url.endsWith('/bind')).length, 1)
  assert.match(ui.channelActionMsg.value, /缺少发送者 ID/)
  assert.equal(timers.size, 0)
})

test('QR poll failure stops polling and displays the service error', async () => {
  const { ui, timers } = channelView({ handle(_, url) {
    if (url.endsWith('/qr/qr-1')) throw new Error('扫码服务暂时不可用')
  } })
  await settle()
  await ui.startQrBind()
  await [...timers][0]()
  assert.match(ui.channelActionMsg.value, /扫码服务暂时不可用/)
  assert.equal(timers.size, 0)
})

test('mood opt-in keeps boolean API values consistent with the visible switch', async () => {
  const source = readSource('views/WeChatSettingsView.vue')
  const patches = []
  const settings = evaluate(source, {
    ref, reactive, onMounted() {}, window: { setTimeout() {} },
    async updateProfile(patch) { patches.push(patch); return { mood_opt_in: patch.mood_opt_in } },
    async listMood() { return [] },
  }, ['form', 'toggleMood'])
  assert.equal(settings.form.mood_opt_in, false)
  assert.match(source, /:checked="form\.mood_opt_in"/)
  assert.doesNotMatch(source, /form\.mood_opt_in\s*===\s*1/)
  await settings.toggleMood({ target: { checked: true } })
  assert.equal(settings.form.mood_opt_in, true)
  await settings.toggleMood({ target: { checked: false } })
  assert.equal(settings.form.mood_opt_in, false)
  assert.deepEqual(patches, [{ mood_opt_in: true }, { mood_opt_in: false }])
})

test('image recognition exposes missing fields for manual correction', async () => {
  const ledger = evaluate(readSource('views/LedgerView.vue'), {
    ref, reactive, onMounted() {},
    async uploadFile() { return { file_id: 'image-1' } },
    request: { async post() { return { data: {
      candidate_id: 'candidate-1', extraction_id: 'extraction-1', confidence: 0,
      fields: { merchant: { value: '商户', confidence: 0.9, needs_review: false } },
      missing_fields: ['amount', 'occurred_at', 'direction'],
    } } } },
  }, ['recognize', 'imageInput', 'candidate', 'error'])
  ledger.imageInput.value = { files: [{}] }
  await ledger.recognize()
  assert.equal(ledger.error.value, '')
  assert.equal(ledger.candidate.value.fields.merchant.value, '商户')
  assert.deepEqual(ledger.candidate.value.fields.amount, { value: '', confidence: 0, needs_review: true })
  assert.ok(ledger.candidate.value.fields.occurred_at)
  assert.ok(ledger.candidate.value.fields.direction)
})

test('image confirmation submits keyed field corrections using the extraction ID', async () => {
  let submitted
  const ledger = evaluate(readSource('views/LedgerView.vue'), {
    ref, reactive, onMounted() {},
    async listTransactions() { return [] },
    request: { async post(url, body) { submitted = { url, body } } },
  }, ['candidate', 'confirmCandidate', 'error'])
  ledger.candidate.value = {
    candidate_id: 'candidate-1', extraction_id: 'extraction-2', confidence: 0.5,
    fields: {
      amount: { value: '12.34', confidence: 0.5, needs_review: true },
      direction: { value: '支出', confidence: 1, needs_review: false },
      occurred_at: { value: '2026-11-09 12:00:00', confidence: 1, needs_review: false },
    },
  }
  await ledger.confirmCandidate()
  assert.equal(ledger.error.value, '')
  assert.equal(submitted.url, '/api/ledger/candidates/extraction-2/confirm')
  assert.deepEqual(submitted.body.corrections, { amount: '12.34', direction: '支出', occurred_at: '2026-11-09 12:00:00' })
  assert.equal(ledger.candidate.value, null)
})

test('refund suggestions display the supplied match method and reason', () => {
  const section = readSource('views/LedgerView.vue').match(/<h3>退款候选<\/h3>([\s\S]*?)<\/section>/)[1]
  assert.doesNotMatch(section, /item\.confidence/)
  assert.match(section, /item\.match_method/)
  assert.match(section, /item\.reason/)
})
