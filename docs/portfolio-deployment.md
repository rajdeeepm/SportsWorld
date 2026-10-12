# Verified portfolio deployment

Completed 11 October 2026 (12 October UTC). The public historical exhibit is live on Vercel Hobby and independent of a running Mac or backend.

## Addresses

| Address | Behaviour |
| --- | --- |
| https://worldofsports.tech | Canonical portfolio, served by Vercel over HTTPS |
| https://www.worldofsports.tech | 308 redirect to the apex |
| https://sportsworld-portfolio.vercel.app | 308 redirect to the apex |

Vercel reports Valid Configuration for all three. Root and www DNS in Cloudflare are CNAME records targeting `c38204e7b3b5c259.vercel-dns-017.com`, DNS only, Auto TTL. They replace the former website tunnel targets. The unrelated wildcard record and registrar were not changed. Domain-level Vercel redirects enforce the canonical address before loading assets.

## Hosting and source

Project: `CSE-594 / sportsworld-portfolio`, Hobby. Repository: `rajdeeepm/SportsWorld`, main branch. Root Directory: `portfolio`; Application Preset: Other; default static output `.`. No custom build/install command, environment variable, database, Supabase project, sports API, Python service, LLM or WebSocket is needed to serve this exhibit. Future connected GitHub commits trigger deployments.

The user kept Chrome extension file access disabled. Publication used GitHub's source editor. Licensed fonts are embedded in styles.css and the compressed input bundle is text-encoded in replay-inputs.b64. GitHub's existing Vercel app gained access only to SportsWorld, with the user's explicit approval; previous repository access was preserved.

## What ships

A dated NFL reconstruction at 2025-11-01 12:00 UTC: 32 teams, 10,000 draws per run, seed 17, correlated/fixed-strength baselines, four saved scenarios per team (128 branches), histogram counts, research evidence, limitations and reproduction instructions. Evaluation uses 40 original NFL 2021–2025 rows. The original seven-league live system remains in source and the recorded demonstration.

## Validation

- Dependency-free `node scripts/verify_portfolio.mjs` passes: all team/branch histograms sum to 10,000, means and deltas agree, probabilities and paired sampling errors are valid, research aggregates match rows, local assets exist and public JS requires no backend calls.
- Offline export from the bundled input reproduced exactly equal parsed model output at the generation code revision. The source commit field changes when regenerating at another revision.
- Browser exercises covered team selection, both modes, all four scenarios, baseline reset and navigation. The public JSON download equals the validated snapshot; the downloaded input bundle matches the declared SHA256.
- Desktop 1277px and mobile 390px captures cover all four sections. No document overflow or console errors appeared during the inspected flow. The reviewer requested three mobile fixes; its verdict pass scored chart ticks, visible navigation and accessible scroll regions resolved, disposition ship, scoped to those fixes.
- `docs/portfolio-design-check.md` records the visual comparison and scoped departures; DESIGN.md and its sidecar were preserved. Earlier tiny-text hook findings were fixed; no suppressions were added.

## Operating cost and limits

The deployment uses the existing Hobby plan and requires no Mac process. Free-tier usage limits still apply. Registration and renewal of worldofsports.tech remain separate. No paid service or new subscription was provisioned.

The public exhibit is historical, not current forecasts. Its UI states retrospective schedule membership, result-availability proxies, approximate ties/tiebreaks, hypothetical interventions and the limited evaluation cohort. This deployment does not certify or fix every backend issue in wrong_details.md.
