# Build, export, fidelity, review

Evidence: the author's lab workflow and production-order notes, card T05. Tags: [lab] =
used in the author's lab rounds; [C20] = a source tutorial's claim, not tested here;
[reelmimic] = practice of the external repo github.com/edenfunf/reelmimic, not tested here.

## §1 Build — every frame is a function of time [lab, r5 onward]

- One HTML page. Expose `window.__setTime(t)`; everything on screen is computed from `t`.
  No `setTimeout`, no `requestAnimationFrame` wall-clock time, no CSS transitions or
  animations left to the browser's live tweening.
- Springs in closed form (step response), not simulated per frame; parameters in
  `element-motion-params.md`.
- Keep tunables in one block at the top (durations, colours, section times, beat grid).
- Beat-locked events carry `// beat-locked: <t>s` comments (see `rhythm-transitions-camera.md` §1).
- Asset and font failures show a visible notice on the page plus a structured console
  error; a silent blank frame is a defect.
- Speed map for demos (author r14: real waits drag; unvalidated, first used in r15). Speed
  changes the mapping from film time to demo time, not the frame rate. Only the demo layer
  reads the mapped time; headlines and captions stay on film time, so their reading hold
  never shrinks.

```js
// demo speed map: [demo_start, demo_end, speed]; speed 1 = real time. Global = one row.
const SPEED = [[0, 3.0, 1], [3.0, 11.0, 6], [11.0, 14.0, 1]];   // e.g. an 8 s download at 6x
const RAMP = 0.25;                       // s of film time to ease between speeds
function demoTime(tf) {                  // film seconds since the demo started -> demo seconds
  let td = 0, left = tf;
  for (const [a, b, v] of SPEED) {
    const film = (b - a) / v;            // film seconds this span takes
    if (left <= film) return td + left * v;
    td += b - a; left -= film;
  }
  return td + left;                      // past the table: real time
}
// Easing: blend neighbouring speeds over RAMP (integrate a smoothstep of v), or keep hard
// changes only where the picture cuts anyway.
```

  Capture the demo densely in real time (about 10 fps of screenshots with their
  timestamps, or a screen recording), then pick the frame nearest `demoTime(t)`; a few
  stills played faster jump (r14 S used a handful of stills at 1.6x). Mark "加速" on
  screen only where the speed would mislead (a download rate, a remaining time).

## §2 Export [lab]

- Playwright: for each frame `t = frame / fps`, call `__setTime(t)`, screenshot; then
  ffmpeg to MP4. Lab round frames use 1280x720 (1080x1920 for vertical) at 30 fps and write
  the exact duration into `build/plan.md`; no codec is fixed — state
  it in the build notes.
- Wait for `document.fonts.ready` before the first capture. [C20 lists "exported before
  fonts loaded" as a common error; no shipped instrument checks it yet — look at frame 0.]
- A background render is finished only when `ffprobe` reads the expected duration (a lab
  run once ended early, r8 B2).
- Audio: a known-beat track (generated with `scripts/make_beat_track.py --bpm 120
  --bars 24 --out <wav>`, which also writes the beat-time JSON; or a real track measured
  with `scripts/beatgrid.py`) before the timeline is laid out; narration generated first
  when the film is narrated. Voice: Windows SAPI only as a stable test voice; a film a
  person will watch uses a TTS model, picked by checking the options current at the time
  (author r18: SAPI "太難聽").
- Cover (author 2026-09-29): a separately designed image, never a frame grabbed from the film.
  Only for YouTube, burn the cover into frame 0 (the platform's frame-0 thumbnail is an
  external claim, unchecked); replace frame 0's pixels only — length, frame count and sound
  unchanged. No other platform gets this.

## §3 Review loop [lab + reelmimic]

1. Whole-film sheet first: 1 fps, 6 x 5 per sheet (`scripts/sheets.py --fps 1 --cols 6 --rows 5`),
   then boundary rows (`--boundaries <segments.json>`: before / mid-transition / after).
2. Feedback as "second / where / change"; one change at a time. [C20]
3. Two severities: BLOCKER (seen once at normal size and speed: broken limb, white flash,
   clipped or wrong text, wrong number) and POLISH (needs pause or zoom). Only blockers fail
   a round. [reelmimic]
4. From round 2, first check last round's fixes (before/after frames at the same second and
   spot), then new blockers only. Items only the user can give (assets, rulings, product
   facts) are listed under "waiting for you", not as defects. At most 3 rounds, then hand
   the decision to the user. [reelmimic, 3 is its default, not validated here]
5. The reviewer is not the session that built the film. [reelmimic]
6. Comparing two versions: show them back to back with sound (one MP4, A then B, e.g. an ffmpeg concat);
   side by side only for overall style (sections are out of sync). Ask for per-section
   picks, not one winner (r10: the best sections were spread over five films).
7. Good-looking / matching is the user's call after watching; numbers never decide it.
8. Motion intent (`whole-film-rules.md` §2a): read the build against the storyboard's
   intent lines; a moving element, stock device or effect layer with no line is a POLISH
   finding (cut it or write the line), not a BLOCKER. No instrument checks this yet.

## §4 Product fidelity (T05) — author rulings 2026-09-27; checked by `scripts/fidelity.py`

1. Product screens are real captures (run the product locally with demo data; Playwright
   screenshots or frame-by-frame recording). If a redraw is unavoidable, every label on it
   is a string the product really has.
2. Operations shown are operations the product really does, captured doing them.
3. Numbers come only from the product: docs, demo data, or computed by the app and visible
   in a capture. No sourceless "80% faster".
4. Headlines state what the current version does; optional / separately installed features
   are marked as optional; planned features are left out.
5. No scope inflation: scope words (all / any / entirely / always / 全程 / 所有) only when
   the docs claim the same scope; otherwise write the exact scope.
6. Illustrations of a pain point that are not the product are marked "illustration"
   (示意); invented numbers never look like real data.
7. Pain points and emphasis come from the docs or the owner; if absent, ask the owner, or
   (unattended) write `build/questions.md` and state only what the feature does. The same
   goes when the docs contradict each other or the running product (a button, flow or
   label the docs name is not in the app): that is a question for the owner, and the film
   shows and words what the running product does, never the docs' stale version. Check
   every headline's wording against the capture before rendering. A paragraph to append
   to any product-video prompt: `ask-owner-addon.md`.
   [lab r14: the skill arm headlined a verb from the README over a GUI version that has no
   such button and wrote no questions; the arm given the add-on listed the mismatch]
8. Deliver `build/claims.json`:

```
claims.json: [{"t": 12.0, "text": "<on-screen text>", "kind": "feature|number|ui|pain|illustration",
               "source": "<file#section | capture file + action | owner answer | 'illustration'>"}]
```
