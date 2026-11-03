# STORYBOARD.md: template and worked example

The storyboard is the contract between you, the builders and the composer:
- builders follow it **verbatim** (copy, timing, assets);
- the composer hits every row of the hit list;
- critics judge against it.

Write it at **v1**, run the two critics, and lock it as v2/v3.

## Rules
- **Grid.** Pick a BPM. At 30 fps:
  - 120 BPM → beat 0.5 s / 15 f, bar 2 s / 60 f;
  - 100 BPM → beat 0.6 s / 18 f, bar 2.4 s / 72 f.
- **Bar lines.** Scene and section boundaries sit on bar lines. Inside the intro you may cut on beats.
- **Times.** Use absolute seconds everywhere. Scenes are contiguous from 0 to the end.
- **Readability.** Each caption gets ≥ 0.35 s per word, fully visible, after its ~0.5 s animate-in. Count the words, and give each caption a start time.
- **Pills.** Words with the house highlight are written `[like this]`. Punctuation after a pill is fine: `[days].`
- **Hard cuts.** Mark them **CUT**. The default hand-off is the "dip" (outgoing blurs out, incoming rises in). Use **XFADE** only when both scenes share a background.
- **One story.** The product section follows ONE metric/outcome from goal to result. Hypotheses, approaches, PR/result and payoff numbers must all refer to it.
- **Demo data.** Fictional/demo-tenant numbers only ever appear inside UI shots, never in headline type and never under a "proof" heading.

## Shapes

| Length | Shape |
|---|---|
| **60 s** (default) | Tension 0–12 · Reveal 12–16 · Product loop 16–42 (3–4 steps, 6–8 s each) · Proof 42–52 · Close 52–60 |
| **30 s** | Hook + problem 0–6 · Reveal 6–8 · Loop 8–22 (3 steps) · Proof 22–26 · End card 26–30 |
| **90 s** | Tension 0–14 · Reveal 14–18 · Loop 18–60 (4–5 steps) · Proof 60–76 · Close 76–90 |

## Template

```markdown
# <COMPANY> — "<Working title>" · <length> launch film · storyboard v<1>

**Logline:** <2 sentences: the tension, the reveal, the payoff, the closing line>
**One story through the loop:** <the metric/outcome followed end to end>
**Grid:** <120> BPM · beat <0.5> s = <15> f · bar <2> s = <60> f · 30 fps · 1920×1080. Times are absolute seconds.
**Transitions:** default dip hand-off; CUT and XFADE are marked.
**Readability:** ≥ 0.35 s/word fully visible.
**Copy style:** <sans, weights, case, colour>; pill = `[like this]`; step labels <mono, uppercase, size, tracking>.

## ACT I — TENSION (0.0–12.0)
### S01 · Hook · 0.0–3.5
- **Copy (centre, 84 px), in at 0.2:** `<…[pill]…>` — <pill word swaps on beats …>
- **Behind:** <…>
- **Music:** <…>
### S02 …

## ACT II — REVEAL
### S04 · Meet <Company> · 12.0–16.0 · **CUT on the drop**
- **12.0:** IMPACT — <flash, shockwave>. Logo draws (12.0–12.6), fills (to 13.0); wordmark slides in.
- **13.0:** `The [<category>]` · **13.4:** `<what it does, verbatim from site>`

## ACT III — THE LOOP, IN THE PRODUCT
**Fixed layout:**
- **Caption band:** mono step label at y≈96, caption 56 px at y≈130–200, left-aligned at x=120, one line, max 1500 px.
- **Product window:** 1200×675, centre x≈1040, top y≈300, rotY −6°, rotX 3°, slow dolly 1.00→1.03.
### S05 · 01 <Step> · 16.0–22.0
- **Label:** `01 — <STEP>` · **Caption A (16.3):** `<…>` · **Caption B (19.2):** `<…>`
- **16.0–19.0 · window `<capture>.png`:** push in on <element> (rect ≈ x… y… w… h… from rects.json); light <items> on beats …
- **19.0–22.0 · …**
### S06 … S08

## ACT IV — PROOF
### S09 · <Proof> · 42.0–48.0
- **Label:** `<…>` · card 1: <logo file> + `<+NN%>` counts up over 42.0–42.5 (lands on the hit) · `<metric label>` · secondary at 43.5 …

## ACT V — CLOSE
### S11 · <Resolve line> · 52.0–56.0 · XFADE into S12 (shared background)
### S12 · End card · 56.0–60.0
- 56.0 logo sting · 56.3 tagline · 56.6 CTA row (`<url>` + `[<Button> →]`) · 57.0 footer line · last 15 frames fade to black.

## Hit list (absolute seconds)
| t | kind | note |
|---|---|---|
| 0.0 | pad-in | … |

Kinds:
- **Sound effects:** tick, soft-tick, tick-rise, type-hit, swish, whoosh, click, stamp, thunk, bell, impact, logo-sting.
- **Music events:** pad-in, pluck-in, riser-start, silence, drop, section, snare-fill, drums-out, fade.

## Music plan
- **0–12 Intro:** <…>
- **12.0 Drop:** <…>
- **Groove A …**
- **Peak …**
- **Proof …**
- **Close …**
- **Master:** −14 LUFS integrated, ≤ −1 dBTP.

## Global design notes
<Background treatment, window spec, rebuilt-card spec, status colours, pill spec, type scale, motion vocabulary.>
```

