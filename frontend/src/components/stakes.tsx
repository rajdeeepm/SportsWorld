import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Eye, Target } from 'lucide-react'
import { getJSON } from '../lib/api'
import { useMeta } from '../lib/data'
import { ago, pct } from '../lib/format'
import { Loading, Panel, ProbSplit, TeamLogo } from './ui'

export interface Stakes {
  event_id: string; state: string; home: string; away: string; home_id: string; away_id: string
  p_home: number; favourite: string; p_favourite: number; milestone: string; milestone_name: string
  home_now: number | null; away_now: number | null; swing_home: number; swing_away: number
  affected: { team_id: string; name: string; now: number | null; if_home_wins: number; roots_for: string; why?: string }[]
  home_if_win?: number | null; home_if_lose?: number | null; away_if_win?: number | null; away_if_lose?: number | null; reason?: string
  action: string; tone: 'must' | 'upset' | 'look' | 'low' | 'skip' | 'final'; as_of: string | null; global_state_version: number | null
}

const TONE: Record<Stakes['tone'], string> = { must: 'Must-watch', upset: 'Upset watch', look: 'Worth a look', low: 'Low stakes', skip: 'Skip', final: 'Final' }
const toneLabel = (s: Stakes) => (s.action.startsWith('Effectively decided') ? 'Effectively decided' : TONE[s.tone])

function label(pf: number) {
  return pf < 0.6 ? 'Toss-up' : pf < 0.7 ? 'Lean' : pf < 0.85 ? 'Clear favourite' : 'Heavy favourite'
}

/** Why one game matters: win probability, playoff swing for both sides, who else it moves, and a viewing call. */
export function WhyItMatters({ league, eventId, headline }: { league: string; eventId?: string; headline?: boolean }) {
  const url = eventId ? `/games/${league}/${eventId}/stakes` : `/competitions/${league}/game-of-the-day`
  const q = useQuery({ queryKey: ['stakes', league, eventId ?? 'top'], queryFn: () => getJSON<Stakes>(url), refetchInterval: 60_000, retry: 0 })
  const meta = useMeta(league).data ?? {}
  const s = q.data
  if (q.isError) return null
  // each side: odds with a win vs with a loss (the swing is the gap between them)
  const swing = (v: number, now: number | null, win?: number | null, lose?: number | null) => (now != null && now < 0.005 && Math.abs(v) < 0.005 ? (
    <><b className="down">Under 1%</b><small>out of the race either way</small></>
  ) : win != null && lose != null ? (
    <>
      <b className="up">{pct(win, 0)} <span className="why-vs">with a win</span></b>
      <small>{pct(lose, 0)} with a loss · now {pct(now ?? 0, 0)} · swing {Math.abs(v * 100).toFixed(0)} pts</small>
    </>
  ) : (
    <>
      <b className={v >= 0 ? 'up' : 'down'}>{v >= 0 ? '+' : '−'}{Math.abs(v * 100).toFixed(0)} pts</b>
      <small>{now == null ? '' : `now ${pct(now, 0)}`}</small>
    </>
  ))
  return (
    <Panel title={headline ? 'Game of the day: why it matters' : 'Why this game matters'} icon={Target} className="why"
      foot={s ? <>From 10,000 simulated seasons{s.global_state_version != null ? `, state v${s.global_state_version}` : ''}{s.as_of ? `, computed ${ago(s.as_of)} from results known then` : ''}. Odds with a win and with a loss come from the same simulated seasons; the swing is the gap between them. Other teams are listed only when the effect is beyond simulation noise (3 standard errors).</> : undefined}>
      {q.isLoading || !s ? <Loading rows={3} /> : (
        <div className="why-body">
          <div className="why-match">
            <Link to={`/${league}/game/${s.event_id}`} className="why-teams">
              <TeamLogo meta={meta[s.away_id]} name={s.away} size={30} /><span>{meta[s.away_id]?.short_name ?? s.away}</span>
              <span className="muted">{s.state === 'in' ? 'live at' : 'at'}</span>
              <TeamLogo meta={meta[s.home_id]} name={s.home} size={30} /><span>{meta[s.home_id]?.short_name ?? s.home}</span>
            </Link>
            <ProbSplit pHome={s.p_home} home={meta[s.home_id]} away={meta[s.away_id]} />
          </div>
          {s.reason && <p className="why-reason">{s.reason}</p>}
          <div className="why-grid">
            <div className="why-cell">
              <span className="kpi-label">Win probability</span>
              <b>{pct(s.p_favourite, 0)}</b>
              <small>{label(s.p_favourite)}: {meta[s.home_id] && s.favourite === s.home ? meta[s.home_id].short_name : meta[s.away_id] && s.favourite === s.away ? meta[s.away_id].short_name : s.favourite}</small>
            </div>
            <div className="why-cell">
              <span className="kpi-label">{s.milestone_name} odds · {meta[s.away_id]?.abbreviation ?? s.away}</span>
              {swing(s.swing_away, s.away_now, s.away_if_win, s.away_if_lose)}
            </div>
            <div className="why-cell">
              <span className="kpi-label">{s.milestone_name} odds · {meta[s.home_id]?.abbreviation ?? s.home}</span>
              {swing(s.swing_home, s.home_now, s.home_if_win, s.home_if_lose)}
            </div>
            <div className="why-cell why-affected">
              <span className="kpi-label">Also affected</span>
              {s.affected.length ? s.affected.map((a) => (
                <div key={a.team_id} className="why-aff">
                  <TeamLogo meta={meta[a.team_id]} name={a.name} size={18} />
                  <span>{meta[a.team_id]?.short_name ?? a.name}</span>
                  <small>{a.why ? `${a.why} · ` : ''}+{Math.abs(a.if_home_wins * 100).toFixed(1)} pts if {meta[a.roots_for === s.home ? s.home_id : s.away_id]?.abbreviation ?? a.roots_for} wins</small>
                </div>
              )) : <small>No other team moves beyond simulation noise.</small>}
            </div>
          </div>
          <div className={`why-action tone-${s.tone}`}>
            <Eye size={16} aria-hidden />
            <div><b>{toneLabel(s)}</b><span>{s.action.replace(/^(Must-watch|Watch for the upset|Worth a look|Good game, low stakes|Skip it for the season picture|Tune in now|Final|Effectively decided)[:.]\s*/, '').replace(/^./, (c) => c.toUpperCase())}</span></div>
          </div>
        </div>
      )}
    </Panel>
  )
}
