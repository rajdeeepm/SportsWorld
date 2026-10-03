---
name: SportsWorld
description: Season Intelligence Engine. A broadcast-grade season terminal where every panel reads out one persistent, calibrated season model.
colors:
  ground: "#060b18"
  panel: "rgba(9, 19, 38, 0.92)"
  panel-solid: "#0a1528"
  edge: "#16305a"
  edge-strong: "#2559a6"
  ink: "#eaf0fd"
  ink-2: "#a9badb"
  ink-3: "#7086b0"
  ink-4: "#4b5f86"
  accent: "#2f8cff"
  accent-ink: "#6fb2ff"
  accent-soft: "rgba(47, 140, 255, 0.14)"
  gold: "#f4c94e"
  good: "#27d17f"
  warn: "#f6b73c"
  bad: "#ff4d61"
  live: "#ff3b4f"
  away-fallback: "#e64a5c"
typography:
  display:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "clamp(34px, 3.6vw, 54px)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "0.002em"
  numeral:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "34px"
    fontWeight: 800
    lineHeight: 1
    fontFeature: "'tnum' 1"
  title:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "0.01em"
  tab:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "16px"
    fontWeight: 700
    letterSpacing: "0.02em"
  body:
    fontFamily: "'Barlow', system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "'tnum' 1"
  table:
    fontFamily: "'Barlow', system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "'Barlow', system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.05em"
rounded:
  sm: "5px"
  control: "6px"
  field: "7px"
  md: "8px"
  lg: "12px"
  pill: "18px"
spacing:
  xs: "4px"
  sm: "8px"
  gutter: "12px"
  panel-x: "14px"
  lg: "18px"
components:
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "12px 14px"
  panel-head:
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    padding: "11px 14px 9px"
  kpi:
    textColor: "{colors.ink}"
    typography: "{typography.numeral}"
    padding: "14px 16px"
  button:
    backgroundColor: "rgba(20, 44, 86, 0.6)"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "30px"
  button-hover:
    backgroundColor: "rgba(47, 140, 255, 0.26)"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "30px"
  button-big:
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "42px"
  league-tab:
    textColor: "{colors.ink-2}"
    typography: "{typography.tab}"
    rounded: "{rounded.sm}"
    padding: "7px 16px"
  league-tab-active:
    backgroundColor: "rgba(47, 140, 255, 0.42)"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
  rail-link:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  rail-link-active:
    backgroundColor: "rgba(47, 140, 255, 0.3)"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
  input-field:
    backgroundColor: "rgba(8, 17, 34, 0.95)"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "0 10px"
    height: "34px"
  search:
    backgroundColor: "rgba(8, 17, 34, 0.9)"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    height: "36px"
    width: "280px"
  segmented-on:
    backgroundColor: "{colors.accent-soft}"
    textColor: "#ffffff"
    rounded: "{rounded.field}"
    padding: "5px 11px"
  chip-info:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-leverage-low:
    backgroundColor: "rgba(39, 209, 127, 0.14)"
    textColor: "#7fe3a9"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-leverage-medium:
    backgroundColor: "rgba(246, 183, 60, 0.14)"
    textColor: "#ffd27e"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-leverage-high:
    backgroundColor: "rgba(255, 77, 97, 0.14)"
    textColor: "#ff8c99"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-leverage-very-high:
    backgroundColor: "rgba(255, 77, 97, 0.38)"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-live:
    backgroundColor: "{colors.live}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-neutral:
    backgroundColor: "rgba(112, 134, 176, 0.14)"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  table-header:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.ink-3}"
    padding: "7px 10px"
  prob-split:
    backgroundColor: "rgba(112, 134, 176, 0.12)"
    rounded: "{rounded.sm}"
    height: "26px"
  team-band:
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    height: "96px"
  result-card:
    backgroundColor: "rgba(14, 28, 53, 0.6)"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px"
  day-tab-on:
    backgroundColor: "rgba(47, 140, 255, 0.2)"
    textColor: "#ffffff"
    rounded: "{rounded.field}"
    padding: "6px 12px"
---

# Design System: SportsWorld

## Overview

**Creative North Star: "The Season Terminal"**

