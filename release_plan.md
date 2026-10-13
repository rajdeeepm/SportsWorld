# Original SportsWorld deployment correction

The user rejected the NFL-only static exhibit on 11 October 2026. The required release is the original React application with all seven league tabs, original design, team pages, Simulation Lab, research and live API. Hosting changes do not authorize a redesign or reduction in scope.

Current deployment: the original frontend now serves worldofsports.tech from Vercel (`frontend`, Vite, `dist`), with the original API on Render Free at sportsworld-api.onrender.com. Account verification is complete. Apex HTTPS and both 308 redirects are verified. Public runtime inputs restore 514 original files; 41 backend checks and the frontend build pass locally. Real public NFL and college-basketball scenarios completed with 10,000 seasons per branch after memory, archive-read and CPU-priority fixes. The largest observed round trip was about ten minutes on the free CPU; see the deployment notes for exact checks and limits. Optional credential-backed integrations remain unconfigured.

See `docs/original-cloud-deployment.md`. The previous static release notes below are retained as history and are superseded.

---

## Superseded static release history

On 11 October 2026 the user chose an interactive historical exhibit plus the reproducible GitHub repo. Deploy `portfolio/` from `rajdeeepm/SportsWorld`, preset Other, no build/install command, no environment variables. No Supabase database or always-on engine is needed. The earlier full-production proposal below is retained for future reference and is superseded for this launch.

Canonical address: `https://worldofsports.tech`. Attach apex and `www` to this Vercel project, point their DNS records at the exact values Vercel assigns, and redirect `www` to the apex. Connect the domain only after the Vercel preview passes validation. Keep unrelated DNS records. Domain registration renewal remains separate from free-tier hosting.

Status: deployed to Vercel Hobby and verified over HTTPS at https://worldofsports.tech. The www host and sportsworld-portfolio.vercel.app production alias redirect to the apex with 308 redirects. GitHub source, static data checks, offline regeneration, public downloads, desktop/mobile review and DNS cutover are complete. See docs/portfolio-deployment.md for the verified setup. This ships the scoped historical exhibit; it does not resolve every issue in the original engine audit.

# SportsWorld release plan

Prepared October 11, 2026 against source HEAD `5cfd6be`. Goal: a reliable public release on worldofsports.tech with defensible forecasts and a coherent product experience. Findings: [wrong_details.md](wrong_details.md).

## Current state

## Proposed GitHub + Vercel + Supabase deployment

User preference: use GitHub, Vercel and Supabase. This is a supported proposed topology; accounts have not been connected and nothing has been deployed.

| Component | Proposed placement | Repository work |
|---|---|---|
| React/Vite frontend | Vercel, connected to the existing GitHub repo | Root directory `frontend`, build `npm run build`, output `dist`; SPA fallback and explicit API routing |
| PostgreSQL/history | Supabase | Versioned SQL migrations for existing core/history tables, secure backend connection, permissions and tested history import |
| Python API, trackers and simulation loops | Always-on container/VM runtime | Production backend image, supervised worker/state ownership, persistent model/data storage and deploy workflow |
| Live browser subscriptions | Existing SpacetimeDB initially, or a deliberate Supabase Realtime migration | Keeping existing hooks reduces first-release changes; replacing them requires snapshot tables/publishers, Supabase client hooks, access policies and reconnect/version tests |

