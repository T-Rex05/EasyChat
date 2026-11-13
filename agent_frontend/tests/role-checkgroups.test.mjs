// P6 回归：编辑角色恢复"分组原子权限复选框"主 UI。
// 行为断言走 permissionGroups 依赖规则纯函数；主区形态走源码结构断言。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

async function loadUtility(name) {
  const source = readFileSync(new URL(`../src/utils/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}

const DEFS = [
  { key: 'chat.use', label: '对话', group_name: 'chat', lifecycle: 'active', depends: [] },
  { key: 'ledger.import', label: '导入账单', group_name: 'ledger', lifecycle: 'active', depends: ['file.upload'] },
  { key: 'ledger.export', label: '导出账单', group_name: 'ledger', lifecycle: 'active', depends: ['file.read'] },
  { key: 'trace.manage', label: '全局用量', group_name: 'trace', lifecycle: 'active', depends: [] },
  { key: 'file.upload', label: '上传文件', group_name: 'file', lifecycle: 'active', internal: true, depends: [] },
  { key: 'file.read', label: '读取文件', group_name: 'file', lifecycle: 'active', internal: true, depends: [] },
  { key: 'old.retired', label: '退役项', lifecycle: 'deprecated', depends: [] },
]

test('可见原子权限：internal 与 deprecated 不直接呈现（内部依赖随动作显示）', async () => {
  const { visiblePermissions } = await loadUtility('permissionGroups')
  const keys = visiblePermissions(DEFS).map((d) => d.key)
  assert.deepEqual(keys, ['chat.use', 'ledger.import', 'ledger.export', 'trace.manage'])
})

test('新勾选 ledger.import 只附加后端定义的 file.upload 依赖', async () => {
  const { permsAfterCheck } = await loadUtility('permissionGroups')
  const next = permsAfterCheck(['chat.use'], 'ledger.import', DEFS)
  assert.deepEqual(next.sort(), ['chat.use', 'file.upload', 'ledger.import'].sort())
})

test('新勾选 ledger.export 只附加 file.read 依赖', async () => {
  const { permsAfterCheck } = await loadUtility('permissionGroups')
  const next = permsAfterCheck([], 'ledger.export', DEFS)
  assert.deepEqual(next.sort(), ['file.read', 'ledger.export'].sort())
})

test('勾选无依赖项（trace.manage）不扩大为其他授权', async () => {
  const { permsAfterCheck } = await loadUtility('permissionGroups')
  assert.deepEqual(permsAfterCheck([], 'trace.manage', DEFS), ['trace.manage'])
})

test('取消 ledger.import 仅移除自身，保留共享 file.upload', async () => {
  const { permsAfterUncheck } = await loadUtility('permissionGroups')
  const current = ['ledger.import', 'ledger.export', 'file.upload', 'file.read']
  const next = permsAfterUncheck(current, 'ledger.import', DEFS)
  assert.deepEqual(next.sort(), ['ledger.export', 'file.upload', 'file.read'].sort())
  // 再取消 ledger.export：file.read 失去引用来源——仍按"取消不删共享权限"，
  // 内部项由用户显式取消（与后端不强推的历史行为一致）
  const after = permsAfterUncheck(next, 'ledger.export', DEFS)
  assert.deepEqual(after.sort(), ['file.upload', 'file.read'].sort())
})

test('内部依赖项可被显式取消（独立勾选历史配置原样回显）', async () => {
  const { permsAfterUncheck } = await loadUtility('permissionGroups')
  const next = permsAfterUncheck(['ledger.export', 'file.read'], 'file.read', DEFS)
  assert.deepEqual(next, ['ledger.export'])
})

test('重复勾选幂等，不产生重复键', async () => {
  const { permsAfterCheck } = await loadUtility('permissionGroups')
  const next = permsAfterCheck(['ledger.import', 'file.upload'], 'ledger.import', DEFS)
  assert.deepEqual(next.filter((k) => k === 'file.upload').length, 1)
  assert.deepEqual(next.filter((k) => k === 'ledger.import').length, 1)
})

test('结构：主编辑区为分组复选框，模式下拉不再是唯一真值来源', () => {
  const dialog = readFileSync(new URL('../src/views/admin/RoleEditDialog.vue', import.meta.url), 'utf8')
  // 主区出现按分组的原子权限复选框（v-model form.permissions 逐项）
  assert.match(dialog, /groupPermissions/)
  assert.match(dialog, /type="checkbox"[\s\S]{0,120}form\.permissions/)
  // 旧"模块模式互斥下拉"不再是权限真值：即使保留也应退出主区
  const moduleRowsBlock = /v-for="row in moduleRows"[\s\S]*?mode-select/.exec(dialog)
  if (moduleRowsBlock) {
    // 若仍渲染 mode-select，必须限定在高级/兼容折叠区内
    assert.ok(
      dialog.indexOf('mode-select') > dialog.indexOf('showAdvanced'),
      '模式预设只能留在高级折叠区，不能作为主编辑区',
    )
  }
  // 依赖提示与定义加载失败保留策略
  assert.match(dialog, /file\.upload|依赖/)
})
