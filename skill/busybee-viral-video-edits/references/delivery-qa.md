# Encoding, Delivery & QA

## House encode settings

- **Format: 1080×1920 @ 30fps** (9:16 vertical), always. Cover-crop: `scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920`.
- `libx264 -pix_fmt yuv420p -movflags +faststart`; audio `aac -b:a 192k -shortest`.
- CRF tiers: **17** for any final that passed through a frame-pipe or in-shader pass (per-pixel work deserves visually-lossless); **18** for segment-concat finals and procedural silent intermediates (drop to 19 only if file size genuinely matters); **20 with `-g 1`** (all-intra) for prep masters that need clean seeking; **26** for proxies. Preset: `fast`/`veryfast` intermediates, `medium` finals.
- Audio mux: trim with `-ss START -t DUR` on the audio input; fade in `afade=t=in:st=0:d=0.04–0.10`. Fade out: short (0.25–0.30s) when the window ends mid-phrase or the edit is a loop (protect the loop seam); long (1.0–1.4s) when the window resolves a section and the piece is meant to end. Delete silent intermediates after muxing.
- Concat: write `concat.txt` (absolute paths), `ffmpeg -f concat -safe 0 -i concat.txt -c copy` — all segments must share codec params.
- Frame-pipe encode input: `-f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 30 -i -` (+ `-vf vflip` if the source is GL).
- Also produce a QuickTime-compatible `.mov` when the deliverable will be reviewed in Apple players, and QA it separately.

## Per-edit deliverables (always)

1. The final mp4 (versioned name: `<song>_<concept>_v<N>[_<variant>].mp4` under `outputs/<project>/`).
2. A **contact sheet** covering the FULL duration: pick fps so `fps × duration ≈ tile capacity` (e.g. 15s → `fps=2,tile=6x5`; 30s → `fps=1,tile=6x5` or `fps=2,tile=8x8`): `ffmpeg -i final.mp4 -vf "fps=2,scale=270:-1,tile=6x5" -frames:v 1 contact.jpg`. A sheet that silently truncates the back half hides ending failures.
3. A **timeline** (JSON or CSV): every cut with time, source, and role.
4. For multi-variant batches: a `manifest.csv` row per video (slug, track, lane, density, hook, window, segments, file) and a filterable HTML review gallery of contact sheets.

## The QA pass (automated + human — automated NEVER replaces watching)

Automated probe (write `qa_<name>.md` + `.json`):
- ffprobe: duration matches contract EXACTLY (e.g. 15.000s), 1080×1920, 30fps, h264, audio stream present (aac).
- Frame-count checks: segments frame-exact against the plan; short clips freeze-padded (`tpad=stop_mode=clone`), never grid-shortened.
- Flags list (empty = clean), then this line verbatim: "No automated flags. **Still review the contact sheet or final render by eye.**"

Human review checklist (contact sheet + watching at normal speed):
- No blank frames, shader artifacts, watermarks, stock overlays, title cards, or accidental black.
- Subject/action readable after crop, at phone scale as well as full size.
- Accents look intentional, not random filler; priority musical hits served by strong footage.
- **Integrated-FX cohesion check**: does any effect read as a sticker/overlay? Does any segment read as a cutaway to a different video? Does one shot break the shared grade? Any = revision.
- Text-sync check: hook line 2 lands within ±100ms of its onset (measure the actual frame).
- Loop check: replay the ending into the start.
- Save review frames at mandated timestamps (e.g. 1.0/4.0/8.0/12.0/14.0s of a 15s piece) plus a late-frame spot check; keep them with the QA report.

Five independent QA gates for anything going public: technical, visual, narrative, originality/rights, platform package.

**Cheap-proof stage**: before a full/VFX build, render a low-res skeleton of the first 3–5s and watch it at scroll speed. Kill criteria are cheap at this gate and expensive after VFX.

## Verdict format

End every QA with one of: ready / needs small revision (list) / needs rerender (why). Failure patterns that always send it back: no/wrong audio; wrong aspect or unintended crop; action hidden by the vertical crop; FX cutaways or sticker-look composites; timeline and render materially disagree; weak first frame.

## Publishing package (when requested)

Web encodes (~720p) into a deploy dir, gallery HTML + manifest, posting schedule CSV/MD. Static hosting (e.g. Cloudflare Pages) — remember branch flags so deploys go to production, not previews. Log every post into the experiment ledger (see hooks-and-text.md, optimization loop).
