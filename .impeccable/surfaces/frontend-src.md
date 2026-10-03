---
version: 1
slug: "frontend-src"
primary_target: "frontend/src"
related_targets: []
---

# Surface: SportsWorld app shell, league Season World, team Season World, Season Simulation Lab

Mode: Operate (judges watch a live 3-5 minute walkthrough; the screen must work as a real product).
Scope: frontend/src (all routes). Leagues: F1, NFL, CFB, NBA, CBB, NHL, College Hockey. CFB built first, Michigan (ESPN id 130) is the demo path.
Constraints: real engine data only; no coaches, player ratings, spreads, TV, weather, storylines. Real ESPN logos and team colours only; no photos of people.
Unresolved: College Hockey has no season run until its season starts; CFB standings record source disagrees with ESPN.

## Direction contract
THESIS: A broadcast-grade season terminal: every panel is a live readout of one persistent season model. Refuses the generic SaaS card grid with a hero metric and soft grey tiles.
OWN-WORLD: Pinned by the user's renderings. Deep navy ground (#060b18 to #0b1428), cobalt panel edges with a faint inner glow, electric blue (#2f8cff) as the system accent, the team's official colours owning its header band and charts, win-probability bars split in two team colours, green/amber/red only for state and leverage. Condensed heavy display face for titles, tabular numerals everywhere.
STORY: The judge sees the whole league season at a glance, opens Michigan, watches a live game move its odds, then branches the season in the Lab and sees playoff and title paths shift.
FIRST VIEWPORT: Top league tab bar and left rail; huge "<Team> — Season World" title over a team-colour band with the official logo; a header strip (record, conference standing, rating rank, next game); six outlook figures; trend chart left, remaining schedule right, next-game outlook in the right column.
FORM: pinned brief (user reference renderings), no concept-seed roll; code-led (no image generation).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
