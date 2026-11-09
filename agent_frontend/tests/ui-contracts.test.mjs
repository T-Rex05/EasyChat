import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

async function loadUtility(name) {
  const source = readFileSync(new URL(`../src/utils/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}

test('flat permissions become renderable groups without losing registered keys', async () => {
  const { groupPermissions } = await loadUtility('permissionGroups')
  const groups = groupPermissions([
    { key: 'chat.use', label: '对话', group_name: 'chat', group_label: '对话' },
    { key: 'superagent.view', label: '查看任务', group_name: 'superagent', group_label: '编码' },
  ])
  assert.deepEqual(groups.flatMap(group => group.permissions.map(permission => permission.key)),
    ['chat.use', 'superagent.view'])
  assert.equal(groups[0].group_name, 'chat')
})

test('grouped legacy permissions remain compatible', async () => {
  const { groupPermissions } = await loadUtility('permissionGroups')
  const input = [{ group_name: 'chat', group_label: '对话', permissions: [{ key: 'chat.use', label: '对话' }] }]
  assert.deepEqual(groupPermissions(input), input)
})

test('saved panel widths handle invalid storage and stay within limits', async () => {
  const { clampPanelWidth } = await loadUtility('panelWidth')
  assert.equal(clampPanelWidth(NaN, 240, 180, 360), 240)
  assert.equal(clampPanelWidth(100, 240, 180, 360), 180)
  assert.equal(clampPanelWidth(900, 240, 180, 360), 360)
})

test('report downloads use the authenticated request client and release the blob URL', async () => {
  const source = readFileSync(new URL('../src/utils/downloadFile.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source.replace(/^import .*$/gm, '').replace('export async', 'async'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  })
  const calls = []
  const link = { click() { calls.push('click') }, remove() { calls.push('remove') } }
  const request = { async get(path, options) { calls.push([path, options]); return { data: 'blob' } } }
  const download = new Function('request', 'URL', 'document', 'window', `${outputText}; return downloadFile`)(
    request,
    { createObjectURL: () => 'blob:test', revokeObjectURL: url => calls.push(url) },
    { createElement: () => link, body: { appendChild() {} } },
    { setTimeout: callback => callback() },
  )
  await download('file id', '报告.csv')
  assert.deepEqual(calls[0], ['/api/files/file%20id/content', { responseType: 'blob' }])
  assert.equal(link.download, '报告.csv')
  assert.deepEqual(calls.slice(1), ['click', 'remove', 'blob:test'])
})
