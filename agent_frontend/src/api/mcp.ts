// MCP 配置 API（P4）。凭据只写不读：响应仅 credential_set。
import request from './request'

export interface McpServer {
  id: string
  name: string
  url: string
  credential_set: boolean
  allowed_tools: string[]
  excluded_tools: string[]
  connect_timeout_s: number
  call_timeout_s: number
  audience: 'config_admin' | 'all'
  enabled: boolean
  last_check_state: string
  last_check_error: string
  last_check_tools: string[]
  last_checked_at: string
}

export interface McpTestResult {
  ok: boolean
  state: string
  tools: string[]
  truncated: boolean
  error_kind: string
  error_message: string
}

export interface McpDraft {
  name: string
  url: string
  credential?: string
  clear_credential?: boolean
  allowed_tools?: string[]
  excluded_tools?: string[]
  connect_timeout_s?: number
  call_timeout_s?: number
  audience?: string
  enabled?: boolean
}

export async function listServers(): Promise<McpServer[]> {
  const res = await request.get<{ servers: McpServer[] }>('/api/mcp/servers')
  return res.data.servers
}

export async function createServer(draft: McpDraft): Promise<McpServer> {
  const res = await request.post<{ server: McpServer }>('/api/mcp/servers', draft)
  return res.data.server
}

export async function updateServer(id: string, draft: Partial<McpDraft>): Promise<McpServer> {
  const res = await request.put<{ server: McpServer }>(`/api/mcp/servers/${id}`, draft)
  return res.data.server
}

export async function deleteServer(id: string): Promise<void> {
  await request.delete(`/api/mcp/servers/${id}`)
}

export async function setEnabled(id: string, enabled: boolean): Promise<McpServer> {
  const res = await request.post<{ server: McpServer }>(`/api/mcp/servers/${id}/enable`, { enabled })
  return res.data.server
}

export async function testServer(id: string): Promise<McpTestResult> {
  const res = await request.post<McpTestResult>(`/api/mcp/servers/${id}/test`, {})
  return res.data
}

export async function getHealth(): Promise<Record<string, any>> {
  const res = await request.get<{ servers: Record<string, any> }>('/api/mcp/health')
  return res.data.servers
}
