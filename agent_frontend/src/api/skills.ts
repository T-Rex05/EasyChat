// 技能 API

import request from './request'

export interface Skill {
  name: string
  description: string  // 后端 get_skill 恒返回字符串（frontmatter 缺失时默认 ''）
  content: string
  body?: string
  author?: string
  version?: string
  category?: string
  enabled?: boolean
  status?: string
  locked?: boolean
  owner_id?: number
  owner_name?: string
  frontmatter?: Record<string, any>  // 后端 get_skill 返回解析后的 frontmatter 字典
  created_at?: string
}

/**
 * 获取技能列表（分组：my_skills / pool_skills / all_skills?）
 */
export async function listSkills(): Promise<any> {
  const response = await request.get('/api/skills')
  return response.data
}

/**
 * 获取技能详情
 */
export async function getSkill(name: string): Promise<Skill> {
  const response = await request.get<Skill>(`/api/skills/${encodeURIComponent(name)}`)
  return response.data
}

/**
 * 创建技能
 */
export async function createSkill(data: Partial<Skill>): Promise<Skill> {
  const response = await request.post<Skill>('/api/skills', data)
  return response.data
}

/**
 * 更新技能
 */
export async function updateSkill(name: string, content: string, category?: string, description?: string): Promise<Skill> {
  const body: Record<string, string> = { content }
  if (category !== undefined) body.category = category
  if (description !== undefined) body.description = description
  const response = await request.put<Skill>(`/api/skills/${encodeURIComponent(name)}`, body)
  return response.data
}

/**
 * 获取分类列表
 */
export async function listCategories(): Promise<string[]> {
  const response = await request.get<string[]>('/api/skills/categories')
  return response.data
}

/**
 * 创建分类
 */
export async function createCategory(name: string): Promise<{ name: string }> {
  const response = await request.post<{ name: string }>('/api/skills/categories', { name })
  return response.data
}

/**
 * 重命名分类
 */
export async function renameCategory(name: string, newName: string): Promise<{ old_name: string; new_name: string }> {
  const response = await request.put<{ old_name: string; new_name: string }>(`/api/skills/categories/${encodeURIComponent(name)}/rename`, { new_name: newName })
  return response.data
}

/**
 * 删除分类
 */
export async function deleteCategory(name: string): Promise<{ deleted: boolean }> {
  const response = await request.delete<{ deleted: boolean }>(`/api/skills/categories/${encodeURIComponent(name)}`)
  return response.data
}

/**
 * 删除技能
 */
export async function deleteSkill(name: string): Promise<void> {
  await request.delete(`/api/skills/${encodeURIComponent(name)}`)
}

/**
 * 锁定技能
 */
export async function lockSkill(name: string): Promise<{ locked: boolean }> {
  const response = await request.put<{ locked: boolean }>(`/api/skills/${encodeURIComponent(name)}/lock`)
  return response.data
}

/**
 * 解锁技能
 */
export async function unlockSkill(name: string): Promise<{ locked: boolean }> {
  const response = await request.put<{ locked: boolean }>(`/api/skills/${encodeURIComponent(name)}/unlock`)
  return response.data
}

/**
 * 发布技能到池
 */
export async function publishToPool(name: string) {
  return (await request.post(`/api/skills/${encodeURIComponent(name)}/publish`)).data
}

/**
 * 获取技能池列表
 */
export async function listPool(): Promise<any[]> {
  return (await request.get('/api/skills/pool')).data
}

/**
 * 从技能池安装
 */
export async function installFromPool(name: string) {
  return (await request.post(`/api/skills/pool/${encodeURIComponent(name)}/install`)).data
}

/**
 * 从技能池卸载
 */
export async function uninstallFromPool(name: string) {
  return (await request.delete(`/api/skills/pool/${encodeURIComponent(name)}/install`)).data
}

// ── 用户自定义分类 ──

/**
 * 获取用户分类列表
 */
export async function listMyCategories(): Promise<string[]> {
  return (await request.get('/api/skills/my-categories')).data
}

/**
 * 创建用户分类
 */
export async function createMyCategory(category: string): Promise<{ category: string }> {
  return (await request.post('/api/skills/my-categories', { category })).data
}

/**
 * 重命名用户分类
 */
export async function renameMyCategory(oldName: string, newName: string): Promise<{ old_name: string; new_name: string }> {
  return (await request.put(`/api/skills/my-categories/${encodeURIComponent(oldName)}/rename`, { new_name: newName })).data
}

/**
 * 删除用户分类
 */
export async function deleteMyCategory(name: string): Promise<{ category: string; deleted: boolean }> {
  return (await request.delete(`/api/skills/my-categories/${encodeURIComponent(name)}`)).data
}

/**
 * 设置技能分类
 */
export async function setSkillCategory(name: string, category: string): Promise<{ name: string; category: string }> {
  return (await request.put(`/api/skills/${encodeURIComponent(name)}/category`, { category })).data
}

// ── 技能附属文件 ──

/**
 * 读取技能附属文件
 */
export async function getSkillFile(name: string, filePath: string): Promise<{ name: string; file_path: string; content: string }> {
  return (await request.get(`/api/skills/${encodeURIComponent(name)}/files/${filePath}`)).data
}

/**
 * 写入技能附属文件
 */
export async function writeSkillFile(name: string, filePath: string, content: string): Promise<{ name: string; file_path: string; size: number }> {
  return (await request.put(`/api/skills/${encodeURIComponent(name)}/files/${filePath}`, { content })).data
}

/**
 * 删除技能附属文件
 */
export async function deleteSkillFile(name: string, filePath: string): Promise<{ name: string; file_path: string; deleted: boolean }> {
  return (await request.delete(`/api/skills/${encodeURIComponent(name)}/files/${filePath}`)).data
}

/**
 * 批量上传文件到技能目录（支持二进制文件）
 */
export async function uploadSkillFiles(
  name: string,
  files: File[],
  targetDir: string = 'references'
): Promise<{ name: string; uploaded: any[]; errors: string[] }> {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  formData.append('target_dir', targetDir)
  return (await request.post(`/api/skills/${encodeURIComponent(name)}/files/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })).data
}

/**
 * 获取技能附属文件的下载 URL
 */
export function getSkillFileDownloadUrl(name: string, filePath: string): string {
  return `/api/skills/${encodeURIComponent(name)}/files/${filePath}/raw`
}

/**
 * 在技能目录下创建子目录
 */
export async function createSkillDir(name: string, dirPath: string): Promise<{ name: string; dir_path: string; created: boolean }> {
  const formData = new FormData()
  formData.append('dir_path', dirPath)
  return (await request.post(`/api/skills/${encodeURIComponent(name)}/files/mkdir`, formData)).data
}
