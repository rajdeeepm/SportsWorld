import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, ErrorBar, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { pct, shortDate } from '../lib/format'

const tip = (render: (p: any) => React.ReactNode) =>
  ({ active, payload }: any) => (active && payload?.length ? <div className="tt">{render(payload[0].payload)}</div> : null)

/** latent strength posterior over time: mean with a 90% band (mean ± 1.645 sd) */
export function StrengthTrend({ history, color, unit, height = 230 }: { history: { date: string; rating: number; var: number }[]; color: string; unit: string; height?: number }) {
  const data = history.map((h) => {
    const sd = Math.sqrt(Math.max(h.var, 0))
    return { t: new Date(h.date).getTime(), m: h.rating, band: [h.rating - 1.645 * sd, h.rating + 1.645 * sd], sd }
  })
  if (data.length < 2) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: -12 }}>
        <defs>
          <linearGradient id="bandFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity={0.35} />
            <stop offset="1" stopColor={color} stopOpacity={0.08} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} scale="time" tickFormatter={(t) => { const d = new Date(t); return `${d.toLocaleDateString('en-US', { month: 'short' })} '${String(d.getFullYear()).slice(2)}` }} tickLine={false} axisLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} tickFormatter={(v) => v.toFixed(0)} allowDecimals={false} domain={[(lo: number) => Math.floor(lo / 10) * 10, (hi: number) => Math.ceil(hi / 10) * 10]} tickCount={6} />
        <ReferenceLine y={0} stroke="rgba(160,190,240,.35)" strokeDasharray="3 4" />
        <Tooltip content={tip((p) => (<><b>{shortDate(new Date(p.t).toISOString())}</b>Strength {p.m.toFixed(1)} {unit} vs avg · ±{p.sd.toFixed(1)} sd</>))} />
        <Area dataKey="band" stroke="none" fill="url(#bandFill)" isAnimationActive={false} />
        <Line dataKey="m" stroke={color} strokeWidth={2.6} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** distribution of final win totals from the season simulation */
export function WinDistribution({ hist, draws, color, current, height = 180, label = 'wins' }: { hist: number[]; draws: number; color: string; current?: number; height?: number; label?: string }) {
  const data = hist.map((c, w) => ({ w, p: c / draws })).filter((d, i, a) => d.p > 0.0005 || (i > 0 && a[i - 1].p > 0.0005 && i < a.length - 1 && a[i + 1].p > 0.0005))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 6, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="w" tickLine={false} axisLine={false} />
        <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} width={48} />
        <Tooltip cursor={{ fill: 'rgba(47,140,255,.08)' }} content={tip((p) => (<><b>{p.w} {label}</b>{pct(p.p)} of simulated seasons</>))} />
        <Bar dataKey="p" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((d) => <Cell key={d.w} fill={color} fillOpacity={current != null && d.w < current ? 0.35 : 0.95} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** title probabilities with Monte Carlo 95% error bars */
export function TitleOdds({ rows, height = 240 }: { rows: { name: string; p: number; se: number; color: string }[]; height?: number }) {
  const data = rows.map((r) => ({ ...r, err: 1.96 * r.se }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 6, bottom: 0, left: -10 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="name" tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} width={44} />
        <Tooltip cursor={{ fill: 'rgba(47,140,255,.08)' }} content={tip((p) => (<><b>{p.name}</b>{pct(p.p)} · 95% MC interval ±{pct(p.err, 2)}</>))} />
        <Bar dataKey="p" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((d) => <Cell key={d.name} fill={d.color} />)}
          <ErrorBar dataKey="err" width={5} stroke="rgba(234,240,253,.7)" strokeWidth={1.4} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** overlaid base vs scenario distributions */
export function CompareDistribution({ base, alt, draws, height = 200, label = 'wins' }: { base: number[]; alt: number[]; draws: number; height?: number; label?: string }) {
  const n = Math.max(base.length, alt.length)
  const data = Array.from({ length: n }, (_, w) => ({ w, b: (base[w] ?? 0) / draws, a: (alt[w] ?? 0) / draws })).filter((d) => d.a > 0.001 || d.b > 0.001)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 6, bottom: 0, left: -16 }} barGap={1}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="w" tickLine={false} axisLine={false} />
        <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} width={48} />
        <Tooltip cursor={{ fill: 'rgba(47,140,255,.08)' }} content={tip((p) => (<><b>{p.w} {label}</b>Baseline {pct(p.b)} · Scenario {pct(p.a)}</>))} />
        <Bar dataKey="b" fill="rgba(169,186,219,.45)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="a" fill="#2f8cff" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
