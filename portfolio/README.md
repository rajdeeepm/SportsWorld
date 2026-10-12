# Static portfolio exhibit

This directory is the Vercel project root. It is plain HTML, CSS and JavaScript with local fonts and a frozen data payload. It has no API, database, WebSocket, service worker, credential or runtime backend dependency.

## Deployment

Import `rajdeeepm/SportsWorld` in Vercel. Set Root Directory to `portfolio`, Framework Preset to Other, leave Build and Install Commands empty and use the static root as Output Directory. No environment variables are needed. Review the preview before attaching `worldofsports.tech` and `www.worldofsports.tech`. Use the exact DNS values displayed in Vercel, preserve unrelated records and redirect `www` to the apex. Do not redirect both hosts toward each other. The project can use Hobby within its limits; domain renewal is separate.

Vercel serves the committed files while your Mac is off. GitHub commits update the deployment when the repository integration is connected. Supabase and a continuously running simulator are unnecessary for this exhibit.

## Verification and reproduction

From the repository root, run `node scripts/verify_portfolio.mjs`. To view locally, serve this directory with a static server, for example `python3 -m http.server 8080 --directory portfolio`.

To regenerate model outputs from bundled inputs: create a Python 3.11+ virtual environment, install `pip install -e backend`, then run `python scripts/export_portfolio.py` and `node scripts/verify_portfolio.mjs`. The exporter does not make provider calls. `--capture` is a maintainer operation that refreshes inputs from local archives; it is not necessary to reproduce the committed exhibit.

## Evidence and limits

The cutoff is 2025-11-01 12:00 UTC; all 32 NFL teams have baseline fixed-strength and correlated-strength runs and four saved correlated scenario branches. Each run uses 10,000 draws and seed 17. Strength interventions are hypothetical point offsets, not causal injury estimates. Paired intervals describe Monte Carlo sampling error, not total model uncertainty.

The Base64-encoded gzip replay bundle is content-addressed by the hash in `snapshot.json`. `snapshot-data.js` contains the same payload so the browser needs no fetching API. Source code at generation is recorded in the manifest. Results use retrospective schedule/membership snapshots and proxy result-known times. NFL ties and tiebreaks are approximate. The two simulation modes differ in marginal probabilities as well as dependence; their comparison does not isolate correlation alone.

Research tables are filtered original evaluation artifacts for NFL 2021–2025, not a new independent validation. Team outcomes within seasons are dependent and the cohort contains only five seasons. Coverage alone does not establish calibration. See the in-product limitations and `../wrong_details.md` for the broader engine audit.

Barlow fonts retain their bundled Open Font License in `FONT-LICENSE.txt`.
