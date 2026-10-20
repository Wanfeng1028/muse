# Assembly: one HTML page, headless Chrome + ffmpeg (the Stage API)

Assembly (cuts, trims, graphics, captions, audio) is ONE `index.html` that is a **pure function of time**, rendered frame by frame by headless Chrome and encoded by ffmpeg. A new project has `stage.js` at its root but no `index.html` until you write it; the page includes `<script src="stage.js"></script>`.

**Files:** create the page once with `composer_write_file(project_id, path="index.html", content=…)`. After that, `composer_read_file` then `composer_edit_file` with an exact `old_string` (copied without the line-number prefix) for every change. Read before every edit. Don't write the page through a heredoc in `composer_exec`.

```html
<div class="shot" id="s1"></div><div class="shot" id="s2"></div>
<div id="cta">…</div>
<script src="stage.js"></script>
<script>
Stage.setup({width: 1080, height: 1920, fps: 30, duration: 15});
Stage.clip('#s1', {src: 'gen/shot1.mp4', at: 0,   in: 0.4, dur: 4.2});
Stage.clip('#s2', {src: 'gen/shot2.mp4', at: 4.2, in: 0,   dur: 5.0, keep_audio: true, volume: 0.8});
Stage.audio({src: 'gen/music.mp3', at: 0, dur: 15, volume: 0.35, fade_in: 0.3, fade_out: 1.5});
Stage.render(t => {            // set EVERY animated style from t, nothing else
  const u = Stage.spring(t, 12.1);
  cta.style.transform = `translateY(${(1 - u) * 60}px)`; cta.style.opacity = Stage.clamp(u * 1.5);
});
</script>
```

