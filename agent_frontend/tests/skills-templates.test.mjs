// P3 结构回归：技能页模板面板接线（目录、双动作、来源固定版本与依赖展示）。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const view = readFileSync(new URL('../src/views/SkillsView.vue', import.meta.url), 'utf8')

test('技能页出现模板面板并读取真实目录端点', () => {
  assert.match(view, /\/api\/skills\/templates/)
  assert.match(view, /示例技能模板/)
})

test('导入与激活是两个显式动作（导入≠默认激活）', () => {
  assert.match(view, /导入为候选/)
  assert.match(view, /导入并激活/)
  assert.match(view, /importTemplate\(tpl, false\)/)
  assert.match(view, /importTemplate\(tpl, true\)/)
})

test('卡片展示来源、固定 commit、许可、依赖与资源状态', () => {
  assert.match(view, /tpl\.origin/)
  assert.match(view, /tpl\.commit/)
  assert.match(view, /tpl\.license/)
  assert.match(view, /tpl\.dependencies/)
  assert.match(view, /tpl\.resources/)
})

test('模板目录失败不影响技能主流程', () => {
  // loadTemplates 的 catch 不设置 error banner，只置空面板数据
  const fn = /async function loadTemplates[\s\S]*?\n}/.exec(view)?.[0] || ''
  assert.match(fn, /templates\.value = \[\]/)
  assert.doesNotMatch(fn, /error\.value =/)
})