SportsWorld is a broadcast control room for a whole season. A deep navy ground holds dense, edge-lit panels that each read out one part of a single persistent Monte Carlo model: standings, schedules, title odds, live games, counterfactual branches. The register is a sports-network graphics package crossed with a trading terminal: condensed heavy numerals, cobalt hairlines, one electric blue accent, and the teams' own official colours wherever a team is the subject.

Density is high and deliberate. A desktop viewport carries a league tab bar, a section rail, a title, a KPI strip and three or more data panels at once; nothing is a soft grey tile with one hero metric. Every surface is dark (the system declares `color-scheme: dark` and has no light theme). Depth comes from luminous edges, not from lifting cards off the page.

The world refuses decoration that the data cannot back. The only imagery is real ESPN team logos (plus generated monogram discs when a logo is missing); no photography, illustration or shipped raster exists in the frontend. Every number on screen is real engine output, and the visual grammar exists to make that output legible: probabilities in one blue hue, signal colours held back for leverage, live state and change.

**Key Characteristics:**
- Navy ground with two fixed radial blue glows; cobalt-edged translucent panels with a gradient glow on their top edge.
- One accent, electric blue, in two strengths (fill and readable ink); gold only for trophies and headline title odds.
- Barlow Condensed at 700 to 800 for every title and headline figure; Barlow for UI; tabular numerals everywhere.
- Team-colour header band and two-colour win-probability bars in official team colours.
- Twelve-column panel grid that steps down at 1360px, 1080px and 760px, swapping game tables for phone game cards.
- Three motions only, all removed under reduced-motion.

## Colors

A cold, near-monochrome navy-and-cobalt field lit by a single electric blue, with a disciplined set of signal colours held in reserve.

### Primary
- **Electric Blue** (accent): the system accent. Fills for primary buttons, the active league tab, the default win-probability bar, scenario bars in comparison charts, range-input thumbs, focus borders on fields, and the left inset rule on a focused table row.
- **Signal Blue Ink** (accent-ink): the readable form of the accent on navy. Panel-head icons, KPI icons, links, the strongest probability tier, the focus-visible outline, info chips, and the default emphasis colour in page titles.
- **Blue Wash** (accent-soft): the 14% accent tint behind info chips, the active segmented-control option and hovered search results.

### Secondary
- **Trophy Gold** (gold): reserved for title-related emphasis. Trophy KPI icons (expected wins, title odds, championship lead), the favourite's title odds beside the league title, and insight headings in the Lab.

### Tertiary (signal set, reserved)
- **Leverage Green / Amber / Red** (good, warn, bad): leverage chips step low (green), medium (amber), high (red tint) and very high (solid red tint). The same three colours carry signed deltas (up green, down red, flat in ink-3), feed icons (finals green, injuries red, news amber), the dashed amber playoff cut line in standings, and pass/fail tinting on model-health figures.
- **Broadcast Red** (live): the live pulse dot, live chips, the "LIVE" schedule label, the live-games KPI when non-zero, and the score-tick flash.
- **Away Fallback Red** (away-fallback): the away segment of a probability bar only when the away team has no usable official colour.

### Neutral
- **Midnight Ground** (ground): page background beneath two fixed radial glows (blue at 18% top-right, deeper blue at 14% bottom-left).
- **Panel Navy** (panel): translucent panel fill so the ground glows faintly through.
- **Solid Panel Navy** (panel-solid): opaque surfaces that must cover content: sticky table headers, search results, chart tooltips.
- **Cobalt Edge** (edge): every panel border, rail and topbar divider, segmented-control and tab outlines. Internal dividers use the same hue at 45 to 90% alpha.
- **Bright Cobalt Edge** (edge-strong): borders on interactive controls (buttons, fields, scenario chips), the team band, and popovers.
- **Ink ramp** (ink, ink-2, ink-3, ink-4): primary text; secondary text and inactive tabs; labels, captions, table headers and muted cells; placeholders and provenance lines.

### Named Rules
**The One Hue Probability Rule.** A probability is shown in one blue hue whose intensity rises with its value: 50% and above is bold Signal Blue Ink, 10 to 50% is bold ink, 0.5 to 10% is ink-2, below 0.5% is ink-3. Probabilities are never coloured green, amber or red.

