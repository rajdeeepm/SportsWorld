# Deploy the original SportsWorld app

The user requires the original `frontend/` React application and `backend/`
FastAPI engine, with the existing UI and seven league tabs. The replacement
NFL-only `portfolio/` exhibit was rejected. Do not use it as the main site.

## Backend

`render.yaml` specifies a Free Python web service. It installs `./backend`,
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

Cloud runs use `SEASON_BATCH_DRAWS=64`: all 10,000 season draws are simulated,
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

Verify every league, team navigation, real scenario submission, research,
news, direct route reloads and live connections before replacing the domain's
deployment. Preserve `www.worldofsports.tech` and the Vercel alias redirects to
`worldofsports.tech`. The Mac and its Cloudflare tunnel are not cloud hosting.

## Status

Prepared, not yet deployed. Backend sign-in and service provisioning remain
pending; the original frontend is built locally. Do not mark this release done
until the correct experience is visibly live and API checks pass.

Local verification on 12 October 2026: the original frontend production build
passes with the cloud REST fallback; 33 backend tests pass. Production admin
protection returns 403 without a configured token, and the bound scenario
limiter returns 429 with Retry-After. All 29 published input parts match the
local data bundle; restoration matches all 514 original input files.
With all seven tracker inputs and original warm states loaded, the largest
college-basketball 10,000-draw recomputation peaks at about 474 MiB on the Mac,
down from about 4 GiB before batching. Cloud memory and latency still need
verification on the actual Free instance.
