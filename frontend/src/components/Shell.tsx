import { useMemo, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Activity, CalendarDays, FlaskConical, Home, ListOrdered, MapPinned, Microscope, Radio, Search } from 'lucide-react'
import { BrandMark, TeamLogo } from './ui'
import { LEAGUES, league as leagueOf } from '../lib/leagues'
import { useBoard, useMeta, useSeason } from '../lib/data'
import { useLiveStatus } from '../lib/live'
import { AskPanel } from './AskPanel'

export function Shell({ children }: { children: ReactNode }) {
  const params = useParams()
  const loc0 = useLocation()
  // routes like /f1/live carry no :league param, so fall back to the first path segment
  const lid = params.league ?? loc0.pathname.split('/')[1]
  const lg = leagueOf(lid)
  const board = useBoard(lg.id)
  const live = lg.id === 'f1' ? 0 : (board.data?.events ?? []).filter((e) => e.state === 'in').length
  const base = `/${lg.id}`
  const loc = useLocation()
  const liveView = loc.search.includes('live=1')

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/college-football" className="brand" aria-label="SportsWorld home">
          <BrandMark />
          <span>
            <span className="brand-name">Sports<b>World</b></span>
            <span className="brand-sub">Season Intelligence Engine</span>
          </span>
        </NavLink>
        <nav className="league-tabs" aria-label="Leagues">
          {LEAGUES.map((l) => (
            <NavLink key={l.id} to={`/${l.id}`} className={({ isActive }) => (isActive || l.id === lg.id && !!lid ? 'active' : '')}>
              {l.tab}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-right">
          {lg.id !== 'f1' && <TeamSearch leagueId={lg.id} />}
        </div>
      </header>

      <nav className="rail" aria-label={`${lg.name} sections`}>
        <div className="rail-league">{lg.name}</div>
        <NavLink to={base} end><Home size={19} aria-hidden /> Overview</NavLink>
        {lg.id !== 'f1' && <NavLink to={`${base}/standings`}><ListOrdered size={19} aria-hidden /> Standings</NavLink>}
        {lg.id !== 'f1' && (
          <NavLink to={`${base}/games?live=1`} className={({ isActive }) => (isActive && liveView ? 'active' : '')}>
            <Radio size={19} aria-hidden /> Live {live > 0 && <span className="live-dot" title={`${live} live`} />}
          </NavLink>
        )}
        {lg.id !== 'f1' && <NavLink to={`${base}/games`} className={({ isActive }) => (isActive && !liveView ? 'active' : '')}><CalendarDays size={19} aria-hidden /> Forecasts</NavLink>}
        {lg.id === 'f1' && <NavLink to="/f1/live"><MapPinned size={19} aria-hidden /> Live track</NavLink>}
        <NavLink to={`${base}/lab`}><FlaskConical size={19} aria-hidden /> Simulation Lab</NavLink>
        <NavLink to="/research"><Microscope size={19} aria-hidden /> Research</NavLink>
        <div className="rail-foot">
          <b>Modelling a smarter sports world.</b>
          Every number is point-in-time, versioned and backtested.
          <LiveChip />
        </div>
      </nav>

      <main id="main">{children}</main>
      <AskPanel leagueId={lg.id} />
    </div>
  )
}

function TeamSearch({ leagueId }: { leagueId: string }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const ref = useRef<HTMLInputElement>(null)
  const season = useSeason(leagueId, leagueId !== 'f1')
  const meta = useMeta(leagueId)
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s || leagueId === 'f1') return []
    return (season.data?.teams ?? [])
      .filter((t) => t.name.toLowerCase().includes(s) || (t.abbreviation ?? '').toLowerCase() === s)
      .slice(0, 8)
  }, [q, season.data, leagueId])

  const go = (id: string) => {
    navigate(`/${leagueId}/team/${id}`)
    setQ('')
    ref.current?.blur()
  }

  return (
    <div className="search" role="combobox" aria-expanded={hits.length > 0} aria-haspopup="listbox">
      <Search size={16} aria-hidden />
      <input
        ref={ref}
        value={q}
        placeholder={leagueId === 'f1' ? 'Search is for team leagues' : 'Search teams…'}
        aria-label="Search teams"
        disabled={leagueId === 'f1'}
        onChange={(e) => { setQ(e.target.value); setSel(0) }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { setSel((s) => Math.min(s + 1, hits.length - 1)); e.preventDefault() }
          if (e.key === 'ArrowUp') { setSel((s) => Math.max(s - 1, 0)); e.preventDefault() }
          if (e.key === 'Enter' && hits[sel]) go(hits[sel].team_id)
          if (e.key === 'Escape') setQ('')
        }}
      />
      {hits.length > 0 && (
        <div className="search-results" role="listbox">
          {hits.map((t, i) => (
            <a key={t.team_id} href={`/${leagueId}/team/${t.team_id}`} className={i === sel ? 'on' : ''} role="option" aria-selected={i === sel}
              onMouseDown={(e) => { e.preventDefault(); go(t.team_id) }}>
              <TeamLogo meta={meta.data?.[t.team_id]} name={t.name} size={22} />
              {t.name}
              <small>{t.conference?.replace(' Conference', '')}</small>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function LiveChip() {
  const s = useLiveStatus()
  return (
    <div className="live-chip" title={s.connected ? 'Subscribed to the shared world state in SpacetimeDB; changes are pushed, not polled.' : s.error ?? 'SpacetimeDB not connected; using the REST API'}>
      <Activity size={14} aria-hidden />
      {s.connected ? <><span className="live-dot ok" /> SpacetimeDB live · {s.viewers} viewer{s.viewers === 1 ? '' : 's'}</> : <>REST polling (SpacetimeDB offline)</>}
    </div>
  )
}
