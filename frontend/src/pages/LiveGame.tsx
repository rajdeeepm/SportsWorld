import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, Crosshair, Flag, ListOrdered, MapPinned, Pause, Play, Radio, Route as RouteIcon } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getJSON } from '../lib/api'
import { useLiveGames, useWinProbHistory } from '../lib/live'
import { CommentaryToggle } from '../components/radio'
import { BoxScore } from '../components/stats'
import { useBoard, useMeta, type TeamMeta } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { luminance, pct, time } from '../lib/format'
import { colorDistance, Empty, ErrorNote, Loading, Panel, ProbSplit, segColor, TeamLogo } from '../components/ui'
import { Court, FootballField, Rink, Track, type F1Car, type FootballDrive, type FootballPlay, type FootballSituation } from '../components/surfaces'

interface GameView {
  league: string
  sport: string
  event_id: string
  state: string
  detail: string
  period?: number
  clock?: string
  home: { team_id: string; name: string; abbreviation: string; score: number | null }
  away: { team_id: string; name: string; abbreviation: string; score: number | null }
  situation?: FootballSituation | null
  drives?: FootballDrive[]
  drive_plays?: FootballPlay[]
  events?: { x: number; y: number; type: string; team_id: string; made: boolean; text?: string; points?: number; period?: number; clock?: string }[]
  win_probability: { at: string; p_home: number }[]
  source: string
  note: string
}

/** official colours for both sides; if they clash, the home team switches to its other official colour */
function pair(away?: TeamMeta, home?: TeamMeta): [string, string] {
  const a = segColor(away, '#e64a5c')
  let h = segColor(home, '#2f8cff')
  if (colorDistance(a, h) < 110) {
    const other = h === home?.color ? home?.alt_color : home?.color
    h = other && colorDistance(other, a) >= 110 ? other : '#c9d4ea'
  }
  return [a, h]
}