- **Time purity is the contract (enforced).** The renderer renders the same frames in two different orders and fails the render if any element differs (`nondeterministic`). `Stage` also resets every inline style before each frame and reports a style set to `NaN`/`undefined`/`Infinity` as a page error. The browser silently drops such a value and keeps the previous frame's, which is exactly how a frame comes out different per render worker. The renderer calls `await window.seek(t)` before every captured frame, in any order, across parallel workers. Every style comes from `t` inside `Stage.render`: no CSS transitions or `@keyframes`, no `setTimeout`/`requestAnimationFrame`, no state carried between frames, no `Math.random` (use `Stage.hash(i)`). Helpers: `Stage.prog(t, t0, t1)`, `Stage.ease.{out,inOut,expoOut}`, `Stage.spring(t, t0, {freq, damp})` (closed form, so a value that changes target twice is two springs added), `Stage.lerp`, `Stage.clamp`.
- **Footage.** `Stage.clip(el, {src, at, in, dur, rate})` shows `src` from `in` for `dur` seconds starting at `at`. The renderer extracts those frames with ffmpeg and Stage swaps them per frame. A container gets a full-bleed `object-fit: cover` `<img>`; pass your own `<img>` to place footage anywhere (split screen, phone mockup, picture-in-picture, text behind a masked subject). Hard cuts are consecutive clips that don't overlap; that is the intended transition.
- **Trim, don't speed up.** An H3 clip is 5s+; a 3s shot is a window of it (`in`/`dur`). Use `rate` > 1 only when trimming can't work, and never above 1.25 (the renderer refuses). Never retime footage with ffmpeg (`setpts`, `atempo`, `asetrate`); ffmpeg is for probing, frames, crops and keyframes. Plan `in`/`dur` against `result.probe` durations, not the length you asked for.
- **Audio never goes through the page.** It is declared, and the renderer mixes it at 1.0 and loudnorms to -14 LUFS. Use `Stage.audio({src, at, in, dur, volume, fade_in, fade_out})` for the music bed / dialogue / SFX, and `keep_audio: true` on a clip to use its own sound for its window (0.12s fades are added at its seams). When the edit cuts H3 clips into windows, their sounds no longer join into one soundtrack: leave `keep_audio` off and run ONE continuous bed (Lyria, or the longest shot's ambience) plus any dialogue. Dip the bed to ~0.15–0.3 under speech with a second `Stage.audio` segment rather than a volume automation. `says`, `beats` and `duck` are covered in audio-sync.md.
- **Graphics are the page.** Overlays (captions, badges, packshot, logo, typed UI text, pasted-back reference pixels) are ordinary DOM above the footage, with images from `assets/` by relative path. Canvas size: keep the project canvas. Follow the footage when its aspect matches the request (exact probed pixels, never upscale the shipped take), else the standard size (9:16 → 1080×1920; resolution 480p → 480×854, 720p → 720×1280). Drafts are the one exception: 768P footage returns 768×1344 (slightly off 9:16), so either accept its scale-up onto the project canvas while drafting, or create a 720p project for draft-only checks. Never change the deliverable's canvas to fit a draft. Craft rules are in graphics-craft.md.
- **Edit is cheap, pixel is not.** Timing, cuts, overlays, captions, audio: fix in `index.html` (file tools are free; renders and checks via `composer_exec` cost exec time) and re-render (unchanged frames aren't re-captured). A defect IN the footage (face, label, motion, physics) is an H3 regen.
- **Seams need care in BOTH streams.** Use i2v chaining for the picture (the Loop's planning step) and a bed that runs across the cut for the sound. After a render, `strip` 0.2s either side of every seam and look: the room/person/framing must read continuous.

## Check, look, render, ship

All via `composer_exec`, then `composer_view` the image each one writes:

```bash
python3 -m lib.compose check index.html                                       # manifest, sources, rates, overflow
python3 -m lib.compose sheet index.html --at <one time per beat/read> -o out/check/sheet.jpg
python3 -m lib.compose strip index.html --range 3.8:4.4 -o out/check/seam1.jpg # every frame of a stretch
python3 -m lib.compose sheet index.html --at 12.5 --crop 80,1200,920,400 --width 900 -o out/check/cta.jpg  # full-res detail
python3 -m lib.compose render index.html -o out/video.mp4                     # optional: full render + advisory, no upload
```

Look at the sheet once. Watch for a read that never appears, text clipped or off the safe area, an empty frame, or an overlay hiding a face or the product label. `check` also reports `text_overflow`, `covers_face` and `nondeterministic`; fix every entry before shipping. A long `render` returns a `task_id` after ~50 s; poll it. Then ship with ONE call:

```
composer_ship(project_id, duration=<target seconds>)   # then composer_task_status(task_id, wait=50)
```

It renders (unchanged frames are reused), runs the gate, and only when it passes archives the source and uploads both. The result has `video_url`, `source_url` (absent on a watermarked take), `take` and `advisory`. The gate is deterministic, all from the render:
- `duration`: within 0.5s of the target duration.
- `speech`: every `says` window heard as written (Scribe).
- `text_flicker`: text that blanks for 1–2 frames and comes back (hand-timed caption chunks with a 0.02s gap between them read as blinking). Captions go through `Stage.captions`, which holds each chunk until the next starts. Any other text that changes in steps must also hold until its replacement appears.
- `covers_face`: a visible text element over a face in the footage under it (face detection on the clip frames). Titles, POV lines and captions sit in the band above the heads or below the chin, never across the face.
- `nondeterministic`: a frame that differs by render order (see Time purity), and page errors.
- composition rules: retimed audio, clip rate > 1.25, several shots under 1.5s, a silent video that declares audio.

It also computes advice that does not block: `pops_at` (single-frame jumps not on a cut or a text change; `strip` around each), `static_stretches`, `text_overflow`, `sync`. The ship result carries it as `advisory` (`{}` when there is none); read it after shipping, or run `lib.compose render` through `composer_exec` to see it earlier. The fade/pop advice (`pops_at`) can also fire on a deliberate overlay opacity fade; `strip` the flagged times and look at the frames before reacting.

`SHIP GATE FAIL — nothing uploaded` (the ship task fails with the reasons, and the credit is refunded) means it's not deliverable yet: fix each printed reason and ship again. Ship over it only after telling the user which check fails and why, and getting their agreement: `composer_ship(project_id, duration=…, ship_failed_gate="<which check failed and why you ship anyway>")`. It uploads and records the reason on the take.
