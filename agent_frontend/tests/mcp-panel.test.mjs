// P4 结构回归：MCP 配置面板接线与凭据纪律。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const panel = readFileSync(new URL('../src/components/config/McpSettingsPanel.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/mcp.ts', import.meta.url), 'utf8')
const configView = readFileSync(new URL('../src/views/ConfigView.vue', import.meta.url), 'utf8')

test('面板走真实配置 API（列表/创建/更新/启停/测试/健康）', () => {
  for (const path of ['/api/mcp/servers', '/enable', '/test', '/api/mcp/health']) {
    assert.ok(api.includes(path), path)
  }
})

test('凭据只写不读：输入框 password、无 GET 回显；留空保留/显式清除', () => {
  assert.match(panel, /type="password"/)
  assert.match(panel, /autocomplete="new-password"/)
  assert.match(panel, /留空=保留现有/)
  assert.match(panel, /clear_credential/)
  assert.doesNotMatch(api, /credential.*GET|get.*credential/i)
})

test('fail-closed 启用：启用前先测试连接，未通过保持停用', () => {
  assert.match(panel, /未通过连接测试[\s\S]*保持停用/)
  assert.match(panel, /await api\.testServer\(s\.id\)/)
})

test('ConfigView 出现 MCP Tab 且受 system.config 控制', () => {
  assert.match(configView, /key: 'mcp'[\s\S]{0,60}system\.config/)
  assert.match(configView, /McpSettingsPanel/)
})

test('受众两档可显式选择', () => {
  assert.match(panel, /config_admin/)
  assert.match(panel, /value="all"/)
  assert.match(panel, /仅系统配置者|所有登录用户/)
})
