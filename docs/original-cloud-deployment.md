# Deploy the original SportsWorld app

The user requires the original `frontend/` React application and `backend/`
FastAPI engine, with the existing UI and seven league tabs. The replacement
NFL-only `portfolio/` exhibit was rejected. Do not use it as the main site.

## Backend

`render.yaml` specifies a Free Python web service. It installs `./backend` in
editable mode so the engine's repository-relative artifact paths remain valid,
restores a checksummed bundle of public runtime archives, then runs
`scripts/start_cloud.py` with a single Uvicorn worker. The API owns continuous
score tracking, availability/news updates and season recomputations. Production
administrative writes are disabled unless an admin token is explicitly set.
Public scenario evaluation remains available.

The runtime bundle contains 514 original files: normalized score archives,
schedules and structures, metadata, F1 inputs, box scores, news caches and warm
states. The SHA-256 is recorded in `deployment/engine-data/manifest.json`.
Raw odds, play-by-play and provider summaries used for training are intentionally
not part of runtime startup; the original backfill scripts reproduce those
downloads. Existing tracked backtest artifacts remain available to Research.

Cloud runs use `SEASON_BATCH_DRAWS=256`: all 10,000 season draws are simulated,
and their exact summaries are computed from temporary disk-backed arrays. This
bounds memory without replacing the engine with saved scenario branches.
Batching changes random-number ordering, so outputs record
`team_season_sim_v1_batched_v1`, the seed and the batch size.

Free Render services sleep after 15 idle minutes and take roughly a minute to
wake. Their writable filesystem is ephemeral: startup inputs are restored on
each build, and live caches are regenerated following a restart. Free usage
limits apply. No payment method or paid instance is authorized. Persistent
historical run archival and optional third-party voice/LLM integrations require
separate configured credentials; do not claim them connected without testing.

## Frontend and cutover

Use Vercel's Vite preset with Root Directory `frontend`, build `npm run build`
and output `dist`. Configure a same-origin `/api` rewrite to the verified cloud
backend, a React Router fallback to `/index.html`, and `VITE_WS_BASE` for direct
secure WebSocket access to that backend. The original Maincloud subscription
must only overlay REST data if the cloud backend is publishing to it.
After the backend URL has been verified, run
`python scripts/configure_cloud_frontend.py https://VERIFIED-BACKEND-ORIGIN`
to generate those public settings. Then build, publish the generated config
and public environment file, and change Vercel's root from `portfolio` to
`frontend`. Do not cut over using the placeholder above.

Verify every league, team navigation, real scenario submission, research,
news, direct route reloads and live connections before replacing the domain's
deployment. Preserve `www.worldofsports.tech` and the Vercel alias redirects to
`worldofsports.tech`. The Mac and its Cloudflare tunnel are not cloud hosting.

## Status — 12 October 2026

The original frontend is deployed at https://worldofsports.tech, using Vercel
project `cse-594/sportsworld-portfolio`, Root Directory `frontend`, Vite and
`dist`. `www.worldofsports.tech` and `sportsworld-portfolio.vercel.app` both
return HTTP 308 to the canonical domain. The rejected static replacement is
superseded.

The original API is deployed on Render Free at
https://sportsworld-api.onrender.com, service `srv-db6h1a0m7kps73dtn4sg`.
Email verification is complete. Build command:
`pip install -e ./backend && python scripts/prepare_cloud_data.py`.
Start command: `python scripts/start_cloud.py`. Health path: `/health`.
Vercel deploys commits to main automatically. Render uses a public repository
connection: backend updates require **Manual Deploy → Deploy latest commit**.
No paid service or payment method was added. No Supabase service was created.

Original league views, team pages, research and public API responses have been
observed. A real public NFL scenario completed with 10,000 seasons per branch, using the
original controls and displaying the original result tables. At batch size 64,
its observed round trip was 101.2 seconds. Health requests during/after the run
returned 200 in roughly 0.13–0.3 seconds in focused checks. A fresh college-football
canonical recomputation also completed without a worker error.

