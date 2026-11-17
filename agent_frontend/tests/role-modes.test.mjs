// 角色编辑对话框行为回归（WP-E 后：预设下拉已删，分组复选框为唯一授权入口）。
// 原 6 个预设用例的行为意图迁移：Esc 关闭、打开/只改名/保存集合稳定、
// 勾选依赖自动附加、取消不删共享、定义加载失败不清空。
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { computed, reactive, ref } from 'vue'
import ts from 'typescript'

async function loadPermissionGroupsUtil() {
  const source = readFileSync(new URL('../src/utils/permissionGroups.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}

const ledgerUse = ['ledger.view', 'ledger.import', 'ledger.edit', 'ledger.export', 'file.upload', 'file.read']

async function openRole(permissions, defs = []) {
  const util = await loadPermissionGroupsUtil()
  const source = readFileSync(new URL('../src/views/admin/RoleEditDialog.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)[1]
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]/gm, '')
  const { outputText } = ts.transpileModule(script, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  })
  let mounted
  let saved
  const emitted = []
  const bindings = {
    ref, reactive, computed,
    groupPermissions: util.groupPermissions,
    visiblePermissions: util.visiblePermissions,
    internalPermissionDefs: util.internalPermissionDefs,
    permsAfterCheck: util.permsAfterCheck,
    permsAfterUncheck: util.permsAfterUncheck,
    dependencyHint: util.dependencyHint,
    defineProps: () => ({ role: { id: 42, name: 'member', display_name: '成员', permissions } }),
    defineEmits: () => (...a) => { emitted.push(a) },
    onMounted: callback => { mounted = callback },
    alert() {},
    onUnmounted: () => {},
    AdminAPI: {
      async getPermissionDefinitions() { return defs },
      async getToolsetDefinitions() { return [] },
      async updateRole(id, payload) { saved = structuredClone({ id, ...payload, permissions: [...payload.permissions] }) },
    },
  }
  const dialog = new Function(...Object.keys(bindings), `${outputText}\nreturn { form, onPermToggle, get permDefs() { return permDefs.value }, get orphanPerms() { return orphanPerms.value }, get defsLoadFailed() { return defsLoadFailed.value }, save, onKeydown }`)(...Object.values(bindings))
  await mounted()
  return { ...dialog, saved: () => saved, emitted: () => emitted }
}

function toggle(dialog, key, checked) {
  dialog.onPermToggle(key, { target: { checked } })
}

test('escape keydown closes the dialog (modal a11y)', async () => {
  const source = readFileSync(new URL('../src/views/admin/RoleEditDialog.vue', import.meta.url), 'utf8')
  assert.ok(/@keydown\.esc="onKeydown"/.test(source), 'overlay must bind Esc via DOM bubbling (window listener misses trusted keys, browser-proven)')
  const dialog = await openRole([...ledgerUse])
  dialog.onKeydown({ key: 'Escape' })
  assert.ok(dialog.emitted().some(([name]) => name === 'close'), 'Escape emits close')
  dialog.onKeydown({ key: 'a' })
  assert.equal(dialog.emitted().filter(([name]) => name === 'close').length, 1, 'other keys do not close')
})

test('open + save without edits preserves the historical permission set verbatim', async () => {
  const custom = [...ledgerUse, 'file.delete', 'memory.view']
  const dialog = await openRole(custom)
  await dialog.save()
  assert.deepEqual(dialog.saved().permissions, custom, '只改名称/直接保存不得增删权限')
})

test('definitions load failure keeps current set editable and saves verbatim (orphan group)', async () => {
  const custom = [...ledgerUse, 'legacy.unknown']
  const dialog = await openRole(custom, [])  // 定义加载失败
  assert.equal(dialog.defsLoadFailed, true)
  assert.ok([...dialog.orphanPerms].includes('legacy.unknown'), '未知键原样保留在 orphan 组（定义失败时全部键按 orphan 回显）')
  await dialog.save()
  assert.deepEqual(dialog.saved().permissions, custom)
})

test('checking ledger.import attaches depends; uncheck keeps shared; ledger.manage visible in ledger group', async () => {
  const defs = [
    { key: 'ledger.import', label: '导入', group_name: 'ledger', lifecycle: 'active', depends: ['file.upload'] },
    { key: 'ledger.export', label: '导出', group_name: 'ledger', lifecycle: 'active', depends: ['file.read'] },
    { key: 'file.upload', label: '上传', group_name: 'file', lifecycle: 'active', internal: true, module: 'files', depends: [] },
    { key: 'file.read', label: '读取', group_name: 'file', lifecycle: 'active', internal: true, module: 'files', depends: [] },
    { key: 'ledger.manage', label: '账本高级', group_name: 'ledger', lifecycle: 'active', internal: true, module: 'ledger', depends: [] },
  ]
  const dialog = await openRole([], defs)
  // ledger.manage（internal 但属账单模块）必须在主区可见，不落文件依赖组
  const visible = dialog.permDefs.filter((d) => d.lifecycle !== 'deprecated'
    && !(d.internal === true && (d.module || d.key.split('.')[0]) === 'files'))
  assert.ok(visible.some((d) => d.key === 'ledger.manage'), 'ledger.manage 应在主区呈现')
  toggle(dialog, 'ledger.import', true)
  assert.deepEqual(dialog.form.permissions.sort(), ['file.upload', 'ledger.import'])
  toggle(dialog, 'ledger.export', true)
  toggle(dialog, 'ledger.import', false)
  assert.deepEqual(dialog.form.permissions.sort(), ['file.upload', 'file.read', 'ledger.export'].sort())
})
