# Audit method — how to verify without watching

The core stance: **don't ask "does it look good", ask "which frame can prove it is dead / fake /
wrong"**, then measure. `scripts/audit_video.py` implements the checks below; it prints a JSON
report and exits `0` (pass) / `1` (below the line).

## The checks

| Check | Method | Flag |
|---|---|---|
| Length / aspect / audio track | `ffprobe` | `--total`, `--expect-res`, `--dur-tol` |
| Opening not silent | segment RMS; ratio of 0–3s to whole film (< 0.6 is weak) | `--head-seconds` |
| Where it's dead | 960×540 @10fps, 12×6 blocks, per-block diff; reports **frozen** and **low-motion** separately | `--static-threshold` |
| Blank / black frames | `std<8` / `mean<12` | (always) |
| Beat actually aligned | onset envelope of the **music file**, offset per downbeat | `--grid-json --bgm` |
| Push-in amount | **region template matching**, reports median/max + NCC | `--scale-windows` |
| Real video playing | "hot sub-block ratio" in the play region vs a static region | `--playback` |
| Number count-up continuous | per-frame diff in the number region; frozen frame-pairs should be 0 | `--countup` |
| Typing is gradual | count discrete diff bursts in the input region | `--typing` |
| Contrast / overflow / occlusion | the renderer's own `check` (Contrast / Layout) | — |

All region coordinates are in the **960×540 analysis resolution**, not the source resolution.

## Thresholds used as defaults

- active-frame ratio ≥ 0.55
- no **frozen** segment ≥ 1s
- blank frames = 0, black frames = 0
- opening energy ratio ≥ 0.6
- clipped-sample ratio < 0.001

Tune per film; keep them visible in the report.

## How the metric itself lies (keep these in mind every time)

These are real failures hit while building this tooling. They are the reason the reference exists.

1. **One word, two definitions, one masking the other.**
   "No static segment ≥ 1s" was reported as clean. A true per-frame diff later found two
   **low-motion** stretches near the end. They were *not* pixel-frozen — the ambient layer kept
   moving — but the content barely moved. Fix: report **frozen** (whole-frame mean diff < 0.15)
   and **low-motion** (active-block share < 2%) as two separate signals. Never collapse them.

2. **A mis-parameterised probe silently returns "pass".**
   The first scale probe used whole-frame cross-correlation; when shapes didn't line up it
   `continue`d, so **every window returned 1.0×** — looking like "no push-in" when the probe was
   simply broken. Fix: region template matching, print the NCC, and emit `error` when there is no
   trustworthy match instead of guessing a number. **A probe that always returns "normal" is worse
   than no probe.**

3. **Use the source file as the baseline, not the deliverable.**
   Beat alignment was once computed against the **rendered film** — mixed with SFX and encoded with
   a delay, so the offsets were garbage. Switching the baseline to the **music source file**
   brought the mean downbeat offset to ~4 ms.

5. **A passing check is only valid for the pixels that were checked.** The renderer's contrast and
   occlusion checks are computed against the actual frames. Swap a placeholder for a real photo and
   the background luminance under your HUD text changes — a green check can turn red with no code
   change to that text. **Re-run the full check after any asset swap, not just after a code change.**

4. **Sampling can manufacture the artifact.**
   A 10fps pass read two stretches as long static runs; a 30fps re-check showed only a handful of
   frozen frame-pairs. Always confirm a suspected freeze at a higher frame rate before acting.

> One line: **the auditor must itself be audited.** Every probe should give the true value on a
> known-true sample and the false value on a known-false sample; otherwise it is just producing
> professional-looking numbers.

## Beat grid

Run `scripts/make_beat_grid.py` on the music file to freeze the pulse grid to JSON. Automatic BPM
detection drifts between the truth, its double, and unrelated candidates (same track:
`librosa.feature.tempo` gave 143.55, autocorrelation gave 69.84). The script pins the fundamental
via autocorrelation within a given BPM range, and `--align-to` resolves the 4-way downbeat ambiguity.
**Commit the resulting grid; never re-derive it at render time.**
