# Footage Sourcing & the Shot-Level Quality Gate

Rules learned from a failed first library (coffee beans in "cozy", silent-film title cards, random junk in frame). Root causes: query literalism (text matches vocabulary, not vibe), file-level pooling (whole files admitted, random timestamps sampled), no real quality floor. Bundled implementation of the gate below: `scripts/scan_shot_quality.py`.

## The SOP

1. **Write a vibe spec BEFORE any search query**: shots wanted (concrete visual descriptions) + explicit rejects. Derive queries from the spec, not from the lane name.
2. **Source from the highest tier first**: NOAA/NASA/LOC/Prelinger master-quality archives (ProRes/4K, public domain) > curated shelves (Mixkit/Coverr/Pexels featured; Pexels API needs a key the user must create) > YouTube CC > AI generation. Cinematic masters beat filtered slush.
3. **Every file gets a dense contact-sheet human glance** — license filters pass horror slop, vlogs, endcards, watermarks. Trim bad ranges; quarantine bad files (`_quarantine/`). Then the automated shot gate (below). Builders pick ONLY from accepted shots.
4. **Licensing is real**: verify the license field per file, not just the search filter (`yt-dlp --dump-json`, require "creative commons" in the license string). Keep an attribution manifest (CC-BY needs a visible credit line). Mark any `--any-license` pulls DEMO-ONLY, never posted publicly. Duration gate 45–2400s, height ≥720, `bv*[height<=1080][ext=mp4]` preferred, max 400MB.
5. **House grade over everything**: one palette + one grain pass over all sourced clips so mixed sources read as one film.
6. **Film grain is GOOD** (viewers prefer it) — never filter it. The real penalties: blockiness, banding, upscale blur, watermarks, borders (also official platform reach penalties).
7. Personal/family footage: per-file owner approval before anything posts publicly.

## The shot-level quality gate (v2 — per SHOT, never per file)

Split each file into shots (PySceneDetect `ContentDetector(threshold=27.0)`); subdivide continuous spans >25s into 12s windows (judge dashcams/timelapses locally). Sample 3 frames per shot (at 0.2/0.5/0.8 of the span), metrics on a 480px-wide resize:

| Metric | Gate | Notes |
|---|---|---|
| luma (gray mean) | 28.0 – 215.0 | dark-by-design lanes (night drives, plankton): floor 11.0 + require highlight fraction ≥0.02 |
| sharpness (Laplacian variance) | ≥ 40.0 | B&W archival: ≥ 16.0 (grain-tolerant) |
| text_ratio (OCR word-box area, conf>55, `--psm 11`) | ≤ 0.045 | kills title cards / intertitles / captions |
| border (black rows/cols mean<12) | ≤ 0.18 | kills pillarboxed junk |
| colorfulness (Hasler-Süsstrunk) | ≥ 8.0 | also the B&W detector (<8 → B&W vote) |
| motion (mean abs gray delta between samples) | scored, not gated | reserve high-motion for high-energy sections |

Output `shot_map.json`: per file → `{duration, is_bw, shots_accepted, shots_rejected{dark,soft,text,border,short}, accepted:[{start,end,luma,sharp,text,color,motion}]}`. Builders' `good_start()` picks a random start inside an accepted shot long enough for the segment.

Engineering: scan incrementally (skip files already in the map, write the map after EVERY file — crash-safe), isolate each file in a subprocess with a timeout (600s; batch scanners hang on 8K files), and proxy anything taller than 2160px to 1080p first (timestamps map 1:1).

## Semantic verification (does the shot depict what the edit needs?)

The deterministic gate answers "is this a usable shot"; a second layer answers "does it satisfy the concept contract." Pattern: sample coarse+fine frame sets; a LOCAL vision-language model (deterministic: temperature 0, seed 0) produces *blind* per-frame observations first, then a separate adjudication pass checks them against a named contract — required label groups (with min confidence + min matching frames), required temporal actions (with min evidence frames), geometric floors (subject area fraction ≥0.06, salient-crop survival ≥0.45, min usable window 1.2s). Add deterministic label/geometry checks (e.g. an Apple Vision helper) so pass/fail isn't purely LLM-judged. Content-address everything (media, contract, prompts, model digest → cache key) so identical inputs never recompute.

## Person-footage contracts (for matte pipelines)

Before an FX pass consumes a person clip + matte pair: `ffprobe -count_frames` both, assert frame-exact sync, and enforce matte statistics (mean coverage 0.02–0.90, coverage jump ≤0.20, low-coverage run ≤2 frames, non-person island ≤0.005). Know your subject: keep a ground-truth identity reference (which person is the artist vs friends) and only promote approved angles.
