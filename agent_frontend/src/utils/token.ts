// JWT Token 工具函数

/**
 * 解码 JWT payload（不验证签名，仅读取声明）
 */
export function decodeJwtPayload(token: string): Record<string, any> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    // base64url → base64 → 解码
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - base64.length % 4) % 4)
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

/**
 * 获取 token 剩余有效秒数。返回负数表示已过期。
 */
export function getTokenRemainingSeconds(token: string): number {
  const payload = decodeJwtPayload(token)
  if (!payload || !payload.exp) return -1
  return payload.exp - Math.floor(Date.now() / 1000)
}

/**
 * token 是否已过期
 */
export function isTokenExpired(token: string): boolean {
  return getTokenRemainingSeconds(token) <= 0
}

/**
 * token 是否即将过期（默认阈值 5 分钟）
 */
export function isTokenExpiringSoon(token: string, thresholdSeconds = 300): boolean {
  const remaining = getTokenRemainingSeconds(token)
  return remaining >= 0 && remaining < thresholdSeconds
}
