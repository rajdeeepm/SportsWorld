import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, Radio } from 'lucide-react'
import { useBoard, useMeta } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { day } from '../lib/format'
import { Empty, ErrorNote, Loading, Panel } from '../components/ui'
import { GamesTable, maxLeverage } from '../components/games'

export function Games({ lg }: { lg: LeagueConfig }) {
  const [params, setParams] = useSearchParams()
  const liveOnly = params.get('live') === '1'
  const team = params.get('team') ?? undefined
  const board = useBoard(lg.id, team)
  const meta = useMeta(lg.id)
  const [sort, setSort] = useState<'time' | 'leverage'>('time')
  const [limit, setLimit] = useState(120)

  const games = useMemo(() => {
    let g = board.data?.events ?? []
    if (liveOnly) g = g.filter((e) => e.state === 'in')
    if (sort === 'leverage') g = g.slice().sort((a, b) => maxLeverage(b) - maxLeverage(a))
    return g
  }, [board.data, liveOnly, sort])

  const groups = useMemo(() => {
    if (sort === 'leverage' || liveOnly) return [['', games.slice(0, limit)] as const]
    const out: [string, typeof games][] = []
    for (const g of games.slice(0, limit)) {
      const k = day(g.start_time)
      if (!out.length || out[out.length - 1][0] !== k) out.push([k, []])
      out[out.length - 1][1].push(g)
    }
    return out
  }, [games, sort, limit, liveOnly])

  return (
    <>
      <div className="hero">
        <div>
          <h1>{lg.name} — <em>{liveOnly ? 'Live games' : 'Every game, forecast'}</em></h1>
          <p>{liveOnly ? 'In-game win probabilities, updated every 20 seconds and fed straight into the season simulation.' : `All ${board.data?.count.toLocaleString() ?? ''} remaining games with a calibrated forecast and the season leverage of each result.`}</p>
        </div>
      </div>
      <Panel title={liveOnly ? 'Live now' : team ? 'Team schedule' : 'Forecast board'} icon={liveOnly ? Radio : CalendarDays} flush
        action={<>
          {team && <button className="btn ghost" onClick={() => { params.delete('team'); setParams(params) }}>Clear team filter</button>}
          {!liveOnly && <div className="seg"><button className={sort === 'time' ? 'on' : ''} onClick={() => setSort('time')}>By date</button><button className={sort === 'leverage' ? 'on' : ''} onClick={() => setSort('leverage')}>By leverage</button></div>}
        </>}
        foot={games.length > limit ? <button className="btn" onClick={() => setLimit((l) => l + 200)}>Show more ({games.length - limit} remaining)</button> : undefined}>
        {board.isLoading ? <div style={{ padding: 14 }}><Loading rows={10} /></div> : board.error ? <ErrorNote error={board.error} what="the forecast board" /> : games.length === 0 ? (
          <Empty title={liveOnly ? 'No live games right now' : 'No remaining games'}>{liveOnly ? 'Live games appear here automatically when they kick off.' : ''}</Empty>
        ) : groups.map(([k, g]) => (
          <div key={k || 'all'}>
            {k && <div style={{ padding: '12px 14px 4px', fontFamily: 'var(--display)', fontWeight: 700, fontSize: 17, color: 'var(--ink-2)' }}>{k}</div>}
            <GamesTable lg={lg} games={[...g]} meta={meta.data} showDate={!k} focusTeam={team} />
          </div>
        ))}
      </Panel>
    </>
  )
}
