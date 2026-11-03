# Parallel-builder brief — template

One document per round. Dispatch one subagent per **owner**; each owner has an exclusive file set.
Copy this file, fill the angle brackets, delete what does not apply. Keep it under ~50 lines: a brief
long enough to be skimmed is a brief that gets ignored.

---

```markdown
# <film name> <round / version> (<date>): <one-line summary of what this round changes>

<Where the work happens: the tree path. What the variant is: `?variant=<name>` →
`window.__FLAG=true`, classes `theme-<x> theme-<y>`.>

<What is already DONE and must NOT be edited, with its owner: e.g. "the ground module is owned by the
coordinator, do not edit".>

**The other shipped variants must render EXACTLY as before**: every change below is scoped to
`.theme-<x>` or to code that only runs when `window.__FLAG` is set.

## Standing rules (unchanged from <earlier brief>)
- Every visual is a pure function of the scene-local `lt`; no state across frames, no timers, no CSS transitions.
- One easing curve per move. No two writers on the same element's transform in the same frame.
- Read your scene's `start` / `dur` / `cues` from `timing.json`. Do not hard-code a beat a cue can anchor.
- Fonts / palette / copy rules: <the kit>. No <banned punctuation>. No invented numbers or copy.
- Do not run <the orchestrator-only scripts>. Keep every shell call under <N> s.

## The look / the moves
<Numbered description of each new move, precise enough to implement without asking:
what happens, on which cue, over how long, with which easing, to what final value.
Name the accent colour / token per scene where it differs.>

## How the tokens work (<owner> implements, everyone uses)
<Which file gets the token block, which tokens are static vs dynamic, and the card-scoped ink rule
each owner copies for their own surfaces.>

## Owners

### A — <exclusive file list>
1. <task>
2. <task>
Frames to check (`VARIANT=<x>`): <t, t, t …>, plus 1/30 s steps across <the moves you touched>.

### B — <exclusive file list>
1. <task>
Frames to check: <t …>. Look for: <the specific failure mode, e.g. "dark-UI leftovers: dark chips,
white-on-white text, invisible hairlines">.

### C — <exclusive file list>
1. <task>
Frames: <t …>.

## Proof of no regression (every owner, before reporting done)
- `node scripts/play.mjs 14` → `errors: 0`, and the same for every other shipped variant.
- `VARIANT=<x> node scripts/shots.mjs <your shots dir> <your frames>` — **look at every JPEG**.
- Shoot ONE frame of your own area in each older variant and confirm nothing moved.
- `grep -n "<forbidden words>" <your files>` prints nothing in visible strings.
- Report back: what you changed, any deviation from this brief and why, and the frames you checked.

Shots go under `<scratchpad>/shots<round><owner>/`.
```

---

## Why each part is there

- **Exclusive file sets** are the only thing that makes parallelism safe. Shared files (the token sheet,
  the HTML's script tags, the timing config) get exactly one named owner and an explicit "nobody else
  edits this" line.
- **Frames to check** must be concrete times, computed from `timing.json` (`<scene>.start + offset`).
  "Check the chapter looks right" produces no verification; `63.0 / 66.9 / 86.5` produces JPEGs.
- **Look at every JPEG.** An error-free sweep proves the code runs, not that the frame is correct.
  Say this explicitly or it will not happen.
- **Proof of no regression** is what lets a film carry six variants without each round breaking the last.
  Requiring one *old-variant* frame per owner catches the unscoped CSS rule that a new-variant-only
  check never would.
- **Report deviations.** Builders will and should deviate where the brief is wrong about a collision or
  an overlap. Those deviations are the next round's spec entries — collect them back into `SPEC.md`.
