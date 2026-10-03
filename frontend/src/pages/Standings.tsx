import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ListOrdered } from 'lucide-react'
import { useMeta, useSeason, useStandings } from '../lib/data'
import { qualify, title, type LeagueConfig } from '../lib/leagues'
import { num, signed } from '../lib/format'
import { ErrorNote, Loading, P, Panel, TeamLogo } from '../components/ui'

export function Standings({ lg }: { lg: LeagueConfig }) {
  const st = useStandings(lg.id)
  const season = useSeason(lg.id)
  const meta = useMeta(lg.id)
  const m = meta.data ?? {}
  const sim = useMemo(() => Object.fromEntries((season.data?.teams ?? []).map((t) => [t.team_id, t])), [season.data])
  const groups = useMemo(() => {
    const map = new Map<string, NonNullable<typeof st.data>['rows']>()
    for (const r of st.data?.rows ?? []) {
      const k = [r.conference, lg.college ? null : r.division].filter(Boolean).join(' · ') || 'Independent'
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(r)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [st.data, lg.college])
  const [conf, setConf] = useState<string>('')
  const q = qualify(lg)
  const tt = title(lg)
  const hockey = lg.sport === 'hockey'

  const shown = conf ? groups.filter(([k]) => k === conf) : groups
  return (
    <>
      <div className="hero">
        <div>
          <h1>{lg.name} — <em>Standings & projections</em></h1>
          <p>Today’s records next to where the season simulation expects each team to finish.</p>
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>
        <select className="field" value={conf} onChange={(e) => setConf(e.target.value)} aria-label="Conference">
          <option value="">All {lg.college ? 'conferences' : 'divisions'}</option>
          {groups.map(([k]) => <option key={k} value={k}>{k.replace(/ Conference/g, '')}</option>)}
        </select>
      </div>
      {st.isLoading ? <Loading rows={12} /> : st.error ? <ErrorNote error={st.error} what="standings" /> : (
        <div className="grid">
          {shown.map(([k, rows]) => (
            <div className={shown.length === 1 ? 'c12' : 'c6'} key={k}>
              <Panel title={k.replace(/ Conference/g, '')} icon={ListOrdered} flush>
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead><tr>
                      <th>Team</th><th className="num">W</th><th className="num">L</th>{hockey && <th className="num">OTL</th>}{hockey && <th className="num">Pts</th>}
                      <th className="num">Conf</th><th className="num">Diff</th><th className="num">Exp. W</th><th className="num">{q.short}</th><th className="num">{tt.short}</th>
                    </tr></thead>
                    <tbody>
                      {rows.slice().sort((a, b) => Number(sim[b.team_id]?.[q.key] ?? 0) - Number(sim[a.team_id]?.[q.key] ?? 0) || (b.wins - b.losses) - (a.wins - a.losses)).map((r) => (
                        <tr key={r.team_id}>
                          <td><Link to={`/${lg.id}/team/${r.team_id}`} className="team-cell"><TeamLogo meta={m[r.team_id]} name={r.name} size={22} /><span>{m[r.team_id]?.short_name ?? r.name}</span></Link></td>
                          <td className="num">{r.wins}</td><td className="num">{r.losses}</td>
                          {hockey && <td className="num">{r.ot_losses}</td>}{hockey && <td className="num"><b>{r.points}</b></td>}
                          <td className="num muted">{r.conf_record}</td>
                          <td className={`num ${r.point_diff > 0 ? 'up' : r.point_diff < 0 ? 'down' : 'flat'}`}>{signed(r.point_diff, 0)}</td>
                          <td className="num">{num(sim[r.team_id]?.expected_wins)}</td>
                          <td className="num"><P p={sim[r.team_id]?.[q.key] as number} /></td>
                          <td className="num"><P p={sim[r.team_id]?.[tt.key] as number} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
