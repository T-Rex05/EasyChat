// P2 回归：全局用量并入"用量与排行"单入口。
// 行为断言走 globalUsage 纯逻辑；入口/路由/组件接线走源码结构断言（防回退）。
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

test('筛选切换重置页码到 1', async () => {
  const { onFilterChanged } = await loadUtility('globalUsage')
  assert.deepEqual(onFilterChanged(7), { page: 1, selectedUid: 7 })
})

test('快速切换用户：旧令牌响应判定为过期，新令牌可落数据', async () => {
  const { beginLoad, isStaleResponse } = await loadUtility('globalUsage')
  let token = 0
  const a = beginLoad(token); token = a.nextToken
  const b = beginLoad(token); token = b.nextToken
  // A 请求晚到：requestToken(a) !== 当前 token → 丢弃
  assert.equal(isStaleResponse(token, a.requestToken), true)
  // B 正常返回：应用
  assert.equal(isStaleResponse(token, b.requestToken), false)
})

test('分页真实口径：满页才给下一页，不再展示伪总数', async () => {
  const { canGoNext, GLOBAL_PAGE_SIZE } = await loadUtility('globalUsage')
  assert.equal(canGoNext(GLOBAL_PAGE_SIZE), true)
  assert.equal(canGoNext(GLOBAL_PAGE_SIZE - 1), false)
  assert.equal(canGoNext(0), false)
})

test('本人区 owner 校验：身份未知返回 0（组件必须拒发请求）', async () => {
  const { resolveMyUid } = await loadUtility('globalUsage')
  assert.equal(resolveMyUid(''), 0)
  assert.equal(resolveMyUid(null), 0)
  assert.equal(resolveMyUid('3'), 3)
})

test('结构：单菜单入口 + 旧链接重定向 + 全局区域按 trace.manage 渲染', () => {
  const router = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
  const sidebar = readFileSync(new URL('../src/components/AppSidebar.vue', import.meta.url), 'utf8')
  const usage = readFileSync(new URL('../src/views/UsageView.vue', import.meta.url), 'utf8')

  // /trace/users 不再是独立页面组件，必须是重定向到合并页
  assert.doesNotMatch(router, /path: '\/trace\/users'[\s\S]{0,120}component/)
  assert.match(router, /\/trace\/users[\s\S]{0,160}redirect/)
  // 侧栏只保留一个用量入口：全局项已移除
  assert.doesNotMatch(sidebar, /traceUsers/)
  assert.doesNotMatch(sidebar, /\/trace\/users/)
  // 合并页嵌入全局区域且仅 manage 可见；本人区显式 owner_id 且等待身份就绪
  assert.match(usage, /UserUsageView/)
  assert.match(usage, /trace.*manage|canManageGlobal/)
  assert.match(usage, /owner_id/)
  assert.match(usage, /ready/)
})
