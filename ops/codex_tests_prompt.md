Write ONE new pytest file: backend/tests/test_season_acceptance.py. Do not modify any other file.
It must test the SportsWorld season engine against spec acceptance tests, using small synthetic GameRecord archives
written to pytest's tmp_path (see backend/tests/test_real_ingest.py for how GameRecord/TeamLine are constructed,
and backend/src/sportsworld/season/structure.py for LeagueStructure/TeamSlot + save_structure).
Required tests:
- G6: run_season for a synthetic 32-team NFL-like league (2 conferences x 4 divisions x 4 teams, a short schedule) with 2000 draws:
  exactly one champion per draw; per conference exactly 7 playoff teams per draw with seeds 1..7 each used once; division winners are seeds 1-4.
- NBA-like 30-team league: exactly 16 playoff teams per draw (8 per conference), play-in teams are ranks 7-10.
- G8 counterfactual isolation: running a SeasonScenario (rating_shifts) does not mutate setup.mu/var/played arrays, and with the same seed
  the base run is bit-identical before and after.
- Determinism: same seed => identical results; different seed => different.
- DYNAMIC vs FAST: with large posterior variance, DYNAMIC wins_sd >= FAST wins_sd for a typical team.
- Point-in-time: build_setup(as_of) excludes games whose result_known_time > as_of from played tables.
- F1: run_f1_season on a tiny synthetic state (5 drivers, 3 constructors, 2 remaining races, one sprint) — exactly one driver champion and one constructor champion per draw; expected points >= current points.
Use PYTHONPATH=src from backend/. Run `cd backend && PYTHONPATH=src ../../env/bin/python -m pytest tests/test_season_acceptance.py -q` and iterate until it passes. If a test reveals a genuine engine bug, do NOT fix the engine; mark that test xfail with a clear reason string describing the bug.
