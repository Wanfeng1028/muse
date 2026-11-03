# Pipeline — timing → scenes → render → mix

Four stages. Each writes files the next one reads, so any stage can be re-run alone.

```
script.json ──TTS w/ word timestamps──> vo/<id>.mp3 + vo/alignments.json + vo/durations.json
     │
     └─ compute_timing.js ──> timing.json (start/dur/cues/words) · timing.js (window.__TIMING)
                              vo_events.json · captions.js
     │
     └─ the page (engine.js + ch_<id>.js) reads window.__TIMING, draws render(gt)
     │
     └─ render_scene_step.mjs ──> renders_${VER}/NN_<id>.mp4   (one clip per scene)
     │
     └─ build_mix.mjs ──> warped_${VER}/ + stems ──> Versions/<name>_${VER}_final.mp4
```

---

## 1. Timing from the voice

Record **one VO clip per scene**, with word-level timestamps (character-level alignments work too — index
into the joined string). Never record the whole film as one clip: a per-scene clip is what lets you
re-record a single chapter in round 6 without disturbing anything else.

`compute_timing.js` configuration shapes:

```js
const CONFIG = [                                  // ORDER IS THE TIMELINE. Position == scene index.
  { id: 'hook',  cues: [['ready','ready'], ['everywhere','everywhere']] },
  { id: 't_ch1', cues: [] },                      // a silent or short title card still gets a slot
  { id: 'ch1',   cues: [['start','Red team'], ['report','report', 1]] },  // 3rd element = occurrence index
];
const HEAD  = 0.45;                               // default silence before the clip starts
const HEADS = { t_ch1: 0.7, ch1: 0.6, close: 2.0 };   // per-scene override
const TAILS = { t_ch1: 0.15, close: 2.4 };            // default TAIL applies otherwise
const MIN   = { hook: 5.2, ch1: 25.8 };               // floor when the action outruns the voice
```

For each scene:

```
cue.at   = HEAD + wordTime(id, word, occurrence)
scene.dur = max( HEAD + voLength + TAIL ,  lastCue + 1.0 ,  MIN[id] || 0 )
scene.start = running total
```

The `lastCue + 1.0` term is what makes every chapter end **one second after its last spoken word** —
the single most effective pacing fix in the whole pipeline. `MIN` exists for chapters where a live
demo run, a scrolling list or a report has to be readable for longer than the voice takes.

Also emitted:
- `scene.words[]` — per-word times for opening scenes that land text word by word.
- `vo_events.json` — `{t, clip, gain}` so a silent bed can be rebuilt from per-scene clips.
- `captions.js` — sentence-level captions split at punctuation, long ones halved at the nearest comma,
  with overlaps trimmed. Skip scenes that have no alignment (a silent card) or the loop throws.

**`CUT` env**: `CUT=t_ch4,ch4 node compute_timing.js` splices those scenes out of `CONFIG` before
anything is computed, producing a short cut of the same film. Keep the full `timing.json` aside and
restore it afterwards; the mix must also skip SFX for absent scenes (`has(id)` guards).

---

## 2. The page

**Engine responsibilities** (one file, loaded last):

- **Clock.** `t` advances by `dt * (window.__RATE||1)`; `seek(t)` renders any time directly; `render(gt)`
  is exported on `window` so the render tools can drive it.
- **Scene registry.** `SCENES[id] = { layer, draw(lt, dur, scene), enter?, exit?, nav?, crumbs?, hideApp?, nocap?, noIris? }`.
  `sceneAt(gt)` picks the scene, `lt = gt - scene.start`.
- **Cue lookup.** `C(id,key)` reads `window.__TIMING`; it should **throw** on a missing cue so a renamed cue
  fails loudly at sweep time instead of silently drawing at 0.
- **Layers.** Film layer, dashboard/app layer, page layers. Scene changes toggle layer visibility; a
  transition (e.g. a shaped iris) clips the incoming layer for ±0.4 s around the cut.
- **Per-frame hooks.** Call the ground/token writer *before* the scene draws: `if (window.GROUND) GROUND.update(gt)`.
- **Theme flag from the URL**, applied to `<body>` and `<html>` (see THEMING.md).
- **Motion helpers**, all pure: `seg(x,a,b)`, `ez/eo/ei/eb` easings, `lerp`, `mix(hexA,hexB,p)`,
  `fallIn(root,lt,t0,opts)` (3D deal-in of `[data-fall]` children), `odo()` (number odometers),
  `drawIcons()` (stroke-dashoffset draw-on), `stagger()`, `typeText()`, `kine()` (kinetic headlines).