export function LiveGame({ lg, eventId }: { lg: LeagueConfig; eventId: string }) {
  const q = useQuery({ queryKey: ['game', lg.id, eventId], queryFn: () => getJSON<GameView>(`/games/${lg.id}/${eventId}/view`), refetchInterval: 15_000 })
  const meta = useMeta(lg.id)
  const board = useBoard(lg.id)
  const m = meta.data ?? {}
  const liveRows = useLiveGames(lg.id)
  const wpLive = useWinProbHistory(eventId)
  const g0 = q.data
  const lrow = liveRows.map.get(eventId)
  // SpacetimeDB pushes score and state the moment they change; its win-probability history survives API restarts
  const g = g0 && lrow ? { ...g0, state: lrow.state, home: { ...g0.home, score: lrow.homeScore }, away: { ...g0.away, score: lrow.awayScore },
    win_probability: wpLive.length > g0.win_probability.length ? wpLive : g0.win_probability } : g0
  if (q.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (q.error || !g) return <ErrorNote error={q.error} what="this game" />
  const row = board.data?.events.find((e) => e.event_id === g.event_id)
  const hm = m[g.home.team_id], am = m[g.away.team_id]
  const [ac, hcRaw] = pair(am, hm)
  // lines and dots must read on the navy ground: lift very dark official colours slightly
  const lift = (c: string) => (luminance(c) < 0.03 ? `color-mix(in srgb, ${c} 70%, #ffffff)` : c)
  const hc = lift(hcRaw)
  const colors = { [g.away.team_id]: ac, [g.home.team_id]: hc }
  const live = g.state === 'in'
  const pHome = lrow?.pHome ?? row?.p_home ?? g.win_probability.at(-1)?.p_home ?? null

  return (
    <>
      <div className="hero">
        <div>
          <h1>{am?.short_name ?? g.away.name} at {hm?.short_name ?? g.home.name}: <em>{live ? 'Live' : g.state === 'post' ? 'Final' : 'Game'} view</em></h1>
          <p>Real {lg.sport === 'football' ? 'ball position, drives and plays' : lg.sport === 'basketball' ? 'shot locations' : 'shot, goal and hit locations'} from the {g.source}, next to SportsWorld’s own live win probability.</p>
        </div>
      </div>
      <div className="stack">
        <section className="panel scoreboard">
          <ScoreSide meta={am} name={g.away.name} abbr={g.away.abbreviation} score={g.away.score} color={ac} lg={lg} id={g.away.team_id} />
          <div className="sb-mid">
            <span className={`chip ${live ? 'live' : 'neutral'}`}>{live ? <><Radio size={12} /> LIVE</> : g.detail}</span>
            <b>{live ? `${g.detail}` : ''}</b>
            <div style={{ width: 260 }}><ProbSplit pHome={pHome} home={hm ?? { team_id: g.home.team_id, name: g.home.name, abbreviation: g.home.abbreviation }} away={am ?? { team_id: g.away.team_id, name: g.away.name, abbreviation: g.away.abbreviation }} /></div>
            <small className="muted">SportsWorld win probability · model {row?.model_version ?? 'live engine'}</small>
            <CommentaryToggle league={lg.id} eventId={g.event_id} live={live} />
          </div>
          <ScoreSide meta={hm} name={g.home.name} abbr={g.home.abbreviation} score={g.home.score} color={hc} lg={lg} id={g.home.team_id} right />
        </section>

        <div className="grid">
          <div className="c8">
            <Panel title={lg.sport === 'football' ? 'On the field' : lg.sport === 'basketball' ? 'Shot chart' : 'On the ice'} icon={MapPinned}
              foot={<>{g.note} Source: {g.source}.</>}>
              {lg.sport === 'football' && <FootballPanel g={g} ac={ac} hc={hc} />}
              {lg.sport === 'basketball' && <ShotPanel g={g} colors={colors} am={am} hm={hm} />}
              {lg.sport === 'hockey' && <RinkPanel g={g} colors={colors} am={am} hm={hm} />}
            </Panel>
          </div>
          <div className="c4 stack">
            <Panel title="Win probability" icon={Activity} foot="SportsWorld’s calibrated in-game model, every update this session. Not ESPN’s or a market’s.">
              <WinProbChart rows={g.win_probability} homeAbbr={g.home.abbreviation} awayAbbr={g.away.abbreviation} hc={hc} ac={ac} />
            </Panel>
            {lg.sport === 'football' && <PlayList plays={g.drive_plays ?? []} />}
            {lg.sport !== 'football' && <EventList events={g.events ?? []} colors={colors} />}
          </div>
          {lg.sport === 'football' && <div className="c12"><DriveChart drives={g.drives ?? []} colors={colors} away={g.away.abbreviation} home={g.home.abbreviation} /></div>}
          <div className="c12"><BoxScore league={lg.id} eventId={g.event_id} live={live} /></div>
        </div>
      </div>
    </>
  )
}

function ScoreSide({ meta, name, abbr, score, color, lg, id, right }: { meta?: TeamMeta; name: string; abbr: string; score: number | null; color: string; lg: LeagueConfig; id: string; right?: boolean }) {
  return (
    <Link to={`/${lg.id}/team/${id}`} className={`sb-side ${right ? 'right' : ''}`} style={{ ['--team-c' as string]: color }}>
      <TeamLogo meta={meta} name={name} size={64} />
      <div><b>{meta?.short_name ?? name}</b><span>{abbr}</span></div>
      <strong className="tick" key={score ?? -1}>{score ?? '–'}</strong>
    </Link>
  )
}

function FootballPanel({ g, ac, hc }: { g: GameView; ac: string; hc: string }) {
  const s = g.situation
  return (
    <>
      <FootballField situation={s ?? null} plays={g.drive_plays ?? []} away={g.away.abbreviation} home={g.home.abbreviation} awayColor={ac} homeColor={hc} />
      {s ? (
        <div className="field-facts">
          <div><span>Possession</span><b>{s.offense_id === g.home.team_id ? g.home.abbreviation : g.away.abbreviation} →{s.direction === 'left' ? ' left' : ' right'}</b></div>
          <div><span>Down & distance</span><b>{s.down && s.down >= 1 && s.down <= 4 ? `${['', '1st', '2nd', '3rd', '4th'][s.down]} & ${s.distance === 0 ? 'goal' : s.distance}` : 'Between plays'}</b></div>
          <div><span>Ball on</span><b>{s.ball_x == null ? '-' : s.ball_x <= 0 || s.ball_x >= 100 ? 'End zone' : s.ball_x === 50 ? 'Midfield' : s.ball_x < 50 ? `${g.away.abbreviation} ${Math.round(s.ball_x)}` : `${g.home.abbreviation} ${Math.round(100 - s.ball_x)}`}</b></div>
          <div><span>Red zone</span><b>{s.red_zone ? 'Yes' : 'No'}</b></div>
          <div style={{ gridColumn: '1 / -1' }}><span>Last play</span><b style={{ fontFamily: 'var(--ui)', fontSize: 13.5, fontWeight: 500 }}>{s.last_play}</b></div>
        </div>
      ) : <Empty title="No drive data yet">The field fills in from the first snap.</Empty>}
      <div className="legend" style={{ marginTop: 8 }}>
        <span><i style={{ background: '#3b9bff' }} />Line of scrimmage</span><span><i style={{ background: '#f6d84a' }} />First-down line</span><span><i style={{ background: '#fff' }} />Current drive, play by play</span>
      </div>
    </>
  )
}

function ShotPanel({ g, colors, am, hm }: { g: GameView; colors: Record<string, string>; am?: TeamMeta; hm?: TeamMeta }) {
  const [team, setTeam] = useState<string>('')
  const ev = (g.events ?? []).filter((e) => !team || e.team_id === team)
  const made = ev.filter((e) => e.made).length
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div className="seg">
          <button className={!team ? 'on' : ''} onClick={() => setTeam('')}>Both</button>
          <button className={team === g.away.team_id ? 'on' : ''} onClick={() => setTeam(g.away.team_id)}>{g.away.abbreviation}</button>
          <button className={team === g.home.team_id ? 'on' : ''} onClick={() => setTeam(g.home.team_id)}>{g.home.abbreviation}</button>
        </div>
        <span className="muted">{made}/{ev.length} field goals · {ev.length ? pct(made / ev.length, 0) : '-'}</span>
      </div>
      {ev.length ? <div style={{ maxWidth: 560, margin: '0 auto' }}><Court shots={ev} colors={colors} /></div> : <Empty title="No shots yet" />}
      <div className="legend" style={{ marginTop: 8 }}>
        <span><i style={{ background: colors[g.away.team_id] }} />{am?.short_name ?? g.away.abbreviation}</span><span><i style={{ background: colors[g.home.team_id] }} />{hm?.short_name ?? g.home.abbreviation}</span><span>dot = made, cross = missed; both halves are folded onto one basket</span>
      </div>
    </>
  )
}

