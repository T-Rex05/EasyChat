export interface PermissionItem {
  key: string
  label: string
  group_name?: string
  group_label?: string
  description?: string
  risk?: string
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

// ---- P6 分组原子复选框的依赖规则（后端 catalog depends 为唯一来源） --------

export interface PermissionDef extends PermissionItem {
  depends?: string[]
  internal?: boolean
  lifecycle?: string
  description?: string
  risk?: string
}

/**
 * 主编辑区应呈现的原子权限：仅 active 且非 internal（文件依赖随动作自动
 * 勾选并单独成组展示）。deprecated/退役项不显示新勾选入口，但历史值在
 * form.permissions 中原样保留、保存不丢。
 */
export function visiblePermissions(defs: PermissionDef[]): PermissionDef[] {
  return defs.filter((d) => d.lifecycle !== 'deprecated' && !d.internal)
}

/** 内部依赖项（file.*）定义，单独成组呈现当前随附状态。 */
export function internalPermissionDefs(defs: PermissionDef[]): PermissionDef[] {
  return defs.filter((d) => d.internal && d.lifecycle !== 'deprecated')
}

/**
 * 新勾选动作项：附加后端已定义的 depends（幂等，不重复、不扩大）。
 * 取消勾选不经过这里（见 permsAfterUncheck）。
 */
export function permsAfterCheck(current: string[], key: string, defs: PermissionDef[]): string[] {
  const next = new Set(current)
  next.add(key)
  const def = defs.find((d) => d.key === key)
  for (const dep of def?.depends || []) next.add(dep)
  return [...next]
}

/** 取消动作：仅移除所选项自身；共享/内部依赖权保留（由用户显式取消）。 */
export function permsAfterUncheck(current: string[], key: string, _defs?: PermissionDef[]): string[] {
  return current.filter((k) => k !== key)
}

/** 勾选某动作时会被自动附带的依赖（提示文案用）。 */
export function dependencyHint(key: string, defs: PermissionDef[]): string[] {
  return defs.find((d) => d.key === key)?.depends || []
}
