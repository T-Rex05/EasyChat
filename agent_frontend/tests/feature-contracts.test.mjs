import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'
import { computed, reactive, ref } from 'vue'

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

function view(path, request, exposed) {
  return evaluate(readSource(`views/${path}.vue`), {
    request, ref, reactive, computed, onMounted() {},
  }, exposed)
}

test('manual memory uses a supported, user-confirmed source type', async () => {
  let submitted
  const memory = view('MemoryView', {
    async post(url, body) { submitted = { url, body } },
    async get() { return { data: { memories: [] } } },
  }, ['remember', 'draft', 'error'])
  Object.assign(memory.draft, { content: '偏好茶', source: 'chat:42', quote: '记住我喜欢茶', pinned: true })
  await memory.remember()
  assert.equal(submitted.url, '/api/memory/remember')
  assert.equal(submitted.body.source_type, 'user_confirmed')
  assert.deepEqual(submitted.body.source_refs, [{ kind: 'manual', ref: 'chat:42', quote: '记住我喜欢茶' }])
  assert.equal(submitted.body.pinned, true)
  assert.equal(memory.error.value, '')
})

test('successive skill activations submit the latest expected active version', async () => {
  let active = null
  const activations = []
  const skill = () => ({ skill_id: 'skill-1', name: 'demo', active_version_id: active })
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
  }, ['activate', 'selected', 'error'])
  skills.selected.value = skill()
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
  }, ['activate', 'selected', 'error'])
  skills.selected.value = { skill_id: 'skill-1', active_version_id: 'stale-v1' }
  await skills.activate('v2')
  assert.equal(skills.error.value, '技能激活指针已变化')
  assert.equal(skills.selected.value.active_version_id, 'stale-v1')
})

function platformApi(request) {
  return evaluate(readSource('api/platform.ts'), { request }, ['savePlatformConfig', 'createUserBinding'])
}

test('platform configuration preserves the custom service URL', async () => {
  let submitted
  const api = platformApi({ async post(url, body) { submitted = { url, body } } })
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

test('manual WeChat binding passes the entered account through to the binding API', async () => {
  const posts = []
  const api = platformApi({
    async post(url, body) { posts.push({ url, body }); return { data: { binding: { id: 'binding-1' } } } },
  })
  const source = readSource('views/ConfigView.vue').match(/<script setup[^>]*>([\s\S]*?)<\/script>/)[1]
  const parsed = ts.createSourceFile('ConfigView.ts', source, ts.ScriptTarget.Latest, true)
  const handler = parsed.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name?.text === 'submitManualBind')
  const bindings = {
    ...api,
    manualBindForm: { token: ' token ', account_id: ' bot-1 ', base_url: 'https://wechat.example', wxid: ' user-2 ', nickname: '用户' },
    savingManual: ref(false), manualBindMsg: ref(''), manualBindOk: ref(false), showManualBind: ref(true),
    isSuperAdmin: ref(true), async loadWechatConfig() {}, async loadWechatBinding() {},
  }
  const { submitManualBind } = evaluate(handler.getText(parsed), bindings, ['submitManualBind'])
  await submitManualBind()
  assert.equal(bindings.manualBindOk.value, true)
  assert.equal(posts[0].body.base_url, 'https://wechat.example')
  assert.equal(posts[1].body.account_id, 'bot-1')
  assert.equal(posts[1].body.external_user_id, 'user-2')
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
