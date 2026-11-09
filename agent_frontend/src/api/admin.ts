// 用户与角色管理 API

import request from './request'
import { groupPermissions, type PermissionGroup, type PermissionItem } from '@/utils/permissionGroups'

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
export interface PermissionDefinition {
  key: string
  label: string
  description: string
  group_name: string
  group_label: string
  sort_order: number
  lifecycle: string
  module?: string
  op?: string
  depends?: string[]
  risk?: string
  scope?: string
  internal?: boolean
}

export async function getPermissionDefinitions(): Promise<PermissionDefinition[]> {
  const response = await request.get<PermissionDefinition[]>('/api/admin/permissions')
  return response.data
}

export async function getPermissionTree(): Promise<PermissionGroup[]> {
  const response = await request.get<(PermissionItem | PermissionGroup)[]>('/api/admin/permissions')
  return groupPermissions(response.data)
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
  const response = await request.get<(ToolsetDef & { description?: string })[]>('/api/admin/toolsets')
  return response.data.map(tool => ({
    ...tool,
    desc: tool.desc || tool.description || '',
    group: tool.group || 'hermes',
  }))
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

