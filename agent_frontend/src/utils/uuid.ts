/**
 * 生成 UUID v4
 * 兼容所有浏览器，包括不支持 crypto.randomUUID() 的旧浏览器
 */
export function generateUUID(): string {
  // 优先使用原生 API（如果可用）
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  
  // Fallback: 使用 Math.random 生成
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}
