// 权限整改 P2 新增 API：capabilities、有效权限明细、模板升级预览/应用
import request from './request'

export interface ModuleCapability {
  label: string
  enabled: boolean
  read: boolean
  use: boolean
  manage: boolean
}

export interface UserCapabilities {
  modules: Record<string, ModuleCapability>
  tools: string[]
  super_admin: boolean
  permissions: string[]
}

export async function getMyCapabilities(): Promise<UserCapabilities> {
  const res = await request.get<{ capabilities: UserCapabilities }>('/api/auth/capabilities')
  return res.data.capabilities
}

export interface EffectivePermItem {
  permission: string
  from_role: boolean
  override: '' | 'grant' | 'revoke'
  effective: boolean
}

export interface UserEffectiveDetail {
  user_id: number
  role: string
  super_admin: boolean
  permissions: EffectivePermItem[]
  effective_permissions: string[]
}

export async function getUserEffectivePerms(userId: number): Promise<UserEffectiveDetail> {
  const res = await request.get<UserEffectiveDetail>(`/api/admin/users/${userId}/effective-perms`)
  return res.data
}

export interface UpgradePreviewRole {
  role: string
  template_version: string
  pending: boolean
  missing_from_role: string[]
  not_in_template: string[]
  high_risk_missing: string[]
  toolsets_in_db: string[]
  toolsets_in_template: string[]
}

export interface UpgradePreview {
  current_template_version: string
  roles: UpgradePreviewRole[]
}

export async function getPermissionUpgradePreview(): Promise<UpgradePreview> {
  const res = await request.get<UpgradePreview>('/api/admin/permission-upgrade-preview')
  return res.data
}

export async function applyRoleTemplate(roleName: string): Promise<{ previous_permissions: string[] }> {
  const res = await request.post(`/api/admin/roles/${roleName}/apply-template`)
  return res.data
}
