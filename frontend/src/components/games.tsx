import { Link, useNavigate } from 'react-router-dom'
import { MapPinned } from 'lucide-react'
import type { BoardRow, TeamMeta } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { clock, isTbd, time } from '../lib/format'
import { Leverage, ProbSplit, TeamLogo } from './ui'
import { mergeLive, useLiveGames } from '../lib/live'

export function maxLeverage(g: BoardRow) {
  return Math.max(Math.abs(g.leverage_home ?? 0), Math.abs(g.leverage_away ?? 0))
}

function TeamName({ lg, id, name, meta, rank }: { lg: LeagueConfig; id: string; name: string; meta?: TeamMeta; rank?: number | null }) {
  const label = meta?.short_name || meta?.location || name
  return (
    <Link to={`/${lg.id}/team/${id}`} className="team-cell" title={name}>
      <TeamLogo meta={meta} name={name} size={24} />
      <span>{rank ? <small className="muted" style={{ marginRight: 4 }}>#{rank}</small> : null}{label}</span>
    </Link>
  )
}

export function GamesTable({ lg, games, meta, showDate = false, showLeverage = true, focusTeam }: {
  lg: LeagueConfig
  games: BoardRow[]
  meta?: Record<string, TeamMeta>
  showDate?: boolean
  showLeverage?: boolean
  focusTeam?: string
}) {
  const live = useLiveGames(lg.id)
  games = mergeLive(games, live.map)
  const navigate = useNavigate()
  const open = (g: BoardRow) => navigate(`/${lg.id}/game/${g.event_id}`)
  return (
    <>
    <div className="tbl-wrap games-table">
      <table className="tbl">
        <thead>
          <tr>
            <th>{showDate ? 'Date · time' : 'Time'}</th>
            <th>Away</th>
            <th />
            <th>Home</th>
            <th style={{ minWidth: 170 }}>Win probability</th>
            {showLeverage && <th title="How much the game moves each team's headline odds (win vs loss)">Leverage</th>}
            <th><span className="sr-only">Game view</span></th>
          </tr>
        </thead>
        <tbody>
          {games.map((g) => {
            const live = g.state === 'in'
            return (
              <tr key={g.event_id} className={`game-row ${focusTeam && (g.home_id === focusTeam || g.away_id === focusTeam) ? 'focus' : ''}`}>
                <td className="muted">
                  {live ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink)' }}>
                      <span className="live-dot" /> {clock(lg.sport, g.period, g.clock_seconds) || 'Live'}
                    </span>
                  ) : showDate ? (
                    <>{new Date(g.start_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · {isTbd(g.start_time) ? 'TBD' : time(g.start_time)}</>
                  ) : isTbd(g.start_time) ? 'TBD' : time(g.start_time)}
                </td>
                <td><TeamName lg={lg} id={g.away_id} name={g.away} meta={meta?.[g.away_id]} rank={g.away_rank} /></td>
                <td className="muted" style={{ textAlign: 'center' }}>
                  {live ? <span key={`${g.away_score}-${g.home_score}`} className="score tick">{g.away_score ?? 0}–{g.home_score ?? 0}</span> : g.neutral_site ? 'vs' : '@'}
                </td>
                <td><TeamName lg={lg} id={g.home_id} name={g.home} meta={meta?.[g.home_id]} rank={g.home_rank} /></td>
                <td>
                  <ProbSplit pHome={g.p_home} home={meta?.[g.home_id]} away={meta?.[g.away_id]} />
                </td>
                {showLeverage && (
                  <td><Leverage value={maxLeverage(g) || null} milestone={lg.milestones.find((m) => m.key === g.leverage_milestone)?.label} /></td>
                )}
                <td><button className={`btn ${live ? 'primary' : 'ghost'}`} style={{ height: 26, padding: '0 9px' }} onClick={() => open(g)} aria-label={`Open game view: ${g.away} at ${g.home}`}><MapPinned size={13} /> {live ? 'Watch' : 'View'}</button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
    <ul className="game-cards">
      {games.map((g) => {
        const live = g.state === 'in'
        return (
          <li key={g.event_id}>
            <div className="gc-top">
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {live ? <><span className="live-dot" /> {clock(lg.sport, g.period, g.clock_seconds) || 'Live'}</> : `${new Date(g.start_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · ${isTbd(g.start_time) ? 'TBD' : time(g.start_time)}`}
              </span>
              <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                {showLeverage && <Leverage value={maxLeverage(g) || null} />}
                <button className={`btn ${live ? 'primary' : 'ghost'}`} style={{ height: 26, padding: '0 9px' }} onClick={() => open(g)} aria-label={`Open game view: ${g.away} at ${g.home}`}><MapPinned size={13} /> {live ? 'Watch' : 'View'}</button>
              </span>
            </div>
            <div className="gc-teams">
              <TeamName lg={lg} id={g.away_id} name={g.away} meta={meta?.[g.away_id]} rank={g.away_rank} />
              <span className="score" style={{ fontFamily: 'var(--display)', fontWeight: 800, fontSize: 18 }}>{live ? <span key={`${g.away_score}-${g.home_score}`} className="tick">{g.away_score ?? 0}–{g.home_score ?? 0}</span> : g.neutral_site ? 'vs' : '@'}</span>
              <span className="team-cell r"><TeamName lg={lg} id={g.home_id} name={g.home} meta={meta?.[g.home_id]} rank={g.home_rank} /></span>
            </div>
            <ProbSplit pHome={g.p_home} home={meta?.[g.home_id]} away={meta?.[g.away_id]} />
          </li>
        )
      })}
    </ul>
    </>
  )
}
