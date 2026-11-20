// English short units give K/M consistently, including in the Chinese UI.
const compact = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 2,
})

export function formatUsageCount(value: number | null | undefined): string {
  return value != null && Number.isFinite(value) ? compact.format(value) : '—'
}
