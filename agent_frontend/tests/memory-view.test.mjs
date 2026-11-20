import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

async function loadMemoryView() {
  const source = readFileSync(new URL('../src/utils/memoryView.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}

test('memory login preserves a single record locator without accepting arbitrary redirect URLs', async () => {
  const { memoryReturnLocation } = await loadMemoryView()
  assert.deepEqual(memoryReturnLocation('mem_a'), { name: 'Memory', query: { memory: 'mem_a' } })
  assert.deepEqual(memoryReturnLocation('mem_a', '2'), { name: 'Memory', query: { memory: 'mem_a', version: '2' } })
  assert.deepEqual(memoryReturnLocation('mem_a', '2#malformed'), { name: 'Memory', query: { memory: 'mem_a' } })
  assert.equal(memoryReturnLocation(['mem_a', 'mem_b']), '/chat')
  assert.equal(memoryReturnLocation('https://example.invalid/#/memory?memory=mem_a'), '/chat')
  assert.equal(memoryReturnLocation('/memory'), '/chat')
})

test('read-only capability never grants edit and edit-only cannot open memory', async () => {
  const { memoryAccess } = await loadMemoryView()
  assert.deepEqual(memoryAccess(['memory.view'], { read: true, use: true, manage: true }), { view: true, edit: false })
  assert.deepEqual(memoryAccess(['memory.edit']), { view: false, edit: false })
  assert.deepEqual(memoryAccess(['memory.view', 'memory.edit'], { read: false, use: true, manage: true }), { view: false, edit: false })
  assert.deepEqual(memoryAccess(['memory.view', 'memory.edit'], { read: true, use: true, manage: false }), { view: true, edit: true })
})

test('graph groups are stable, bounded to the current page, and reflect forget', async () => {
  const { groupMemories } = await loadMemoryView()
  const a = { memory_id: 'a', kind: 'fact', tags: ['日常', '日常', '工作'] }
  const b = { memory_id: 'b', kind: 'fact', tags: ['日常'] }
  const c = { memory_id: 'c', kind: 'event', tags: [] }
  const groups = items => Object.fromEntries(groupMemories(items, 'tag').map(g => [g.label, g.items.map(item => item.memory_id)]))
  assert.deepEqual(groups([c, b, a]), { 工作: ['a'], 日常: ['a', 'b'], 未标记: ['c'] })
  assert.deepEqual(groups([b, c]), { 日常: ['b'], 未标记: ['c'] })
  assert.deepEqual(groupMemories([a, b], 'kind').map(g => [g.label, g.items.length]), [['事实', 2]])
})

test('scope filtering distinguishes legacy default records, private roles and shared records', async () => {
  const { matchesMemoryScope } = await loadMemoryView()
  const items = [{ memory_id: 'a' }, { memory_id: 'b', persona_id: 'p1' }, { memory_id: 'c', is_shared: true }]
  const matching = scope => items.filter(record => matchesMemoryScope(record, scope)).map(record => record.memory_id)
  assert.deepEqual(matching('all'), ['a', 'b', 'c'])
  assert.deepEqual(matching('shared'), ['c'])
  assert.deepEqual(matching('default'), ['a'])
  assert.deepEqual(matching('p1'), ['b'])
})
test('expired authentication keeps only a memory locator and valid version for login', async () => {
  const { memoryLoginHash } = await loadMemoryView()
  assert.equal(memoryLoginHash('#/memory?memory=mem_1a2b&version=3&token=excluded'), '#/login?memory=mem_1a2b&version=3')
  assert.equal(memoryLoginHash('#/memory?memory=https://example.invalid'), '#/login')
  assert.equal(memoryLoginHash('#/chat?memory=mem_1a2b'), undefined)
})
