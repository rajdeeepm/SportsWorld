# SportsWorld: demo video script (v4, 4:30)

Record at https://worldofsports.tech in a clean browser window (1512×900 or 1920×1080), zoom 100 %, no
bookmarks bar. Have a second window ready for the SpacetimeDB shot. Record on a Saturday night or Sunday
afternoon so live games are on.

**The one-line thesis to repeat:** *Know what matters before you watch.* We do not claim to out-predict ESPN or
the betting market. We claim a calibrated, explainable model of the whole season that you can question.

---

## 0:00 · Hook (league page, college football) · 25 s
**Screen:** CFB overview. Hold on the kicker and the headline.
> "Every sports app tells you who will probably win tonight. None of them tells you what tonight *means*.
> SportsWorld plays out the rest of the season 10,000 times, so every game shows what it means for the playoff
> race. Know what matters before you watch."

## 0:25 · Why this game matters · 40 s
**Screen:** scroll to **Game of the day: why it matters**. Point at each cell left to right.
> "Here is tonight's game of the day. Win probability, and how one honest label describes it. The playoff swing
> for each side: if they win versus if they lose. Other teams whose odds move beyond simulation noise, and who
> they should root for. And a plain recommendation: must-watch, upset watch, or skip."

Click through to that game's page; the same card sits above the live field.

## 1:05 · Live game · 30 s
**Screen:** a live football game. Ball spot, drive, win probability line. Turn on **Live commentary**
(ElevenLabs) for one play.
> "Real ball position from the play-by-play, our live win probability, and live commentary voiced by
> ElevenLabs, written from the real play text and our numbers."

## 1:35 · SpacetimeDB, visibly · 30 s
**Screen:** two browser windows side by side, both on the CFB overview. Wait for a score change.
> "Every viewer subscribes to one shared world state in SpacetimeDB. When a score lands, the engine
> publishes once and both windows update at the same instant. Here's the push: same state version, both
> screens." (In testing, two clients received the same push 4 ms apart.)

Point at the **Pushed by SpacetimeDB · state vN** notice and the **last push 0s ago** chip.

## 2:05 · Team world and the Lab · 40 s
**Screen:** Michigan team page (season outlook, schedule with leverage, season paths, player stats). Then
Simulation Lab: **Starting QB out 3 games**, plus **Michigan beats Ohio State**. Run.
> "Michigan's whole season: expected wins with a range, odds by final record, every remaining game ranked by
> stakes. In the Lab we branch the world: their QB out for three games, a learned effect of minus 2.9 points,
> and a forced win over Ohio State. Both branches share random numbers, so every difference is the scenario."

## 2:45 · Ask the agent (Fetch.ai on ASI:One) · 30 s
**Screen:** ASI:One or the site's **Ask SportsWorld**: "What if Michigan beats Ohio State?"
> "The same analyst lives on ASI:One as a Fetch.ai agent. It does not chat about sports; it runs the engine:
> 10,000 seasons per branch, and answers with the numbers. Llama rewrites it conversationally, and we reject
> any rewrite whose numbers or wording the engine didn't give."

## 3:15 · Proof it isn't using the future · 35 s
**Screen:** Research page, **Rewind** (NFL, then CFB). Then the league page **Today's scorecard**.
> "Every forecast is point-in-time. Here's each past champion and what the model gave them on each date,
> rebuilt from only what was known then. Tampa Bay started at 1.3 percent; the model caught up as the season
> showed it. And every night it grades its own kickoff forecasts against what happened, next to ESPN and the
> betting market."

## 3:50 · Honest results · 25 s
**Screen:** Model health / Research (season replay coverage, market benchmark).
> "On seven replayed seasons our 90 percent ranges catch the truth 91 to 95 percent of the time. Treating games
> as independent, the standard approach, gets 52 to 77. Game by game we're on par with ESPN's own model and
> about 0.03 log loss behind the betting market, which sees lineups we deliberately don't use. Our edge isn't
> a better coin flip; it's a model of the season you can trust and question."

## 4:15 · Multi-sport flash and close · 15 s
**Screen:** click NFL, NHL, F1 (track view) tabs, about 3 s each, then back to CFB.
> "One engine for the NFL, college football, the NBA, NHL, college basketball, college hockey and Formula 1.
> SportsWorld: know what matters before you watch. worldofsports.tech."

---

### Checklist before recording
- Site loads at https://worldofsports.tech; the SpacetimeDB chip says *live*.
- At least one live game (check **Live** in the rail).
- Ask SportsWorld answers "What if Michigan beats Ohio State?" in under ~20 s.
- ElevenLabs voice plays (Listen to the briefing).
- Second browser window logged into nothing, same page, side by side.

### Do not say
"State of the art", "beats ESPN", "more accurate than Vegas", or anything implying betting advice.
