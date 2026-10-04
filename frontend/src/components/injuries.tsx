import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { HeartPulse, Search } from 'lucide-react'
import { getJSON } from '../lib/api'
import { useMeta } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { ago } from '../lib/format'
import { Empty, Loading, Panel, TeamLogo } from './ui'

interface InjRow { name: string; position?: string | null; status: string; reported_at?: string | null; source: string; source_url?: string | null; evidence_span?: string | null; role?: string | null; effect_points: number; why: string }
interface InjTeam { team_id: string; team: string; delta_points: number; players: InjRow[] }
interface InjReport { teams: InjTeam[]; players: number; fetched_at: string | null; sources: string }

const sev = (s: string) => { const x = (s || '').toLowerCase(); return x.startsWith('out') || x.startsWith('injured') || x.startsWith('susp') ? 'high' : x.startsWith('doubt') ? 'high' : x.startsWith('quest') || x.startsWith('game-time') || x.startsWith('day') ? 'med' : 'low' }

/** every listed player for every team, each marked with whether (and why) it moves the forecast */
export function InjuryReport({ lg, team }: { lg: LeagueConfig; team?: string }) {
  const q = useQuery({ queryKey: ['injury-report', lg.id], queryFn: () => getJSON<InjReport>(`/competitions/${lg.id}/injury-report`), refetchInterval: 120_000, retry: 0 })
  const meta = useMeta(lg.id).data ?? {}
  const [only, setOnly] = useState<'all' | 'priced'>('all')
  const [find, setFind] = useState('')
  const teams = useMemo(() => (q.data?.teams ?? [])
    .filter((t) => !team || t.team_id === team)
    .filter((t) => !find || `${t.team} ${meta[t.team_id]?.short_name ?? ''}`.toLowerCase().includes(find.toLowerCase()))
    .map((t) => ({ ...t, players: only === 'priced' ? t.players.filter((p) => p.effect_points) : t.players }))
    .filter((t) => t.players.length), [q.data, team, find, only, meta])
  const priced = (q.data?.teams ?? []).reduce((n, t) => n + t.players.filter((p) => p.effect_points).length, 0)
  return (
    <Panel title={team ? 'Injury report' : 'Injury report: every team'} icon={HeartPulse} flush
      action={<div className="inj-tools">
        {!team && <label className="field-search sm"><Search size={13} aria-hidden /><input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Team" aria-label="Filter teams" /></label>}
        <div className="seg"><button className={only === 'all' ? 'on' : ''} onClick={() => setOnly('all')}>All {q.data ? `(${q.data.players})` : ''}</button><button className={only === 'priced' ? 'on' : ''} onClick={() => setOnly('priced')}>Moves the forecast ({priced})</button></div>
      </div>}
      foot={q.data ? <>Sources: {q.data.sources}. Updated {q.data.fetched_at ? ago(q.data.fetched_at) : 'just now'}. Only established key players in roles with a statistically measured effect move a forecast; every other listed player is shown with the reason it is not priced.</> : undefined}>
      {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={5} /></div> : !teams.length ? <Empty title={only === 'priced' ? 'No listed absence moves a forecast right now' : 'No players listed'}>{only === 'priced' ? 'Every listed player is in a role without a measured effect.' : 'Reports appear as the official injury report and conference availability reports are published.'}</Empty> : (
        <div className="tbl-wrap" style={{ maxHeight: team ? 360 : 520 }}>
          <table className="tbl inj-table">
            <thead><tr>{!team && <th>Team</th>}<th>Player</th><th>Status</th><th>Source</th><th className="num">Effect on forecast</th></tr></thead>
            <tbody>
              {teams.flatMap((t) => t.players.map((p, i) => (
                <tr key={t.team_id + p.name + i} className={i === 0 ? 'inj-first' : ''}>
                  {!team && <td>{i === 0 && <Link to={`/${lg.id}/team/${t.team_id}`} className="team-cell"><TeamLogo meta={meta[t.team_id]} name={t.team} size={20} /><span>{meta[t.team_id]?.short_name ?? t.team}</span>{t.delta_points ? <span className="inj-team-delta">{t.delta_points.toFixed(1)} pts</span> : null}</Link>}</td>}
                  <td><b style={{ fontWeight: 600 }}>{p.name}</b>{p.position ? <span className="muted"> · {p.position}</span> : null}{p.role ? <span className="tag" style={{ marginLeft: 6 }}>{p.role}</span> : null}</td>
                  <td><span className={`chip ${sev(p.status)}`}>{p.status}</span></td>
                  <td className="inj-src">{p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer" title={p.evidence_span ? `“${p.evidence_span}”` : undefined}>{p.source}</a> : p.source}{p.reported_at ? <small> · {ago(p.reported_at)}</small> : null}</td>
                  <td className="num" title={p.why}>{p.effect_points ? <b className="down">{p.effect_points.toFixed(1)} pts</b> : <span className="muted inj-why">{p.why.replace(/^not priced: /, 'Not priced: ')}</span>}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
