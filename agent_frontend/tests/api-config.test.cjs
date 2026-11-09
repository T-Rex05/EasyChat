const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

test('fallback API converts model profiles and saves config_ids in order', async () => {
  const calls = []
  const request = {
    get: async () => ({ data: { chain: [{
      config_id: 7, name: 'Backup', provider: 'openai', model: 'backup-model',
      base_url: 'https://example.invalid', api_key_masked: '***',
      is_active: false, is_multimodal: true, reasoning_effort: 'high',
    }] } }),
    put: async (...args) => { calls.push(args); return { data: { ok: true } } },
  }
  const source = fs.readFileSync(path.join(__dirname, '../src/api/config.ts'), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const api = { exports: {} }
  new Function('require', 'exports', 'module', compiled)(() => ({ default: request }), api.exports, api)

  const result = await api.exports.getFallbackChain()
  assert.equal(result.fallback_chain.length, 1)
  assert.equal(result.fallback_chain[0].id, 7)
  assert.equal(result.fallback_chain[0].config_name, 'Backup')
  assert.equal(result.fallback_chain[0].model_name, 'backup-model')
  assert.equal(result.fallback_chain[0].enabled, true)
  await api.exports.saveFallbackChain([7, 3])
  assert.deepEqual(calls, [['/api/model-routes/fallback-chain', { config_ids: [7, 3] }]])
})

test('ledger API unwraps uploaded files and import records', async () => {
  const fileRecord = { file_id: 'file-test', original_name: 'test.csv' }
  const importRecord = {
    import_id: 'import-test', file_id: 'file-test', state: 'ready',
    row_counts: { rows: 12, errors: 1 },
    quality: { commit: { inserted: 8, updated: 2, unchanged: 1 } },
  }
  const calls = []
  const request = {
    post: async (url, body) => {
      calls.push([url, body])
      return { data: url === '/api/files' ? { file: fileRecord } : { import: importRecord } }
    },
  }
  const source = fs.readFileSync(path.join(__dirname, '../src/api/ledger.ts'), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const api = { exports: {} }
  new Function('require', 'exports', 'module', compiled)(() => ({ default: request }), api.exports, api)

  const uploaded = await api.exports.uploadFile(new File(['test'], 'test.csv'))
  assert.deepEqual(uploaded, fileRecord)
  const registered = await api.exports.registerImport(uploaded.file_id)
  assert.equal(registered.import_id, importRecord.import_id)
  assert.equal(registered.rows, 12)
  assert.equal(registered.failed, 1)
  assert.equal(registered.inserted, 8)
  assert.equal(registered.updated, 2)
  assert.equal(registered.unchanged, 1)
  assert.deepEqual(await api.exports.parseImport(registered.import_id), registered)
  assert.equal(calls[1][1].file_id, 'file-test')
  assert.equal(calls[2][0], '/api/ledger/imports/import-test/parse')
})

test('chat streams submit registered attachment IDs without copying media bytes', () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/api/chat.ts'), 'utf8')
  const parsed = ts.createSourceFile('chat.ts', source, ts.ScriptTarget.Latest, true)
  const handler = parsed.statements.find(statement =>
    ts.isFunctionDeclaration(statement) && statement.name?.text === 'sendMessageStreamPost')
  const compiled = ts.transpileModule(handler.getText(parsed), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const api = { exports: {} }
  let submitted
  new Function('API_BASE', 'getAuthToken', 'fetch', 'exports', compiled)(
    '', () => 'offline', (url, options) => {
      submitted = JSON.parse(options.body)
      return new Promise(() => {})
    }, api.exports,
  )
  api.exports.sendMessageStreamPost('read', '1_1', {}, 'message-1', 'normal',
    [{ attachment_id: 'image-ref', data_url: 'data:image/png;base64,preview', mime: 'image/png' }],
    [{ attachment_id: 'file-ref', filename: 'note.txt', url: '', content: 'preview' }])
  assert.deepEqual(submitted.attachment_ids, ['image-ref', 'file-ref'])
  assert.equal(submitted.images, undefined)
  assert.equal(submitted.files, undefined)
})