Render reported earlier health timeouts and a 512 MiB memory failure. Fixes copy
summary rows before remapping, return flushed Linux file-cache pages and freed
heap allocations to the OS, and use column-oriented temporary files for per-team
and per-game summaries. A regression verifies identical summary values after
changing file layout. The largest league's 10,000-draw local run at batch size
256 completed for 365 teams with one champion per draw; the results preserve all requested draws.
The 256-draw cloud build completed the largest public scenario: 365 college-
basketball teams, 10,000 seasons per branch, seed 7, one champion in every draw.
The UI reported 609.3 seconds round trip, including queue time, and engine
runtimes of 242.83 + 190.64 seconds. This is a successful functional check,
not a concurrent-load or uptime certification. The free CPU can make larger
simulations take around ten minutes; smaller NFL scenarios were substantially
faster. The original design and requested draw counts remain intact.

Recent team results now stream only that team's archive records and share a
bounded 20-second, state-versioned cache, rather than repeatedly loading every
historical game in the league. A correction invalidation test confirms the
same results as the original archive merge. Linux simulation workers use lower
CPU priority so the web API can stay responsive. Temporary diagnostic logging
was removed after verification. Render also recorded later memory failures
at 16:59 and 17:03 on the diagnostic build, so passing one large scenario is
not sufficient evidence of sustained stability. The final startup now sets
`PYTHONMALLOC=malloc`; combined with collection and `malloc_trim` before each
worker, this allows Linux to reclaim freed historical-record allocations rather
than retaining them in Python's small-object arenas. The allocator change is
pending its own cloud verification.

Cloud simulation work runs in one isolated subprocess at a time. Expensive
POST routes return an opaque queued job with HTTP 202; the original frontend
polls that job and displays the original result format. Pending jobs and saved
results are bounded and ephemeral, and disappear on restart. This avoids
keeping a long simulation in one gateway request.

LLM, ElevenLabs, SpacetimeDB publishing and PostgreSQL archival credentials
are not configured. REST polling is enabled. Those optional integrations are
not verified live. College hockey retains its original tracker and UI but does
not have a season postseason simulator in the original engine. Historical
model/data-quality findings in `wrong_details.md` remain separate work.

Local verification on 12 October 2026: the original frontend production build
passes with the cloud REST fallback; 41 backend tests pass. Production admin
protection returns 403 without a configured token, and the bound scenario
limiter returns 429 with Retry-After. All 29 published input parts match the
local data bundle; restoration matches all 514 original input files.
With all seven tracker inputs and original warm states loaded, the largest
college-basketball 10,000-draw recomputation peaks at about 474 MiB on the Mac,
down from about 4 GiB before batching. Observed cloud latency and remaining free-tier limitations are recorded above.

## Verification and maintenance

Verified publicly: the original CFB overview, NFL team deep link, populated
Research and News, six season-forecast API responses (32 NFL, 138 CFB, 30 NBA,
365 CBB, 32 NHL, 23 F1 drivers), NFL and CBB private scenario submissions and
results, HTTPS and both canonical redirects. The public mobile overview at
390 × 844 has document width 380 pixels. Screenshots are retained locally in
`docs/deployment/original-live-*.jpg`. The seven league trackers are configured;
that does not imply seven postseason simulators.

After a restart/deploy, cached inputs serve immediately with their original
computation timestamps while the worker rebuilds current runs. Inspect `/health`
for tracker errors, season `status` and `last_error`; a stale run is not a fresh
forecast. Optional integration flags remain false until credentials are added.

Vercel rollback: select a previous **original frontend** deployment and use
Instant Rollback. Do not roll back to the rejected `portfolio/` deployment.
Render rollback: select a tested previous backend deploy in Events; remember
that in-memory private jobs expire on restart and writable caches are ephemeral.
Domain registration renewal is separate from free hosting.
