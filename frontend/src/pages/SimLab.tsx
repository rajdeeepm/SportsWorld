import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Bot, Cpu, FlaskConical, Gauge, HeartPulse, Lightbulb, ListTree, Play, Plus, RotateCcw, Scale, Sparkles, Swords, Trophy, Users, X,
} from 'lucide-react'
import { getJSON, postJSON } from '../lib/api'
import { useMeta, usePlayerImpact, useSeason, useTeam, type SeasonRun, type SeasonTeam, type TeamMeta } from '../lib/data'
import { qualify, title, type LeagueConfig } from '../lib/leagues'
import { num, pct, pp, shortDate } from '../lib/format'
import { Delta, Empty, ErrorNote, Loading, P, Panel, TeamLogo, teamColor } from '../components/ui'
import { CompareDistribution } from '../components/charts'

type Op =
  | { kind: 'absence'; id: string; team: string; role: string; games: number; delta: number; end: string; label: string }
  | { kind: 'shift'; id: string; team: string; delta: number; label: string }
  | { kind: 'force'; id: string; event: string; winner: 'home' | 'away'; label: string }

interface SimResult {
  base: SeasonRun
  scenario: SeasonRun
  deltas: Record<string, any>[]
  label?: string
  parser?: string
  assumptions?: Record<string, any>[]
  warnings?: string[]
  source: 'controls' | 'ask'
  ms: number
}

