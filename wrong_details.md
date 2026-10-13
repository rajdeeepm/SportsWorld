> Deployment correction, 12 October 2026: the user rejected the NFL-only static replacement. The required release is the original seven-league app. The original frontend is now live on Vercel at worldofsports.tech, with its API on Render Free. Public NFL and college-basketball 10,000-draw scenarios completed after memory and request-load fixes; the largest observed round trip was about ten minutes on the free CPU. The historical static-deployment notes are superseded by [docs/original-cloud-deployment.md](docs/original-cloud-deployment.md). Known model findings remain subject to revalidation. Local production admin protection, scenario rate limiting and simulation memory fixes are implemented; functional cloud checks passed; concurrent load, long-term uptime and historical model findings remain separate work.

# SportsWorld — adversarial findings register

Prepared October 11, 2026. Earlier product walkthrough: October 3, 2026. Current source reviewed: `5cfd6be`.

This register preserves the earlier review and adds launch findings. **It is not a claim that every earlier finding remains unfixed.** The earlier temporary screenshots/reproduction files are no longer available in this workspace; their observations below are recorded from the review, not linked as retained evidence. Current code has changed since that review, including additional conversational-verdict checks. Revalidate each historical item before implementing a fix or calling it a current deployed defect.

P1 = material trust/correctness/reliability issue; P2 = significant usability, evidence or integration issue; P3 = limited-impact polish. Conditional findings depend on configuration or optional paths. Related entries describe facets of the same root cause and should be combined into implementation tickets.

No implementation changes, production mutations, credential inspection, load tests or security attacks were performed for this register.

## Current launch blockers — checked October 11

| ID | Priority | Confirmed evidence | Required action |
|---|---|---|---|
| L01 | P1 | Public browser visit shows Cloudflare Tunnel error 1033. [Screenshot](docs/audit/2026-10-11-cloudflare-1033.png), [page text](docs/audit/2026-10-11-cloudflare-1033.txt). | Identify the origin host, restore a healthy connector and supervise it. Verify application/API independently of tunnel connectivity. |
| L02 | P1 | `docker-compose.yml` sets demo mode, memory store and localhost frontend origin; no persistent volumes, health checks or restart policies are defined. Tracking is disabled by default in `config.py`. | Prepare a real production runtime with live tracking, explicit data/artifact paths, persistence, secrets and supervision. |
| L03 | P1 | `season/rules.py:224–245` still selects five highest-ranked conference champions and stores semifinal winners under the semifinal milestone. | Implement current eligibility and mark the four quarterfinal winners as semifinal entrants. Test cardinalities and mandatory bids. |
| L04 | P1 | `season/rules.py:269` still builds a 64-team basketball tournament. | Version tournament field/selection rules by season and support opening rounds; clearly disclose committee approximations. |
| L05 | P1 | `live/spacetime_publisher.py:127–135` still uses queue length and `feed[seen:]` on a newest-first bounded feed. | Use immutable update sequences and replay/deduplication cursors, including restart recovery. |
| L06 | P1 | `live/neon_archive.py:86–100` initializes outside its retry loop. | Retry initialization, supervise failed tasks and expose genuine archive readiness/errors. |
| L07 | P1 | `api/main.py:140–144` still permits admin mutations when the admin token is absent. Production token configuration was not inspected. | Fail closed in production and disable/restrict mutation routes. Verify deployed protection. |
| L08 | P1 | `api/season_routes.py:18–24` receives the expensive-route limiter but does not install it as a dependency. | Apply rate, concurrency and cost bounds to simulation, chat and TTS paths; check any upstream protections. |
| L09 | P1 | `agent/converse.py` adds wording/verdict checks but still verifies numerical strings as sets, allowing small integers and ignoring entity/sign/metric associations. | Validate typed facts or use faithful templates; do not describe lexical checks as complete verification. |
| L10 | P2 | `scripts/serve_public.sh` serves a Vite preview through a foreground, machine-dependent tunnel. `tunnel_watchdog.sh` kills all matching tunnel processes. | Use a production static server and targeted, supervised services on an always-on host. Do not blindly run the watchdog on a machine with other tunnels. |
| L11 | P2 | The frontend Docker build runs `npm install`, copies no lockfile before installation and declares no production SpacetimeDB build configuration. | Use locked builds, explicit build-time public endpoints and secure WebSocket URLs. Never bake private credentials into the frontend. |
| L12 | P2 | `.github/workflows/ci.yml` tests/builds but does not deploy. AWS Terraform provisions supporting resources, not a running application. | Add staged release, versioned artifacts, post-deploy smoke checks and rollback. |

