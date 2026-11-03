// 用户与角色管理 API

import request from './request'

// ── 类型定义 ──

export interface User {
  id: number
  username: string
  role: string
  status: number  // 后端 users.status 为 TINYINT：1=启用 0=禁用
  permissions?: string[]
  created_at?: string
}

export interface Role {
  id: number
  name: string
  display_name?: string
  description?: string
  permissions: string[]
  hermes_tools?: string[]
  is_system?: boolean
  created_at?: string
}

// ── 用户管理 ──

/**
 * 获取用户列表
 */
export async function getUsers(): Promise<User[]> {
  const response = await request.get<User[]>('/api/admin/users')
  return response.data
}

/**
 * 更新用户角色
 */
export async function updateUserRole(userId: number, role: string): Promise<void> {
  await request.put(`/api/admin/users/${userId}/role`, { role })
}

/**
 * 更新用户状态
 */
export async function updateUserStatus(userId: number, status: number): Promise<void> {
  await request.put(`/api/admin/users/${userId}/status`, { status })
}

// ── 权限管理 ──

/**
 * 获取权限分组树
 * 返回: [{ group_name, group_label, permissions: [{ key, label, description }] }]
 */
export async function getPermissionTree(): Promise<any[]> {
  const response = await request.get<any[]>('/api/admin/permissions')
  return response.data
}

// ── Toolset 定义 ──

export interface ToolsetDef {
  key: string
  label: string
  desc: string
  group: string
}

/**
 * 获取全部 toolset 定义（角色管理「AI 对话工具」选项，后端单一数据源）
 */
export async function getToolsetDefinitions(): Promise<ToolsetDef[]> {
  const response = await request.get<ToolsetDef[]>('/api/admin/toolsets')
  return response.data
}

// ── 角色管理 ──

/**
 * 获取角色列表（含权限 + hermes_tools）
 */
export async function getRoles(): Promise<Role[]> {
  const response = await request.get<Role[]>('/api/admin/roles')
  return response.data
}

/**
 * 创建角色
 */
export async function createRole(data: {
  name: string
  display_name: string
  description?: string
  permissions?: string[]
  hermes_tools?: string[]
}): Promise<any> {
  const response = await request.post('/api/admin/roles', data)
  return response.data
}

/**
 * 更新角色
 */
export async function updateRole(roleId: number, data: {
  name?: string
  display_name?: string
  description?: string
  permissions?: string[]
  hermes_tools?: string[]
}): Promise<any> {
  const response = await request.put(`/api/admin/roles/${roleId}`, data)
  return response.data
}

/**
 * 删除角色
 */
export async function deleteRole(roleId: number): Promise<void> {
  await request.delete(`/api/admin/roles/${roleId}`)
}

// ── 技能池审核 ──

/**
 * 获取待审核的技能池项目
 */
export async function getPendingPoolItems(type?: string): Promise<any[]> {
  const params: any = {}
  if (type) params.type = type
  const response = await request.get<any[]>('/api/admin/pool/pending', { params })
  return response.data
}

/**
 * 审核通过
 */
export async function approvePoolItem(id: number): Promise<any> {
  const response = await request.post(`/api/admin/pool/${id}/approve`)
  return response.data
}

/**
 * 审核拒绝
 */
export async function rejectPoolItem(id: number, comment: string): Promise<any> {
  const response = await request.post(`/api/admin/pool/${id}/reject`, { comment })
  return response.data
}

/**
 * 管理员强制发布内容
 */
export async function forcePublish(data: {
  content_type: string
  content_name: string
  owner_id: number
}): Promise<any> {
  const response = await request.post('/api/admin/pool/force-publish', data)
  return response.data
}

/**
 * 从池中移除内容
 */
export async function removeFromPool(name: string): Promise<any> {
  const response = await request.delete(`/api/admin/pool/${name}`)
  return response.data
}

// ── 数据层级（部门）管理 ──

export interface DataLayer {
  id: number
  name: string
  description?: string
  sort_order?: number
  is_system?: number
  kb_count?: number
  user_count?: number
  created_at?: string
}

/**
 * 获取所有数据层级
 */
export async function getDataLayers(): Promise<DataLayer[]> {
  const response = await request.get<{ ok: boolean; data: DataLayer[] }>('/api/data-layers')
  return response.data.data || []
}

/**
 * 创建数据层级
 */
export async function createDataLayer(data: { name: string; description?: string; sort_order?: number }): Promise<any> {
  const response = await request.post('/api/data-layers', data)
  return response.data
}

/**
 * 更新数据层级
 */
export async function updateDataLayer(id: number, data: { name?: string; description?: string; sort_order?: number }): Promise<any> {
  const response = await request.put(`/api/data-layers/${id}`, data)
  return response.data
}

/**
 * 删除数据层级
 */
export async function deleteDataLayer(id: number): Promise<any> {
  const response = await request.delete(`/api/data-layers/${id}`)
  return response.data
}

/**
 * 获取用户的数据层级
 */
export async function getUserDataLayers(userId: number): Promise<number[]> {
  const response = await request.get<{ ok: boolean; layer_ids: number[] }>(`/api/data-layers/user/${userId}`)
  return response.data.layer_ids || []
}

/**
 * 设置用户的数据层级
 */
export async function setUserDataLayers(userId: number, layerIds: number[]): Promise<any> {
  const response = await request.put(`/api/data-layers/user/${userId}`, { layer_ids: layerIds })
  return response.data
}

/**
 * 获取知识库的数据层级
 */
export async function getKbDataLayers(kbId: number): Promise<number[]> {
  const response = await request.get<{ ok: boolean; layer_ids: number[] }>(`/api/data-layers/kb/${kbId}`)
  return response.data.layer_ids || []
}

/**
 * 设置知识库的数据层级
 */
export async function setKbDataLayers(kbId: number, layerIds: number[]): Promise<any> {
  const response = await request.put(`/api/data-layers/kb/${kbId}`, { layer_ids: layerIds })
  return response.data
}
