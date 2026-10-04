import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { useMeta } from '../lib/data'
import { useLastPush, usePushes, usePushRecorder } from '../lib/live'
import { pct } from '../lib/format'

/** Shows SpacetimeDB doing its job: each pushed change slides in here, at the same moment in every open browser. */
export function PushToasts({ league }: { league: string }) {
  usePushRecorder()
  const all = usePushes()
  const meta = useMeta(league).data ?? {}
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  const shown = all.filter((p) => p.league === league && now - p.at < 9000).slice(0, 3)
  if (!shown.length) return null
  return (
    <div className="push-stack" aria-live="polite">
      {shown.map((p) => {
        const a = meta[p.row.awayId]?.abbreviation ?? 'Away', h = meta[p.row.homeId]?.abbreviation ?? 'Home'
        const what = p.kind === 'score' ? `${a} ${p.row.awayScore}, ${h} ${p.row.homeScore}`
          : p.kind === 'state' ? `${a} at ${h}: ${p.row.state === 'post' ? 'final' : p.row.state === 'in' ? 'under way' : p.row.state}`
          : `${a} at ${h}: ${h} win probability ${pct(p.old.pHome, 0)} → ${pct(p.row.pHome, 0)}`
        return (
          <Link key={p.id} to={`/${league}/game/${p.eventId}`} className="push-toast">
            <Zap size={15} aria-hidden />
            <div><b>Pushed by SpacetimeDB · state v{String(p.row.stateVersion)}</b><span>{what}{p.kind === 'score' ? (p.row.pHome >= 0.5 ? ` · ${h} ${pct(p.row.pHome, 0)} to win` : ` · ${a} ${pct(1 - p.row.pHome, 0)} to win`) : ''}</span></div>
            <small>{Math.max(0, Math.round((now - p.at) / 1000))}s ago</small>
          </Link>
        )
      })}
    </div>
  )
}

export function LastPush() {
  const at = useLastPush()
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  if (!at) return null
  const s = Math.round((now - at) / 1000)
  return <span className={`last-push ${s < 3 ? 'fresh' : ''}`}>last push {s < 60 ? `${s}s` : `${Math.round(s / 60)}m`} ago</span>
}
