import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Users } from 'lucide-react'
import { useMeta, useSeason, useStandings } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { pct } from '../lib/format'
import { ErrorNote, Loading, Panel, TeamLogo } from '../components/ui'

export function TeamProfiles({ lg }: { lg: LeagueConfig }) {
  const season = useSeason(lg.id)
  const standings = useStandings(lg.id)
  const meta = useMeta(lg.id).data ?? {}
  const [q, setQ] = useState('')
  const [conf, setConf] = useState('All')
  const rec = useMemo(() => new Map((standings.data?.rows ?? []).map((r) => [r.team_id, r])), [standings.data])
  const teams = season.data?.teams ?? []
  const rank = useMemo(() => new Map(teams.slice().sort((a, b) => b.rating - a.rating).map((t, i) => [t.team_id, i + 1])), [teams])
  const qk = lg.qualify
  const qShort = lg.milestones.find((x) => x.key === lg.qualify)?.short ?? 'Playoffs'
  const groups = useMemo(() => {
    const m = new Map<string, typeof teams>()
    for (const t of teams) {
      const name = meta[t.team_id]?.short_name ?? t.name
      if (q && !`${t.name} ${name} ${t.abbreviation ?? ''}`.toLowerCase().includes(q.toLowerCase())) continue
      const c = t.conference || 'Independent'
      if (conf !== 'All' && c !== conf) continue
      m.set(c, [...(m.get(c) ?? []), t])
    }
    const best = (ts: typeof teams) => ts.reduce((s, t) => s + Number((t as Record<string, unknown>)[qk] ?? 0), 0)
    return [...m.entries()].map(([c, ts]) => [c, ts.slice().sort((a, b) => Number((b as Record<string, unknown>)[qk] ?? 0) - Number((a as Record<string, unknown>)[qk] ?? 0) || b.rating - a.rating)] as const)
      .sort((a, b) => best(b[1]) - best(a[1]))
  }, [teams, meta, q, conf, qk])
  const confs = useMemo(() => ['All', ...[...new Set(teams.map((t) => t.conference || 'Independent'))].sort()], [teams])
  return (
    <>
      <div className="hero"><div>
        <p className="hero-kicker">Know what matters before you watch.</p>
        <h1>{lg.name}: <em>Team Profiles</em></h1>
        <p>Every team SportsWorld tracks, by conference: record, strength rank, and the odds from 10,000 simulated seasons. Open any team for its full season world.</p>
      </div></div>
      <div className="profiles-tools">
        <label className="field-search"><Search size={15} aria-hidden /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a team" aria-label="Find a team" /></label>
        <select className="field" value={conf} onChange={(e) => setConf(e.target.value)} aria-label="Conference">{confs.map((c) => <option key={c}>{c}</option>)}</select>
      </div>
      {season.isLoading ? <Loading rows={8} /> : season.error ? <ErrorNote error={season.error} what="the season run" /> : groups.map(([c, ts]) => (
        <Panel key={c} title={c} icon={Users} className="profiles-conf">
          <div className="profiles-grid">
            {ts.map((t) => {
              const m = meta[t.team_id]
              const r = rec.get(t.team_id)
              const v = t as unknown as Record<string, number | undefined>
              return (
                <Link key={t.team_id} to={`/${lg.id}/team/${t.team_id}`} className="profile-card" style={{ ['--tc' as string]: m?.color ?? '#2f81f7' }}>
                  <TeamLogo meta={m} name={t.name} size={40} />
                  <div className="profile-id">
                    <b>{m?.short_name ?? t.name}</b>
                    <small>{r ? `${r.wins}-${r.losses}${r.ties ? `-${r.ties}` : ''}${r.ot_losses ? `-${r.ot_losses}` : ''}` : '-'}{r?.conf_record ? ` · ${r.conf_record} conf` : ''} · #{rank.get(t.team_id)} strength</small>
                  </div>
                  <div className="profile-odds">
                    <span><small>{qShort}</small><b>{pct(v[qk] ?? null, 0)}</b></span>
                    <span><small>Title</small><b>{pct(v.champion ?? null, (v.champion ?? 0) < 0.01 && (v.champion ?? 0) > 0 ? 1 : 0)}</b></span>
                  </div>
                </Link>
              )
            })}
          </div>
        </Panel>
      ))}
    </>
  )
}