## Worked example (fictional company: Acme Metrics)

> **Logline:** Every team is judged by a number. The next 1% is buried, and finding it takes months. Acme is the experimentation copilot: it reads your stack, takes a metric goal, tests approaches in parallel and turns the winner into a PR. Close: *Find your next 1%.*

| Scene | Time | Copy | Visual |
|---|---|---|---|
| S01 Hook | 0–3.5 | `Every team is judged by [retention].` (the pill rolls: activation → conversion → revenue on beats 1.0/1.5/2.0/2.5) | huge faint pixel-font number ticking 41.2% → 41.6% |
| S02 Stakes | 3.5–7 | `At scale,` / `[+1%] is worth millions.` | thin line chart steps up on 4.0–6.5 |
| S03 Problem | 7–12 | `But the next 1% is buried.` → `Finding it takes [months].` | 4 data cards (CODEBASE, CLICK LOGS, DOCUMENTS, EXPERIMENTS) on beats; collapse to a point; 0.25 s silence |
| S04 Reveal | 12–16 **CUT** | `The [experimentation copilot]` / `<site sub-line>` | flash, dot shockwave, logo draw + fill |
| S05 01 | 16–22 | `It reads your code, data and experiments.` → `Verified on a benchmark [your team] sets.` | real "indexed sources" page; callout chips `4,869 artifacts read`; benchmark card |
| S06 02 | 22–28 | `Give it a goal, not a ticket.` → `It frames the hypotheses. [You] sign off.` | typing wipe of the goal into the real prompt box; goal pill + H1–H4 cards fan out; H1 chosen |
| S07 03 | 28–36 | `Specialist agents test approaches in parallel.` → `Dead ends fail fast — [offline], not on your users.` | real agents list with running → complete checks; rebuilt 5-lane race, 3 fail, winner chip |
| S08 04 | 36–42 | `The winner becomes a [PR].` → `Nothing ships without [your approval].` | rebuilt PR card with typed diff and a `+2.4pp · offline` chip; real review card, click → "✓ Accepted" |
| S09 Proof | 42–48 | `SHIPPED WITH ACME` | two customer cards, numbers counting up and landing on 42.5 / 45.5 |
| S10 Speed | 48–52 | `Goal to validated win: months → [days].` / `More metrics moved, [every quarter].` | months struck through; Q1–Q4 bars on beats |
| S11 Close | 52–56 **XFADE** | `Find your [next 1%].` | landscape painting rises from black like daybreak |
| S12 End card | 56–60 | `Acme` · `The experimentation copilot.` · `acme.com` `[Book a demo →]` | logo sting; full lockup holds ≥ 2.4 s; fade to black |
