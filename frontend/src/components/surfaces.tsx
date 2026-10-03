import { useEffect, useMemo, useRef, useState } from 'react'

/* Playing surfaces drawn from real coordinates. Units are the feed's own: yards (football), feet (court, rink). */

export interface FootballSituation {
  offense_id: string
  ball_x: number | null
  first_down_x: number | null
  down: number | null
  distance: number | null
  red_zone: boolean
  direction: 'left' | 'right'
  last_play?: string
}

export interface FootballDrive { team_id: string; start_x: number | null; end_x: number | null; result?: string; is_score?: boolean; description?: string }
export interface FootballPlay { text: string; type?: string; start_x: number | null; end_x: number | null; down?: number; distance?: number; yards?: number; scoring?: boolean; clock?: string; period?: number }

const ordinal = (n: number) => ['', '1st', '2nd', '3rd', '4th'][n] ?? `${n}th`

/** football field, away end zone on the left; x in yards from the away goal line */
export function FootballField({ situation, plays, away, home, awayColor, homeColor }: {
  situation: FootballSituation | null; plays: FootballPlay[]; away: string; home: string; awayColor: string; homeColor: string
}) {
  const W = 120, H = 53.3
  const X = (x: number) => x + 10
  const offColor = situation ? (situation.direction === 'right' ? awayColor : homeColor) : '#fff'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="surface" role="img" aria-label={situation ? `Ball at ${situation.ball_x} yards, ${ordinal(situation.down ?? 1)} and ${situation.distance}` : 'Football field'}>
      <defs>
        <pattern id="turf" width="10" height={H} patternUnits="userSpaceOnUse">
          <rect width="5" height={H} fill="#123b26" /><rect x="5" width="5" height={H} fill="#10351f" />
        </pattern>
      </defs>
      <rect x="10" y="0" width="100" height={H} fill="url(#turf)" />
      <rect x="0" y="0" width="10" height={H} fill={awayColor} opacity=".85" />
      <rect x="110" y="0" width="10" height={H} fill={homeColor} opacity=".85" />
      <text x="5" y={H / 2} className="ez" transform={`rotate(-90 5 ${H / 2})`}>{away}</text>
      <text x="115" y={H / 2} className="ez" transform={`rotate(90 115 ${H / 2})`}>{home}</text>
      {Array.from({ length: 21 }, (_, i) => i * 5).map((y) => (
        <line key={y} x1={X(y)} x2={X(y)} y1="0" y2={H} stroke="rgba(255,255,255,.55)" strokeWidth={y % 10 === 0 ? 0.28 : 0.14} />
      ))}
      {[10, 20, 30, 40, 50, 60, 70, 80, 90].map((y) => (
        <g key={y} className="yd">
          <text x={X(y)} y="9">{y <= 50 ? y : 100 - y}</text>
          <text x={X(y)} y={H - 6}>{y <= 50 ? y : 100 - y}</text>
        </g>
      ))}
      {Array.from({ length: 99 }, (_, i) => i + 1).map((y) => (
        <g key={`h${y}`} stroke="rgba(255,255,255,.4)" strokeWidth=".12">
          <line x1={X(y)} x2={X(y)} y1="0.6" y2="1.6" /><line x1={X(y)} x2={X(y)} y1={H - 1.6} y2={H - 0.6} />
          <line x1={X(y)} x2={X(y)} y1={H * 0.36} y2={H * 0.36 + 0.9} /><line x1={X(y)} x2={X(y)} y1={H * 0.64 - 0.9} y2={H * 0.64} />
        </g>
      ))}
      {/* the current drive's plays, oldest faint */}
      {plays.filter((p) => p.start_x != null && p.end_x != null && p.start_x !== p.end_x).map((p, i, a) => {
        const yLane = 14 + ((i * 3.1) % 26)
        return (
          <g key={i} opacity={0.35 + 0.65 * ((i + 1) / a.length)}>
            <line x1={X(p.start_x!)} x2={X(p.end_x!)} y1={yLane} y2={yLane} stroke={offColor} strokeWidth=".7" strokeLinecap="round" />
            <circle cx={X(p.end_x!)} cy={yLane} r=".75" fill={offColor} />
          </g>
        )
      })}
      {situation?.first_down_x != null && <line x1={X(situation.first_down_x)} x2={X(situation.first_down_x)} y1="0" y2={H} stroke="#f6d84a" strokeWidth=".5" />}
      {situation?.ball_x != null && (
        <g className="ball-mark">
          <line x1={X(situation.ball_x)} x2={X(situation.ball_x)} y1="0" y2={H} stroke="#3b9bff" strokeWidth=".5" />
          <ellipse cx={X(situation.ball_x)} cy={H / 2} rx="1.3" ry=".8" fill="#8a4b23" stroke="#fff" strokeWidth=".18" />
          <path d={situation.direction === 'right' ? `M${X(situation.ball_x) + 2},${H / 2} l2,-1.4 v2.8 z` : `M${X(situation.ball_x) - 2},${H / 2} l-2,-1.4 v2.8 z`} fill="#fff" opacity=".85" />
        </g>
      )}
    </svg>
  )
}

