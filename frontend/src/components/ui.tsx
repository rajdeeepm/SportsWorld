import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp, type LucideIcon } from 'lucide-react'
import { luminance, pct, pp, visibleColor } from '../lib/format'
import type { TeamMeta } from '../lib/data'

export function Panel(props: {
  title: ReactNode
  icon?: LucideIcon
  action?: ReactNode
  foot?: ReactNode
  flush?: boolean
  className?: string
  children: ReactNode
  id?: string
}) {
  const Icon = props.icon
  return (
    <section className={`panel ${props.className ?? ''}`} id={props.id} aria-label={typeof props.title === 'string' ? props.title : undefined}>
      <header className="panel-head">
        {Icon && <Icon className="ph-icon" size={18} strokeWidth={2.2} aria-hidden />}
        <h2>{props.title}</h2>
        {props.action && <div className="ph-action">{props.action}</div>}
      </header>
      <div className={`panel-body ${props.flush ? 'flush' : ''}`}>{props.children}</div>
      {props.foot && <footer className="panel-foot">{props.foot}</footer>}
    </section>
  )
}

export interface KpiItem {
  icon: LucideIcon
  label: string
  value: ReactNode
  sub?: ReactNode
  gold?: boolean
}

export function Kpis({ items }: { items: KpiItem[] }) {
  return (
    <section className="panel kpis" style={{ ['--n' as string]: items.length }}>
      {items.map((k) => (
        <div className="kpi" key={k.label}>
          <k.icon className={`kpi-icon ${k.gold ? 'gold' : ''}`} size={34} strokeWidth={1.6} aria-hidden />
          <div style={{ minWidth: 0 }}>
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            {k.sub && <div className="kpi-sub">{k.sub}</div>}
          </div>
        </div>
      ))}
    </section>
  )
}

export function TeamLogo({ meta, name, size = 26, abbr }: { meta?: TeamMeta; name?: string; size?: number; abbr?: string | null }) {
  if (meta?.logo) {
    return <img src={meta.logo_dark || meta.logo} alt="" width={size} height={size} loading="lazy" style={{ width: size, height: size, objectFit: 'contain', flex: 'none' }} />
  }
  const c = visibleColor(meta?.color, meta?.alt_color, '#24498a')
  const label = (abbr || meta?.abbreviation || name || '?').slice(0, 3)
  return (
    <span className="logo-fallback" aria-hidden style={{ width: size, height: size, background: c, fontSize: size * 0.36 }}>
      {label}
    </span>
  )
}

export function teamColor(meta?: TeamMeta, fallback = '#2f8cff') {
  return visibleColor(meta?.color, meta?.alt_color, fallback)
}

export function colorDistance(a: string, b: string) {
  const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.replace('#', '').padEnd(6, '0').slice(i - 1, i + 1), 16))
  const [x, y] = [rgb(a), rgb(b)]
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2])
}

/** official colour of a team for a bar segment: primary, or the alternate when the primary is near-black */
export function segColor(meta?: TeamMeta, fallback = '#2f8cff') {
  if (meta?.color && luminance(meta.color) > 0.035) return meta.color
  return meta?.alt_color || meta?.color || fallback
}

/** two-sided win probability bar in official team colours; away on the left as broadcasts list "away @ home".
 *  Both ends always carry the team code and its probability, so the bar never reads ambiguously. */
