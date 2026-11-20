import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const view = readFileSync(new URL('../src/views/SkillsView.vue', import.meta.url), 'utf8')

test('个人和内置技能分开浏览，内置正文按需查看', () => {
  assert.match(view, /aria-label="技能分类"[\s\S]*?个人技能[\s\S]*?内置技能/)
  assert.match(view, /v-if="category === 'personal'"[\s\S]*?v-for="skill in skills"[\s\S]*?v-for="template in templates"/)
  assert.match(view, /\/api\/skills\/templates\/\$\{key\}/)
  assert.match(view, /启用技能/)
  assert.doesNotMatch(view, /导入为候选|导入并激活|示例技能模板/)
})

test('技能详情显示来源和作者，以安全 Markdown 渲染正文', () => {
  assert.match(view, /renderMarkdown/)
  assert.match(view, /selectedTemplate\.author/)
  assert.match(view, /selectedTemplate\.source_published_at/)
  assert.match(view, /selectedTemplate\.source_url/)
  assert.match(view, /selectedTemplate\.commit/)
  assert.match(view, /selectedTemplate\.license/)
  assert.match(view, /selectedTemplate\.dependencies/)
  assert.match(view, /selectedTemplate\.resources/)
})

test('通过原生弹窗选版本，以持久化版本内容比较并保留历史激活入口', () => {
  assert.match(view, /<dialog[\s\S]*?对比版本[\s\S]*?历史版本[\s\S]*?当前版本[\s\S]*?<\/dialog>/)
  assert.match(view, /\.showModal\(\)/)
  assert.match(view, /\/versions\/\$\{versionId\}/)
  assert.match(view, /activate\(comparisonVersion\.version_id\)/)
})
