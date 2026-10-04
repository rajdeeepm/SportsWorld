import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity, BarChart3, CalendarRange, FlaskConical, Gauge, GitBranch, HeartPulse, Home, Medal, Route, Scale, ShieldHalf, Sigma, Target, Trophy,
} from 'lucide-react'
import { useAvailability, useMeta, useSeason, useStandings, useTeam, type TeamMeta, type TeamRemaining } from '../lib/data'
import { qualify, title, type LeagueConfig } from '../lib/leagues'
import { clock, day, isTbd, num, pct, shortDate, signed, time, visibleColor, luminance } from '../lib/format'
import { Empty, ErrorNote, Kpis, Leverage, Loading, P, Panel, ProbSplit, TeamLogo, probClass } from '../components/ui'
import { OddsTrend, StrengthTrend, WinDistribution } from '../components/charts'
import { useQuery } from '@tanstack/react-query'
import { getJSON } from '../lib/api'
import { WorldUpdates } from './LeagueWorld'
import { ListenButton } from '../components/radio'
import { TeamPlayerStats } from '../components/stats'

export function TeamWorld({ lg, teamId }: { lg: LeagueConfig; teamId: string }) {
  const team = useTeam(lg.id, teamId)
  const season = useSeason(lg.id)
  const meta = useMeta(lg.id)
  const standings = useStandings(lg.id)
  const m = meta.data ?? {}
  const me = { ...(m[teamId] ?? {}), ...(team.data?.meta ?? {}) } as TeamMeta

  if (team.isLoading) return <div style={{ padding: 20 }}><Loading rows={10} /></div>
  if (team.error || !team.data) return <ErrorNote error={team.error} what="this team" />

  const t = team.data.team
  const run = season.data
  const teams = run?.teams ?? []
  const rankBy = (k: string) => 1 + teams.filter((x) => Number(x[k] ?? 0) > Number(t[k] ?? 0)).length
  const strengthRank = rankBy('rating')
  const q = qualify(lg)
  const tt = title(lg)
  const st = standings.data?.rows.find((r) => r.team_id === teamId)
  // our standings update the moment a final lands; ESPN's team page is a cached fallback
  const record = st ? `${st.wins}-${st.losses}${st.ties ? `-${st.ties}` : ''}` : me.record_summary ?? '-'
  const remaining = team.data.remaining
  const next = remaining.find((r) => r.state !== 'post')
  const color = visibleColor(me.color, me.alt_color)
  const heroAccent = me.alt_color && luminance(me.alt_color) > 0.25 ? me.alt_color : luminance(me.color) > 0.25 ? me.color! : 'var(--accent-ink)'
  const confShort = (t.conference ?? '').replace(' Conference', '')
  const mid = lg.milestones.find((x) => x.key === 'conference_champion' || x.key === 'division_title')
  const extra = lg.milestones.find((x) => x.key === 'semifinal' || x.key === 'conference_title' || x.key === 'final_four' || x.key === 'sweet_16')

  return (
    <div style={{ ['--hero-accent' as string]: heroAccent }}>
      <div className="hero">
        <div>
          <h1>{me.name ?? t.name}: <em>Season World</em></h1>
          <p>Persistent team intelligence across the {lg.seasonLabel} {lg.name.toLowerCase().startsWith('n') ? lg.name : lg.name.toLowerCase()} season.</p>
          <div className="hero-actions"><ListenButton league={lg.id} team={teamId} label={`Listen: ${me.short_name ?? t.name} briefing`} /></div>
        </div>
      </div>

      <div className="stack">
        <section className="team-band" style={{ ['--team-c' as string]: me.color ?? '#0b2a5c', ['--team-glow' as string]: `${color}88` }} aria-label="Team summary">
          <div className="tb-logo"><TeamLogo meta={me} name={t.name} size={84} /></div>
          <div className="tb-name">
            <b>{me.location ?? t.name}<br />{me.nickname ?? ''}</b>
            <span>{me.standing_summary ?? confShort}{me.rank ? ` · AP #${me.rank}` : ''}</span>
          </div>
          <div className="tb-stat keep"><b>{record}</b><span>Overall</span><span className="m-only">{st?.conf_record ?? '-'} {confShort}</span><span className="m-only">#{strengthRank} strength</span></div>
          <div className="tb-stat"><b>{st?.conf_record ?? '-'}</b><span>{confShort || 'Conference'}</span></div>
          <div className="tb-stat"><b>#{strengthRank}</b><span>Strength of {teams.length}</span></div>
          <div className="tb-stat"><b>{signed(t.rating, 1)}</b><span>{lg.unit} vs average</span></div>
          {next ? <NextGameCard lg={lg} g={next} meta={m} teamId={teamId} /> : <div className="tb-next"><div><div className="k">Next game</div><b>Season complete</b></div></div>}
        </section>

        <Kpis items={[
          { icon: Trophy, label: 'Expected wins', value: num(t.expected_wins), sub: `90% range ${t.wins_p05}–${t.wins_p95} of ${t.games}`, gold: true },
          { icon: Target, label: `${q.short} probability`, value: <P p={t[q.key] as number} />, sub: `±${pct(Number(t[`${q.key}_se`] ?? 0), 2)} sim. error` },
          ...(mid && !/independ/i.test(t.conference ?? '') ? [{ icon: Medal, label: mid.short === 'Conf. champ' ? 'Conference title' : mid.label, value: <P p={t[mid.key] as number} />, sub: `rank ${rankBy(mid.key)}` }] : []),
          ...(extra ? [{ icon: ShieldHalf, label: extra.short === 'Semis' ? 'CFP semifinal' : extra.label, value: <P p={t[extra.key] as number} />, sub: `rank ${rankBy(extra.key)}` }] : []),
          { icon: Trophy, label: lg.titleName, value: <P p={t[tt.key] as number} />, sub: `rank ${rankBy(tt.key)}`, gold: true },
          { icon: Gauge, label: 'Strength rating', value: <>{signed(t.rating, 1)}<small>±{num(t.rating_sd, 1)}</small></>, sub: `#${strengthRank} of ${teams.length}` },
        ]} />

        <div className="grid">
          <div className="c4">
            <Panel title="Team strength trend" icon={Activity}
              foot={<>Posterior mean of latent strength with its 90% band ({lg.unit} vs an average team). Updated after every result.</>}>
              {team.data.rating_history.length > 1
                ? <StrengthTrend history={team.data.rating_history} color={color} unit={lg.unit} height={250} />
                : <Empty title="No rating history yet" />}
            </Panel>
          </div>
          <div className="c5"><Schedule lg={lg} rows={remaining} meta={m} teamId={teamId} /></div>
          <div className="c3 stack">
            {next && <MatchupOutlook lg={lg} g={next} meta={m} teamId={teamId} teams={teams} hfa={run?.rating_params?.hfa} />}
          </div>

          <div className="c4">
            <Panel title="Final record distribution" icon={BarChart3} foot={`${run?.draws.toLocaleString() ?? '10,000'} simulated seasons; faded bars are already out of reach.`}>
              <WinDistribution hist={t.win_hist} draws={run?.draws ?? 10000} color={color} current={st?.wins} height={220} />
            </Panel>
          </div>
          <div className="c5"><SeasonPaths lg={lg} teamId={teamId} t={t} color={color} /></div>
          <div className="c3"><Availability lg={lg} teamId={teamId} /></div>

          <div className="c7"><OddsOverTime lg={lg} teamId={teamId} color={color} /></div>
          <div className="c5"><WorldUpdates lg={lg} meta={m} team={teamId} /></div>
          <div className="c7"><TeamPlayerStats league={lg.id} teamId={teamId} /></div>
          <div className="c5"><RecentResults lg={lg} rows={team.data.recent_results} name={t.name} season={run?.season} /></div>
        </div>

        <div className="provenance">
          <span><b>Season run</b> {team.data.season_run_id}</span>
          <span><b>State</b> v{team.data.global_state_version}</span>
          {run && <span><b>As of</b> {new Date(run.as_of).toLocaleString()}</span>}
          {run?.event_model_version && <span><b>Game model</b> {run.event_model_version}</span>}
          <span><b>Identity</b> ESPN team API</span>
        </div>
      </div>
    </div>
  )
}