Vercel supports FastAPI, but deploys it as a traffic-scaled Function. Given this project's continuous pollers/background loops and process-owned state, the recommendation is to retain an always-on engine runtime rather than upload the existing whole backend as a Function unchanged. This is an architecture inference from the source and [Vercel's runtime documentation](https://vercel.com/docs/frameworks/backend/fastapi).

The existing Neon archive uses ordinary PostgreSQL SQL and psycopg. Supabase can supply that database, subject to schema/connection testing and historical-data migration. Renaming the archive class alone does not migrate data or solve existing cursor/recovery defects. For a persistent backend, use the appropriate direct or session-pooler connection according to network support, per [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

The Vite development/preview proxy does not become a production Vercel proxy. Configure `/api` rewrites to the engine or an explicit public API base with correct origins. Configure secure live endpoints separately, and keep production secrets on the backend. Database tables exposed through the Supabase browser APIs require deliberate permissions/RLS; service-role credentials never belong in the frontend. [Supabase Realtime setup](https://supabase.com/docs/guides/realtime/postgres-changes).

GitHub can drive Vercel pull-request previews and production-branch deployments. Database migrations and backend releases need their own coordinated pipeline so frontend releases do not race incompatible schema/API changes. [Vercel GitHub deployment workflow](https://vercel.com/docs/git/vercel-for-github).

Implementation sequence: fix confirmed release blockers → provision/configure Supabase schema and engine runtime → deploy a Vercel preview → validate the complete flow and recovery → move worldofsports.tech to the tested Vercel release. Preserve the old deployment until cutover and rollback are verified.

## Existing runtime observations

The public browser currently displays Cloudflare Tunnel error1033. This means Cloudflare cannot find a healthy connector, not proof that application code itself caused the failure. [Cloudflare troubleshooting](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/troubleshoot-tunnels/common-errors/).

The repository's public-serving script expects a local API, Vite preview, optional LLM tunnel and a Cloudflare Tunnel, with the machine kept awake. Checked-in Compose is a demo configuration, not a finished production deployment. Existing CI builds/tests but does not deploy. Supporting AWS infrastructure does not provision the full runtime.

No deployment was performed. Hosting account, origin host, production version, credentials and budget have not been established. Do not paste secrets into these documents or chat.

## 0. Restore and identify the existing deployment

- [ ] Identify where the Cloudflare connector and origin application run, who owns them and the exact deployed commit.
- [ ] Check connector health, DNS/hostname mapping, origin listener and API readiness separately. At inspection, no local listeners were found on8000or5173; the public script uses4173 for preview, so those checks alone do not establish the full local state.
- [ ] Restore the existing service where appropriate without resetting production data, killing unrelated tunnels or exposing unprotected admin routes.
- [ ] Capture a baseline deployment manifest: code SHA, model/rules/artifact versions, environment-variable names, storage locations and rollback procedure.

Done when: both root/www domains load, a public API request succeeds, a valid team deep link works on refresh, and origin/tunnel processes recover after a controlled restart. Restoration alone is not a production-quality release.

## 1. Make displayed numbers mean what they say

- [ ] Revalidate earlier findings against the present commit; add regression cases for confirmed defects.
- [ ] Fix CFP semifinal cardinality, current eligibility and season-specific historical rules.
- [ ] Correct basketball field/opening-round/conference-tournament support; disclose committee selection approximations.
- [ ] Reconcile league membership and complete schedules, including NHL season boundaries and unresolved NBA Cup slots.
- [ ] Remove future contingent-matchup leakage and duplicate conference championships from historical replay.
- [ ] Choose/document the probability contract: calibrated game marginals versus correlated season outcomes. Either align them or visibly distinguish them.
- [ ] Capture canonical/live state once for scenario branches. Validate IDs, outcome enums, finite deltas and effective windows; reject unsupported operations explicitly.
- [ ] Fix seeds, postseason windows, postseason conditioning and F1 countback/classification consistency where supported.
- [ ] Display sampling/model uncertainty honestly, including near0/100% and paired scenario changes.
- [ ] Replace complete-number-verification claims with typed fact validation or deterministic templates.

Done when: official eligibility/cardinality checks pass; scenarios use the stated baseline and dates; invalid operations fail clearly; state hashes include causal inputs; served forecast/version provenance can be inspected.

## 2. Make updates, storage and errors reliable

- [ ] Fix feed sequences/cursors across bounded queues and restarts; settle removed/final games.
- [ ] Make ingestion atomic and serialize conflicting transitions; validate batches before mutation.
- [ ] Persist unique run identifiers and recover durable-history writers after initial/transient failures.
- [ ] Compare versions/timestamps before merging pushed and REST snapshots; use one committed snapshot marker.
- [ ] Separate source-attempt time, source-success time and compute time. Expose degraded/stale/unsupported states.
- [ ] Repair active injury horizons and expiry/correction invalidation.
- [ ] Bound telemetry caches, histories, concurrent jobs and paid-provider usage.
- [ ] Make admin authentication fail closed; install limits on actual simulation/chat/TTS routes.
- [ ] Isolate listener commentary and fix latest-result ordering, live/replay wording and actual draw counts.
- [ ] Verify explicit scope of F1, Neon, SpacetimeDB and optional agent/storage paths.

Done when: more than60successive updates archive correctly; restart history does not collide; disconnect/reconnect does not regress state; injected source/storage failures visibly degrade and recover; concurrent ingestion loses no accepted transition; expensive requests remain bounded.

## 3. Regenerate evidence before restoring research claims

- [ ] Run historical evaluation with correct season formats and publication/known-time cutoffs.
- [ ] Exclude incomplete truth; use the exact serving prediction/aggregation function.
- [ ] Match inputs when comparing model capacity; bootstrap/infer at the correct game/team grain.
- [ ] Generate published tables from actual held-out counts and artifact metrics.
- [ ] Validate interval/delta coverage or relabel unvalidated bands; disclose market timing and associational effects.
- [ ] Link versioned artifacts, sample sizes, windows, exclusions and limitations from Research.

Done when: every numerical claim traces to a versioned artifact and reproducible command; affected before/after performance is measured on matched samples. Retraining is targeted to affected pipelines, not an automatic prerequisite for every UI fix.

## 4. Finish the user experience

- [ ] Correct coverage denominators and paginate the whole game board.
- [ ] Keep Lab results associated with executed inputs and mark them stale after edits.
- [ ] Preserve viewed team/league context; add valid404and separate loading/error/empty states.
- [ ] Fix phone reflow, team search, readable captions/provenance and keyboard controls.
- [ ] Correct standings/rank/period/unit labels and sport-specific examples.
- [ ] Make F1 tables complete, round quantiles and synchronize replay chronology/classification.
- [ ] Retire unsupported/legacy views or label them explicitly; keep synthetic-data disclosures visible.
- [ ] Walk every advertised league/page family at desktop and phone sizes, including failed/unsupported states.

Done when: a visitor can choose a team, inspect its next game, run a scenario and understand the result without encountering hidden context changes or misleading labels.

## 5. Build a production deployment

Recommended architecture for this codebase: an always-on backend/worker runtime, a production static frontend, durable model/data storage, Neon history and SpacetimeDB subscriptions. Keep the existing Cloudflare domain/routing if useful. A VM or managed container service can provide the runtime; choose the actual host after current ownership/access and budget are known.

The engine contains long-lived trackers, in-memory state and background loops. Do not blindly increase API workers: each process may start another tracker/archive publisher and serve a different state. Begin with one supervised engine process or separate tracking/simulation workers from stateless API replicas with shared durable state.

- [ ] Production Compose/runtime configuration with explicit real-data/model/artifact paths and live-tracking mode.
- [ ] Persistent volumes/backups for mutable archives, warm state and caches; test restore.
- [ ] Server-side secrets for admin, database, Spacetime publisher and optional providers. Frontend configuration contains only public endpoints.
- [ ] HTTPS/wss, correct API/WebSocket proxy routes, public origin, trusted proxy handling and SPA deep-link fallback.
- [ ] Locked dependency installation/builds, versioned image/artifact releases and nondevelopment serving.
- [ ] Supervised processes, readiness/liveness checks, logs and alerts for uptime, source lag, writer failures, queue backlog and resource usage.
- [ ] Degraded operation for unavailable LLM/TTS/history; core forecasts remain usable when optional integrations fail.
- [ ] Staging release, smoke checks and one-command rollback to the previous compatible version.

Done when: the site keeps operating without a laptop session, restarts safely, persists updates, exposes genuine readiness, and can be rolled back without corrupting data.

## 6. Verify and cut over

- [ ] Backend checks appropriate to rule, state, concurrency, recovery and security changes pass.
- [ ] Frontend TypeScript/production build passes.
- [ ] Staging exercises all seven league overviews and supported team/standings/forecast/Lab/research/replay routes.
- [ ] Real-time synchronization works across two browsers and after reconnect/restart.
- [ ] Controlled sustained traffic measures resource/cost ceilings; no unbounded public simulations or TTS loops.
- [ ] Staging data/provider failures display accurate fallback states.
- [ ] Production release is traceable to a tested commit and artifact set; public smoke checks pass after cutover.
- [ ] A monitored observation period spans ordinary polling, simulation and archival activity. Final changes to rules/models regenerate the necessary forecasts/evidence before closing the release.

## Required external inputs

1. Current origin/connector host and authorized deployment access.
2. Hosting budget and whether an existing cloud account/server should be reused.
3. Existing secure credentials/access for Cloudflare, Neon, SpacetimeDB and optional voice/LLM/agent services.
4. Release deadline and whether unsupported leagues may be labeled preview while being completed.

These inputs affect hosting/cutover choices; local correctness, reliability, report and UX work can progress independently. No paid resource should be provisioned without an agreed budget. No secrets should be committed to the repository.
