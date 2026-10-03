import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Shell } from './components/Shell'
import { LEAGUE_BY_ID, league } from './lib/leagues'
import { LeagueWorld } from './pages/LeagueWorld'
import { TeamWorld } from './pages/TeamWorld'
import { SimLab } from './pages/SimLab'
import { Games } from './pages/Games'
import { Standings } from './pages/Standings'
import { F1World, F1Lab, F1Constructor } from './pages/F1World'
import { ResearchPage } from './pages/ResearchPage'
import { EventTerminalPage } from './pages/EventTerminalPage'
import { LiveGame, F1Live } from './pages/LiveGame'

function LeagueRoute({ view }: { view: 'overview' | 'team' | 'lab' | 'games' | 'standings' | 'game' | 'live' }) {
  const p = useParams()
  if (!p.league || !(p.league in LEAGUE_BY_ID)) return <Navigate to="/college-football" replace />
  const lg = league(p.league)
  if (lg.id === 'f1') {
    if (view === 'team') return <F1Constructor id={p.teamId!} />
    if (view === 'lab') return <F1Lab />
    if (view === 'live') return <F1Live />
    if (view !== 'overview') return <Navigate to="/f1" replace />
    return <F1World />
  }
  switch (view) {
    case 'team': return <TeamWorld key={p.teamId} lg={lg} teamId={p.teamId!} />
    case 'lab': return <SimLab lg={lg} />
    case 'game': return <LiveGame key={p.eventId} lg={lg} eventId={p.eventId!} />
    case 'games': return <Games lg={lg} />
    case 'standings': return <Standings lg={lg} />
    default: return <LeagueWorld lg={lg} />
  }
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/college-football" replace />} />
      <Route path="/research" element={<Shell><ResearchPage /></Shell>} />
      <Route path="/event/:eventId" element={<Shell><EventTerminalPage /></Shell>} />
      <Route path="/:league" element={<Shell><LeagueRoute view="overview" /></Shell>} />
      <Route path="/:league/team/:teamId" element={<Shell><LeagueRoute view="team" /></Shell>} />
      <Route path="/:league/lab" element={<Shell><LeagueRoute view="lab" /></Shell>} />
      <Route path="/:league/games" element={<Shell><LeagueRoute view="games" /></Shell>} />
      <Route path="/:league/standings" element={<Shell><LeagueRoute view="standings" /></Shell>} />
      <Route path="/:league/game/:eventId" element={<Shell><LeagueRoute view="game" /></Shell>} />
      <Route path="/f1/live" element={<Shell><F1Live /></Shell>} />
      <Route path="*" element={<Navigate to="/college-football" replace />} />
    </Routes>
  )
}
