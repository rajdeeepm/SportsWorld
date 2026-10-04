import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getJSON } from '../lib/api'
import { WhyItMatters } from '../components/stakes'
import { Link } from 'react-router-dom'
import {
  BadgeCheck, CalendarClock, CalendarDays, Gauge, HeartPulse, Layers3, ListChecks, Newspaper, Radio, Shuffle, Swords, Trophy, Users, Zap,
} from 'lucide-react'
import { useAvailability, useBoard, useMeta, useRolling, useSeason, useSeasonSummary, useStatus, useUpdates, type BoardRow, type SeasonTeam, type TeamMeta, type WorldUpdate } from '../lib/data'
import { qualify, title, type LeagueConfig } from '../lib/leagues'
import { ago, day, num, pct, time } from '../lib/format'
import { Empty, ErrorNote, Kpis, Loading, P, Panel, TeamLogo, teamColor } from '../components/ui'
import { GamesTable, maxLeverage } from '../components/games'
import { TitleOdds } from '../components/charts'
import { ListenButton, RadioToggle } from '../components/radio'

export function LeagueWorld({ lg }: { lg: LeagueConfig }) {
  const status = useStatus(lg.id)
  const season = useSeason(lg.id)
  const board = useBoard(lg.id)
  const meta = useMeta(lg.id)
  const m = meta.data ?? {}

  if (status.data && !status.data.run_id && !season.data) return <NoSeason lg={lg} />

  const events = board.data?.events ?? []
  const d = season.data?.diagnostics ?? status.data?.diagnostics ?? {}
  const played = d.played_games ?? 0
  const remaining = d.remaining_games ?? events.length
  const live = events.filter((e) => e.state === 'in').length
  const teams = season.data?.teams ?? []

  return (
    <>
      <div className="hero">
        <div>
          <p className="hero-kicker">Know what matters before you watch.</p>
          <h1>{lg.name}: <em>{lg.seasonLabel} Season World</em></h1>
          <p>SportsWorld plays out the rest of the season 10,000 times, so every game shows what it means for the playoff race, not just who is favoured. Updated as results land.</p>
          <div className="hero-actions"><ListenButton league={lg.id} label="Listen to the briefing" /><RadioToggle league={lg.id} /></div>
        </div>
        {teams[0] && (
          <Link to={`/${lg.id}/team/${teams[0].team_id}`} className="hero-mark" title={`${lg.titleName} favourite`}>
            <div>
              <b>{lg.titleName} favourite</b>
              {m[teams[0].team_id]?.short_name ?? teams[0].name} · {season.data?.draws.toLocaleString()} seasons, updated {season.data ? ago(season.data.as_of) : ''}
            </div>
            <TeamLogo meta={m[teams[0].team_id]} name={teams[0].name} size={64} />
            <span className="lead-odds">{pct(Number(teams[0].champion ?? 0), 0)}</span>
          </Link>
        )}
      </div>

      <div className="stack">
        <Kpis items={[
          { icon: ListChecks, label: 'Games played', value: played.toLocaleString(), sub: played + remaining ? `${pct(played / (played + remaining), 0)} of regular season` : undefined },
          { icon: CalendarDays, label: 'Games remaining', value: remaining.toLocaleString(), sub: d.contingent_postseason_events ? `+${d.contingent_postseason_events} postseason` : 'regular season' },
          { icon: Users, label: 'Teams tracked', value: teams.length || '-', sub: lg.id === 'college-football' ? 'all FBS teams' : lg.college ? 'all Division I teams' : `all ${lg.name} teams` },
          { icon: Radio, label: 'Live games', value: <span style={{ color: live ? 'var(--live)' : undefined }}>{live}</span>, sub: live ? 'feeding the season run' : 'none right now' },
          { icon: Gauge, label: 'Forecast coverage', value: remaining ? pct(events.filter((e) => e.p_home != null).length / Math.max(events.length, 1), 0) : '-', sub: `${events.length.toLocaleString()} games forecast` },
          { icon: Shuffle, label: 'Simulated seasons', value: season.data ? season.data.draws.toLocaleString() : '-', sub: season.data ? `state v${season.data.global_state_version} · ${d.runtime_s ?? '-'}s` : '' },
        ]} />

        <WhyItMatters league={lg.id} headline />

        <div className="grid">
          <div className="c7"><FeaturedMatchups lg={lg} events={events} meta={m} loading={board.isLoading} /></div>
          <div className="c5"><TitleOutlook lg={lg} teams={teams} meta={m} loading={season.isLoading} error={season.error} /></div>

          <div className="c4"><SwingGames lg={lg} events={events} meta={m} /></div>
          <div className="c4">
            <Panel title={`${lg.titleName} odds`} icon={Trophy} foot="Bars: share of 10,000 simulated seasons. Whiskers: 95% Monte Carlo interval.">
              {season.isLoading ? <Loading /> : (
                <TitleOdds rows={teams.slice(0, 10).map((t) => ({
                  name: m[t.team_id]?.abbreviation ?? t.abbreviation ?? t.name.slice(0, 4),
                  p: Number(t.champion ?? 0), se: Number(t.champion_se ?? 0), color: teamColor(m[t.team_id]),
                }))} />
              )}
            </Panel>
          </div>
          <div className="c4"><WorldUpdates lg={lg} meta={m} /></div>

          <div className="c8"><ConferenceRace lg={lg} teams={teams} meta={m} /></div>
          <div className="c4"><InjuryImpact lg={lg} meta={m} /></div>

          <div className="c12"><Scorecard lg={lg} meta={m} /></div>
          <div className="c12"><ModelHealth lg={lg} diag={d} /></div>
        </div>
      </div>
    </>
  )
}