function NextGameCard({ lg, g, meta, teamId }: { lg: LeagueConfig; g: TeamRemaining; meta: Record<string, TeamMeta>; teamId: string }) {
  const oppId = g.is_home ? g.away_id : g.home_id
  const opp = meta[oppId]
  const live = g.state === 'in'
  const mine = g.is_home ? g.home_score : g.away_score
  const theirs = g.is_home ? g.away_score : g.home_score
  return (
    <Link to={live ? `/${lg.id}/game/${g.event_id}` : `/${lg.id}/games?team=${teamId}`} className="tb-next" aria-label={live ? 'Watch the live game' : 'Next game'}>
      <TeamLogo meta={opp} name={g.is_home ? g.away : g.home} size={54} />
      <div style={{ minWidth: 0 }}>
        <div className="k" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{live ? <><span className="live-dot" /> Live · {clock(lg.sport, g.period, g.clock_seconds)}</> : 'Next game'}</div>
        <b>{g.is_home ? 'vs' : '@'} {opp?.short_name ?? (g.is_home ? g.away : g.home)}{live ? ` · ${mine}–${theirs}` : ''}</b>
        <span>{live ? `Win probability ${pct(g.p_win, 0)} (pregame ${pct(g.is_home ? g.p_home_pregame : 1 - (g.p_home_pregame ?? 0.5), 0)})` : `${day(g.start_time)} · ${isTbd(g.start_time) ? 'time TBD' : time(g.start_time)}`}</span>
      </div>
    </Link>
  )
}

