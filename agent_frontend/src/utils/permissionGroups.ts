export interface PermissionItem {
  key: string
  label: string
  group_name?: string
  group_label?: string
}

export interface PermissionGroup {
  group_name: string
  group_label: string
  permissions: PermissionItem[]
}

// 新接口返回平铺定义，兼容历史分组接口，在 HTTP 边界统一视图结构。
export function groupPermissions(items: (PermissionItem | PermissionGroup)[]): PermissionGroup[] {
  const groups = new Map<string, PermissionGroup>()
  for (const item of items) {
    if ('permissions' in item) {
      groups.set(item.group_name, item)
      continue
    }
    const name = item.group_name || item.key.split('.')[0]
    if (!groups.has(name)) {
      groups.set(name, { group_name: name, group_label: item.group_label || name, permissions: [] })
    }
    groups.get(name)!.permissions.push(item)
  }
  return [...groups.values()]
}