function NoSeason({ lg }: { lg: LeagueConfig }) {
  return (
    <>
      <div className="hero"><div><h1>{lg.name}: <em>{lg.seasonLabel} Season World</em></h1><p>Know what matters before you watch.</p></div></div>
      <Panel title="Season not started" icon={CalendarClock}>
        <Empty title={`The ${lg.seasonLabel} ${lg.name} season run starts with the first scheduled game.`}>
          The tracker is watching ESPN for the schedule. As soon as games are listed, SportsWorld builds the season, simulates it 10,000 times, and this page fills in. Last season is available in Research → historical replay.
        </Empty>
      </Panel>
    </>
  )
}

function FeaturedMatchups({ lg, events, meta, loading }: { lg: LeagueConfig; events: BoardRow[]; meta: Record<string, TeamMeta>; loading: boolean }) {
  const days = useMemo(() => {
    const map = new Map<string, BoardRow[]>()
    for (const e of events) {
      const k = new Date(e.start_time).toDateString()
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(e)
    }
    return [...map.entries()].slice(0, 7)
  }, [events])
  const [sel, setSel] = useState(0)
  const games = (days[sel]?.[1] ?? [])
    .slice()
    .filter((g) => g.state !== 'post')
    .sort((a, b) => maxLeverage(b) - maxLeverage(a) || (b.state === 'in' ? 1 : 0) - (a.state === 'in' ? 1 : 0))
    .slice(0, 10)

  return (
    <Panel title="Featured matchups" icon={Swords} flush
      action={<Link to={`/${lg.id}/games`} className="link">Full schedule</Link>}
      foot={<>The day’s 10 biggest games by season leverage: how much each result moves the teams’ headline odds. <Link className="link" to={`/${lg.id}/games?live=1`}>All live games</Link></>}>
      {loading ? <div style={{ padding: 14 }}><Loading rows={6} /></div> : days.length === 0 ? <Empty title="No upcoming games on the board" /> : (
        <>
          <div className="day-tabs" role="tablist">
            {days.map(([k, g], i) => (
              <button key={k} role="tab" aria-selected={i === sel} className={i === sel ? 'on' : ''} onClick={() => setSel(i)}>
                <b>{i === 0 && new Date(k).toDateString() === new Date().toDateString() ? 'Today' : day(g[0].start_time).split(',')[0]}</b>
                {new Date(g[0].start_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · {g.length}
              </button>
            ))}
          </div>
          <GamesTable lg={lg} games={games} meta={meta} />
        </>
      )}
    </Panel>
  )
}

function TitleOutlook({ lg, teams, meta, loading, error }: { lg: LeagueConfig; teams: SeasonTeam[]; meta: Record<string, TeamMeta>; loading: boolean; error: unknown }) {
  const q = qualify(lg)
  const t = title(lg)
  const mid = lg.milestones.find((x) => x.key === 'conference_champion' || x.key === 'conference_title' || x.key === 'final_four')
  return (
    <Panel title={`${lg.titleName} outlook`} icon={Trophy} flush action={<Link to={`/${lg.id}/standings`} className="link">All teams</Link>}>
      {loading ? <div style={{ padding: 14 }}><Loading rows={8} /></div> : error ? <ErrorNote error={error} what="the season run" /> : (
        <div className="tbl-wrap" style={{ maxHeight: 430 }}>
          <table className="tbl">
            <thead><tr><th>#</th><th>Team</th><th className="num">Exp. W</th><th className="num">{q.short}</th>{mid && <th className="num">{mid.short}</th>}<th className="num">{t.short}</th></tr></thead>
            <tbody>
              {teams.slice(0, 12).map((x, i) => (
                <tr key={x.team_id}>
                  <td className="rank">{i + 1}</td>
                  <td><Link to={`/${lg.id}/team/${x.team_id}`} className="team-cell"><TeamLogo meta={meta[x.team_id]} name={x.name} size={22} /><span>{meta[x.team_id]?.short_name ?? x.name}</span></Link></td>
                  <td className="num">{num(x.expected_wins)}</td>
                  <td className="num"><P p={x[q.key] as number} se={x[`${q.key}_se`] as number} /></td>
                  {mid && <td className="num">{/independ/i.test(x.conference ?? '') && mid.key.startsWith('conference') ? <span className="p-faint" title="Independent: no conference title">-</span> : <P p={x[mid.key] as number} se={x[`${mid.key}_se`] as number} />}</td>}
                  <td className="num"><b><P p={x[t.key] as number} se={x[`${t.key}_se`] as number} /></b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function SwingGames({ lg, events, meta }: { lg: LeagueConfig; events: BoardRow[]; meta: Record<string, TeamMeta> }) {
  const horizon = Date.now() + 15 * 86400_000
  const top = events.filter((e) => new Date(e.start_time).getTime() < horizon).sort((a, b) => maxLeverage(b) - maxLeverage(a)).slice(0, 7)
  const q = qualify(lg)
  return (
    <Panel title="Games that move the race" icon={Zap} flush foot={`Next 15 days, ranked by the swing in ${q.short} odds between winning and losing.`}>
      {top.length === 0 ? <Empty title="No games in the next 15 days" /> : (
        <table className="tbl">
          <tbody>
            {top.map((g) => {
              const homeSide = Math.abs(g.leverage_home ?? 0) >= Math.abs(g.leverage_away ?? 0)
              const id = homeSide ? g.home_id : g.away_id
              const name = homeSide ? g.home : g.away
              return (
                <tr key={g.event_id}>
                  <td className="muted" style={{ width: 54 }}>{new Date(g.start_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
                  <td>
                    <div className="team-cell"><TeamLogo meta={meta[g.away_id]} size={20} name={g.away} /><span style={{ fontSize: 12.5 }}>{meta[g.away_id]?.abbreviation ?? g.away_abbr}</span>
                      <span className="muted">@</span><TeamLogo meta={meta[g.home_id]} size={20} name={g.home} /><span style={{ fontSize: 12.5 }}>{meta[g.home_id]?.abbreviation ?? g.home_abbr}</span></div>
                  </td>
                  <td className="num" title={`${name}: ${q.label} odds differ by ${((homeSide ? g.leverage_home : g.leverage_away)! * 100).toFixed(1)} points between a win and a loss`}>
                    <span className="muted" style={{ fontSize: 12 }}>{meta[id]?.abbreviation ?? name} </span>
                    <b style={{ color: 'var(--warn)' }}>±{(maxLeverage(g) * 100).toFixed(1)}</b><span className="muted" style={{ fontSize: 11 }}> pts</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </Panel>
  )
}

function updateKind(u: WorldUpdate): { cls: string; Icon: typeof Zap; label: string } {
  if (u.news) return { cls: 'news', Icon: Newspaper, label: 'News' }
  if (/availability|injur/i.test(u.reason)) return { cls: 'injury', Icon: HeartPulse, label: 'Availability' }
  if (/final/i.test(u.reason)) return { cls: 'final', Icon: BadgeCheck, label: 'Final' }
  return { cls: '', Icon: Layers3, label: 'Update' }
}

function WorldUpdates({ lg, meta, team }: { lg: LeagueConfig; meta: Record<string, TeamMeta>; team?: string }) {
  const updates = useUpdates(lg.id)
  const rows = (updates.data ?? [])
    .filter((u) => !u.news || (u.news.player && u.news.category !== 'other'))
    .filter((u) => !team || u.teams?.includes(team))
    .slice()
    .reverse()
    .slice(0, 9)
  return (
    <Panel title="Live world updates" icon={Radio} flush>
      {updates.isLoading ? <div style={{ padding: 14 }}><Loading /></div> : rows.length === 0 ? <Empty title="No updates yet this session">Finals, injury-report changes and grounded news appear here as they arrive.</Empty> : (
        <ul className="feed">
          {rows.map((u, i) => {
            const k = updateKind(u)
            return (
              <li key={`${u.at}-${i}`}>
                <time dateTime={u.at}>{time(u.at)}</time>
                <k.Icon className={`ic ${k.cls}`} size={16} aria-hidden />
                <p>
                  {u.news ? <>{u.news.player ? <b>{u.news.player}</b> : null} {u.news.status ?? ''} <span className="muted">({u.news.team})</span></> : u.reason}
                  <small>
                    {u.news ? <>“{u.news.evidence_span}” · <a className="src" href={u.news.source_url} target="_blank" rel="noreferrer">source</a> · display only, not a model input</> : <>state v{u.global_state_version} · {u.teams?.map((t) => meta[t]?.abbreviation ?? t).join(', ')}</>}
                  </small>
                </p>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
export { WorldUpdates }

const SHORT_CONF: Record<string, string> = {
  'American Football Conference': 'AFC', 'National Football Conference': 'NFC', 'Eastern Conference': 'East', 'Western Conference': 'West',
}

function ConferenceRace({ lg, teams, meta }: { lg: LeagueConfig; teams: SeasonTeam[]; meta: Record<string, TeamMeta> }) {
  const groups = useMemo(() => {
    const map = new Map<string, SeasonTeam[]>()
    for (const t of teams) {
      const c = t.conference ?? 'Independent'
      if (!map.has(c)) map.set(c, [])
      map.get(c)!.push(t)
    }
    return [...map.entries()]
  }, [teams])
  const q = qualify(lg)

  if (!lg.college) {
    // pro leagues: two conference tables with the expected qualifier cut line
    return (
      <Panel title={`${SHORT_CONF[groups[0]?.[0]] ?? 'Conference'} / ${SHORT_CONF[groups[1]?.[0]] ?? ''} ${q.short.toLowerCase()} outlook`} icon={Layers3} flush
        foot={`Dashed line: expected number of ${q.short.toLowerCase()} qualifiers per conference (sum of probabilities).`}>
        <div className="grid" style={{ gap: 0 }}>
          {groups.slice(0, 2).map(([conf, ts]) => {
            const rows = ts.slice().sort((a, b) => Number(b[q.key] ?? 0) - Number(a[q.key] ?? 0))
            const cut = Math.round(rows.reduce((s, t) => s + Number(t[q.key] ?? 0), 0))
            return (
              <div className="c6" key={conf} style={{ borderRight: '1px solid rgba(22,48,90,.6)' }}>
                <div className="tbl-wrap" style={{ maxHeight: 420 }}>
                  <table className="tbl">
                    <thead><tr><th>#</th><th>{SHORT_CONF[conf] ?? conf}</th><th className="num">Exp. W</th><th className="num">{q.short}</th><th className="num">Conf.</th><th className="num">{title(lg).short}</th></tr></thead>
                    <tbody>
                      {rows.slice(0, 12).map((t, i) => (
                        <tr key={t.team_id} className={i + 1 === cut ? 'cut' : ''}>
                          <td className="rank">{i + 1}</td>
                          <td><Link to={`/${lg.id}/team/${t.team_id}`} className="team-cell"><TeamLogo meta={meta[t.team_id]} name={t.name} size={20} /><span>{meta[t.team_id]?.short_name ?? t.name}</span></Link></td>
                          <td className="num">{num(t.expected_wins)}</td>
                          <td className="num"><P p={t[q.key] as number} /></td>
                          <td className="num"><P p={t.conference_title as number} /></td>
                          <td className="num"><P p={t.champion as number} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
        </div>
      </Panel>
    )
  }

  // college: one row per conference, leader and challenger by conference-title probability
  const key = lg.milestones.find((m) => m.key === 'conference_champion')?.key
  const rows = groups
    .filter(([conf]) => !(key && /independ/i.test(conf)))
    .map(([conf, ts]) => {
      const sorted = ts.slice().sort((a, b) => (key ? Number(b[key] ?? 0) - Number(a[key] ?? 0) : 0) || Number(b[q.key] ?? 0) - Number(a[q.key] ?? 0))
      return { conf, top: sorted.slice(0, 3), best: Math.max(...ts.map((t) => Number(t[q.key] ?? 0))) }
    })
    .sort((a, b) => b.best - a.best)
    .slice(0, 12)
  return (
    <Panel title="Conference race outlook" icon={Layers3} flush foot={key ? 'Conference-title probability for the three leading contenders in each conference.' : `Top three ${q.short} contenders per conference.`}>
      <div className="tbl-wrap" style={{ maxHeight: 440 }}>
        <table className="tbl">
          <thead><tr><th>Conference</th><th>Favourite</th><th className="num">{key ? 'Conf. title' : q.short}</th><th>Contenders</th><th className="num">Best {q.short}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.conf}>
                <td><b>{r.conf.replace(' Conference', '')}</b></td>
                <td><Link to={`/${lg.id}/team/${r.top[0].team_id}`} className="team-cell"><TeamLogo meta={meta[r.top[0].team_id]} name={r.top[0].name} size={22} /><span>{meta[r.top[0].team_id]?.short_name ?? r.top[0].name}</span></Link></td>
                <td className="num" style={{ minWidth: 120 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                    <div className="bar" style={{ width: 60 }}><i style={{ width: `${Number(r.top[0][key ?? q.key] ?? 0) * 100}%`, background: teamColor(meta[r.top[0].team_id]) }} /></div>
                    <P p={r.top[0][key ?? q.key] as number} />
                  </div>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 10 }}>
                    {r.top.slice(1).map((t) => (
                      <Link key={t.team_id} to={`/${lg.id}/team/${t.team_id}`} className="team-cell" title={t.name}>
                        <TeamLogo meta={meta[t.team_id]} name={t.name} size={18} />
                        <span className="muted" style={{ fontSize: 12.5 }}>{meta[t.team_id]?.abbreviation ?? t.abbreviation} {pct(Number(t[key ?? q.key] ?? 0), 0)}</span>
                      </Link>
                    ))}
                  </div>
                </td>
                <td className="num"><P p={r.best} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function InjuryImpact({ lg, meta }: { lg: LeagueConfig; meta: Record<string, TeamMeta> }) {
  const av = useAvailability(lg.id)
  const rows = (av.data?.teams ?? []).slice(0, 8)
  return (
    <Panel title="Injury report → strength" icon={HeartPulse} flush
      foot={av.data ? <>ESPN injury report, refreshed {ago(av.data.fetched_at)}. Effect sizes are learned; status→availability is a labelled prior.</> : undefined}>
      {av.isLoading ? <div style={{ padding: 14 }}><Loading /></div> : av.isError ? <Empty title="No injury model for this league" /> : rows.length === 0 ? (
        <Empty title="No key players listed out">Starting {lg.sport === 'football' ? 'quarterbacks' : lg.sport === 'hockey' ? 'goalies' : 'rotation players'} are all available on the current report.</Empty>
      ) : (
        <table className="tbl">
          <thead><tr><th>Team</th><th>Player</th><th>Status</th><th className="num">Δ strength</th></tr></thead>
          <tbody>
            {rows.map((t) => t.absences.map((a, i) => (
              <tr key={`${t.team_id}-${a.player}`}>
                <td>{i === 0 && <Link to={`/${lg.id}/team/${t.team_id}`} className="team-cell"><TeamLogo meta={meta[t.team_id]} name={t.team} size={20} /><span>{meta[t.team_id]?.abbreviation ?? t.team}</span></Link>}</td>
                <td>{a.player} <span className="tag">{a.role}</span></td>
                <td><span className={`chip ${a.p_play === 0 ? 'high' : 'med'}`}>{a.status}</span></td>
                <td className="num down">{a.delta_points.toFixed(1)}</td>
              </tr>
            )))}
          </tbody>
        </table>
      )}
    </Panel>
  )
}

function ModelHealth({ lg, diag }: { lg: LeagueConfig; diag: Record<string, any> }) {
  const ss = useSeasonSummary()
  const rolling = useRolling()
  const rows = (ss.data?.summary ?? []).filter((r: any) => r.league === lg.id && r.checkpoint === 0)
  const dyn = rows.find((r: any) => r.mode === 'dynamic')
  const fast = rows.find((r: any) => r.mode === 'fast')
  const roll = (rolling.data ?? []).find((r: any) => r.league === lg.id)
  const item = (label: string, value: React.ReactNode, sub: React.ReactNode, good?: boolean) => (
    <div style={{ padding: '12px 16px', borderLeft: '1px solid rgba(22,48,90,.6)' }}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ fontSize: 28, color: good == null ? undefined : good ? 'var(--good)' : 'var(--warn)' }}>{value}</div>
      <div className="kpi-sub" style={{ whiteSpace: 'normal' }}>{sub}</div>
    </div>
  )
  return (
    <Panel title="Model health & calibration" icon={BadgeCheck} flush action={<Link to="/research" className="link">Full research</Link>}
      foot={dyn ? `Point-in-time replays of ${dyn.seasons?.[0]}–${dyn.seasons?.[dyn.seasons.length - 1]} preseason; rolling-origin = train on earlier seasons, test on the next.` : 'Backtests load from data/fixtures/backtests.'}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
        {item('90% win-band coverage', dyn ? pct(dyn.wins_90_coverage, 0) : '-', fast ? <>target 90% · independent-game sim only {pct(fast.wins_90_coverage, 0)}</> : 'historical replay', dyn ? Math.abs(dyn.wins_90_coverage - 0.9) < 0.06 : undefined)}
        {item('Win-total error', dyn ? num(dyn.wins_mae, 2) : '-', dyn ? <>mean abs. error, vs {num(dyn.wins_mae_pace_baseline, 2)} for a pace baseline</> : '', dyn ? dyn.wins_mae < dyn.wins_mae_pace_baseline : undefined)}
        {item('Champion log loss', dyn ? num(dyn.champion_log_loss, 2) : '-', dyn ? <>vs {num(dyn.champion_uniform_log_loss, 2)} for picking uniformly</> : '', dyn ? dyn.champion_log_loss < dyn.champion_uniform_log_loss : undefined)}
        {item('Game model log loss', roll ? num(roll.model_log_loss_mean, 3) : '-', roll ? <>walk-forward mean ± {num(roll.model_log_loss_sd, 3)}; state-space only {num(roll.kalman_only_log_loss_mean, 3)}</> : 'rolling-origin evaluation', roll ? roll.model_log_loss_mean <= roll.kalman_only_log_loss_mean : undefined)}
        {item('Champions per draw', diag.champions_per_draw_min_max ? diag.champions_per_draw_min_max.join('–') : '-', 'structural check: exactly one title winner in every simulated season', diag.champions_per_draw_min_max?.[0] === 1)}
        {item('Board ↔ season consistency', diag.board_vs_sim_expected_wins_mad != null ? num(diag.board_vs_sim_expected_wins_mad, 2) : '-', 'mean |Δ expected wins| between game forecasts and the season simulation', diag.board_vs_sim_expected_wins_mad != null ? diag.board_vs_sim_expected_wins_mad < 0.3 : undefined)}
      </div>
    </Panel>
  )
}

interface ScoreMetrics { games: number; log_loss: number; brier: number; accuracy: number }
interface ScoreRow { event_id: string; home: string; away: string; home_id: string; away_id: string; home_score: number; away_score: number; home_won: boolean; sportsworld: number; espn: number | null; market: number | null; sportsworld_correct: boolean; upset: boolean }
interface Scorecard { date: string; games: number; sportsworld: ScoreMetrics | null; on_common_games: { games: number; sportsworld: ScoreMetrics | null; espn: ScoreMetrics | null; market: ScoreMetrics | null }; calibration: { range: string; games: number; expected: number; actual: number }[]; rows: ScoreRow[]; method: string }

function Scorecard({ lg, meta }: { lg: LeagueConfig; meta: Record<string, TeamMeta> }) {
  const q = useQuery({ queryKey: ['scorecard', lg.id], queryFn: () => getJSON<Scorecard>(`/research/scorecard/${lg.id}`), refetchInterval: 300_000, retry: 0 })
  const [all, setAll] = useState(false)
  const d = q.data
  const c = d?.on_common_games
  const col = (name: string, m: ScoreMetrics | null | undefined, best: boolean) => (
    <div className={`sc-col ${best ? 'best' : ''}`}>
      <span className="kpi-label">{name}</span>
      <b>{m ? `${Math.round(m.accuracy * m.games)}/${m.games}` : '-'}</b>
      <small>{m ? <>log loss <strong>{m.log_loss.toFixed(3)}</strong> · Brier {m.brier.toFixed(3)}</> : 'no data'}</small>
    </div>
  )
  const ll = (m?: ScoreMetrics | null) => m?.log_loss ?? 9
  const bestKey = c ? (['sportsworld', 'espn', 'market'] as const).reduce((a, k) => (ll(c[k]) < ll(c[a]) ? k : a), 'sportsworld' as 'sportsworld' | 'espn' | 'market') : null
  const rows = (d?.rows ?? []).slice().sort((a, b) => Number(b.upset) - Number(a.upset) || Math.abs(b.sportsworld - 0.5) - Math.abs(a.sportsworld - 0.5))
  return (
    <Panel title="Today's scorecard: forecasts vs what happened" icon={BadgeCheck} flush
      foot={d ? <>{d.method} One day is a small sample; the 7-season replay above is the real evidence.</> : undefined}>
      {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={4} /></div> : !d || d.games === 0 ? <Empty title="No completed games yet today">The scorecard fills in as games finish.</Empty> : (
        <>
          <div className="sc-head">
            {col('SportsWorld', c?.games ? c.sportsworld : d.sportsworld, bestKey === 'sportsworld')}
            {col("ESPN's model", c?.espn, bestKey === 'espn')}
            {col('Betting market', c?.market, bestKey === 'market')}
            <div className="sc-cal">
              <span className="kpi-label">Calibration (favourite won)</span>
              {d.calibration.map((b) => (
                <div key={b.range} className="sc-cal-row"><span>{b.range}</span><div className="bar"><i style={{ width: `${b.actual * 100}%` }} /></div><small>{Math.round(b.actual * b.games)}/{b.games}</small></div>
              ))}
            </div>
          </div>
          <div className="tbl-wrap" style={{ maxHeight: all ? 520 : 290 }}>
            <table className="tbl">
              <thead><tr><th>Final</th><th className="num">SportsWorld</th><th className="num">ESPN</th><th className="num">Market</th><th>Result</th></tr></thead>
              <tbody>
                {rows.slice(0, all ? rows.length : 8).map((r) => {
                  const winner = r.home_won ? r.home_id : r.away_id
                  const pw = (p: number | null) => (p == null ? null : r.home_won ? p : 1 - p)
                  return (
                    <tr key={r.event_id}>
                      <td><span className="team-cell"><TeamLogo meta={meta[r.away_id]} name={r.away} size={18} /><span className={winner === r.away_id ? '' : 'muted'}>{meta[r.away_id]?.abbreviation ?? r.away} {r.away_score}</span>
                        <span className="muted">@</span><TeamLogo meta={meta[r.home_id]} name={r.home} size={18} /><span className={winner === r.home_id ? '' : 'muted'}>{meta[r.home_id]?.abbreviation ?? r.home} {r.home_score}</span></span></td>
                      <td className="num" title="probability SportsWorld gave the eventual winner"><P p={pw(r.sportsworld)} digits={0} /></td>
                      <td className="num"><P p={pw(r.espn)} digits={0} /></td>
                      <td className="num"><P p={pw(r.market)} digits={0} /></td>
                      <td>{r.upset ? <span className="chip high">Upset</span> : r.sportsworld_correct ? <span className="chip low">Called it</span> : <span className="chip med">Missed</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {rows.length > 8 && <div style={{ padding: '8px 14px' }}><button className="btn ghost" onClick={() => setAll((x) => !x)}>{all ? 'Show fewer' : `Show all ${rows.length} games`}</button></div>}
        </>
      )}
    </Panel>
  )
}