function Schedule({ lg, rows, meta, teamId }: { lg: LeagueConfig; rows: TeamRemaining[]; meta: Record<string, TeamMeta>; teamId: string }) {
  const q = qualify(lg)
  return (
    <Panel title="Remaining schedule" icon={CalendarRange} flush action={<Link to={`/${lg.id}/lab?team=${teamId}`} className="link">Branch a result</Link>}
      foot={`Leverage = ${q.short} odds if this game is won minus if it is lost, from the same simulated seasons.`}>
      {rows.length === 0 ? <Empty title="No games remaining" /> : (
        <div className="tbl-wrap" style={{ maxHeight: 360 }}>
          <table className="tbl">
            <thead><tr><th>Date</th><th>Opponent</th><th>Site</th><th className="num">Win prob</th><th>Leverage</th></tr></thead>
            <tbody>
              {rows.map((g) => {
                const oppId = g.is_home ? g.away_id : g.home_id
                const lev = g.is_home ? g.leverage_home : g.leverage_away
                const live = g.state === 'in'
                return (
                  <tr key={g.event_id}>
                    <td className="muted">{live ? <span style={{ color: 'var(--live)', fontWeight: 700 }}>LIVE</span> : shortDate(g.start_time)}</td>
                    <td><Link to={`/${lg.id}/team/${oppId}`} className="team-cell"><TeamLogo meta={meta[oppId]} name={g.is_home ? g.away : g.home} size={22} /><span>{g.is_home ? 'vs' : '@'} {meta[oppId]?.short_name ?? (g.is_home ? g.away : g.home)}</span></Link></td>
                    <td className="muted">{g.neutral_site ? 'Neutral' : g.is_home ? 'Home' : 'Away'}</td>
                    <td className="num">
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                        <span className="bar" style={{ width: 46, height: 6 }}><i style={{ width: `${(g.p_win ?? 0) * 100}%` }} /></span>
                        <b className={probClass(g.p_win)}>{pct(g.p_win, 0)}</b>
                      </span>
                    </td>
                    <td><Leverage value={lev} milestone={q.label} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function MatchupOutlook({ lg, g, meta, teamId, teams, hfa }: { lg: LeagueConfig; g: TeamRemaining; meta: Record<string, TeamMeta>; teamId: string; teams: { team_id: string; rating: number; rating_sd: number; expected_wins: number }[]; hfa?: number }) {
  const home = teams.find((t) => t.team_id === g.home_id)
  const away = teams.find((t) => t.team_id === g.away_id)
  const live = g.state === 'in'
  const margin = home && away ? home.rating - away.rating + (g.neutral_site ? 0 : hfa ?? 0) : null
  const sd = home && away ? Math.sqrt(home.rating_sd ** 2 + away.rating_sd ** 2) : null
  const myHome = g.home_id === teamId
  const side = (id: string, name: string, right = false) => (
    <div className={`mu-side ${right ? 'right' : ''}`}>
      <TeamLogo meta={meta[id]} name={name} size={50} />
      <div style={{ minWidth: 0 }}>
        <b>{meta[id]?.abbreviation ?? name}</b>
        <span>{teams.find((t) => t.team_id === id) ? `${signed(teams.find((t) => t.team_id === id)!.rating, 1)} strength` : ''}</span>
      </div>
    </div>
  )
  return (
    <Panel title="Next game outlook" icon={Scale}>
      <div className="matchup">
        {side(g.away_id, g.away)}
        <div className="mu-vs">{live ? <span className="score">{g.away_score}–{g.home_score}</span> : g.neutral_site ? 'vs' : 'at'}</div>
        {side(g.home_id, g.home, true)}
      </div>
      <ProbSplit pHome={g.p_home} home={meta[g.home_id]} away={meta[g.away_id]} />
      <div className="mu-figs" style={{ marginTop: 10 }}>
        <div><b>{pct(g.p_win, 0)}</b><span>{meta[teamId]?.abbreviation} win prob</span></div>
        <div><b>{margin != null ? signed(myHome ? margin : -margin, 1) : '-'}</b><span>Exp. margin</span></div>
        <div><b>{pct(myHome ? g.p_home_pregame : 1 - (g.p_home_pregame ?? 0.5), 0)}</b><span>Pregame</span></div>
      </div>
      <div className="factor"><Sigma size={15} /><span>{meta[teamId]?.abbreviation} strength edge (posterior means)</span><span className="v">{home && away ? signed(myHome ? home.rating - away.rating : away.rating - home.rating, 1) : '-'}</span></div>
      <div className="factor"><Home size={15} /><span>Home field ({g.neutral_site ? 'neutral site' : myHome ? 'learned, in our favour' : 'learned, against'})</span><span className="v">{g.neutral_site ? '0.0' : signed(myHome ? hfa ?? 0 : -(hfa ?? 0), 1)}</span></div>
      <div className="factor"><Sigma size={15} /><span>Uncertainty in the gap (sd)</span><span className="v">±{sd != null ? num(sd, 1) : '-'}</span></div>
      <div className="factor"><Route size={15} /><span>{qualify(lg).short} swing (win vs loss)</span><span className="v">{pct(Math.abs((myHome ? g.leverage_home : g.leverage_away) ?? 0), 1)}</span></div>
      {g.interval_90 && <div className="factor"><Activity size={15} /><span>{meta[teamId]?.abbreviation} pregame win prob, 90% interval</span><span className="v">{myHome ? `${pct(g.interval_90[0], 0)}–${pct(g.interval_90[1], 0)}` : `${pct(1 - g.interval_90[1], 0)}–${pct(1 - g.interval_90[0], 0)}`}</span></div>}
    </Panel>
  )
}

function SeasonPaths({ lg, teamId, t, color }: { lg: LeagueConfig; teamId: string; t: { season_paths?: { milestone: string; by_wins: { wins: number; p: number; champion: number | null; [k: string]: number | null }[] }; games: number }; color: string }) {
  const paths = t.season_paths
  const q = qualify(lg)
  const rows = useMemo(() => (paths?.by_wins ?? []).slice().reverse(), [paths])
  return (
    <Panel title="Season path simulator" icon={GitBranch} action={<Link to={`/${lg.id}/lab?team=${teamId}`} className="link"><FlaskConical size={13} /> Open in Lab</Link>}
      foot={`Every final record that happens in at least 0.5% of simulated seasons, with ${q.short} and title odds given that record.`}>
      {rows.length === 0 ? <Empty title="Paths unavailable for this league" /> : (
        <div className="paths">
          <div className="row" style={{ color: 'var(--ink-3)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>
            <span>Final record</span><span>How often</span><span className="num">{q.short}</span><span className="num">{title(lg).short}</span>
          </div>
          {rows.map((r) => (
            <div className="row" key={r.wins}>
              <span className="rec">{r.wins}–{t.games - r.wins}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="bar" style={{ flex: 1 }}><i style={{ width: `${Math.min(r.p / Math.max(...rows.map((x) => x.p)), 1) * 100}%`, background: color }} /></div>
                <span className="muted" style={{ width: 44, textAlign: 'right' }}>{pct(r.p, 0)}</span>
              </span>
              <span className="num"><P p={r[paths!.milestone] as number} digits={0} /></span>
              <span className="num"><P p={r.champion} /></span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function Availability({ lg, teamId }: { lg: LeagueConfig; teamId: string }) {
  const av = useAvailability(lg.id)
  const mine = av.data?.teams.find((x) => x.team_id === teamId)
  const imp = av.data?.impact?.by_position ?? {}
  return (
    <Panel title="Availability" icon={HeartPulse}
      foot={av.data ? <>ESPN injury report · learned effect per absence ({Object.entries(imp).map(([k, v]: any) => `${k} ${v.points.toFixed(1)}±${v.se.toFixed(1)}`).join(', ')})</> : undefined}>
      {av.isLoading ? <Loading rows={3} /> : av.isError ? <Empty title="No availability model for this league" /> : !mine ? (
        <Empty title="No key absences">The current injury report lists none of this team’s established key players.</Empty>
      ) : (
        <>
          {mine.absences.map((a) => (
            <div className="factor" key={a.player}>
              <HeartPulse size={15} style={{ color: 'var(--bad)' }} />
              <span><b>{a.player}</b> <span className="tag">{a.role}</span> <span className="muted">{a.status}</span></span>
              <span className="v down">{a.delta_points.toFixed(1)}</span>
            </div>
          ))}
          <div className="factor"><Sigma size={15} /><span>Applied to strength</span><span className="v down">{mine.delta_points.toFixed(1)} {lg.unit}</span></div>
        </>
      )}
    </Panel>
  )
}

function RecentResults({ lg, rows, name, season }: { lg: LeagueConfig; rows: { event_id: string; date: string; home: string; away: string; home_score: number; away_score: number }[]; name: string; season?: number }) {
  const list = rows.slice().reverse().slice(0, 8)
  return (
    <Panel title="Recent results" icon={Activity} flush foot={season ? `Most recent completed games (including last season when this season is young).` : undefined}>
      {list.length === 0 ? <Empty title="No completed games yet" /> : (
        <table className="tbl">
          <thead><tr><th>Date</th><th>Game</th><th className="num">Score</th><th>Result</th></tr></thead>
          <tbody>
            {list.map((r) => {
              const home = r.home === name
              const mine = home ? r.home_score : r.away_score
              const theirs = home ? r.away_score : r.home_score
              const res = mine > theirs ? 'W' : mine < theirs ? 'L' : 'T'
              return (
                <tr key={r.event_id}>
                  <td className="muted">{new Date(r.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}</td>
                  <td>{home ? `vs ${r.away}` : `@ ${r.home}`}</td>
                  <td className="num"><b>{mine}–{theirs}</b></td>
                  <td><span className={`chip ${res === 'W' ? 'low' : res === 'L' ? 'high' : 'neutral'}`}>{res}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </Panel>
  )
}

function OddsOverTime({ lg, teamId, color }: { lg: LeagueConfig; teamId: string; color: string }) {
  const h = useQuery({ queryKey: ['history', lg.id, teamId], queryFn: () => getJSON<{ points: any[]; source: string }>(`/history/team/${lg.id}/${teamId}`), refetchInterval: 120_000, retry: 0 })
  const q = qualify(lg)
  return (
    <Panel title="Odds over the season" icon={Activity}
      foot={<><span className="legend" style={{ display: 'inline-flex', marginRight: 10 }}><span><i style={{ background: color }} />{qualify(lg).short}</span><span><i style={{ background: '#6fb2ff' }} />{title(lg).short}</span><span><i style={{ background: 'rgba(169,186,219,.7)' }} />Expected wins (right axis)</span></span>Before the marker: point-in-time replays rebuilt from data available each day. After it: runs archived live. Stored in Neon Postgres.</>}>
      {h.isLoading ? <Loading rows={4} /> : h.isError || !h.data?.points?.length ? <Empty title="History archive unavailable">Start the API with DATABASE_URL set (Neon) and run scripts/backfill_history.py.</Empty>
        : <OddsTrend points={h.data.points} color={color} qualifyLabel={q.short} titleLabel={title(lg).short} height={250} />}
    </Panel>
  )
}
