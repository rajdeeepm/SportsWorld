import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { getJSON } from '../lib/api'
import { Empty, Loading, Panel } from './ui'

export interface StatCategory { name: string; labels: string[]; rows: { id: string; name: string; starter?: boolean | null; stats: string[] }[] }

const TITLE: Record<string, string> = {
  passing: 'Passing', rushing: 'Rushing', receiving: 'Receiving', defensive: 'Defense', interceptions: 'Interceptions', fumbles: 'Fumbles',
  kicking: 'Kicking', punting: 'Punting', kickReturns: 'Kick returns', puntReturns: 'Punt returns', players: 'Players',
  forwards: 'Forwards', defenses: 'Defense', skaters: 'Skaters', goalies: 'Goalies',
}

export function StatTables({ categories, prefer }: { categories: StatCategory[]; prefer?: string[] }) {
  const order = prefer ?? ['passing', 'rushing', 'receiving', 'defensive', 'players', 'forwards', 'defenses', 'goalies']
  const rank = (n: string) => (order.indexOf(n) < 0 ? 99 : order.indexOf(n))
  const cats = categories.slice().sort((a, b) => rank(a.name) - rank(b.name))
  const lead = ['passing', 'rushing', 'receiving', 'defensive', 'players', 'skaters', 'forwards', 'goalies'].map((n) => cats.find((x) => x.name === n)).filter(Boolean) as StatCategory[]
  const hasLeaders = lead.length >= 2
  const [sel, setSel] = useState(hasLeaders ? -1 : 0)
  const c = cats[Math.min(Math.max(sel, 0), cats.length - 1)]
  if (!c) return <Empty title="No player stats yet" />
  const keyCols = (x: StatCategory) => x.labels.map((l, i) => [l, i] as const).filter(([l]) => l !== 'GP').slice(0, 4)
  return (
    <>
      <div className="stat-tabs" role="tablist">
        {hasLeaders && <button role="tab" aria-selected={sel === -1} className={sel === -1 ? 'on' : ''} onClick={() => setSel(-1)}>Leaders</button>}
        {cats.map((x, i) => <button key={x.name} role="tab" aria-selected={i === sel} className={i === sel ? 'on' : ''} onClick={() => setSel(i)}>{TITLE[x.name] ?? x.name}</button>)}
      </div>
      {sel === -1 ? (
        <div className="tbl-wrap" style={{ maxHeight: 380 }}>
          <table className="tbl">
            <thead><tr><th>Category</th><th>Player</th><th>Key numbers</th></tr></thead>
            <tbody>
              {lead.flatMap((x) => x.rows.slice(0, 3).map((r, k) => (
                <tr key={x.name + r.id}>
                  <td className="muted">{k === 0 ? TITLE[x.name] ?? x.name : ''}</td>
                  <td><b style={{ fontWeight: 600 }}>{r.name}</b></td>
                  <td>{keyCols(x).map(([l, i]) => <span key={l} className="stat-kv"><small>{l}</small> {r.stats[i]}</span>)}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      ) : (
      <div className="tbl-wrap" style={{ maxHeight: 380 }}>
        <table className="tbl">
          <thead><tr><th>Player</th>{c.labels.map((l) => <th key={l} className="num">{l}</th>)}</tr></thead>
          <tbody>
            {c.rows.map((r) => (
              <tr key={r.id + r.name}>
                <td><b style={{ fontWeight: 600 }}>{r.name}</b>{r.starter ? <span className="tag" style={{ marginLeft: 6 }}>starter</span> : null}</td>
                {r.stats.map((v, i) => <td key={i} className="num">{v}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </>
  )
}

/** season stats for one team, summed from every completed game's box score */
export function TeamPlayerStats({ league, teamId }: { league: string; teamId: string }) {
  const q = useQuery({ queryKey: ['player-stats', league, teamId], queryFn: () => getJSON<{ games: number; categories: StatCategory[] }>(`/entities/team/${league}/${teamId}/player-stats`), staleTime: 300_000, retry: 0 })
  return (
    <Panel title="Player stats this season" icon={Users} flush foot={q.data ? `Summed from the box score of all ${q.data.games} completed games this season (ESPN). Averages recomputed from the totals.` : undefined}>
      {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={5} /></div> : !q.data?.categories.length ? <Empty title="No completed games this season yet" /> : <StatTables categories={q.data.categories} />}
    </Panel>
  )
}

/** live / final box score for one game, both teams */
export function BoxScore({ league, eventId, live }: { league: string; eventId: string; live: boolean }) {
  const q = useQuery({ queryKey: ['box', league, eventId], queryFn: () => getJSON<{ teams: { team_id: string; abbreviation: string; categories: StatCategory[] }[] }>(`/games/${league}/${eventId}/boxscore`), refetchInterval: live ? 30_000 : false, retry: 0 })
  const [t, setT] = useState(0)
  const teams = q.data?.teams ?? []
  return (
    <Panel title="Box score" icon={Users} flush action={teams.length > 1 ? <div className="seg">{teams.map((x, i) => <button key={x.team_id} className={i === t ? 'on' : ''} onClick={() => setT(i)}>{x.abbreviation}</button>)}</div> : undefined}
      foot={live ? 'Updates every 30 seconds from ESPN’s box score.' : 'Final box score (ESPN).'}>
      {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={5} /></div> : !teams.length ? <Empty title="No box score yet" /> : <StatTables key={t} categories={teams[t].categories} />}
    </Panel>
  )
}