function RinkPanel({ g, colors, am, hm }: { g: GameView; colors: Record<string, string>; am?: TeamMeta; hm?: TeamMeta }) {
  const [kinds, setKinds] = useState<'shots' | 'all'>('shots')
  const ev = (g.events ?? []).filter((e) => kinds === 'all' || ['Shot', 'Goal', 'Missed', 'Blocked'].includes(e.type))
  const sog = (id: string) => (g.events ?? []).filter((e) => e.team_id === id && (e.type === 'Shot' || e.type === 'Goal')).length
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div className="seg"><button className={kinds === 'shots' ? 'on' : ''} onClick={() => setKinds('shots')}>Shot attempts</button><button className={kinds === 'all' ? 'on' : ''} onClick={() => setKinds('all')}>All events</button></div>
        <span className="muted">Shots on goal {g.away.abbreviation} {sog(g.away.team_id)} · {g.home.abbreviation} {sog(g.home.team_id)}</span>
      </div>
      {ev.length ? <Rink events={ev} colors={colors} /> : <Empty title="No events yet" />}
      <div className="legend" style={{ marginTop: 8 }}>
        <span><i style={{ background: colors[g.away.team_id] }} />{am?.short_name ?? g.away.abbreviation}</span><span><i style={{ background: colors[g.home.team_id] }} />{hm?.short_name ?? g.home.abbreviation}</span><span>large ring = goal · filled = on goal · hollow = missed/blocked · diamond = hit</span>
      </div>
    </>
  )
}

