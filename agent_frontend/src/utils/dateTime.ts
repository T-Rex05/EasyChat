// 时间显示工具（WP-B）：UTC 存储不变，展示按明确用户时区格式化为 YYYY-MM-DD HH:mm。
// 时区缺失时回退 Asia/Shanghai；无效/空值返回占位符，绝不显示 raw UTC 原文。

export const DEFAULT_TIMEZONE = 'Asia/Shanghai'

const partsCache = new Map<string, Intl.DateTimeFormat>()

function formatter(tz: string): Intl.DateTimeFormat {
  let f = partsCache.get(tz)
  if (!f) {
    f = new Intl.DateTimeFormat('zh-CN', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    })
    partsCache.set(tz, f)
  }
  return f
}

/** 解析并格式化：兼容 Z、+00:00 偏移、无时区后缀(按 UTC 解释——项目存储约定)、无效值。 */
export function formatDateTime(value: string | null | undefined, tz?: string | null): string {
  if (!value) return '—'
  let iso = String(value).trim()
  // 项目存储为 UTC ISO-8601；历史数据存在无偏移形式，按 UTC 解释保持口径一致
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(iso)) iso += 'Z'
  const d = new Date(iso.replace(' ', 'T'))
  if (isNaN(d.getTime())) return '—'
  const zone = tz && tz.trim() ? tz.trim() : DEFAULT_TIMEZONE
  try {
    const p = formatter(zone).formatToParts(d)
    const get = (t: string) => p.find(x => x.type === t)?.value || ''
    return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
  } catch {
    // 未知时区名:回退默认时区,不抛错打断页面
    const p = formatter(DEFAULT_TIMEZONE).formatToParts(d)
    const get = (t: string) => p.find(x => x.type === t)?.value || ''
    return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
  }
}

/** 显示时区口径标签(如 UTC+08:00),用于表头说明。 */
export function timezoneLabel(tz?: string | null): string {
  const zone = tz && tz.trim() ? tz.trim() : DEFAULT_TIMEZONE
  return zone
}
