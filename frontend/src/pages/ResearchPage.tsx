import { SeasonReplay, Bakeoffs, PlayerImpact, Consensus, Rolling } from '../components/RealResearch'
import { Rewind } from '../components/rewind'

export function ResearchPage() {
  return (
    <>
      <div className="hero">
        <div>
          <h1>Quant research: <em>what the model knew, and how well it calibrated</em></h1>
          <p>Point-in-time season replays, walk-forward evaluation, in-game model bake-offs with game-clustered intervals, a market benchmark, and learned player-availability effects. Real data only.</p>
        </div>
      </div>
      <div style={{ marginBottom: 16 }}><Rewind /></div>
      <section className="research-grid">
        <SeasonReplay />
        <Rolling />
        <Bakeoffs />
        <Consensus />
        <PlayerImpact />
      </section>
    </>
  )
}
