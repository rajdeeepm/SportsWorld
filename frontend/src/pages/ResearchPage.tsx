import { SeasonReplay, Bakeoffs, PlayerImpact, Consensus, Rolling } from '../components/RealResearch'

export function ResearchPage() {
  return (
    <>
      <div className="hero">
        <div>
          <h1>Quant research — <em>what the model knew, and how well it calibrated</em></h1>
          <p>Point-in-time season replays, walk-forward evaluation, in-game model bake-offs with game-clustered intervals, a market benchmark, and learned player-availability effects. Real data only.</p>
        </div>
      </div>
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