/** half court, ESPN shot coordinates in feet: x across (0–50), y from the baseline (0–47) */
export function Court({ shots, colors }: { shots: { x: number; y: number; made: boolean; team_id: string; text?: string; points?: number }[]; colors: Record<string, string> }) {
  const stroke = 'rgba(200,220,255,.55)'
  return (
    <svg viewBox="-2 -2 54 51" className="surface" role="img" aria-label={`${shots.length} shots plotted`}>
      <rect x="0" y="0" width="50" height="47" fill="#2a1d12" />
      <g fill="none" stroke={stroke} strokeWidth=".2">
        <rect x="0" y="0" width="50" height="47" />
        <rect x="17" y="0" width="16" height="19" />
        <circle cx="25" cy="19" r="6" />
        <path d="M3,0 V14 A23.75,23.75 0 0 0 47,14 V0" />
        <circle cx="25" cy="5.25" r=".75" stroke="#ff8a3d" strokeWidth=".25" />
        <line x1="22" x2="28" y1="4" y2="4" strokeWidth=".3" />
        <path d="M21,5.25 A4,4 0 0 0 29,5.25" />
        <path d="M19,47 A6,6 0 0 1 31,47" />
      </g>
      {shots.map((s, i) => {
        const c = colors[s.team_id] ?? '#2f8cff'
        return s.made
          ? <circle key={i} cx={s.x} cy={s.y} r=".85" fill={c} stroke="#fff" strokeWidth=".15"><title>{s.text}</title></circle>
          : <g key={i} stroke={c} strokeWidth=".32" opacity=".85"><title>{s.text}</title><line x1={s.x - 0.6} x2={s.x + 0.6} y1={s.y - 0.6} y2={s.y + 0.6} /><line x1={s.x - 0.6} x2={s.x + 0.6} y1={s.y + 0.6} y2={s.y - 0.6} /></g>
      })}
    </svg>
  )
}

/** full rink, ESPN event coordinates in feet: x −100..100 (goal lines at ±89), y −42.5..42.5 */
export function Rink({ events, colors }: { events: { x: number; y: number; type: string; team_id: string; text?: string }[]; colors: Record<string, string> }) {
  const line = 'rgba(160,190,240,.5)'
  return (
    <svg viewBox="-102 -45 204 90" className="surface" role="img" aria-label={`${events.length} rink events plotted`}>
      <rect x="-100" y="-42.5" width="200" height="85" rx="28" fill="#dfe8f3" />
      <g fill="none" strokeWidth=".6">
        <line x1="0" x2="0" y1="-42.5" y2="42.5" stroke="#d6283a" strokeWidth="1" />
        <line x1="-25" x2="-25" y1="-42.5" y2="42.5" stroke="#2259c8" strokeWidth="1" />
        <line x1="25" x2="25" y1="-42.5" y2="42.5" stroke="#2259c8" strokeWidth="1" />
        <line x1="-89" x2="-89" y1="-38" y2="38" stroke="#d6283a" />
        <line x1="89" x2="89" y1="-38" y2="38" stroke="#d6283a" />
        <circle cx="0" cy="0" r="15" stroke="#2259c8" />
        {[[-69, -22], [-69, 22], [69, -22], [69, 22]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="15" stroke="#d6283a" />)}
        <path d="M-89,-4 A6,6 0 0 1 -89,4" stroke="#d6283a" fill="rgba(80,140,230,.25)" />
        <path d="M89,-4 A6,6 0 0 0 89,4" stroke="#d6283a" fill="rgba(80,140,230,.25)" />
      </g>
      <rect x="-100" y="-42.5" width="200" height="85" rx="28" fill="none" stroke={line} strokeWidth="1.2" />
      {events.map((e, i) => {
        const c = colors[e.team_id] ?? '#2f8cff'
        const t = e.type
        if (t === 'Goal') return <g key={i}><title>{e.text}</title><circle cx={e.x} cy={e.y} r="3.6" fill={c} stroke="#111" strokeWidth=".7" /><circle cx={e.x} cy={e.y} r="1.2" fill="#fff" /></g>
        if (t === 'Shot') return <circle key={i} cx={e.x} cy={e.y} r="2" fill={c} stroke="#0b1428" strokeWidth=".4"><title>{e.text}</title></circle>
        if (t === 'Missed' || t === 'Blocked') return <circle key={i} cx={e.x} cy={e.y} r="1.9" fill="none" stroke={c} strokeWidth=".7"><title>{e.text}</title></circle>
        if (t === 'Hit') return <rect key={i} x={e.x - 1.2} y={e.y - 1.2} width="2.4" height="2.4" transform={`rotate(45 ${e.x} ${e.y})`} fill={c} opacity=".55"><title>{e.text}</title></rect>
        return <circle key={i} cx={e.x} cy={e.y} r=".9" fill={c} opacity=".45"><title>{e.text}</title></circle>
      })}
    </svg>
  )
}

