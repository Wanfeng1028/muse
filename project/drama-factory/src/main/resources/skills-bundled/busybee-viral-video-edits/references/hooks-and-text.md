# Hooks, Text Layers & the Tournament Method

The written hook is half the video. These rules are evidence-backed (field data + a 158-hook human review: the funny/concrete ones worked, the poetic ones failed universally).

## The 5-test QA gate (every hook must pass ≥4 of 5, or rewrite)

1. **Glance test** — fully decoded in one read at scroll speed (processing fluency).
2. **Speech test** — a real person would text this to a friend.
3. **Name test** — a *specific* someone feels personally addressed.
4. **Gap test** — watching the video resolves something the text left open (aphorisms self-resolve = no reason to watch).
5. **Pull test** — one tension word, odd number, or benign violation present.

**Stack formula** (a drafting aid, not the gate): concrete image + odd specific detail (3:07, not 3:00) + identity tag + one tension word + one withheld resolution. Draft toward 3+ ingredients; 0–1 means start over. The 5-test gate above is the binding pass/fail — a hook that stacks well but fails the gate gets rewritten.

**Banned**: abstract/poetic aphorisms ("liner notes" — un-picturable); "nobody:" (dated 2018 meme); explicit send/tag/comment commands on Meta surfaces (formal engagement-bait demotion); ALL-CAPS; story-setup openers. A/B axis is always **warm-funny vs quiet-specific**, never loud-vs-poetic.

Field-proven winner shape: odd specificity ("it's 3:41am and the mushrooms are winning").

## The affirmation-identity lane (share-dominant)

First-person present-tense affirmation ("I call all my energy back to me") + golden/ambient SINGLE-SHOT visual + zero cuts + familiar/nostalgic audio = share-dominant performance (observed 16:1 shares:comments). Mechanism: viewers share it as self-expression — the text is a feeling-claim they can claim as theirs. Identity text over ownable art wins repeatedly; slow single-shot loops beat fast cuts for SHARES (fast onset-cuts win RETENTION). Run both lanes; let posted metrics decide, not vibes.

## Text kinetics (first 3 seconds)

Winner of a 20-thesis adversarial tournament: **the Second-Line Drop** — hook line 1 static at frame 0; line 2 appears beat-fused within ±100ms of a real onset at 0.8–1.3s; designed sound-off-first. When 0.8–1.3s contains several onsets, fuse to the strongest; if it contains none, take the onset nearest 1.0s within 0.6–1.5s (and reconsider the window — a hook zone with no accent is a weak opening). QC gate: measure the rendered offset between the text-appearance frame and the audio accent; if |offset| > 100ms, re-render. Other top theses: bright single-subject first frame; loop-in mid-phrase so the ending replays into the start.

Also machine-verify any claim in the text: a timecode shown on screen must equal `source_t - window_start` checked against the section CSV before the text layer renders.

## The container format (Sweeps-style)

1080×1920 black canvas; footage in a centered window (square ~1000px at (40,470), or 4:3); monospace white hook text above (Courier New Bold, ~52px, per-line `drawtext` with `enable='gte(t,...)'` timing); credit lines below (`song | artist ~ track` + album/footage credit). Never let text cover the footage window.

**Which text format for which lane**: the container is for faceless sourced-footage lanes (Sweeps-style montages, batch variants). Artist-in-frame cinematic pieces go full-bleed with the letterbox treatment instead — title inside the bottom bar (see cinematic-grade.md), hook text minimal or absent. Don't put a cinematic piece in the container; don't letterbox a faceless montage.

## The tournament method (for any creative decision at scale)

When choosing between many creative approaches, don't brainstorm-and-pick — run an adversarial tournament:

1. **20 dimensions**, one researcher agent each, writes a thesis (core claim + mechanism with evidence tiered A/B/C, honest about weak legs).
2. **Adversarial critique**: ~2 attacks per thesis (40 total).
3. **Revision**: every thesis revises to concede valid critiques (winners are always v2+).
4. **3-judge panel** (methodologist / copy-chief-or-growth-operator / brand guardian) scores /50; rank by mean.
5. Every thesis must include: numbered decidable rules, a concrete example artifact, and a **testable prediction** with named A/B arms, primary metric, and explicit FALSIFIERS (what result kills the thesis).
6. Ship the winner as doctrine, then build the real test fleet: N videos on ONE identical body where only the tested variable changes, manifest CSV mapping thesis→video, post, and correlate judge rank vs actual views.

## Field references (competitor teardowns)

When shown a competitor page/reel, write a field-reference doc: URL + followers; observed logged-in performance (recent view counts, computed reach %, engagement shape); the outliers and WHY they won; mechanism; "lessons that transfer" — and convert each lesson into a concrete A/B lever queued in the optimization loop config. Corrections to priors are the most valuable part (e.g. "top reels are slow single-shot loops, NOT fast cuts"). The loop decides, not vibes.

## The optimization loop (posting side)

Ledger-driven experiment engine: first a ~10-post calibration cohort (champion config only — measures the noise floor), then one lever at a time from a queue, levels interleaved across the schedule so time-of-week never confounds, ~3 posts/day. Ingest metrics (platform API or CSV exports), decide by median of the primary metric (avg watch ratio, or shares/reach for share-lane tests) with a minimum N per level, update the champion config, log the decision, pop the lever. Hooks and cut engines are levers like any other.
