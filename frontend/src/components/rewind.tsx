import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { getJSON } from '../lib/api'
import { pct } from '../lib/format'
import { Loading, Panel } from './ui'

interface RewindRow { league: string; league_name: string; season: number; champion: string; teams: number; uniform: number; checkpoints: { checkpoint: number; as_of: string; champion_prob: number }[] }

const day = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })

/** Point-in-time proof: the odds the model gave each eventual champion, frozen at each date, knowing nothing after it. */
export function Rewind() {
  const q = useQuery({ queryKey: ['rewind'], queryFn: () => getJSON<{ rows: RewindRow[]; method: string }>('/research/rewind'), staleTime: Infinity })
  const leagues = [...new Set((q.data?.rows ?? []).map((r) => r.league))]
  const [lg, setLg] = useState('nfl')
  const rows = (q.data?.rows ?? []).filter((r) => r.league === lg).sort((a, b) => b.season - a.season)
  return (
    <Panel title="Rewind: what the model knew, and when" icon={History} flush className="rewind"
      action={<div className="seg">{leagues.map((l) => <button key={l} className={l === lg ? 'on' : ''} onClick={() => setLg(l)}>{q.data?.rows.find((r) => r.league === l)?.league_name.replace('College Football', 'CFB') ?? l}</button>)}</div>}
      foot={q.data ? <>{q.data.method} Odds shown are for the team that went on to win; the baseline is one team in {rows[0]?.teams ?? 'N'} picked at random.</> : undefined}>
      {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={5} /></div> : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Season</th><th>Eventual champion</th>{['Preseason', '¼ season', '½ season', '¾ season'].map((h) => <th key={h} className="num">{h}</th>)}<th className="num">Random pick</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.season}>
                  <td>{r.league === 'nfl' || r.league === 'college-football' ? r.season : `${r.season}–${String(r.season + 1).slice(2)}`}</td>
                  <td><b style={{ fontWeight: 600 }}>{r.champion}</b></td>
                  {r.checkpoints.map((c) => (
                    <td key={c.checkpoint} className="num" title={`Rebuilt as of ${day(c.as_of)}, using only results known by then`}>
                      <b className={c.champion_prob >= 3 * r.uniform ? 'rw-hi' : c.champion_prob >= r.uniform ? '' : 'muted'}>{pct(c.champion_prob, 1)}</b>
                      <small className="rw-date">as of {day(c.as_of)}</small>
                    </td>
                  ))}
                  <td className="num muted">{pct(r.uniform, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
