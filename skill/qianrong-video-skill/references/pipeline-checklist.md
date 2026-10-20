# Pipeline checklist — shortest end-to-end run

Every command runs from the composition project directory unless noted. `<skill>` is where this
skill is installed.

## 0. Read first (do not skip)

- `references/acceptance-rubric.md` — write the pass line from it
- `references/creative-brief.md` — how to write the content
- `references/asset-production.md` — how to get real assets
- `references/design-rules.md` — the four rules every reference film obeys
- `references/audit-method.md` — what will be checked, and how metrics lie

## 0.5. Prove your toolchain

Copy the starter and confirm it renders before writing anything:

```bash
cp -r <skill>/assets/starter/my-film . && cd my-film
npx hyperframes@0.8.147 check                 # expect 0 errors as shipped
npx hyperframes@0.8.147 render -o renders/smoke.mp4 --crf 24
```

## 1. Write the pass line

Create the project's acceptance doc from `references/acceptance-rubric.md` before any code.
Gate: definition + weighted dimensions + hard-veto list exist.

## 2. Make the demo data fully real

- Strip seeded fake content; keep only real items.
- Fill every field the film shows (cover, transcript, analysis, score…).
- Verify each item opens / plays. A hollow dataset fills the film with placeholders.

## 3. Capture assets

- Real browser, `deviceScaleFactor=2`, at the delivery viewport.
- Drive the real interaction and capture the real state (empty / filled / playing / report open).
- Record the pixel box of any control you'll zoom into.
- For motion, pull a short real clip with ffmpeg and play it on the timeline.

## 3.5 Study references (quantitative + semantic)

```bash
python3 <skill>/scripts/make_frame_sheets.py ref.mp4 --out sheets/ref --label "Vendor X" --window 8 --grid 3
python3 <skill>/scripts/teardown_video.py ref.mp4 --out reports/ref.json --label "Vendor X"
VISION_ENDPOINT=... VISION_MODEL=... VISION_API_KEY=... \
  python3 <skill>/scripts/vision_teardown.py --sheets sheets --out analyses --ours my-film --jobs 2
```

Gate: ≥3 references; adopt a rule only if it repeats across ≥3. Details: `design-rules.md`,
`multimodal-teardown.md`, `reference-teardown.md`.

## 4. Build the composition

- One main timeline; scenes with explicit start/duration.
- Freeze the beat grid first and commit it:

```bash
python3 <skill>/scripts/make_beat_grid.py assets/bgm.mp3 \
  -o assets/beat-grid.json --bpm-range 55 110 --align-to <a known downbeat>
```

- Snap every scene boundary and key action to the frozen grid.
- Number counters: per-frame interpolation, not stepped.
- Give every scene three motion layers (camera + ambient + content).

## 5. Render

```bash
npx hyperframes@<pinned> check                       # must be 0 error
npx hyperframes@<pinned> render -o renders/video.mp4 --crf 20
```

Low CRF on a slow full-frame zoom balloons file size; CRF ~20 is usually visually identical.

## 6. Audit

```bash
python3 <skill>/scripts/audit_video.py renders/video.mp4 \
  --total <seconds> \
  --grid-json assets/beat-grid.json --bgm assets/bgm.mp3 \
  --countup   "<t0:t1:x:y:w:h>" \
  --playback  "<t0:t1:px:py:pw:ph:sx:sy:sw:sh>" \
  --scale-windows "<t0:t1:x:y:w:h>,<...>" \
  --json evidence/audit.json
```

Exit `0` = passed. Any failing signal → back to step 4. Keep the JSON as evidence.

## Re-running later / adapting to another product

Nothing here is product-specific. Swap the acceptance doc, creative brief, and real captures; reuse
the scripts unchanged. If the aspect ratio changes (vertical, square), pass `--expect-res` and
recompute the region coordinates for the 960×540 analysis space.

**After any asset swap, re-run the full `check`** — a passing layout can fail once the actual pixels
under your text change (see `asset-production.md`).
