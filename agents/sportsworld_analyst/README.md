# SportsWorld Analyst

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Agent name:** `sportsworld-analyst`
**Agent address:** `agent1qwh0gtgvn9j8cv8dzsa6jjz7tan0xr0yazds2vymxlvhyq8ehzevja34v5w`

An agent that runs **SportsWorld**, a live probabilistic world model of entire sporting seasons: every team and
game in the NFL, college football, NBA, NHL, college basketball and Formula 1. It does not chat about sports; it
turns your question into actions on the live engine and answers with calibrated numbers.

## What it does
| Ask | Action the agent takes |
|---|---|
| *How are Michigan doing?* | Reads the live season run: record, expected wins with a 90% range, playoff and title odds, next game, and the remaining game that swings their season most |
| *What if Michigan's starting QB misses 3 games?* | Builds a typed scenario (learned player-impact effect, exact game window), runs **10,000 simulated seasons per branch** with common random numbers, reports before / after for the affected teams |
| *What if Michigan beats Ohio State?* | Finds the real remaining game, forces the result on a private branch, re-simulates the whole season |
| *Which games matter tonight?* | Ranks live and upcoming games by season leverage × how close they are, and recommends one |
| *Should I watch BYU or Texas Tech?* | Compares the two games' stakes and closeness and picks one |
| *Who wins Ohio State vs Iowa?* | Live score and SportsWorld's in-game win probability, or the final if it is over |
| *Who will win the Super Bowl?* / *F1 title odds* | Title odds with Monte Carlo error |

Every number comes from the SportsWorld engine (Kalman latent team strength, learned game models, whole-season Monte
Carlo with versioned playoff rules), backtested on seven replayed seasons. Intent routing is deterministic; no
language model writes a probability.

## Run
```
python agents/sportsworld_analyst/agent.py     # next to a running SportsWorld API (SPORTSWORLD_API, default http://127.0.0.1:8000)
```
The agent uses an Agentverse **mailbox**, so ASI:One conversations reach it without a public endpoint. It speaks the
**Agent Chat Protocol**.

Live site: https://worldofsports.tech
