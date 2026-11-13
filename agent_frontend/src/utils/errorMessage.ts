// 统一错误提取（11-14 P5）：后端错误存在两种形态——
// - FastAPI HTTPException / 校验：detail（字符串、数组或对象）；
// - AppError.to_payload()：{ error, message } 顶层中文 message，没有 detail。
// 页面必须显示真实业务原因，不得退化为 "Request failed with status code 422"。

function normalizeDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === 'string') return d
        if (d && typeof d === 'object') {
          const item = d as { loc?: unknown[]; msg?: string }
          const loc = Array.isArray(item.loc)
            ? item.loc.filter((x) => typeof x === 'string').join('.')
            : ''
          const text = item.msg || JSON.stringify(d)
          return loc ? `${loc}: ${text}` : text
        }
        return String(d)
      })
      .filter(Boolean)
      .join('；')
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as { message?: string; reason?: string }
    if (typeof obj.message === 'string' && obj.message.trim()) return obj.message.trim()
    if (typeof obj.reason === 'string' && obj.reason.trim()) return obj.reason.trim()
    try { return JSON.stringify(detail) } catch { return '' }
  }
  return ''
}

export function extractErrorMessage(err: unknown): string {
  const e = err as {
    response?: { data?: { detail?: unknown; message?: unknown } }
    message?: unknown
  } | null
  const data = e?.response?.data
  if (data) {
    const fromDetail = normalizeDetail(data.detail)
    if (fromDetail) return fromDetail
    if (typeof data.message === 'string' && data.message.trim()) return data.message.trim()
  }
  // axios 默认 "Request failed with status code NNNN" 对用户无信息量：跳过
  if (typeof e?.message === 'string' && e.message.trim()
    && !/^Request failed with status code \d+$/.test(e.message.trim())) {
    return e.message
  }
  return '未知错误，请稍后重试'
}

const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|heic|heif)$/i

/** 账单文件入口的图片判定：MIME 或扩展名任一命中即分流到截图识别（P5）。 */
export function looksLikeImageFile(file: { name: string; type?: string }): boolean {
  return (file.type || '').startsWith('image/') || IMAGE_EXT_RE.test(file.name || '')
}
