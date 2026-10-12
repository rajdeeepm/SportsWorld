# Portfolio deployment status

Prepared on 11 October 2026. This is a deployment handoff, not confirmation that the site is live.

## Completed

- Added `portfolio/`, a static historical NFL exhibit with local assets, 32 teams, 128 saved scenarios, 40 archived evaluation rows, downloads and visible methodological limits.
- Added an offline exporter and dependency-free Node verification script.
- Verified all histogram totals, probability bounds, scenario deltas, evaluation aggregates, the input hash and identical browser/JSON payloads.
- Regenerated the snapshot from the Base64-encoded gzip bundle and obtained exactly equal parsed output.
- Published `portfolio/README.md` in GitHub commit `b322806b2b31472ceed96e4251d3af2dd190fd6a`.

## Account prerequisites

The user chose to keep Chrome extension file access disabled. Publish only the selected public source through GitHub's text editor. Fonts are embedded in styles.css; the compressed input bundle is encoded in replay-inputs.b64 and decoded by the exporter. No extension permission change or binary upload is needed.

Vercel is signed in to the CSE-594 Hobby team. Its existing GitHub app sees two other repositories, but does not see SportsWorld. Adding only `rajdeeepm/SportsWorld` requires GitHub email reauthentication and action-time approval for the repository access change. Do not select All repositories.

Cloudflare is signed out. The user must complete sign-in before the DNS cutover. Do not transfer or buy a domain, remove unrelated DNS records, or expose API/tunnel credentials.

## Publication manifest

Upload all files in `portfolio/` to the corresponding GitHub directory. Upload `scripts/export_portfolio.py` and `scripts/verify_portfolio.mjs` under scripts. Publish the changed root README.md and PRODUCT.md plus wrong_details.md and release_plan.md. The scoped design brief is `.impeccable/surfaces/portfolio.md`. Audit evidence under docs/audit is dated historical evidence.

## Vercel configuration

Import `rajdeeepm/SportsWorld`, project name `sportsworld-portfolio`, Root Directory `portfolio`, Framework Preset Other. No install/build command, no backend, no environment variables. Serve the static root. Review the generated Vercel URL on desktop and at 390px before domain cutover. The browser blocked file:// previews and the shell sandbox blocked a local listening server, so visual QA remains pending; do not claim a visual pass from source checks.

Check team selection, both modes, all four scenario buttons and baseline reset; navigation, keyboard focus, expandable exact counts, downloads, no page overflow, no failed assets and no external backend calls. Preserve screenshot evidence for the design finish review. No finish-review or visual sign-off has been claimed yet.

## Existing .tech domain

Add `worldofsports.tech` and `www.worldofsports.tech` in the new Vercel project's Domains settings. Obtain the exact assigned DNS values from that screen. In Cloudflare replace only the apex/www website records currently pointing at the old tunnel. Use the proxy setting recommended by Vercel and preserve mail and unrelated records. Wait for valid configuration and HTTPS, then verify both URLs.

Use apex as the canonical address. The committed vercel.json redirects www to apex. A Vercel host can serve the same project; redirect its production alias to apex only after the custom domain works. Never create redirects in both directions.

Free-tier hosting still has usage limits and the existing domain's renewal cost is separate. No Supabase or running Mac is necessary for the final static deployment.