export interface F1Car { number: number; code: string; colour: string | null; position?: number | null }

/** circuit outline + every car interpolated along its real OpenF1 location samples */
export function Track({ outline, tracks, cars, seconds, playing, focus }: {
  outline: number[][]; tracks: Record<string, number[][]>; cars: F1Car[]; seconds: number; playing: boolean; focus?: number | null
}) {
  const [t, setT] = useState(0)
  const raf = useRef<number>()
  const last = useRef<number>()
  useEffect(() => {
    if (!playing) return
    const step = (now: number) => {
      if (last.current != null) setT((x) => (x + (now - last.current!) / 1000) % seconds)
      last.current = now
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => { if (raf.current) cancelAnimationFrame(raf.current); last.current = undefined }
  }, [playing, seconds])

  const box = useMemo(() => {
    const pts = [...outline, ...Object.values(tracks).flat().map((p) => [p[1], p[2]])]
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
    const pad = Math.max(maxX - minX, maxY - minY) * 0.06
    return { minX: minX - pad, minY: minY - pad, w: maxX - minX + 2 * pad, h: maxY - minY + 2 * pad }
  }, [outline, tracks])

  const at = (pts: number[][]) => {
    if (!pts?.length) return null
    let i = pts.findIndex((p) => p[0] > t)
    if (i <= 0) i = i === 0 ? 1 : pts.length - 1
    const a = pts[i - 1], b = pts[i] ?? a
    const f = b[0] === a[0] ? 0 : Math.min(Math.max((t - a[0]) / (b[0] - a[0]), 0), 1)
    return [a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
  }
  const r = Math.max(box.w, box.h) / 95
  const path = outline.length ? `M${outline.map((p) => `${p[0]},${-p[1]}`).join('L')}` : ''
  return (
    <svg viewBox={`${box.minX} ${-(box.minY + box.h)} ${box.w} ${box.h}`} className="surface track" role="img" aria-label="Circuit map with live car positions">
      <path d={path} fill="none" stroke="rgba(120,160,230,.25)" strokeWidth={r * 2.4} strokeLinejoin="round" strokeLinecap="round" />
      <path d={path} fill="none" stroke="rgba(220,232,255,.75)" strokeWidth={r * 0.45} strokeLinejoin="round" strokeLinecap="round" />
      {cars.slice().sort((a, b) => (b.position ?? 99) - (a.position ?? 99)).map((c) => {
        const p = at(tracks[String(c.number)])
        if (!p) return null
        const on = focus == null || focus === c.number
        return (
          <g key={c.number} transform={`translate(${p[0]},${-p[1]})`} opacity={on ? 1 : 0.35}>
            <circle r={r * (focus === c.number ? 1.5 : 1.05)} fill={c.colour ?? '#2f8cff'} stroke="#060b18" strokeWidth={r * 0.28} />
            <text y={-r * 1.7} textAnchor="middle" fontSize={r * 1.7} className="car-code">{c.code}</text>
          </g>
        )
      })}
    </svg>
  )
}