function WinProbChart({ rows, homeAbbr, awayAbbr, hc, ac }: { rows: { at: string; p_home: number }[]; homeAbbr: string; awayAbbr: string; hc: string; ac: string }) {
  if (rows.length < 2) return <Empty title="Waiting for in-game updates">The line starts at kickoff / tip-off / puck drop.</Empty>
  const data = rows.map((r) => ({ t: new Date(r.at).getTime(), h: r.p_home, a: 1 - r.p_home }))
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={(t) => time(new Date(t).toISOString())} tickLine={false} axisLine={false} minTickGap={40} />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => `${v * 100}%`} tickLine={false} axisLine={false} width={44} />
        <ReferenceLine y={0.5} stroke="rgba(160,190,240,.35)" strokeDasharray="3 4" />
        <Tooltip content={({ active, payload }: any) => active && payload?.length ? <div className="tt"><b>{time(new Date(payload[0].payload.t).toISOString())}</b>{awayAbbr} {pct(payload[0].payload.a, 0)} · {homeAbbr} {pct(payload[0].payload.h, 0)}</div> : null} />
        <Line dataKey="a" stroke={ac} strokeWidth={2.4} dot={false} isAnimationActive={false} name={awayAbbr} />
        <Line dataKey="h" stroke={hc} strokeWidth={2.4} dot={false} isAnimationActive={false} name={homeAbbr} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function PlayList({ plays }: { plays: FootballPlay[] }) {
  return (
    <Panel title="Current drive" icon={ListOrdered} flush>
      {plays.length === 0 ? <Empty title="No plays yet" /> : (
        <ul className="feed">
          {plays.slice().reverse().map((p, i) => (
            <li key={i}>
              <time>{p.period ? `Q${p.period}` : ''} {p.clock}</time>
              <Crosshair className={`ic ${p.scoring ? 'final' : ''}`} size={15} />
              <p>{p.text}<small>{p.down ? `${['', '1st', '2nd', '3rd', '4th'][p.down]} & ${p.distance}` : p.type}{p.yards != null ? ` · ${p.yards > 0 ? '+' : ''}${p.yards} yds` : ''}</small></p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function EventList({ events, colors }: { events: GameView['events'] & {}; colors: Record<string, string> }) {
  const rows = events.slice().reverse().slice(0, 10)
  return (
    <Panel title="Latest plays" icon={ListOrdered} flush>
      {rows.length === 0 ? <Empty title="No plays yet" /> : (
        <ul className="feed">
          {rows.map((e, i) => (
            <li key={i}>
              <time>P{e.period} {e.clock}</time>
              <span aria-hidden style={{ width: 10, height: 10, borderRadius: 3, background: colors[e.team_id] ?? '#2f8cff', marginTop: 4 }} />
              <p>{e.text}<small>{e.type}{e.made ? ` · ${e.points ?? ''} pts` : ''}</small></p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function DriveChart({ drives, colors, away, home }: { drives: FootballDrive[]; colors: Record<string, string>; away: string; home: string }) {
  return (
    <Panel title="Drive chart" icon={RouteIcon} foot={`Each bar runs from where a drive started to where it ended; ${away} attacks right, ${home} attacks left.`}>
      {drives.length === 0 ? <Empty title="No drives yet" /> : (
        <div className="drives">
          <div className="drive-axis"><span>{away} goal</span><span>50</span><span>{home} goal</span></div>
          {drives.map((d, i) => {
            if (d.start_x == null || d.end_x == null) return null
            const lo = Math.min(d.start_x, d.end_x), hi = Math.max(d.start_x, d.end_x)
            return (
              <div className="drive-row" key={i} title={`${d.description ?? ''} · ${d.result ?? ''}`}>
                <div className="drive-track">
                  <i style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.8)}%`, background: colors[d.team_id] ?? '#2f8cff' }} />
                </div>
                <span className={`chip ${d.is_score ? 'low' : 'neutral'}`}>{d.result ?? '-'}</span>
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}

/* ---------------------------------------------------------------- F1 live track */

interface F1LiveView {
  session: { session_key: number; session_name: string; circuit_short_name: string; country_name: string; date_start: string; date_end: string; year: number }
  live: boolean
  window: { start: string; end: string; seconds: number }
  drivers: (F1Car & { name: string; team: string })[]
  outline: number[][]
  tracks: Record<string, number[][]>
  source: string
}

export function F1Live() {
  const q = useQuery({ queryKey: ['f1-live'], queryFn: () => getJSON<F1LiveView>('/f1/live?seconds=30'), refetchInterval: (qq) => (qq.state.data?.live ? 25_000 : false) })
  const [playing, setPlaying] = useState(true)
  const [focus, setFocus] = useState<number | null>(null)
  const v = q.data
  const order = useMemo(() => (v?.drivers ?? []).slice().sort((a, b) => (a.position ?? 99) - (b.position ?? 99)), [v])
  if (q.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (q.error || !v) return <ErrorNote error={q.error} what="the OpenF1 session" />
  return (
    <>
      <div className="hero">
        <div>
          <h1>F1: <em>{v.live ? 'Live track' : 'Track replay'}</em></h1>
          <p>{v.session.year} {v.session.country_name} · {v.session.circuit_short_name} · {v.session.session_name}. Every car at its real position from OpenF1 location data{v.live ? ', refreshed every 25 seconds' : `, replaying ${v.window.seconds} seconds from ${time(v.window.start)}`}.</p>
        </div>
      </div>
      <div className="grid">
        <div className="c8">
          <Panel title={`${v.session.circuit_short_name} · ${v.session.session_name}`} icon={Flag}
            action={<button className="btn" onClick={() => setPlaying((p) => !p)}>{playing ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Play</>}</button>}
            foot={<>Source: {v.source}. Positions are sampled about 4 times a second and interpolated between samples. {v.live ? '' : 'Outside a live session this is a replay of recorded data.'}</>}>
            {v.outline.length ? <Track outline={v.outline} tracks={v.tracks} cars={v.drivers} seconds={v.window.seconds} playing={playing} focus={focus} /> : <Empty title="No location data for this session" />}
          </Panel>
        </div>
        <div className="c4">
          <Panel title="Running order" icon={ListOrdered} flush foot="Click a driver to highlight their car.">
            <table className="tbl">
              <tbody>
                {order.map((d) => (
                  <tr key={d.number} className={focus === d.number ? 'focus' : ''} style={{ cursor: 'pointer' }} onClick={() => setFocus((f) => (f === d.number ? null : d.number))}>
                    <td className="rank">{d.position ?? '-'}</td>
                    <td><span className="team-cell" style={{ gap: 7 }}><span aria-hidden style={{ width: 5, height: 18, borderRadius: 2, background: d.colour ?? '#2f8cff' }} /><b>{d.code}</b></span></td>
                    <td className="muted">{d.name}</td>
                    <td className="muted">{d.team}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      </div>
      <div className="provenance"><span><b>Session</b> {v.session.session_key}</span><span><b>Window</b> {time(v.window.start)}–{time(v.window.end)}</span><Link className="link" to="/f1">Season World</Link></div>
    </>
  )
}
