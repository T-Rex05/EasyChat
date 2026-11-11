import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { computed, reactive, ref } from 'vue'
import ts from 'typescript'

const ledgerUse = ['ledger.view', 'ledger.import', 'ledger.edit', 'ledger.export', 'file.upload', 'file.read']

async function openRole(permissions) {
  const source = readFileSync(new URL('../src/views/admin/RoleEditDialog.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const { outputText } = ts.transpileModule(script, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  })
  let mounted
  let saved
  let unmounted
  const listeners = []
  const emitted = []
  const bindings = {
    ref, reactive, computed,
    defineProps: () => ({ role: { id: 42, name: 'member', display_name: '成员', permissions } }),
    defineEmits: () => (...a) => { emitted.push(a) }, onMounted: callback => { mounted = callback }, alert() {},
    onUnmounted: callback => { unmounted = callback },
    window: {
      addEventListener: (name, fn) => listeners.push([name, fn]),
      removeEventListener: (name, fn) => { const i = listeners.findIndex(l => l[0] === name && l[1] === fn); if (i >= 0) listeners.splice(i, 1) },
    },
    AdminAPI: {
      async getPermissionDefinitions() { return [] },
      async getToolsetDefinitions() { return [] },
      async updateRole(id, payload) { saved = structuredClone({ id, ...payload, permissions: [...payload.permissions] }) },
    },
  }
  const dialog = new Function(...Object.keys(bindings), `${outputText}\nreturn { form, moduleRows, detectMode, onModeChange, onAtomToggle, save, onKeydown }`)(...Object.values(bindings))
  await mounted()
  return { ...dialog, saved: () => saved, emitted: () => emitted, listeners, runUnmount: () => unmounted && unmounted() }
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

test('ledger use with shared file dependencies survives loading and saving', async () => {
  const dialog = await openRole([...ledgerUse, 'file.delete'])
  assert.equal(dialog.form.moduleModes.ledger, 'use')
  await dialog.save()
  assert.deepEqual(dialog.saved().permissions, [...ledgerUse, 'file.delete'])
})

test('incomplete ledger use remains custom when a required file dependency is absent', async () => {
  for (const missing of ['file.upload', 'file.read', 'ledger.export']) {
    const dialog = await openRole(ledgerUse.filter(permission => permission !== missing))
    assert.equal(dialog.form.moduleModes.ledger, 'custom', missing)
  }
})

test('lowering ledger access preserves shared chat and explicitly granted file permissions', async () => {
  for (const chat of [[], ['chat.use']]) {
    for (const mode of ['read', 'off']) {
      const dialog = await openRole([...ledgerUse, ...chat, 'file.delete', 'memory.view'])
      dialog.form.moduleModes.ledger = mode
      dialog.onModeChange('ledger')
      assert.deepEqual(dialog.form.permissions.filter(permission => permission.startsWith('ledger.')), mode === 'read' ? ['ledger.view'] : [])
      for (const permission of ['file.upload', 'file.read', 'file.delete', 'memory.view', ...chat]) {
        assert.ok(dialog.form.permissions.includes(permission), `${mode} must preserve ${permission}`)
      }
      await dialog.save()
      assert.ok(dialog.saved().permissions.includes('file.upload'))
    }
  }
})

test('selecting ledger use adds its existing dependencies without unrelated grants', async () => {
  const dialog = await openRole([])
  dialog.form.moduleModes.ledger = 'use'
  dialog.onModeChange('ledger')
  assert.deepEqual(dialog.form.permissions, ledgerUse)
  dialog.onAtomToggle('file.read')
  assert.equal(dialog.form.moduleModes.ledger, 'use')
})

test('selecting ledger read does not add file or chat permissions', async () => {
  const dialog = await openRole([])
  dialog.form.moduleModes.ledger = 'read'
  dialog.onModeChange('ledger')
  assert.deepEqual(dialog.form.permissions, ['ledger.view'])
})
