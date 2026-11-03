// 统一的 API 错误消息提取。
// 后端可能返回：
//   - 字符串 detail（HTTPException）
//   - 对象/数组 detail（FastAPI 422 校验错误等）
// 无论哪种形状都转成可读字符串，避免 alert 显示 "[object Object]"。

export function errMsg(e: unknown): string {
  const err = e as any
  if (!err) return '未知错误'
  const detail = err.response && err.response.data && err.response.data.detail

  // FastAPI 422 校验错误: [{ loc, msg, type }, ...]
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: any) => {
        if (typeof d === 'string') return d
        if (d && typeof d === 'object') {
          const loc = Array.isArray(d.loc)
            ? d.loc.filter((x: any) => typeof x === 'string').join('.')
            : ''
          const msg = d.msg || JSON.stringify(d)
          return loc ? loc + ': ' + msg : msg
        }
        return String(d)
      })
      .filter(Boolean)
      .join('；')
  }

  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') {
    try { return JSON.stringify(detail) } catch { /* ignore */ }
  }

  if (typeof err.message === 'string' && err.message) return err.message
  return '请求失败'
}