- **Cursor whitelist.** `window.CURSOR_ALLOW[sceneId] = lt => bool`. A synthetic cursor that is on screen
  the whole film reads as a screen recording; show it only for the two or three real interactions.
- **HUD** (scene dropdown, loop, scrub) hidden under `?render`.

**Chapter modules** own one chapter each and nothing else. A chapter reads its cues at load
(`const CUE = window.__TIMING…`) and offsets every beat from them, so a re-recorded VO line moves the
whole chapter automatically.

**Query parameters worth having:** `?render` (hide HUD, disable CSS transitions), `?t=` (open at a time),
`?scene=<id>&loop` (review one scene), `?rate=` (sweep speed), `?theme=`, `?nocap`.

---

## 3. Per-scene frame-step render

For every output frame `k` of a scene:

```js
await page.evaluate(x => new Promise(res => { seek(x); requestAnimationFrame(() => requestAnimationFrame(res)); }),
                    start + (k + 0.5) / FPS);
await page.screenshot({ path: `seq/s${k}.jpg`, type: 'jpeg', quality: 92 });
```

Two rAFs: the first applies the style writes, the second lets the compositor settle. The `+0.5`
samples the middle of the frame interval. Then `ffmpeg -framerate 30 -i seq/s%05d.jpg` plus the
scene's slice of the VO.

Why not a real-time screencast: on heavy blur/glass chapters the screencast duplicated ~50 % of frames
in one chapter and the film juddered. Frame-step is slower per scene but exactly right, and it lets you
re-render one 15 s chapter instead of a 3.5 minute film.

Warm the page before stepping: `seek(start - 0.05)` and wait ~200 ms so `enter()` side effects, fonts
and layout settle; otherwise frame 0 of the scene differs from every later render of it.

`render_all.sh` shards scenes across `WORKERS` Chrome instances (3 is the sweet spot on a laptop),
writes one log per scene, and **skips a scene whose output file already exists and is non-empty** —
that skip is the whole re-render workflow. A render interrupted mid-file leaves a truncated MP4 that
looks "existing": probe durations and delete the broken ones before resuming.

---

## 4. Mix and assembly

`build_mix.mjs` has three modes: `stems` (audio only, nominal timeline — fast iteration on the sound),
`warp` (warp whatever renders exist), `final` (everything, measured).

**Stage 1 — pacing warp.** Each scene gets a nominal speed factor, e.g. opening 1.08×, the "meet the
product" beat 1.0×, chapters 1.05×, title cards 1.0×, close 1.0×. Video is warped with
`setpts=PTS/f,fps=30`. This is how you take 3 % off the running time without re-animating anything.

**Stage 2 — measure back.** After warping, `ffprobe` each warped clip and rebuild the segment table from
the **measured** lengths. Warping never lands exactly on `dur/f`; if the audio is built to the nominal
lengths it drifts a frame or two per scene and a minute in it is audible.

**Stage 3 — VO tempo-fit.** Slice the VO per scene, `atempo` each slice to exactly its segment length,
`apad` to the target, concat. Seams sit at scene cuts, where the voice is silent.

**Stage 4 — SFX event table.** Events are written in *original* time and mapped through `W(t)` into
warped time, so retiming the film moves the sound with it:

```js
const add = (t, src, vol, dur, note) => EV.push({ t: W(t), src, vol, dur, note });
for (const k of ['a','b','c']) add(cue('ch1', k) + 0.3, 'pop.mp3', 0.22, 0.5, 'zoom ' + k);
```
Keep the palette tiny and physical: a soft tap when a card lands, a camera click on an allowed cursor
action, typewriter ticks for typing and pipeline steps, one or two low impacts for the logo beats.
Nothing on transitions that have no diegetic cause; no whooshes; no riser synths.

**Stage 5 — music.** One bespoke bed with a known BPM and first-beat phase. Compute the warped time of
the beat you want the music to hit (e.g. the lockup click), solve for the offset `SS` that puts a beat
there, and trim the bed from `SS`. Keep it low-passed and quiet until that moment, then cross-fade into
the open version. Sidechain-compress it under the VO stem
(`sidechaincompress=threshold=0.012:ratio=12:attack=20:release=500`) so the voice always wins.

**Stage 6 — master.** `amix` VO + music (≈0.40) + SFX, then **two-pass** `loudnorm` (measure with
`print_format=json`, then apply with the measured values and `linear=true`) to −16 LUFS / −1.5 dBTP.
One-pass loudnorm is dynamic and will pump.

**Stage 7 — concat + mux.** `ffmpeg -f concat -c copy` the warped clips (identical codec settings, so
stream copy is valid), then mux the mastered audio with `-c copy -shortest`.