Relevant official sources, checked October 11: [CFP format](https://collegefootballplayoff.com/sports/2024/5/29/12-team-format), [NCAA expansion](https://www.ncaa.org/championships/march-madness/expansion-what-to-know/). The current CFP guarantees four power-conference champions, a specified other-conference representative and a conditional Notre Dame bid. The current basketball expansion is 76 teams beginning 2026–27. These differ from the local encoding.

## Earlier UI/design review — revalidate against the current build

All seven league overviews were inspected, along with representative team, standings, forecast/live-list, Lab/results, F1 constructor/replay, research and assistant flows. Phone inspection used 390×844 browser emulation. This was not every individual entity/event or a full accessibility certification.

| ID | Priority | Finding and evidence location | Fix direction |
|---|---|---|---|
| U01 | P2 | At 1280px, Lab controls occupy half a row and results fall below a long form. Spatial-game charts similarly fall below the field. `styles/app.css` middle breakpoint. | Use explicit responsive layouts and focus/scroll completed results into view. |
| U02 | P2 | Provenance uses `#4b5f86` on dark backgrounds, measured at about 2.85:1 against `#0a1528`; small captions are difficult to read. | Raise text contrast/size; verify actual rendered pairs. |
| U03 | P2 | Phone Research document width was 526px at a 390px viewport; not all tables were contained. `RealResearch.tsx`. | Contain each table or offer compact mobile views. |
| U04 | P2 | Team search disappears on phones without a replacement. `app.css:555`, `Shell.tsx`. | Provide mobile search/team picker. |
| U05 | P2 | Escape did not close Ask SportsWorld; no announced answer log or focus return. `AskPanel.tsx`. | Complete keyboard dismissal/focus/status semantics. |
| U06 | P2 | Search combobox lacks active-option IDs, controls linkage and autocomplete semantics. Simple Enter navigation worked. `Shell.tsx`. | Implement complete combobox semantics and no-match feedback. |
| U07 | P2 | F1 car highlighting uses clickable table rows without keyboard controls. `LiveGame.tsx`. | Use named, focusable selection buttons. |
| U08 | P2 | Statistics tabs lack complete tabpanel/keyboard linkage; research titles are generic spans. `stats.tsx`, `RealResearch.tsx`. | Add semantic headings and valid tabs, or ordinary filters. |
| U09 | P2 | Loading league transitions briefly assert zero games/no upcoming games before requests resolve. `LeagueWorld.tsx`. | Distinguish loading from successful empty data. |
| U10 | P2 | Availability/statistics errors appear as no model/no games/no box score. `TeamWorld.tsx`, `stats.tsx`. | Distinguish error, unsupported, stale and empty states. |
| U11 | P2 | Global `/research` falls back to a CFB shell/assistant context regardless of the incoming league. `App.tsx`, `Shell.tsx`. | Use a neutral shell or preserve selected competition. |
| U12 | P2 | Conference filter survives a league change and can hide all new results. `Standings.tsx`. | Reset or scope filters by league. |
| U13 | P2 | Unknown routes redirect to CFB; unknown teams are retried as warming; legacy back links use nonexistent `/leagues` routes. | Show real 404s; retry temporary failures only; fix canonical links. |
| U14 | P2 | College hockey promised historical research absent from the displayed table; standings showed only Ohio State and forecasts zero without a coverage warning. | Expose league readiness and calendar/membership completeness. |
| U15 | P2 | F1 replay session 11730 combined Bahrain and Kuala Lumpur labels. Root cause was not established. | Inspect raw provider metadata and reject/flag incompatible identities. |
| U16 | P2 | F1 cars animate through the window but running order stays at its end snapshot. `ingest/live_game.py`, `LiveGame.tsx`. | Synchronize classification and cars to playback time. |
| U17 | P2 | Championship outlook displays only 12 of 22 modeled entries with no show-all control. `F1World.tsx`. | Expose all entries and distinguish current from historical drivers. |
| U18 | P3 | McLaren interval printed `383.95000000000005`. `F1World.tsx` directly renders quantiles. | Round consistently by units. |
| U19 | P3 | Next race was Oct11 but panel said this weekend on Oct3. `F1World.tsx`. | Use date-aware wording or Next Grand Prix. |
| U20 | P2 | Race-win bars normalize by the favorite: a 22% favorite fills the track. Other panels use absolute probabilities. | Standardize scales or clearly label relative scaling. |
| U21 | P2 | Empirical 100% title odds show zero MC error; chart DOM exposed a negative probability tick. `charts.tsx`, F1 summary. | Use boundary-safe intervals, bounded axes and explicit sampling/model uncertainty. |
| U22 | P2 | Standings sort by qualification odds; conference-title rank is league-wide (Michigan rank108); ties omitted from relevant tables. | Separate record/projection ordering and label ranking universe/record format. |
| U23 | P2 | Michigan 56% win odds sat beside −0.2 expected margin with a separate rating-based explanation. Not inherently impossible, but model distinction was absent. | Explain the actual served model or label the separate margin model. |
| U24 | P2 | Lab claims common random numbers make every difference effect, not noise. Finite simulations still have delta uncertainty. | Compute paired delta intervals and soften the claim. |
| U25 | P2 | Changing/removing/resetting controls leaves old scenario results visible. `SimLab.tsx`. | Capture executed inputs; mark results stale or clear them. |
| U26 | P2 | Projected field caps at16 and numbers qualification-probability ranks as if seeds. `SimLab.tsx`. | Label top contenders or render real field/seed distributions. |
| U27 | P2 | Sidebar Lab loses viewed-team context; assistant receives league only and retains history across league changes. | Carry explicit context and tag/reset conversation scope. |
| U28 | P2 | Replay window gives clock times without date/time zone; navigation always says Live track. | Show full replay chronology and availability-aware labels. |
| U29 | P1 conditional | Legacy CSS hides the synthetic-demo disclosure while `/event/:eventId` remains routable. | Retire the route or preserve prominent synthetic/live/replay provenance. |
| U30 | P2 | Football SVG described `−1th and10` while visible facts said between plays. Ball coordinates conflicted with scoring text; upstream origin unverified. | Validate semantic situation and label unknown/between-play states. |
| U31 | P3 | NBA Lab offered starting-quarterback questions; missing league suggestions fall back to CFB. | Use supported, league-specific examples. |
| U32 | P2 | Live view overlays pushed scores but retains REST clock/plays and chooses history by length. `LiveGame.tsx`. | Merge compatible versions/times and expose component freshness. |
| U33 | P3 | `maxLeverage(g)||null` converts true zero leverage to missing. `components/games.tsx`. | Preserve zero with nullish checks. |
| U34 | P2 | Research tables/model health omit inspectable artifact links, row windows/sample sizes and exclusions. | Expose evidence and distinguish structural checks from predictive performance. |
| U35 | P2 | Legacy terminal nests main landmarks and uses a different navigation/pipeline. | Consolidate routes or explicitly isolate legacy demo functionality. |

## Earlier simulation/model review — revalidate current source/artifacts

| ID | Priority | Finding / source | Fix direction |
|---|---|---|---|
| M01 | P1 | CFP semifinal milestone counts championship finalists, two rather than four. `season/rules.py:237–245`. | Mark quarterfinal winners; separate final milestone. Current defect rechecked in L03. |
| M02 | P1 | Actual future conference-title matchups enter historical regular schedules, then simulated conference titles are generated again. `engine.py:136`, `rules.py:213–221`, `backtest.py:91`. | Model contingent phases and known times; instantiate once. |
| M03 | P1 | Current CFP automatic-bid eligibility is wrong. `rules.py:224–229`. | Season-versioned official guarantees and remaining at-large slots. Rechecked in L03. |
| M04 | P1 | Basketball field64; regular-record leaders replace conference tournament winners. `rules.py:256–275`. | Correct field/opening rounds and conference tournaments. Rechecked in L04. |
| M05 | P1 | Historical seasons use current NFL/NBA/CFB playoff rules, ignoring expansion/pandemic changes. | Dispatch rules by league and season; regenerate evaluation. |
| M06 | P2 latent | Latest completed postseason winner can be called champion when archives are incomplete. NBA2020 raw helper returned Phoenix. **Delivered extended artifacts exclude those incomplete title metrics; no allegation of a published Phoenix champion.** | Verify complete championship series and calendar before scoring. |
| M07 | P1 | Scenario setup omits canonical live probabilities. `service.py:167–172` versus `331–337`. | Branch one captured canonical/live setup. |
| M08 | P2 | Integer seed matrix summarized as Bernoulli probability; mean includes nonqualifier zero; seed SE becomes nonsensical. `engine.py:483–489`. | Separate seed distribution/conditional expectation from milestones. |
| M09 | P2 | Postseason shifts ignore future starts and individual expiry dates. `engine.py:245–247`. | Evaluate dated windows for every postseason event. |
| M10 | P2 latent | FAST scenarios sample unchanged board probabilities despite rating overrides. `engine.py:298–304`. Public Lab used DYNAMIC. | Recompute branch marginals or reject FAST override support. |
| M11 | P2 | Unknown targets/events silently ignored; invalid side strings force away. | Validate IDs, finite deltas, timezone-aware windows and typed outcomes. |
| M12 | P2 | F1 drops windows/forced results and overwrites repeated target shifts. `service.py:327–329`. | Typed supported operations and additive per-round windows. |
| M13 | P2 | F1 historical countback has wins only and attributes previous finishes to current employers. | Seed actual full finish histograms by race/constructor. |
| M14 | P2 | F1 DNFs can get modeled podium/win counts while denied points. | Use consistent classified-finisher eligibility/distance. |
| M15 | P2 | Long-term injury influence ends28days after original report even if active; freshness/window changes do not reliably invalidate caches. | Explicit active horizons and expiry/status recomputations. |
| M16 | P2 | Older player-effect artifacts lacking significant metadata bypass the nonsignificant-role guard. | Validate/version artifact schema and regenerate. |
| M17 | P2 | State hash omits live probabilities, dates, venue, membership, parameters and board probabilities. | Hash all causal inputs and model/rule versions. |
| M18 | P2 | Any completed postseason event disables postseason simulation instead of conditioning the bracket. | Support live brackets or clearly scope forecasts to regular season. |
| M19 | P1 | NHL window startsOct1, omitting September opening games; earlier archive had1336of1344. This is **not preseason misclassification**. | Correct season boundaries, reconcile opening games and recompute ratings. |
| M20 | P2 | Coverage100% measures archived rows only; NBA simulates80scheduled games without pending Cup slots. | Separate provider-matchup coverage from full-season completeness. |
| M21 | P2 | Retrospective calendars/membership and fixed result-known offsets exceed true evidence-as-observed PIT claims; F1 can use finals after start before finish. | Store publication/known times and reconstruct genuine cutoffs. |
| M22 | P2 | FAST leverage is displayed beside DYNAMIC odds without conditional sample counts/uncertainty. | Label estimand/model; prefer paired interventions with delta uncertainty. |

## Earlier research/evaluation review — revalidate before regenerating claims

| ID | Priority | Finding / source | Fix direction |
|---|---|---|---|
| R01 | P1 | Default DYNAMIC season Gaussian outcomes bypass calibrated game-board marginals. `engine.py:284–306`, `service.py:175–193`. | Align correlated season draws with served probabilities or clearly distinguish models. |
| R02 | P2 | Historical FAST lacks populated calibrated board probabilities, unlike serving FAST. | Benchmark the actual versioned serving pipeline. |
| R03 | P2 | Research report calls total rows test rows, overstating held-out size roughly5×; headline numbers differ from artifacts. | Generate tables from test counts/metrics and distinguish games from correlated states. |
| R04 | P2 | Capacity studies give neural/tree models extra raw features absent from logistic. `wp_bakeoff*.py`. | Compare identical inputs before attributing gains to architecture/memory. |
| R05 | P2 | Row bootstrap treats repeated game states as independent;90% bands include unvalidated heuristic/member spread. | Game-cluster bootstrap and explicit interval meaning/coverage validation. |
| R06 | P2 | Historical F1 checkpoints use eventual completed race length and proxy timestamps; leakage audit cannot detect this. | Scheduled distance and actual available-time states. |
| R07 | P2 | Player-effect t/SE use fragile IID regression assumptions; significance affects serving. | Robust clustered inference, confounding controls and prospective checks. |
| R08 | P2 | Football RB/WR/DEF effects mislabeled as top-minutes players; positive estimates styled negative. `RealResearch.tsx:22`. | Position-specific definitions and significance displays. |
| R09 | P2 | Market performance gap is presented as causal information value; archived quote timing caveat omitted. | Describe observed benchmark difference and expose timing/model limitations. |
| R10 | P2 | Default board limit2000 truncates coverage/live/swing summaries; earlier CBB had5729remaining but2000forecasts at100%. | Full coverage endpoint, server-filtered summaries and actual pagination. |
| R11 | P2 | Pushed state overwrites REST regardless of version and leaves newer REST provenance attached. `lib/live.tsx:50–58`. | Monotonic version/timestamp guards. Related B23/U32. |
| R12 | P2 | WebSocket cleanup leaves a scheduled reconnect timer alive. `lib/ws.ts`. | Cancel timers and guard stopped callbacks. |
| R13 | P2 | Research loading/errors appear empty or unavailable. | Separate loading/error/absence with retry and provenance. |
| R14 | P2 | Unknown team404 treated as warming/retried40times. | Distinct temporary and not-found responses. |
| R15 | P3 | Public error UI tells visitors to run make commands and prints raw API details. | Visitor recovery messages; debug detail in logs. |
| R16 | P2 | Generic period formatter calls NCAA halves quarters and overtime Q5/P4. | League-specific regulation/OT semantics. |
| R17 | P3 | F1 data snapshot hash is row count, not content fingerprint. | Hash source/config/rows reproducibly. |
| R18 | P3 | Evaluation calibrates mean ensemble probability; serving averages calibrated members. | Share one aggregator and reevaluate actual predictions. |

## Earlier backend/integration review — source findings, conditional deployment impact

| ID | Priority | Finding / source | Fix direction |
|---|---|---|---|
| B01 | P1 | Bounded newest-first feed consumed using append-only length cursor; new updates missed and delivery stops at60. | Durable sequences, deduplication and recovery. Rechecked L05. |
| B02 | P1 | Numerical-faithfulness gate does not preserve entities, signs, units or relationships. Additional wording checks now exist but do not solve association validation. | Typed facts/templates; accurate verification claims. Rechecked L09. |
| B03 | P1 | Expensive season/chat/TTS routes bypass existing limiter. | Rate/concurrency/cost controls. Rechecked L08. |
| B04 | P1 conditional | Admin auth fails open if token unset; actual production configuration unknown. | Fail closed. Rechecked L07. |
| B05 | P1 | Observation appended/deduplicated before payload validation and state/forecast commit. `core/engine.py:113–156`. | Validate first and commit atomically with rollback. |
| B06 | P1 | Concurrent ingestion can both calculate versionN+1 and lose an accepted transition. Memory locks individual methods; Postgres conflict ignored. | Per-event serialization or transactional compare-and-swap/retry. |
| B07 | P1 | Run counter resets while state version restores; old run IDs collide and archive conflict suppresses new history. | Persist counters or use content/epoch-unique IDs. |
| B08 | P1 | Failed scoreboard fetch still advances sync time; cached forecasts stamped fresh and top-level healthok. | Separate attempted/successful source times and degraded readiness. |
| B09 | P2 | Injury freshness expiry has no timed invalidation of existing forecasts. | Invalidate on age/error transitions. |
| B10 | P2 | Active long-term injury loses influence after arbitrary28-day original-report horizon. | Status/return-based explicit horizons. Related M15. |
| B11 | P2 | NextN games in NL becomes estimated days and disagrees with actual schedule. | Resolve Nth actual scheduled event. |
| B12 | P2 | Ambiguous team fragments silently choose first/fuzzy match. | Exact aliases and disambiguation/rejection. |
| B13 | P2 | Quote existence/player surname does not prove extracted news status. News was state-only, not authoritative probability input. | Entailment/team validation and honest grounding claims. |
| B14 | P2 | LLM JSON client only parses JSON despite claiming local schema validation; parser trusts unverified user-stated deltas. | Schema/domain validation and operation traceability. |
| B15 | P2 | Lab NL advertises force_result but rejects it; assistant has a separate resolver. | Shared supported operation executor. |
| B16 | P2 | Latest final selects oldest retained final from newest-first feed. | Correct ordering/timestamps. |
| B17 | P2 | Voice/analyst hardcode draws and announce recomputation complete at invalidation time. | Speak committed run metadata/status. |
| B18 | P2 | Commentary delta state shared by game across listeners. | Stateless client cursors or isolated listener state. |
| B19 | P2 | Commentary intro ignores available current score and calls final streams live. | Current-score priority and live/final/replay language. |
| B20 | P1 | TTL caches retain expired entries; unique F1 windows and in-memory evidence grow indefinitely. | Bounded eviction and retention/archive policy. |
| B21 | P2 | Publisher marks win-probability point delivered before write succeeds. | Advance cursor after successful idempotent commit. |
| B22 | P1 | Neon initial failure permanently exits its task. | Initialization retry and supervision. Rechecked L06. |
| B23 | P2 | Competition version advances before team/game chunks; UI overlays ignore version. | Snapshot commit marker/transaction and compatible merges. |
| B24 | P2 | Removed games never dropped/settled in SpacetimeDB. | Reconcile published sets and archive final status. |
| B25 | P2 | F1 excluded from shared-state/archive loops while broad claims imply all seasons. | Implement F1 persistence or narrow claims. |
| B26 | P2 conditional | Spacetime storage adapter expects a gateway/schema absent from supplied module. Live publisher is separate. | Supply supported adapter or remove unsupported configuration. |
| B27 | P2 | Failed box scores silently omitted and player categories capped12; totals look complete. | Coverage/missing IDs and pagination. |
| B28 | P2 | Batch applies earlier observations before validating later ones, then returns failure. | Validate whole batch and transact or explicit partial results. |
| B29 | P2 optional | Fetch observation bridge accepts unauthenticated senders with default deterministic identity seed. Not proven deployed. | Authorized identities/senders and provenance verification. |
| B30 | P2 | WebSocket restart resets sequence without epoch/resync. Old high cursor misses restart backlog; new broadcasts still arrive. | Epoch plus snapshot/replay recovery. |
| B31 | P2 | Generic F1 radio checks run.teams and says season not started despite drivers/constructors. | F1-aware briefing or explicit unsupported endpoint. |
| B32 | P2 | Postponed/suspended games mapped to completed. | Explicit semantic status/resumption handling. |
| B33 | P2 | Final-score corrections do not replay ratings or invalidate season; final box-score cache assumes immutability. | Corrected result fingerprints and affected-history replay. |
| B34 | P2 architecture risk | Sync assistant self-HTTP calls occupy shared worker threads while waiting for child handlers. No load outage was reproduced. | Direct service calls or async bounded execution. |
| B35 | P2 | Live history only archives in-progress games, missing terminal settlement probabilities/scores. | Explicit final points with event known times. |

## Preserve these distinctions

- Monte Carlo sampling precision is not model accuracy, official-rule validity or full uncertainty.
- Approximate committee selection, tiebreaks, injury priors and F1 pace assumptions must be labeled rather than presented as official certainty.
- Earlier extra NFL all-star squads were intersected with actual membership in evaluation; do not claim confirmed playoff-score corruption from those extra names alone.
- The longer research report already acknowledges associational player effects and some retrospective limitations; the issue is stronger UI/headline claims and specific invalid calculations.
- Reduced-motion CSS exists. Do not claim it is wholly absent.
- Local source evidence does not identify the deployed commit. Prior live observations are dated, not current uptime assertions.

## Next action

Use [release_plan.md](release_plan.md) to revalidate and fix these in dependency order. First recover service availability, then repair forecast contracts and durability, regenerate affected evidence, finish UX, and release a tested version with rollback.
