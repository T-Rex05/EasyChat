// 全局用量区域纯逻辑（11-14 P2）：筛选切换重置页码、晚到响应丢弃、
// 分页真实口径（无精确总数时只承诺"本页 + 能否继续翻页"）。

export const GLOBAL_PAGE_SIZE = 50

/** 用户筛选变化：回到第 1 页（分页参数与页码一致）。 */
export function onFilterChanged(uid: number): { page: number; selectedUid: number } {
  return { page: 1, selectedUid: uid }
}

/** 每次加载分配递增令牌；仅当前令牌可落数据——快速切换时旧响应必须丢弃。 */
export function beginLoad(currentToken: number): { nextToken: number; requestToken: number } {
  const next = currentToken + 1
  return { nextToken: next, requestToken: next }
}

export function isStaleResponse(currentToken: number, requestToken: number): boolean {
  return requestToken !== currentToken
}

/** 下一页可用性：本页装满即可能有下一页；不满即为真实末尾。不再展示伪总数。 */
export function canGoNext(rowsLength: number, pageSize: number = GLOBAL_PAGE_SIZE): boolean {
  return rowsLength >= pageSize
}

/** 本人区归属：身份未就绪或非法时必须拒绝发起"本人调用"请求（防全量泄漏）。 */
export function resolveMyUid(userId: string | number | null | undefined): number {
  const n = Number(userId)
  return Number.isFinite(n) && n > 0 ? n : 0
}