export function SimLab({ lg }: { lg: LeagueConfig }) {
  const [params, setParams] = useSearchParams()
  const season = useSeason(lg.id)
  const meta = useMeta(lg.id)
  const m = meta.data ?? {}
  const teams = season.data?.teams ?? []
  const fallback = lg.id === 'college-football' ? '130' : teams[0]?.team_id
  const teamId = params.get('team') ?? fallback ?? ''
  const team = useTeam(lg.id, teamId)
  const impact = usePlayerImpact()
  const roles = (impact.data ?? []).find((x: any) => x.league === lg.id)?.by_position ?? {}
  const [ops, setOps] = useState<Op[]>([])
  const [draws, setDraws] = useState(10000)
  const [result, setResult] = useState<SimResult | null>(null)
  const [ask, setAsk] = useState('')

  useEffect(() => { setOps([]); setResult(null) }, [lg.id])

  const remaining = (team.data?.remaining ?? []).filter((g) => g.state === 'pre')
  const me = teams.find((t) => t.team_id === teamId)
  const shortName = (id: string) => m[id]?.abbreviation ?? teams.find((t) => t.team_id === id)?.abbreviation ?? id

  const run = useMutation({
    mutationFn: async (override?: Op[]) => {
      const list = override ?? ops
      const t0 = performance.now()
      const body = {
        label: list.map((o) => o.label).join(' + '),
        draws,
        rating_shifts: list.flatMap((o) =>
          o.kind === 'absence' ? [{ target_id: o.team, delta: o.delta, end: o.end }] : o.kind === 'shift' ? [{ target_id: o.team, delta: o.delta }] : []),
        forced_results: Object.fromEntries(list.filter((o) => o.kind === 'force').map((o: any) => [o.event, o.winner])),
      }
      const r = await postJSON<Omit<SimResult, 'source' | 'ms'>>(`/competitions/${lg.id}/seasons/current/season-simulations`, body)
      return { ...r, source: 'controls' as const, ms: performance.now() - t0 }
    },
    onSuccess: setResult,
  })
  const asked = useMutation({
    mutationFn: async () => {
      const t0 = performance.now()
      const r = await postJSON<any>(`/competitions/${lg.id}/seasons/current/scenario/ask`, { text: ask, draws })
      if (!r.base) throw new Error(r.warnings?.join('; ') || 'The question could not be turned into a supported scenario.')
      return { ...r, label: ask, source: 'ask' as const, ms: performance.now() - t0 } as SimResult
    },
    onSuccess: setResult,
  })

  const add = (o: Op) => setOps((xs) => [...xs.filter((x) => x.id !== o.id), o])

  if (season.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (season.error) return <ErrorNote error={season.error} what="the season run" />

  return (
    <>
      <div className="hero">
        <div>
          <h1>{lg.name}: <em>Season Simulation Lab</em></h1>
          <p>Branch the world. Simulate the rest of the season. Measure {qualify(lg).short === 'Playoffs' ? 'playoff' : qualify(lg).short} and title paths. Canonical state is never touched.</p>
        </div>
      </div>

      <div className="stack">
        <section className="panel">
          <div className="chips-row">
            <b>Active scenario</b>
            {ops.length === 0 && <span className="muted">Baseline: the canonical season, including the live injury report.</span>}
            {ops.map((o) => (
              <span className="scen-chip" key={o.id}>
                {o.kind !== 'force' && <TeamLogo meta={m[o.team]} size={18} name={o.team} />}
                {o.label}
                <button aria-label={`Remove ${o.label}`} onClick={() => setOps((xs) => xs.filter((x) => x.id !== o.id))}><X size={14} /></button>
              </span>
            ))}
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
              <button className="btn" onClick={() => { setOps([]); setResult(null) }}><RotateCcw size={14} /> Restore baseline</button>
              <button className="btn primary" disabled={ops.length === 0 || run.isPending} onClick={() => run.mutate(undefined)}>
                <Play size={14} /> {run.isPending ? 'Simulating…' : `Run ${draws.toLocaleString()} seasons`}
              </button>
            </span>
          </div>
        </section>

        <div className="grid">
          <div className="c3">
            <Panel title="Scenario controls" icon={FlaskConical} flush action={<button className="btn ghost" onClick={() => setOps([])}>Reset all</button>}>
              <div className="ctl">
                <h3><Users size={16} /> Team</h3>
                <select className="field" value={teamId} aria-label="Team" onChange={(e) => { params.set('team', e.target.value); setParams(params, { replace: true }) }}>
                  {teams.slice().sort((a, b) => a.name.localeCompare(b.name)).map((t) => <option key={t.team_id} value={t.team_id}>{t.name}</option>)}
                </select>
              </div>

              <AbsenceControl lg={lg} roles={roles} teamId={teamId} abbr={shortName(teamId)} remaining={remaining.map((g) => g.start_time)} onAdd={add} />

              <ShiftControl teamId={teamId} abbr={shortName(teamId)} unit={lg.unit} onAdd={add} />

              <div className="ctl">
                <h3><Swords size={16} /> Force a result</h3>
                {remaining.length === 0 ? <span className="hint">No upcoming games for this team.</span> : remaining.slice(0, 10).map((g) => {
                  const opp = g.is_home ? g.away_id : g.home_id
                  const win = g.is_home ? 'home' : 'away'
                  const lose = g.is_home ? 'away' : 'home'
                  const id = `force-${g.event_id}`
                  const cur = ops.find((o) => o.id === id) as Extract<Op, { kind: 'force' }> | undefined
                  const set = (w: 'home' | 'away', verb: string) => add({ kind: 'force', id, event: g.event_id, winner: w, label: `${shortName(teamId)} ${verb} ${shortName(opp)}` })
                  return (
                    <div className="row" key={g.event_id} style={{ fontSize: 13 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 2 }}>
                        <span className="muted" style={{ width: 44 }}>{shortDate(g.start_time)}</span>
                        <TeamLogo meta={m[opp]} size={18} name={opp} />{g.is_home ? 'vs' : '@'} {shortName(opp)}
                      </span>
                      <div className="seg" style={{ flex: 'none' }}>
                        <button className={cur?.winner === win ? 'on' : ''} onClick={() => set(win, 'beat')}>Win</button>
                        <button className={cur?.winner === lose ? 'on' : ''} onClick={() => set(lose, 'lose to')}>Loss</button>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="ctl">
                <h3><Bot size={16} /> Ask in plain English</h3>
                <textarea value={ask} onChange={(e) => setAsk(e.target.value)} placeholder={`e.g. What if ${me?.name ?? 'this team'}'s starting quarterback misses the next three games?`} aria-label="Scenario question" />
                <button className="btn" disabled={ask.trim().length < 6 || asked.isPending} onClick={() => asked.mutate()}><Sparkles size={14} /> {asked.isPending ? 'Structuring + simulating…' : 'Ask and simulate'}</button>
                <span className="hint">Llama 3.3 70B only turns the question into typed operations; effect sizes come from the learned player-impact model.</span>
                {asked.error && <span className="err" style={{ padding: 0 }}>{(asked.error as Error).message.slice(0, 220)}</span>}
              </div>

              <div className="ctl">
                <h3><Cpu size={16} /> Simulation size</h3>
                <div className="seg">
                  {[5000, 10000, 25000, 50000].map((d) => <button key={d} className={draws === d ? 'on' : ''} onClick={() => setDraws(d)}>{d / 1000}k</button>)}
                </div>
              </div>
            </Panel>
          </div>

          <div className="c9">
            {run.error && <ErrorNote error={run.error} what="the simulation" />}
            {!result ? (
              <LabStart lg={lg} me={me} teams={teams} teamId={teamId} remaining={remaining} meta={m} shortName={shortName} busy={run.isPending}
                onRun={(list) => { setOps(list); run.mutate(list) }} />
            ) : <Results lg={lg} r={result} teamId={teamId} meta={m} />}
          </div>
        </div>
      </div>
    </>
  )
}

interface Regular { name: string; role: string; label: string; share: number | null; points: number; se: number; significant: boolean }

function AbsenceControl({ lg, roles, teamId, abbr, remaining, onAdd }: { lg: LeagueConfig; roles: Record<string, { points: number; se: number; t?: number; significant?: boolean }>; teamId: string; abbr: string; remaining: string[]; onAdd: (o: Op) => void }) {
  const regs = useQuery({ queryKey: ['regulars', lg.id, teamId], queryFn: () => getJSON<{ players: Regular[]; note?: string }>(`/entities/team/${lg.id}/${teamId}/regulars`), enabled: !!teamId, staleTime: 600_000 })
  const roleLabel = (r: string) => ({ QB: 'Starting QB', G: 'Starting goalie', KEY: 'Top-minutes player', RB1: 'Lead running back', WR1: 'Top receiver', DEF1: 'Top tackler' } as Record<string, string>)[r] ?? r
  // a named player per regular when we have them; otherwise the role menu
  const options = useMemo(() => {
    const ps = regs.data?.players ?? []
    if (ps.length) return ps.map((p) => ({ key: p.name, title: `${p.name} · ${p.label.replace(' of team ', ' of ')}`, points: p.points, se: p.se, significant: p.significant }))
    return Object.entries(roles).map(([k, v]) => ({ key: k, title: roleLabel(k), points: v.points, se: v.se, significant: v.significant !== false }))
  }, [regs.data, roles])
  const [pick, setPick] = useState('')
  const [games, setGames] = useState(1)
  useEffect(() => { if (options.length && !options.some((o) => o.key === pick)) setPick((options.find((o) => o.significant) ?? options[0]).key) }, [options.map((o) => o.key).join()])
  if (!options.length) return <div className="ctl"><h3><HeartPulse size={16} /> Player availability</h3><span className="hint">{regs.isLoading ? 'Loading this team’s regulars…' : `No learned player-impact model for ${lg.name}.`}</span></div>
  const o = options.find((x) => x.key === pick) ?? options[0]
  const n = Math.min(games, Math.max(remaining.length, 1))
  const end = remaining[n - 1] ? new Date(new Date(remaining[n - 1]).getTime() + 6 * 3600_000).toISOString() : new Date().toISOString()
  const sig = options.filter((x) => x.significant), est = options.filter((x) => !x.significant)
  const fmt = (x: typeof o) => `${x.title} · ${x.points > 0 ? '+' : '−'}${Math.abs(x.points).toFixed(1)}`
  return (
    <div className="ctl">
      <h3><HeartPulse size={16} /> Player availability</h3>
      <div className="row">
        <select className="field" value={o.key} onChange={(e) => setPick(e.target.value)} aria-label="Who is out">
          {sig.length > 0 && <optgroup label="Measured effect (applies in the live model)">{sig.map((x) => <option key={x.key} value={x.key}>{fmt(x)}</option>)}</optgroup>}
          {est.length > 0 && <optgroup label="Estimate only (not statistically significant)">{est.map((x) => <option key={x.key} value={x.key}>{fmt(x)}</option>)}</optgroup>}
        </select>
      </div>
      <label className="hint" htmlFor="absence-games">Out for the next <b style={{ color: 'var(--ink)' }}>{n}</b> game{n > 1 ? 's' : ''}</label>
      <input id="absence-games" type="range" min={1} max={Math.max(remaining.length, 1)} value={n} onChange={(e) => setGames(Number(e.target.value))} />
      <span className="hint">{o.significant
        ? <>Learned effect {o.points.toFixed(1)} ± {o.se.toFixed(1)} {lg.unit} per game (associational), from 2018–2026 box scores.</>
        : <>Estimate {o.points.toFixed(1)} ± {o.se.toFixed(1)} {lg.unit} per game. It isn’t statistically distinguishable from zero, so the live model doesn’t apply it; here it runs as a labelled what-if.</>}
        {regs.data?.note ? <> {regs.data.note}</> : null}</span>
      <button className="btn" onClick={() => onAdd({ kind: 'absence', id: `abs-${teamId}-${o.key}`, team: teamId, role: o.key, games: n, delta: o.points, end, label: `${abbr} ${o.key in roles ? roleLabel(o.key) : o.key} out ${n} game${n > 1 ? 's' : ''}${o.significant ? '' : ' (estimate)'}` })}><Plus size={14} /> Add to scenario</button>
    </div>
  )
}

function ShiftControl({ teamId, abbr, unit, onAdd }: { teamId: string; abbr: string; unit: string; onAdd: (o: Op) => void }) {
  const [d, setD] = useState(3)
  return (
    <div className="ctl">
      <h3><Scale size={16} /> Team-strength override</h3>
      <label className="hint" htmlFor="shift">Rest of season: <b style={{ color: d >= 0 ? 'var(--good)' : 'var(--bad)' }}>{d > 0 ? '+' : ''}{d} {unit}</b> per game</label>
      <input id="shift" type="range" min={-10} max={10} step={0.5} value={d} onChange={(e) => setD(Number(e.target.value))} />
      <button className="btn" disabled={d === 0} onClick={() => onAdd({ kind: 'shift', id: `shift-${teamId}`, team: teamId, delta: d, label: `${abbr} ${d > 0 ? '+' : ''}${d} ${unit} rest of season` })}><Plus size={14} /> Add to scenario</button>
    </div>
  )
}

function Results({ lg, r, teamId, meta }: { lg: LeagueConfig; r: SimResult; teamId: string; meta: Record<string, TeamMeta> }) {
  const q = qualify(lg)
  const tt = title(lg)
  const conf = lg.milestones.find((x) => x.key === 'conference_champion' || x.key === 'conference_title')
  const base = useMemo(() => Object.fromEntries(r.base.teams.map((t) => [t.team_id, t])), [r])
  const alt = useMemo(() => Object.fromEntries(r.scenario.teams.map((t) => [t.team_id, t])), [r])
  const focusId = alt[teamId] ? teamId : (r.deltas[0]?.team_id as string)
  const b = base[focusId], a = alt[focusId]
  const movers = r.deltas.slice(0, 5).map((d) => d.team_id as string)
  const v = (t: SeasonTeam | undefined, k: string) => Number(t?.[k] ?? 0)

  const field = useMemo(() => {
    const n = Math.min(16, Math.max(4, Math.round(r.scenario.teams.reduce((s, t) => s + v(t, q.key), 0))))
    const top = r.scenario.teams.slice().sort((x, y) => v(y, q.key) - v(x, q.key)).slice(0, n)
    return top.map((t, i) => ({ seed: i + 1, t, d: v(t, q.key) - v(base[t.team_id], q.key) }))
  }, [r])

  const confRows = useMemo(() => {
    if (!conf || !b) return []
    return r.scenario.teams.filter((t) => t.conference === b.conference).sort((x, y) => v(y, conf.key) - v(x, conf.key)).slice(0, 6)
  }, [r, b])

  const sentence = b && a ? (
    <>
      <strong>{a.name}</strong>: {q.short} odds {pct(v(b, q.key))} → <strong>{pct(v(a, q.key))}</strong> ({pp(v(a, q.key) - v(b, q.key))} pts),
      expected wins {num(b.expected_wins)} → <strong>{num(a.expected_wins)}</strong>, {lg.titleName.toLowerCase()} {pct(v(b, tt.key))} → <strong>{pct(v(a, tt.key))}</strong>.
      {r.deltas.filter((d) => d.team_id !== focusId).slice(0, 2).map((d) => (
        <span key={d.team_id as string}> {d.name as string} {Number(d[q.key] ?? 0) >= 0 ? 'gains' : 'loses'} {Math.abs(Number(d[q.key] ?? 0) * 100).toFixed(1)} pts of {q.short} odds.</span>
      ))}
    </>
  ) : null

  return (
    <div className="stack">
      <Panel title="Simulation results" icon={Gauge} action={<span className="muted" style={{ fontSize: 12.5 }}>{r.scenario.draws.toLocaleString()} seasons per branch · common random numbers</span>}>
        <div className="res-cards" style={{ ['--n' as string]: 6 }}>
          {movers.map((id) => (
            <div className="res-card" key={id}>
              <TeamLogo meta={meta[id]} name={alt[id]?.name} size={46} />
              <b><P p={v(alt[id], q.key)} digits={0} /></b>
              <span>{q.short} · {meta[id]?.abbreviation ?? alt[id]?.abbreviation}</span>
              <div className="d"><Delta d={v(alt[id], q.key) - v(base[id], q.key)} /></div>
            </div>
          ))}
          {b && a && (
            <div className="res-card" style={{ textAlign: 'left', display: 'grid', gap: 4, alignContent: 'center' }}>
              <span>{meta[focusId]?.abbreviation} expected wins <b style={{ fontSize: 22, display: 'inline' }}>{num(a.expected_wins)}</b> <Delta d={a.expected_wins - b.expected_wins} unit="raw" /></span>
              {conf && <span>{conf.short} <b style={{ fontSize: 18, display: 'inline' }}>{pct(v(a, conf.key))}</b> <Delta d={v(a, conf.key) - v(b, conf.key)} /></span>}
              <span>{tt.short} <b style={{ fontSize: 18, display: 'inline' }}>{pct(v(a, tt.key))}</b> <Delta d={v(a, tt.key) - v(b, tt.key)} /></span>
            </div>
          )}
        </div>
        {r.assumptions && r.assumptions.length > 0 && (
          <div style={{ marginTop: 12, display: 'grid', gap: 4 }}>
            {r.assumptions.map((x, i) => (
              <div key={i} className="factor"><Bot size={15} /><span>{x.team}: {x.kind === 'player_unavailable' ? `${x.position} unavailable` : 'strength shift'} until {String(x.until).slice(0, 10)}</span><span className="v">{Number(x.delta_points).toFixed(2)} <span className="muted">{x.delta_source}</span></span></div>
            ))}
            <span className="hint muted" style={{ fontSize: 12 }}>Parsed by {r.parser}{r.warnings?.length ? ` · ${r.warnings.join('; ')}` : ''}</span>
          </div>
        )}
      </Panel>

      <div className="grid">
        <div className="c7">
          <Panel title={`Projected ${q.short} field`} icon={Trophy} foot={`Teams ranked by scenario ${q.label.toLowerCase()} probability; field size = expected number of qualifiers. Change vs baseline in brackets.`}>
            <div className="bracket">
              {field.map(({ seed, t, d }) => (
                <div className="slot" key={t.team_id} style={t.team_id === focusId ? { borderColor: 'var(--accent)' } : undefined}>
                  <span className="sd">{seed}</span>
                  <TeamLogo meta={meta[t.team_id]} name={t.name} size={24} />
                  <b>{meta[t.team_id]?.short_name ?? t.name}</b>
                  <span><P p={v(t, q.key)} digits={0} /> <small><Delta d={d} digits={1} /></small></span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
        <div className="c5">
          {conf && b ? (
            <Panel title={`${(b.conference ?? '').replace(' Conference', '')} title odds`} icon={ListTree} flush>
              <table className="tbl">
                <thead><tr><th>Team</th><th className="num">Baseline</th><th className="num">Scenario</th><th className="num">Δ</th></tr></thead>
                <tbody>
                  {confRows.map((t) => (
                    <tr key={t.team_id} className={t.team_id === focusId ? 'focus' : ''}>
                      <td><div className="team-cell"><TeamLogo meta={meta[t.team_id]} size={20} name={t.name} /><span>{meta[t.team_id]?.short_name ?? t.name}</span></div></td>
                      <td className="num muted">{pct(v(base[t.team_id], conf.key))}</td>
                      <td className="num"><P p={v(t, conf.key)} /></td>
                      <td className="num"><Delta d={v(t, conf.key) - v(base[t.team_id], conf.key)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          ) : <Panel title="Conference odds" icon={ListTree}><Empty title="Not applicable" /></Panel>}
        </div>

        <div className="c7">
          <Panel title="Before vs after: most affected teams" icon={Scale} flush>
            <div className="tbl-wrap" style={{ maxHeight: 360 }}>
              <table className="tbl">
                <thead><tr><th>Team</th><th className="num">Exp. W</th><th className="num">{q.short}</th>{conf && <th className="num">{conf.short}</th>}<th className="num">{tt.short}</th></tr></thead>
                <tbody>
                  {r.deltas.slice(0, 12).map((d) => {
                    const id = d.team_id as string
                    return (
                      <tr key={id} className={id === focusId ? 'focus' : ''}>
                        <td><div className="team-cell"><TeamLogo meta={meta[id]} size={20} name={d.name as string} /><span>{meta[id]?.short_name ?? (d.name as string)}</span></div></td>
                        <td className="num">{num(base[id]?.expected_wins)} → <b>{num(alt[id]?.expected_wins)}</b></td>
                        <td className="num">{pct(v(base[id], q.key))} → <b>{pct(v(alt[id], q.key))}</b> <Delta d={v(alt[id], q.key) - v(base[id], q.key)} /></td>
                        {conf && <td className="num">{pct(v(base[id], conf.key))} → <b>{pct(v(alt[id], conf.key))}</b></td>}
                        <td className="num">{pct(v(base[id], tt.key))} → <b>{pct(v(alt[id], tt.key))}</b></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
        <div className="c5">
          <Panel title={`${meta[focusId]?.short_name ?? b?.name ?? ''} record distribution`} icon={Gauge}
            foot={<span className="legend"><span><i style={{ background: 'rgba(169,186,219,.45)' }} />Baseline</span><span><i style={{ background: '#2f8cff' }} />Scenario</span></span>}>
            {b && a ? <CompareDistribution base={b.win_hist} alt={a.win_hist} draws={r.scenario.draws} /> : <Empty title="Team not in this run" />}
          </Panel>
        </div>

        <div className="c4">
          <Panel title="Monte Carlo diagnostics" icon={Cpu}>
            <div className="diag" style={{ gridTemplateColumns: '1fr' }}>
              <div><span>Seasons per branch</span><b>{r.scenario.draws.toLocaleString()}</b></div>
              <div><span>Random seed (shared)</span><b>#{r.scenario.seed}</b></div>
              <div><span>Engine runtime</span><b>{num(r.base.diagnostics.runtime_s, 2)}s + {num(r.scenario.diagnostics.runtime_s, 2)}s</b></div>
              <div><span>Round trip</span><b>{(r.ms / 1000).toFixed(1)}s</b></div>
              <div><span>{q.short} std. error ({meta[focusId]?.abbreviation})</span><b>±{pct(Math.sqrt(Math.max(v(a, q.key) * (1 - v(a, q.key)), 0) / r.scenario.draws), 2)}</b></div>
              <div><span>Champions per draw</span><b className="up">{(r.scenario.diagnostics.champions_per_draw_min_max ?? ['-']).join('–')}</b></div>
              <div><span>Simulator</span><b>{r.scenario.simulator_version}</b></div>
            </div>
          </Panel>
        </div>
        <div className="c8">
          <Panel title="Scenario insight" icon={Lightbulb} foot="Written from the simulation output by a template; no language model generates these numbers.">
            <div className="insight">
              <h3>{r.label}</h3>
              {sentence}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

/** before a run: one-click scenarios built from this team's real schedule and players, plus the baseline they change */
function LabStart({ lg, me, teams, teamId, remaining, meta, shortName, busy, onRun }: {
  lg: LeagueConfig; me?: SeasonTeam; teams: SeasonTeam[]; teamId: string; remaining: { event_id: string; start_time: string; is_home: boolean; home_id: string; away_id: string; p_win: number | null; leverage_home?: number | null; leverage_away?: number | null }[]
  meta: Record<string, TeamMeta>; shortName: (id: string) => string; busy: boolean; onRun: (ops: Op[]) => void
}) {
  const regs = useQuery({ queryKey: ['regulars', lg.id, teamId], queryFn: () => getJSON<{ players: Regular[] }>(`/entities/team/${lg.id}/${teamId}/regulars`), enabled: !!teamId, staleTime: 600_000 })
  const q = qualify(lg)
  const me2 = (me ?? {}) as unknown as Record<string, number>
  const lev = (g: (typeof remaining)[number]) => Math.abs((g.is_home ? g.leverage_home : g.leverage_away) ?? 0)
  const endAfter = (n: number) => { const g = remaining[Math.min(n, remaining.length) - 1]; return g ? new Date(new Date(g.start_time).getTime() + 6 * 3600_000).toISOString() : new Date().toISOString() }
  const abbr = shortName(teamId)
  const force = (g: (typeof remaining)[number], win: boolean): Op => {
    const opp = g.is_home ? g.away_id : g.home_id
    return { kind: 'force', id: `force-${g.event_id}`, event: g.event_id, winner: (g.is_home === win ? 'home' : 'away'), label: `${abbr} ${win ? 'beat' : 'lose to'} ${shortName(opp)}` }
  }
  const presets: { title: string; sub: string; ops: Op[] }[] = []
  const qb = (regs.data?.players ?? []).find((p) => p.role === 'QB' || p.role === 'G' || p.role === 'KEY')
  if (qb && remaining.length) presets.push({ title: `${qb.name} out ${Math.min(3, remaining.length)} games`, sub: `${qb.label}, learned ${qb.points.toFixed(1)} pts per game`,
    ops: [{ kind: 'absence', id: `abs-${teamId}-${qb.name}`, team: teamId, role: qb.name, games: Math.min(3, remaining.length), delta: qb.points, end: endAfter(3), label: `${abbr} ${qb.name} out ${Math.min(3, remaining.length)} games` }] })
  const rb = (regs.data?.players ?? []).find((p) => p.role === 'RUSH' && p.significant)
  if (rb && remaining.length) presets.push({ title: `${rb.name} out for the season`, sub: `${rb.label}, ${rb.points.toFixed(1)} pts per game`,
    ops: [{ kind: 'absence', id: `abs-${teamId}-${rb.name}`, team: teamId, role: rb.name, games: remaining.length, delta: rb.points, end: endAfter(remaining.length), label: `${abbr} ${rb.name} out for the season` }] })
  const big = remaining.slice().sort((a, b) => lev(b) - lev(a))[0]
  if (big) {
    const opp = big.is_home ? big.away_id : big.home_id
    presets.push({ title: `Beat ${shortName(opp)}`, sub: `their biggest remaining game: ±${(lev(big) * 100).toFixed(0)} pts of ${q.short} odds`, ops: [force(big, true)] })
  }
  if (remaining[0]) presets.push({ title: `Lose the next game`, sub: `${remaining[0].is_home ? 'vs' : '@'} ${shortName(remaining[0].is_home ? remaining[0].away_id : remaining[0].home_id)}, currently ${pct(remaining[0].p_win ?? 0, 0)} to win`, ops: [force(remaining[0], false)] })
  if (remaining.length > 1) presets.push({ title: 'Win out', sub: `all ${remaining.length} remaining games`, ops: remaining.map((g) => force(g, true)) })
  const field = teams.slice().sort((a, b) => Number((b as unknown as Record<string, number>)[q.key] ?? 0) - Number((a as unknown as Record<string, number>)[q.key] ?? 0)).slice(0, 16)
  return (
    <div className="stack" style={{ height: '100%' }}>
      <Panel title="Try a scenario" icon={Gauge} foot="Each one sets the scenario and runs 10,000 seasons per branch with common random numbers. Or build your own on the left.">
        <div className="lab-presets">
          {presets.map((p) => (
            <button key={p.title} className="lab-preset" disabled={busy} onClick={() => onRun(p.ops)}>
              <b>{p.title}</b><span>{p.sub}</span>
            </button>
          ))}
          {!presets.length && <span className="hint">Pick a team with games left to see suggested scenarios.</span>}
        </div>
      </Panel>
      {me && (
        <Panel title={`${meta[teamId]?.short_name ?? me.name}: baseline the scenario changes`} icon={Gauge}>
          <div className="lab-base">
            <div><span className="kpi-label">Expected wins</span><b>{num(me.expected_wins, 1)}</b><small>90% range {me2.wins_p05}–{me2.wins_p95}</small></div>
            <div><span className="kpi-label">{q.label}</span><b><P p={Number(me2[q.key] ?? 0)} digits={1} /></b><small>baseline</small></div>
            <div><span className="kpi-label">{title(lg).label}</span><b><P p={Number(me2.champion ?? 0)} digits={1} /></b><small>baseline</small></div>
            <div><span className="kpi-label">Strength</span><b>{me.rating >= 0 ? '+' : ''}{me.rating.toFixed(1)}</b><small>± {me.rating_sd.toFixed(1)} pts</small></div>
          </div>
          <table className="tbl" style={{ marginTop: 10 }}>
            <thead><tr><th>Remaining game</th><th className="num">Win prob</th><th className="num">{q.short} swing</th></tr></thead>
            <tbody>{remaining.slice(0, 8).map((g) => {
              const opp = g.is_home ? g.away_id : g.home_id
              return <tr key={g.event_id}><td><span className="team-cell"><span className="muted" style={{ width: 48 }}>{shortDate(g.start_time)}</span><TeamLogo meta={meta[opp]} name={opp} size={18} />{g.is_home ? 'vs' : '@'} {shortName(opp)}</span></td>
                <td className="num"><P p={g.p_win} digits={0} /></td><td className="num">±{(lev(g) * 100).toFixed(1)} pts</td></tr>
            })}</tbody>
          </table>
        </Panel>
      )}
      <Panel title={`Projected ${q.short} field: baseline`} icon={Trophy} className="lab-fill">
        <div className="lab-field">
          {field.map((t, i) => (
            <div key={t.team_id} className={`lab-field-row ${t.team_id === teamId ? 'me' : ''}`}><span className="muted">{i + 1}</span><TeamLogo meta={meta[t.team_id]} name={t.name} size={18} /><span>{meta[t.team_id]?.short_name ?? t.name}</span><b><P p={Number((t as unknown as Record<string, number>)[q.key] ?? 0)} digits={0} /></b></div>
          ))}
        </div>
      </Panel>
    </div>
  )
}
