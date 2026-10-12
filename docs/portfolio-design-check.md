# Portfolio design comparison

Reviewed 11 October 2026. Scope: the static historical NFL exhibit in `portfolio/`, an extension of SportsWorld's existing visual world. `DESIGN.md` remains the normative design authority; this report does not replace it or define a second token system. `DESIGN.md` and `.impeccable/design.json` were preserved.

## Evidence checked

The review screenshots were captured locally for this launch. This text publication does not upload those binary files; existing repository screenshots may show the original interface.

- Product scope in `PRODUCT.md` and direction in `.impeccable/surfaces/portfolio.md`.
- Incumbent `DESIGN.md`, `.impeccable/design.json`, and relevant source in `frontend/src/styles/app.css`.
- Finished extension source: `portfolio/index.html`, `portfolio/styles.css`, and `portfolio/app.js`.
- All eight supplied full-page captures: `.impeccable/review/desktop.png`, `mobile.png`, `desktop-research.png`, `mobile-research.png`, `desktop-method.png`, `mobile-method.png`, `desktop-reproduce.png`, and `mobile-reproduce.png`. Desktop captures are 1277px wide; phone captures are 390px wide. The files contain JPEG data despite their `.png` names.

This is a source and screenshot comparison, not a new browser interaction audit or empirical model validation. Screenshots show baseline explorer results; saved scenario behavior was inspected in source rather than captured here. Hover, error, loading, disabled and reduced-motion behavior were read in source. The desktop explorer capture includes the focused skip link, so it records a keyboard state rather than the default first frame.

## Preserved world

The exhibit retains the Midnight Ground, primary Ink and Trophy Gold values; Barlow and Barlow Condensed; condensed headline figures; tabular numerals; navy surfaces; cobalt-family hairlines; restrained corners; and blue emphasis. The explorer remains a working quantitative readout rather than a decorative illustration. A source rail, distribution, data disclosure and provenance give the numbers context. Methodology and reproduction use the same visual vocabulary.

At phone width the controls stack above results, headings wrap without visible page-wide overflow, and the four navigation destinations remain visible in a two-column layout. Research tables and reproduction code use their own horizontal scroll containers, with visible instructions. The source exposes semantic radio and scenario state, an active navigation state, a skip link, keyboard focus, chart descriptions and exact counts. No live pulse or misleading live badge appears in this historical mode.

Source palette checks give primary text, muted text, blue links and gold emphasis contrast ratios of approximately 15.97:1, 9.81:1, 8.57:1 and 11.57:1 against the opaque panel fill. These calculations cover those palette pairs, not every possible composed state.

## Surface departures from DESIGN.md

The extension remains recognizably SportsWorld, but is not an exact implementation of its normative component system:

| Area | Finished exhibit | Incumbent authority |
| --- | --- | --- |
| Panel treatment | Opaque panel fill, flat hairline edges, no luminous top-edge overlay | Translucent panels with signature top-edge glow |
| Colour values | Edge `#203655`, muted `#afbfda`, blue `#73b6ff` | Edge `#16305a`, secondary ink `#a9badb`, readable accent `#6fb2ff` |
| Gold semantics | Historical badge, nominal coverage target, scenario bars/deltas and focus outline | Gold reserved for title-related emphasis; focus uses readable blue |
| Type and density | 16px base with 1.55 line height; display up to 70px, 46px on phones; more open spacing | 14px base with 1.4 line height; display up to 54px, 34px on phones; dense terminal |
| Shell | Four portfolio destinations, 80px header minimum, 220px rail, 980px/700px responsive steps | League bar, 64px header, 214px rail, 1080px/760px shell steps |
| Team subject | Neutral team heading and system-coloured distributions; no logo or official-colour band | Team-colour band and official colours on team-specific lines/bars |
| Motion | Distribution rectangle transitions and colour fades under a reduced-motion opt-in | Probability-bar ease, live pulse and score tick only |

The READ brief supports a narrower historical workflow and a more readable composition. It does not make the above source values normative or establish approval to refresh the global system. Record these as scoped implementation departures, not an approved identity change. The existing DESIGN.md remains the reference for later extension work.

## Pre-existing drift

The original live-app stylesheet already contains a `.hero-kicker`, a news thumbnail image treatment, a 3px team-coloured profile-card side border, and a push-toast entrance animation. These diverge from the supplied craft floor and/or DESIGN.md's imagery, border and motion constraints. They are outside the portfolio task and were left unchanged. The live application's root palette, font stacks and main panel tokens still match the incumbent authority.

## Disposition

Documentation handoff complete with explicit surface departures. The screenshots and source support an extension of the existing world, not a replacement identity. No design-system refresh, broad drift repair or new token sidecar was warranted by this scoped handoff. Only this report was written. Later visual edits should be compared again against the incumbent authority and corresponding recaptures.
