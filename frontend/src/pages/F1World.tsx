import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { BadgeCheck, CalendarDays, Car, Cpu, Flag, FlaskConical, Gauge, Lightbulb, Play, Plus, RotateCcw, Shuffle, Timer, Trophy, Users, Wrench, X } from 'lucide-react'
import { postJSON } from '../lib/api'
import { useF1, type F1Constructor as Ctor, type F1Driver, type F1Run } from '../lib/data'
import { ago, day, num, pct, shortDate } from '../lib/format'
import { Delta, Empty, ErrorNote, Kpis, Loading, P, Panel } from '../components/ui'
import { TitleOdds } from '../components/charts'

/** Team identity colours (livery), display only. */
const TEAM_COLORS: Record<string, string> = {
  mercedes: '#00d7b6', ferrari: '#ed1131', mclaren: '#f47600', red_bull: '#4781d7', rb: '#6c98ff', alpine: '#00a1e8',
  audi: '#c7c7c7', haas: '#b6babd', williams: '#1868db', aston_martin: '#229971', cadillac: '#d4af37',
}
const tc = (id: string) => TEAM_COLORS[id] ?? '#2f8cff'

function TeamChip({ id, name, size = 'md' }: { id: string; name?: string; size?: 'sm' | 'md' }) {
  return (
    <span className="team-cell" style={{ gap: 7 }}>
      <span aria-hidden style={{ width: size === 'sm' ? 4 : 5, height: size === 'sm' ? 14 : 20, borderRadius: 2, background: tc(id), flex: 'none' }} />
      <span>{name}</span>
    </span>
  )
}

function useF1Derived(run?: F1Run) {
  return useMemo(() => {
    if (!run) return null
    const ctorName = Object.fromEntries(run.constructors.map((c) => [c.constructor_id, c.name.replace(' F1 Team', '')]))
    const drivers = run.drivers.slice().sort((a, b) => b.points_now - a.points_now)
    const ctors = run.constructors.slice().sort((a, b) => b.points_now - a.points_now)
    const total = run.standings_round + run.remaining_races.length
    const sprints = run.remaining_races.filter((r) => r.sprint).length
    return { ctorName, drivers, ctors, total, sprints, next: run.remaining_races[0] }
  }, [run])
}