**The Reserved Signal Rule.** Green, amber and red mean leverage, live state, signed change, or model health. They never encode a team, a probability level or decoration.

**The Official Colours Rule.** A team is drawn only in its official colours from its metadata. A near-black primary falls back to the team's alternate colour; when two teams' colours clash in one bar, the home side switches to its other official colour. No colour is invented for a team.

## Typography

**Display Font:** Barlow Condensed (with Arial Narrow, sans-serif), self-hosted at 600, 700 and 800.
**Body Font:** Barlow (with system-ui, sans-serif), self-hosted at 400, 500, 600 and 700.

**Character:** A sports-broadcast pairing: the condensed face gives titles and scores a stadium-scoreboard punch while staying narrow enough for dense panels; the regular-width sibling keeps tables and captions calm. Tabular numerals are set on the root, so every figure aligns in columns and does not jitter as it updates.

### Hierarchy
- **Display** (800, clamp(34px to 54px), line-height 0.95): page titles in the form "<Team> — Season World". The trailing phrase is set in an emphasis colour: the team's lighter official colour on team pages, Signal Blue Ink elsewhere. Fixed at 34px on phones.
- **Numeral** (800, 34px, line-height 1): KPI values, team-band stats (40px), matchup scores (34px), result-card figures (30px), favourite title odds. Units ride alongside at 17px in ink-2.
- **Title** (700, 20px, line-height 1.1): panel headings, with an optional 12px Barlow ink-3 aside.
- **Tab** (700, 16px, 0.02em tracking): league tabs; team names in matchups and the team band use the condensed face at 800 in uppercase.
- **Body** (400, 14px, line-height 1.4): default UI text. Insight prose opens up to 1.55 line-height.
- **Table** (13.5px): data tables, game rows, feeds (13px).
- **Label** (600, 12px, 0.05em tracking, uppercase): KPI labels, table headers (11px, 0.06em), "Next game" in the team band, the rail's league name.

### Named Rules
**The Condensed Figure Rule.** Any number that is the point of its container (a KPI, a score, a record, title odds) is set in Barlow Condensed at 700 or heavier. Supporting numbers inside tables stay in Barlow.

**The Tabular Everything Rule.** Numerals are tabular across the whole app; never switch a figure to proportional digits.

## Layout

The app is a fixed shell: a 64px sticky topbar spanning the width (brand, league tabs, team search) above a 214px sticky left rail (league name, section links, a short provenance footer) and a main column padded 18px by 20px.

Main content stacks vertically with a 12px gap: title block, then a team band or KPI strip, then a twelve-column grid of panels with a 12px gutter. Panels span 3 to 12 columns; common splits are 7/5 and 4/4/4. The KPI strip divides its width evenly by item count, separated by internal hairlines rather than gaps.

Responsive behaviour steps at three breakpoints:
- **1360px:** narrow spans (3 to 5 columns) widen to half width and 7 to 9 column spans go full width. KPI strips wrap to three per row. The team band drops to two stats.
- **1080px:** the rail leaves the side and becomes a horizontally scrolling row of links under the topbar; its league label and footer are hidden. Search narrows to 180px.
- **760px (phone):** main padding drops to 12px. Every panel goes full width. League tabs wrap onto their own row and search hides. KPIs go two per row and result cards two per row. The team band collapses to logo and name, then a single record line, then the next-game row. Game tables are replaced by stacked game cards (time and leverage, the two teams around the score, then the probability bar), and the rail fades out at its right edge to signal scroll.

Spacing runs on a tight rhythm of 4, 8, 12, 14 and 18px. Panel bodies pad 12px by 14px and table cells 6px by 10px.

## Elevation & Depth