export function ProbSplit({ pHome, home, away }: { pHome: number | null; home?: TeamMeta; away?: TeamMeta }) {
  if (pHome == null) return <span className="p-faint">—</span>
  const pa = 1 - pHome
  const ca = segColor(away, '#e64a5c')
  let ch = segColor(home, '#2f8cff')
  // colours clash: use the home team's other official colour instead of inventing one
  if (colorDistance(ch, ca) < 110) {
    const other = ch === home?.color ? home?.alt_color : home?.color
    if (other && colorDistance(other, ca) >= 110) ch = other
  }
  const fav = pHome >= pa ? 'home' : 'away'
  // labels sit at the two ends; ink is chosen against the segment underneath (dark ink on maize, cream, silver)
  const under = (side: 'l' | 'r') => (side === 'l' ? (pa >= 0.16 ? ca : ch) : pHome >= 0.16 ? ch : ca)
  const ink = (c: string) => (luminance(c) > 0.4 ? 'dark' : '')
  return (
    <div className="split" role="img" aria-label={`${away?.abbreviation ?? 'Away'} ${pct(pa, 0)}, ${home?.abbreviation ?? 'Home'} ${pct(pHome, 0)}`}>
      <div className="seg" style={{ flexBasis: `${pa * 100}%`, background: ca, opacity: fav === 'away' ? 1 : 0.62 }} />
      <div className="seg" style={{ flexBasis: `${pHome * 100}%`, background: ch, opacity: fav === 'home' ? 1 : 0.62 }} />
      <span className={`lab l ${fav === 'away' ? 'fav' : ''} ${ink(under('l'))}`}>{away?.abbreviation} {pct(pa, 0)}</span>
      <span className={`lab r ${fav === 'home' ? 'fav' : ''} ${ink(under('r'))}`}>{pct(pHome, 0)} {home?.abbreviation}</span>
    </div>
  )
}

/** probabilities use one hue whose intensity rises with p; red/amber/green stay reserved for state, leverage and deltas */
export function probClass(p: number | null | undefined) {
  if (p == null || p < 0.005) return 'p-faint'
  if (p >= 0.5) return 'p-strong'
  if (p >= 0.1) return 'p-mid'
  return 'p-weak'
}

export function P({ p, se, digits = 1 }: { p: number | null | undefined; se?: number | null; digits?: number }) {
  return (
    <span className={probClass(p)} title={se != null ? `Monte Carlo standard error ±${pct(se, 2)}` : undefined}>
      {pct(p, digits)}
    </span>
  )
}

/** leverage = change in the headline milestone probability between winning and losing this game */
export function Leverage({ value, milestone }: { value?: number | null; milestone?: string }) {
  if (value == null) return <span className="p-faint">—</span>
  const v = Math.abs(value)
  const cls = v >= 0.2 ? 'vhigh' : v >= 0.08 ? 'high' : v >= 0.025 ? 'med' : 'low'
  const label = v >= 0.2 ? 'Very high' : v >= 0.08 ? 'High' : v >= 0.025 ? 'Medium' : 'Low'
  return (
    <span className={`chip ${cls}`} title={`${milestone ?? 'Milestone'} probability: win vs loss differs by ${(v * 100).toFixed(1)} points`}>
      {label} <small style={{ fontWeight: 600, opacity: 0.8 }}>{(v * 100).toFixed(1)}</small>
    </span>
  )
}

export function Delta({ d, digits = 1, unit = 'pp' }: { d: number | null | undefined; digits?: number; unit?: 'pp' | 'raw' }) {
  if (d == null) return <span className="flat">—</span>
  const cls = Math.abs(d) < (unit === 'pp' ? 0.0005 : 0.05) ? 'flat' : d > 0 ? 'up' : 'down'
  const text = unit === 'pp' ? pp(d, digits) : `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(digits)}`
  const Icon = cls === 'up' ? ArrowUp : cls === 'down' ? ArrowDown : null
  return (
    <span className={cls} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
      {Icon && <Icon size={12} strokeWidth={3} aria-hidden />}
      {text}
    </span>
  )
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 8, padding: 4 }} aria-busy>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ width: `${92 - i * 9}%` }} />)}
    </div>
  )
}

export function ErrorNote({ error, what }: { error: unknown; what: string }) {
  const msg = error instanceof Error ? error.message : String(error)
  const offline = /Failed to fetch|NetworkError|503/.test(msg)
  return (
    <div className="err" role="alert">
      Couldn’t load {what}. {offline ? 'The SportsWorld API is not reachable; start it with `make live` or `make replay-demo`.' : msg.slice(0, 160)}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <b>{title}</b>
      {children}
    </div>
  )
}

export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden>
      <circle cx="20" cy="20" r="15.5" stroke="currentColor" strokeWidth="2.6" />
      <path d="M5 23c8-1 18-6 30-15" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M7 29c9-2 19-8 28-16" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity=".7" />
      <path d="M20 4.5c-5 5-7 10-7 15.5s2 10.5 7 15.5M20 4.5c5 5 7 10 7 15.5s-2 10.5-7 15.5" stroke="currentColor" strokeWidth="1.6" opacity=".55" />
    </svg>
  )
}