export function F1World() {
  const q = useF1()
  const d = useF1Derived(q.data)
  if (q.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (q.error || !q.data || !d) return <ErrorNote error={q.error} what="the F1 season run" />
  const run = q.data
  const leader = d.drivers[0], second = d.drivers[1]
  const titleRows = run.drivers.slice().sort((a, b) => b.title - a.title).slice(0, 8)

  return (
    <>
      <div className="hero">
        <div>
          <p className="hero-kicker">Know what matters before you watch.</p>
          <h1>F1: <em>2026 Season World</em></h1>
          <p>Every driver. Every race. A two-level driver + car model, simulated to the final flag 10,000 times.</p>
        </div>
        {titleRows[0] && <div className="hero-mark"><div><b>Drivers’ title favourite</b>{titleRows[0].name} · {run.draws.toLocaleString()} simulated seasons</div><span className="lead-odds">{pct(titleRows[0].title, 0)}</span></div>}
      </div>
      <div className="stack">
        <Kpis items={[
          { icon: Flag, label: 'Races completed', value: <>{run.standings_round}<small>of {d.total}</small></>, sub: `${pct(run.standings_round / d.total, 0)} of the season` },
          { icon: CalendarDays, label: 'Races remaining', value: run.remaining_races.length, sub: d.next ? `Next: ${d.next.name.replace(' Grand Prix', ' GP')}` : 'season complete' },
          { icon: Users, label: 'Teams tracked', value: run.constructors.length, sub: 'all constructors' },
          { icon: Car, label: 'Drivers modelled', value: run.entry_list?.drivers ?? run.drivers.length, sub: `entry list from round ${run.entry_list?.round ?? run.standings_round}` },
          { icon: Timer, label: 'Sprints remaining', value: d.sprints, sub: 'sprint points simulated' },
          { icon: Trophy, label: 'Championship lead', value: <>{leader.points_now - second.points_now}<small>pts</small></>, sub: `${leader.code} over ${second.code}`, gold: true },
        ]} />

        <div className="grid">
          <div className="c5"><NextRace run={run} ctorName={d.ctorName} /></div>
          <div className="c7"><DriversTable run={run} ctorName={d.ctorName} rows={d.drivers} /></div>

          <div className="c4">
            <Panel title="Drivers’ title odds" icon={Trophy} foot="Whiskers: 95% Monte Carlo interval.">
              <TitleOdds rows={titleRows.map((x) => ({ name: x.code, p: x.title, se: x.title_se, color: tc(x.constructor_id) }))} />
            </Panel>
          </div>
          <div className="c8"><ConstructorsTable rows={d.ctors} /></div>

          <div className="c8"><Calendar run={run} /></div>
          <div className="c4">
            <Panel title="Model health" icon={BadgeCheck} foot="Structural checks from this run. F1 ratings are fit by one-step predictive likelihood on past races.">
              <div className="diag" style={{ gridTemplateColumns: '1fr' }}>
                <div><span>Driver champions per draw</span><b className="up">{run.diagnostics.driver_champions_per_draw}</b></div>
                <div><span>Constructor champions per draw</span><b className="up">{run.diagnostics.constructor_champions_per_draw}</b></div>
                <div><span>Remaining races / sprints</span><b>{run.diagnostics.remaining_races} / {run.diagnostics.remaining_sprints}</b></div>
                <div><span>Engine runtime</span><b>{num(run.diagnostics.runtime_s, 3)}s</b></div>
                <div><span>Driver form persistence ρ</span><b>{run.rating_params.rho_driver}</b></div>
                <div><span>Car form persistence ρ</span><b>{run.rating_params.rho_car}</b></div>
                <div><span>Tie-break</span><b>FIA count-back</b></div>
              </div>
            </Panel>
          </div>
        </div>
        <div className="provenance"><span><b>Run</b> {run.run_id}</span><span><b>Rules</b> f1_rules_2026_v1</span><span><b>Sources</b> Jolpica results · OpenF1 sessions</span></div>
      </div>
    </>
  )
}

function NextRace({ run, ctorName }: { run: F1Run; ctorName: Record<string, string> }) {
  const r = run.remaining_races[0]
  if (!r) return <Panel title="This weekend" icon={Flag}><Empty title="Season complete" /></Panel>
  const byCode = Object.fromEntries(run.drivers.map((x) => [x.code, x]))
  const rows = Object.entries(r.win_probabilities).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const max = rows[0]?.[1] ?? 1
  return (
    <Panel title="This weekend: Grand Prix hub" icon={Flag} foot="Bars: probability of winning the Grand Prix, from 10,000 simulated races." action={<><span className="chip info">Round {r.round}{r.sprint ? ' · Sprint' : ''}</span><Link to="/f1/live" className="btn primary" style={{ height: 26 }}>Live track</Link></>}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
        <div style={{ fontFamily: 'var(--display)', fontWeight: 800, fontSize: 28, lineHeight: 1 }}>{r.name}</div>
        <div className="muted">{day(r.start)}</div>
      </div>
      {rows.map(([code, p]) => {
        const dr = byCode[code]
        return (
          <div key={code} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 54px', gap: 10, alignItems: 'center', padding: '4px 0' }}>
            <TeamChip id={dr?.constructor_id ?? ''} name={dr ? `${dr.name.split(' ').slice(-1)[0]}` : code} />
            <div className="bar" style={{ height: 12 }}><i style={{ width: `${(p / max) * 100}%`, background: tc(dr?.constructor_id ?? '') }} /></div>
            <b style={{ textAlign: 'right' }}>{pct(p, 0)}</b>
          </div>
        )
      })}
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{dr0(run, rows[0]?.[0], ctorName)}</div>
    </Panel>
  )
}
const dr0 = (run: F1Run, code: string | undefined, ctorName: Record<string, string>) => {
  const d = run.drivers.find((x) => x.code === code)
  return d ? `Favourite: ${d.name} (${ctorName[d.constructor_id]}) · driver ${num(d.rating, 2)} ± ${num(d.rating_sd, 2)}, reliability ${pct(d.reliability, 0)}` : ''
}

function DriversTable({ run, ctorName, rows }: { run: F1Run; ctorName: Record<string, string>; rows: F1Driver[] }) {
  return (
    <Panel title="Drivers’ championship outlook" icon={Trophy} flush foot={`Projected = expected final points with the 90% range across ${run.draws.toLocaleString()} simulated seasons.`}>
      <div className="tbl-wrap" style={{ maxHeight: 420 }}>
        <table className="tbl">
          <thead><tr><th>#</th><th>Driver</th><th>Team</th><th className="num">Points</th><th className="num">Projected</th><th className="num">Wins</th><th className="num">Title</th></tr></thead>
          <tbody>
            {rows.slice(0, 12).map((x, i) => (
              <tr key={x.driver_id}>
                <td className="rank">{i + 1}</td>
                <td><b>{x.name}</b> <span className="muted">{x.code}</span></td>
                <td><TeamChip id={x.constructor_id} name={ctorName[x.constructor_id]} size="sm" /></td>
                <td className="num">{x.points_now}</td>
                <td className="num">{num(x.expected_points, 0)} <span className="muted" style={{ fontSize: 12 }}>{x.points_p05}–{x.points_p95}</span></td>
                <td className="num">{x.wins_now} <span className="muted">→ {num(x.expected_wins, 1)}</span></td>
                <td className="num"><b><P p={x.title} se={x.title_se} /></b></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function ConstructorsTable({ rows }: { rows: Ctor[] }) {
  return (
    <Panel title="Constructors’ championship outlook" icon={Wrench} flush>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>#</th><th>Team</th><th className="num">Points</th><th className="num">Projected</th><th className="num">Car pace</th><th className="num">Reliability</th><th className="num">Title</th></tr></thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={c.constructor_id}>
                <td className="rank">{i + 1}</td>
                <td><Link to={`/f1/team/${c.constructor_id}`}><TeamChip id={c.constructor_id} name={c.name.replace(' F1 Team', '')} /></Link></td>
                <td className="num">{c.points_now}</td>
                <td className="num">{num(c.expected_points, 0)} <span className="muted" style={{ fontSize: 12 }}>{c.points_p05}–{c.points_p95}</span></td>
                <td className="num">{num(c.car_rating, 2)}</td>
                <td className="num">{pct(c.reliability, 0)}</td>
                <td className="num"><b><P p={c.title} se={c.title_se} /></b></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function Calendar({ run, filter }: { run: F1Run; filter?: string[] }) {
  const byCode = Object.fromEntries(run.drivers.map((x) => [x.code, x]))
  return (
    <Panel title="Remaining calendar" icon={CalendarDays} flush foot="Race-win probability for the three most likely winners of each Grand Prix.">
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Rd</th><th>Date</th><th>Grand Prix</th><th>Format</th><th>Favourites</th></tr></thead>
          <tbody>
            {run.remaining_races.map((r) => {
              const top = Object.entries(r.win_probabilities).filter(([c]) => !filter || filter.includes(c)).sort((a, b) => b[1] - a[1]).slice(0, 3)
              return (
                <tr key={r.round}>
                  <td className="rank">{r.round}</td>
                  <td className="muted">{shortDate(r.start)}</td>
                  <td><b>{r.name}</b></td>
                  <td>{r.sprint ? <span className="chip med">Sprint</span> : <span className="chip neutral">Race</span>}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 14 }}>
                      {top.map(([c, p]) => <span key={c}><TeamChip id={byCode[c]?.constructor_id ?? ''} name={`${c} ${pct(p, 0)}`} size="sm" /></span>)}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

export function F1Constructor({ id }: { id: string }) {
  const q = useF1()
  const d = useF1Derived(q.data)
  if (q.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (q.error || !q.data || !d) return <ErrorNote error={q.error} what="the F1 season run" />
  const run = q.data
  const c = run.constructors.find((x) => x.constructor_id === id)
  if (!c) return <Empty title="Unknown constructor" />
  const rank = d.ctors.findIndex((x) => x.constructor_id === id) + 1
  const drivers = run.drivers.filter((x) => x.constructor_id === id).sort((a, b) => b.points_now - a.points_now)
  const color = tc(id)
  const leaderGap = d.ctors[0].constructor_id === id ? c.points_now - d.ctors[1].points_now : c.points_now - d.ctors[0].points_now
  return (
    <div style={{ ['--hero-accent' as string]: color }}>
      <div className="hero"><div><h1>{c.name.replace(' F1 Team', '')}: <em>Season World</em></h1><p>Every remaining race, and what it means for the 2026 championship.</p></div></div>
      <div className="stack">
        <section className="team-band" style={{ ['--team-c' as string]: color, ['--team-glow' as string]: `${color}88`, gridTemplateColumns: 'auto repeat(4, auto) 1fr' }}>
          <div className="tb-name" style={{ paddingLeft: 22 }}><b>{c.name.replace(' F1 Team', '')}</b><span>Formula 1 team</span></div>
          <div className="tb-stat keep"><b>{rank}<small style={{ fontSize: 20 }}>{['st', 'nd', 'rd'][rank - 1] ?? 'th'}</small></b><span>Constructors</span></div>
          <div className="tb-stat"><b>{c.points_now}</b><span>Points</span></div>
          <div className="tb-stat"><b>{drivers.reduce((s, x) => s + x.wins_now, 0)}</b><span>Race wins</span></div>
          <div className="tb-stat"><b>{leaderGap > 0 ? '+' : ''}{leaderGap}</b><span>{rank === 1 ? 'lead' : 'to leader'}</span></div>
          <div className="tb-next"><Flag size={40} aria-hidden /><div><div className="k">Next race</div><b>{d.next?.name ?? 'Season complete'}</b><span>{d.next ? day(d.next.start) : ''}</span></div></div>
        </section>
        <Kpis items={[
          { icon: Trophy, label: 'Expected points', value: num(c.expected_points, 0), sub: `90% range ${c.points_p05}–${c.points_p95}`, gold: true },
          { icon: Trophy, label: 'Constructors’ title', value: <P p={c.title} se={c.title_se} />, sub: `±${pct(c.title_se, 2)} MC error` },
          ...drivers.slice(0, 2).map((x) => ({ icon: Users, label: `${x.code} drivers’ title`, value: <P p={x.title} se={x.title_se} />, sub: `${x.points_now} pts → ${num(x.expected_points, 0)}` })),
          { icon: Gauge, label: 'Car pace rating', value: num(c.car_rating, 2), sub: `#${1 + run.constructors.filter((x) => x.car_rating > c.car_rating).length} in the field` },
          { icon: Wrench, label: 'Reliability', value: pct(c.reliability, 0), sub: 'per-race finish probability' },
        ]} />
        <div className="grid">
          {drivers.map((x) => (
            <div className="c6" key={x.driver_id}>
              <Panel title={x.name} icon={Car} action={<span className="chip info">{x.code}</span>}>
                <div className="mu-figs" style={{ gridTemplateColumns: 'repeat(5, 1fr)', margin: 0 }}>
                  <div><b>{x.points_now}</b><span>Points</span></div>
                  <div><b>{x.wins_now}</b><span>Wins</span></div>
                  <div><b>{num(x.expected_podiums_remaining, 1)}</b><span>Exp. podiums left</span></div>
                  <div><b>{num(x.rating, 2)}</b><span>Driver ±{num(x.rating_sd, 2)}</span></div>
                  <div><b><P p={x.title} digits={1} /></b><span>Title</span></div>
                </div>
                <div className="kpi-label" style={{ margin: '12px 0 4px' }}>Final championship position</div>
                <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 70 }}>
                  {x.rank_dist.slice(0, 12).map((p, i) => (
                    <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: 'var(--ink-3)' }} title={`P${i + 1}: ${pct(p)}`}>
                      <div style={{ height: Math.max(2, p * 56), background: color, opacity: 0.35 + p * 0.65, borderRadius: '3px 3px 0 0' }} />
                      P{i + 1}
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          ))}
          <div className="c12"><Calendar run={run} filter={drivers.map((x) => x.code)} /></div>
        </div>
        <div className="provenance"><span><b>Run</b> {run.run_id}</span><span><b>Updated</b> {run.status}</span><Link className="link" to="/f1/lab"><FlaskConical size={13} /> Branch this season in the Lab</Link></div>
      </div>
    </div>
  )
}

type F1Op = { id: string; target: string; delta: number; label: string }

export function F1Lab() {
  const q = useF1()
  const d = useF1Derived(q.data)
  const [ops, setOps] = useState<F1Op[]>([])
  const [target, setTarget] = useState('')
  const [delta, setDelta] = useState(0.1)
  const [ask, setAsk] = useState('')
  const sim = useMutation({
    mutationFn: () => postJSON<any>('/competitions/f1/seasons/current/season-simulations', {
      label: ops.map((o) => o.label).join(' + '), draws: 10000, rating_shifts: ops.map((o) => ({ target_id: o.target, delta: o.delta })),
    }),
  })
  const asked = useMutation({ mutationFn: () => postJSON<any>('/competitions/f1/seasons/current/scenario/ask', { text: ask, draws: 10000 }) })
  if (q.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (q.error || !q.data || !d) return <ErrorNote error={q.error} what="the F1 season run" />
  const run = q.data
  const res = sim.data ?? (asked.data?.base ? asked.data : null)
  const tgt = target || run.constructors[1]?.constructor_id || ''
  const nameOf = (id: string) => d.ctorName[id] ?? run.drivers.find((x) => x.driver_id === id)?.name ?? id

  return (
    <>
      <div className="hero"><div><h1>F1: <em>Season Simulation Lab</em></h1><p>Branch the world. Simulate the rest of the season. Measure championship and constructor paths.</p></div></div>
      <div className="stack">
        <section className="panel"><div className="chips-row">
          <b>Active scenario</b>
          {ops.length === 0 && <span className="muted">Baseline: the canonical season.</span>}
          {ops.map((o) => <span className="scen-chip" key={o.id}>{o.label}<button aria-label="Remove" onClick={() => setOps((xs) => xs.filter((x) => x.id !== o.id))}><X size={14} /></button></span>)}
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => { setOps([]); sim.reset(); asked.reset() }}><RotateCcw size={14} /> Restore baseline</button>
            <button className="btn primary" disabled={!ops.length || sim.isPending} onClick={() => sim.mutate()}><Play size={14} /> {sim.isPending ? 'Simulating…' : 'Run 10,000 seasons'}</button>
          </span>
        </div></section>
        <div className="grid">
          <div className="c3">
            <Panel title="Scenario controls" icon={FlaskConical} flush>
              <div className="ctl">
                <h3><Wrench size={16} /> Car or driver pace</h3>
                <select className="field" value={tgt} onChange={(e) => setTarget(e.target.value)} aria-label="Target">
                  <optgroup label="Constructors (car)">{run.constructors.map((c) => <option key={c.constructor_id} value={c.constructor_id}>{c.name}</option>)}</optgroup>
                  <optgroup label="Drivers">{run.drivers.map((x) => <option key={x.driver_id} value={x.driver_id}>{x.name}</option>)}</optgroup>
                </select>
                <label className="hint" htmlFor="f1d">Pace change: <b style={{ color: delta >= 0 ? 'var(--good)' : 'var(--bad)' }}>{delta > 0 ? '+' : ''}{delta.toFixed(2)}</b> rating units (field sd ≈ 0.10)</label>
                <input id="f1d" type="range" min={-0.3} max={0.3} step={0.02} value={delta} onChange={(e) => setDelta(Number(e.target.value))} />
                <button className="btn" disabled={delta === 0} onClick={() => setOps((xs) => [...xs.filter((x) => x.id !== tgt), { id: tgt, target: tgt, delta, label: `${nameOf(tgt)} ${delta > 0 ? '+' : ''}${delta.toFixed(2)} pace` }])}><Plus size={14} /> Add to scenario</button>
              </div>
              <div className="ctl">
                <h3><Lightbulb size={16} /> Ask in plain English</h3>
                <textarea value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="e.g. What if Ferrari's upgrade adds a tenth of pace?" aria-label="Scenario question" />
                <button className="btn" disabled={ask.trim().length < 6 || asked.isPending} onClick={() => asked.mutate()}>{asked.isPending ? 'Structuring + simulating…' : 'Ask and simulate'}</button>
                {asked.data && !asked.data.base && <span className="err" style={{ padding: 0 }}>{asked.data.warnings?.join('; ') || 'Not a supported F1 scenario.'}</span>}
              </div>
            </Panel>
          </div>
          <div className="c9">
            {!res ? (
              <Panel title="Simulation results" icon={Gauge}><Empty title="Build a scenario, then run it">Shift a car’s or a driver’s pace and watch both championships respond. Both branches share random numbers.</Empty></Panel>
            ) : (
              <div className="stack">
                <Panel title="Simulation results" icon={Shuffle} action={<span className="muted" style={{ fontSize: 12.5 }}>10,000 seasons per branch · common random numbers</span>}>
                  <div className="res-cards" style={{ ['--n' as string]: 5 }}>
                    {res.scenario.drivers.slice().sort((a: F1Driver, b: F1Driver) => b.title - a.title).slice(0, 5).map((x: F1Driver) => {
                      const b0 = res.base.drivers.find((y: F1Driver) => y.driver_id === x.driver_id)
                      return (
                        <div className="res-card" key={x.driver_id} style={{ borderTop: `3px solid ${tc(x.constructor_id)}` }}>
                          <b><P p={x.title} digits={0} /></b><span>{x.name}</span>
                          <div className="d"><Delta d={x.title - (b0?.title ?? 0)} /></div>
                          <span>{num(x.expected_points, 0)} pts <Delta d={x.expected_points - (b0?.expected_points ?? 0)} unit="raw" digits={0} /></span>
                        </div>
                      )
                    })}
                  </div>
                </Panel>
                <Panel title="Before vs after: constructors" icon={Wrench} flush>
                  <table className="tbl">
                    <thead><tr><th>Team</th><th className="num">Exp. points</th><th className="num">Title</th></tr></thead>
                    <tbody>
                      {res.scenario.constructors.map((c: Ctor) => {
                        const b0 = res.base.constructors.find((y: Ctor) => y.constructor_id === c.constructor_id)
                        return (
                          <tr key={c.constructor_id}>
                            <td><TeamChip id={c.constructor_id} name={c.name.replace(' F1 Team', '')} /></td>
                            <td className="num">{num(b0?.expected_points, 0)} → <b>{num(c.expected_points, 0)}</b> <Delta d={c.expected_points - (b0?.expected_points ?? 0)} unit="raw" digits={0} /></td>
                            <td className="num">{pct(b0?.title)} → <b>{pct(c.title)}</b></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </Panel>
                <Panel title="Monte Carlo diagnostics" icon={Cpu}>
                  <div className="diag">
                    <div><span>Seasons per branch</span><b>{res.scenario.draws?.toLocaleString?.() ?? '10,000'}</b></div>
                    <div><span>Driver champions per draw</span><b className="up">{res.scenario.diagnostics?.driver_champions_per_draw}</b></div>
                    <div><span>Runtime</span><b>{num(res.scenario.diagnostics?.runtime_s, 2)}s</b></div>
                    <div><span>Updated</span><b>{ago(new Date().toISOString())}</b></div>
                  </div>
                </Panel>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
