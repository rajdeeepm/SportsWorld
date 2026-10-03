export function pct(p: number | null | undefined, digits = 1): string {
  if (p == null || !Number.isFinite(p)) return '—'
  if (p > 0 && p < 0.001) return '<0.1%'
  if (p < 1 && p > 0.999) return '>99.9%'
  const v = p * 100
  return `${v.toFixed(v >= 10 ? Math.max(digits - 1, 0) : digits)}%`
}

/** percentage-point delta, signed */
export function pp(d: number | null | undefined, digits = 1): string {
  if (d == null || !Number.isFinite(d)) return '—'
  const v = d * 100
  if (Math.abs(v) < 0.05) return '±0.0'
  return `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(digits)}`
}

export function signed(d: number | null | undefined, digits = 1): string {
  if (d == null || !Number.isFinite(d)) return '—'
  if (Math.abs(d) < 0.5 * 10 ** -digits) return (0).toFixed(digits)
  return `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(digits)}`
}

export function num(x: number | null | undefined, digits = 1): string {
  if (x == null || !Number.isFinite(x)) return '—'
  return x.toFixed(digits)
}

const dayFmt = new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
const timeFmt = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })
const shortFmt = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })

export const day = (iso: string) => dayFmt.format(new Date(iso))
export const time = (iso: string) => timeFmt.format(new Date(iso))
export const shortDate = (iso: string) => shortFmt.format(new Date(iso))

/** ESPN uses 04:00 UTC for "time TBD" kickoffs */
export const isTbd = (iso: string) => /T04:00:00/.test(iso)

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function clock(sport: string, period?: number, seconds?: number): string {
  if (!period) return ''
  const m = Math.floor((seconds ?? 0) / 60)
  const s = Math.floor((seconds ?? 0) % 60).toString().padStart(2, '0')
  const per = sport === 'football' ? `Q${period}` : sport === 'hockey' ? `P${period}` : period > 4 ? `OT` : `Q${period}`
  return `${per} ${m}:${s}`
}

/** relative luminance for picking readable ink on team colours */
export function luminance(hex?: string | null): number {
  if (!hex) return 0
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** a team colour that stays visible on the navy ground */
export function visibleColor(primary?: string | null, alt?: string | null, fallback = '#2f8cff'): string {
  if (primary && luminance(primary) > 0.06) return primary
  if (alt && luminance(alt) > 0.06) return alt
  return fallback
}