Depth is luminous rather than lifted. Panels sit almost flat on the ground. Their presence comes from a cobalt border, a one-pixel inner top highlight, and a gradient border overlay that glows blue along the top edge and fades out by 38% of the height. Shadows exist, but they are long, low and dark, grounding a panel rather than floating it. Accent-coloured glows appear only on the active league tab, the primary button and the team band (tinted with the team's colour).

### Shadow Vocabulary
- **Panel rest** (`box-shadow: inset 0 1px 0 rgba(120, 170, 255, 0.07), 0 10px 30px -18px rgba(0, 0, 0, 0.9)`): every panel and KPI strip.
- **Panel top-edge glow** (gradient border, `linear-gradient(180deg, rgba(47, 140, 255, 0.35), transparent 38%)` at 0.55 opacity): every panel; the signature of the world.
- **Active tab glow** (`0 0 0 1px rgba(47, 140, 255, 0.35), 0 6px 18px -6px rgba(47, 140, 255, 0.7)`): the selected league tab only.
- **Primary button glow** (`0 6px 18px -8px rgba(47, 140, 255, 0.9)`): primary buttons only.
- **Team glow** (`0 16px 40px -22px <team colour at ~53% alpha>`): the team band.
- **Popover** (`0 18px 40px -12px rgba(0, 0, 0, 0.8)`): search results and chart tooltips.
- **Logo lift** (`drop-shadow(0 4px 14px rgba(0, 0, 0, 0.55))`): large logos in the team band and title block.

### Named Rules
**The Cobalt Edge Rule.** A container is defined by its edge and its top glow, never by a raised drop shadow or a lighter fill. If a new surface needs to stand out, give it Bright Cobalt Edge, not a bigger shadow.

## Shapes

Corners are firm and modest: 12px on panels and the team band, 8px on rail links, inner figure blocks and result cards, 7px on fields, segmented controls and day tabs, 6px on buttons and bracket slots, 5px on chips, tabs and probability bars. The only full pill is the team search field (18px). Logo fallbacks are circles. Borders are one pixel throughout. Dividers inside panels are hairlines in Cobalt Edge at reduced alpha; the playoff cut line in standings is the single dashed rule.

The team band carries the world's one texture: fine 115° diagonal pinstripes at 3.5% white, masked to fade out across the left 40% of the band.

## Components

### Panel
The universal container: a titled, edge-lit readout.
- **Corner Style:** 12px.
- **Background:** Panel Navy over the ground, with the top-edge glow and the rest shadow.
- **Head:** an 18px Signal Blue Ink line icon, a Title-weight condensed heading with an optional muted aside, and right-aligned actions. Separated from the body by a hairline.
- **Body:** 12px by 14px padding; a flush variant removes padding for tables and scrolls horizontally.
- **Foot:** an optional 12px ink-3 caption that states where the numbers come from or how to read them.

### KPI Strip
A single panel split into equal cells by vertical hairlines. Each cell holds a 34px thin-stroke line icon (Signal Blue Ink, or Trophy Gold for title-related figures), an uppercase label, a Numeral-weight value with an optional small unit, and a muted sub-line carrying the range, rank or standard error.

### Win-Probability Bar (signature)
A 26px two-segment bar, away on the left and home on the right as broadcasts list "away @ home". Segment widths are the two probabilities; colours are each team's official colour. The underdog's segment drops to 62% opacity. Both ends always carry the team code and its percentage in condensed 14px type. The favourite's label is white and heavier, and the ink flips to dark navy when the segment underneath is light (maize, cream, silver). The bar has an accessible label stating both sides. Widths ease over 700ms on `cubic-bezier(0.16, 1, 0.3, 1)` as odds move.

### Team Band (signature)
The team page header: a 96px-tall band with a 12px radius and a Bright Cobalt Edge border. Its background sweeps at 100° from the team's primary colour through a mix of that colour with navy to near-opaque navy. It carries the pinstripe texture and a team-tinted glow. It holds an 84px logo, the team name in uppercase condensed 800, a standing line, up to four stat cells (40px numerals, hairline-separated), and a next-game block at the right that shows a live dot, score and live versus pregame probability once the game starts.

### Buttons
- **Shape:** 6px corners, 30px tall (42px for the big variant).
- **Default:** translucent cobalt fill, Bright Cobalt Edge border, 13px semibold ink.
- **Hover:** fill shifts to a 26% accent wash and the border to Electric Blue over 160ms.
- **Primary:** vertical gradient from a lighter to a deeper electric blue with a blue glow, white text.
- **Ghost:** transparent fill. **Disabled:** 45% opacity.
- **Link:** 12.5px semibold Signal Blue Ink, white on hover.

### Chips
- **Style:** 11.5px bold, 5px corners, a tinted fill at 14% with a matching border at 40 to 50%.
- **Leverage chips** read Low / Medium / High / Very high followed by the swing in points, and step green, amber, red tint, solid red.
- **Variants:** info (blue wash), neutral (slate wash), live (solid Broadcast Red, white text).
- **Scenario chips** in the Lab are larger (13px, 8px corners, cobalt gradient fill) and carry a remove button.

### Inputs / Fields
- **Style:** 34px tall, 7px corners, near-opaque navy fill, Bright Cobalt Edge border, caret in Signal Blue Ink.
- **Focus:** the border turns Electric Blue; keyboard focus everywhere shows a 2px Signal Blue Ink outline offset 2px.
- **Search:** an 18px-radius pill with a leading icon. Results drop in an opaque popover with logo, name and conference, and support arrow-key selection.
- **Segmented control:** hairline-divided buttons; the active option takes the Blue Wash and white text.

### Tables
Dense and quiet: 11px uppercase ink-3 headers on Solid Panel Navy that stick on scroll, 6px by 10px cells with faint hairlines, right-aligned numbers, a 6% blue row hover, and a focus row with a 12% wash plus a 2px accent inset on the left. Team cells pair a 22 to 24px logo with a truncating name.

### Navigation
- **League tabs:** condensed 16px pills with a faint cobalt gradient; the active league fills with electric blue and glows.
- **Rail links:** 15px semibold with a 19px line icon; hover takes an 8% blue wash; active takes a left-to-right blue gradient, a blue border and white text. A live pulse dot rides at the right of the Live link when games are in progress.
- **Phone:** the rail becomes a horizontal scroller and the tabs wrap under the brand.

### Feed
Event rows on a three-column grid: time, a coloured line icon (accent by default, green for finals, red for injuries, amber for news), then a 13px line with a muted source sub-line.

### Charts
Recharts on the same palette: ink-3 tick labels, horizontal-only grid lines in translucent cobalt, opaque tooltip cards. Strength trends draw the team's visible colour as a 2.6px line over a 90% band. Win distributions fade weeks already played to 35%. Title odds carry 95% Monte Carlo error bars. Baseline-versus-scenario comparisons pair translucent ink-2 bars with electric blue bars. Chart animation is off.

### Motion
Exactly three motions exist: the probability bar's flex-basis ease, the 1.8s live pulse ring on live dots, and a 1.6s red flash behind a score when it changes. Hover changes are colour-only fades of 120 to 160ms. Under `prefers-reduced-motion: reduce`, the pulse, the tick flash and all transitions are removed.

## Do's and Don'ts

### Do:
- **Do** colour any probability with the one-hue intensity ramp (Signal Blue Ink at 50% and above, stepping down through ink, ink-2 and ink-3).
- **Do** put a team's official colour on its own band, bar segment and chart line, using the alternate colour when the primary is near-black.
- **Do** label both ends of every win-probability bar with team code and percentage, and choose the ink against the segment underneath.
- **Do** build new containers as Panels: Cobalt Edge border, top-edge glow, 12px corners, condensed 20px title with a line icon.
- **Do** set headline figures in Barlow Condensed 700 to 800 and keep tabular numerals on.
- **Do** caption panels with where their numbers come from (simulation count, state version, backtest window).
- **Do** fall back to a monogram disc in the team's visible colour when a logo is missing.

### Don't:
- **Don't** use green, amber or red for anything but leverage, live state, signed deltas and model health.
- **Don't** invent a colour for a team, or tint a team in the system accent when its own colours are known.
- **Don't** ship photographs, illustrations or decorative rasters; ESPN team logos are the only imagery.
- **Don't** show figures the engine does not produce (coaches, player ratings, spreads, weather, TV, polls), even as placeholders.
- **Don't** lift panels with large drop shadows or lighter fills; depth is the cobalt edge and its glow.
- **Don't** add motion beyond the bar ease, the live pulse and the score tick, and never ship any of them without a reduced-motion opt-out.
