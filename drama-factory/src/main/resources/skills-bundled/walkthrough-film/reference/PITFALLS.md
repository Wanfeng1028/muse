# Pitfalls

Each of these cost at least one render cycle or one review round. Read before the first full render
of a new film, and again before any round that renames, deletes or re-orders a scene.

## Scene indices, renders and the mix

1. **Scene indices are position-based, so deleting a scene shifts every `NN_` file after it.**
   The render filenames are `NN_<id>.mp4` where `NN` is the scene's index in `timing.json`. Remove the
   opening scene and what was `08_products` becomes `07_products`. Before re-rendering after any
   structural change: regenerate `timing.json`, then delete the stale clips **by the new numbering**.

2. **A stale render makes the mix silently tempo-shift the voice.** `build_mix` measures each warped
   clip and `atempo`s that scene's VO slice to fit. If a clip is one version old, its length is wrong,
   the voice for that scene is quietly sped up or slowed to match, and nothing errors. The symptom is
   "the VO sounds slightly off in chapter 4". Always delete **both** `renders_${VER}/NN_id.mp4` and
   `warped_${VER}/NN_id.mp4` when a scene changes.

3. **An interrupted render leaves a truncated MP4 that the skip-existing check accepts.** If a session
   dies mid-render, `ffprobe` every output and delete any whose duration does not match `timing.json`
   before resuming.

4. **`ffmpeg -f concat -c copy` requires identical encode settings** on every clip. If one scene was
   re-rendered with a different CRF/preset/pix_fmt it still concatenates but can glitch at the seam.
   Keep the settings in one place and pass them via env.

5. **The concat demuxer clamps sub-40 ms `duration` entries for MJPEG inputs** (a 36 s film came out
   56 s). If you assemble from a frame list rather than a sequence, hardlink the nearest frame per tick
   into `seq/s%05d.jpg` and use `-framerate 30 -i seq/s%05d.jpg` instead.

6. **Multiple `-ss X -i file` pairs in one ffmpeg command map every output to input 0.** Extract
   verification frames one command each. And put `-ss` **after** `-i` when you need frame accuracy.

## Code traps that produce no error

7. **A `//` comment appended to a line swallows the rest of that line.** Writing
   `el.style.opacity = e;   // holds through the tagline` is fine; writing it *before* the statement on
   a minified multi-statement line deletes the statement. In a dense one-line-per-scene style this is a
   real hazard: a kicker kept lingering on screen for a whole version because a comment ate its opacity
   write. Put comments on their own line in files that pack many statements per line.

8. **`*/` inside a CSS comment closes it early and drops the next rule.** A comment describing
   `--m-*` / `--mr-*` tokens contains `*/` after `--m-`; everything from there to the real `*/` becomes
   live CSS, the parser discards it plus the following rule, and one card silently loses its skin.
   Never write a glob with a star-slash inside a CSS comment — use `--m-…` or `--m-x`.

9. **A cue lookup that returns `undefined` draws everything at t=0.** Make `C(id,key)` throw. A renamed
   or deleted cue then fails loudly in the sweep instead of stacking the whole chapter on frame 0.

10. **Modules loading before the engine.** `$`/`$$`/easing helpers usually live in the engine, which
    loads last. Any module that executes at load time must define its own helpers and must not read
    `window.__THEME` (see THEMING.md, load-order trap).

11. **Elements that start hidden must be driven every frame.** `[data-fall]` cards start `opacity:0` and
    `.num` odometers start at 0; if a scene forgets to call `fallIn()`/`odo()` the cards never appear —
    and the sweep is clean because nothing threw.

## Rendering and verification

12. **A "shots" tool that jumps from scene A to scene Z in a single page leaves A's layers visible.**
    The one-page seek path is not the same as a per-scene render, which loads fresh and warms only its
    own scene. Frames that look wrong in the shots tool but right in the render are usually this.
    When in doubt, render the 30 frames rather than trusting a seek.

13. **`backdrop-filter` rasterisation jitters between identical renders** — up to ~18/255 per channel on
    the same frame rendered twice. Do not treat a pixel diff of a glass area as a regression; compare
    structure, or drop the blur for the comparison.

14. **The render tool must pass the theme parameter.** A render script with a hard-coded URL will
    cheerfully produce the default theme's frames into `renders_light/`. Thread `THEME` through
    `render_scene_step`, `render_all`, `shots` and `play` alike.

15. **`cd ..` from a nested directory, in a tool whose working directory resets between calls, lands
    somewhere you did not expect.** Use absolute paths in every command; make scripts `cd` to their own
    root explicitly.

16. **`pkill -f "<pattern>"` self-kills the running shell** when the pattern appears in its own command
    line. The command after it silently never runs. Kill by PID, in a separate step.

17. **Background `node` stdout is often not captured.** Write progress and errors to a file with
    `fs.appendFileSync` and install `process.on('unhandledRejection'|'uncaughtException')`, or a failed
    launch looks like "exit 0, no output".

18. **A headless capture tool can hang for ~2 minutes at `browser.close()`.** Run it with
    `nohup … > log 2>&1 &` and poll the log. Keep individual shell calls short.

19. **Background browser tabs never fire rAF**, report `innerWidth/Height` as 0, and return stale frames
    mid-transition. Anything that scales a fixed stage by `innerWidth` then scales it to zero and all
    measured rects come back 0. Measure with `offsetLeft` chains, front the tab before screenshots, and
    trust `getComputedStyle` over pixels in a preview pane.

20. **`networkidle0` never fires if the page autoplays `<audio>`** under the capture flags. Gate
    `audio.play()` on `!navigator.webdriver`. A remote webfont `<link>` can also hang headless capture —
    self-host the woff2.

21. **`body { display:flex }` shrinks a fixed-width stage** (flex-shrink) so the whole internal layout
    compresses and every measured position is wrong. `#stage { flex:none }`.

22. **A static tail freezes the capture.** A screencast emits no frames without repaints, so a held final
    logo can end short. Give any held scene a tiny repaint driver (an opacity that breathes 1 → .92 → 1).
    Frame-step rendering does not have this problem — one more reason to prefer it for the last scene.

## Motion and drawing

23. **A hidden dash still draws a dot.** `stroke-dasharray:L L; stroke-dashoffset:L` with round linecaps
    renders a zero-length dash as a dot at the path end in Chrome — including inside `<mask>` paths. Set
    `visibility:hidden` until the element starts animating.

24. **Catmull-Rom control points closer than ~30 px, or crossing in x, kink.** For an arrow use
    start / one bowed midpoint / tip.

25. **Two writers on one transform in the same frame** produce a visible fight, usually at a hand-off
    (a flying mark landing in a slot). Fix by lerping the flying element's box to the *measured* box of
    the destination over the last 15 % of the move and cross-fading the two over the last 8 % — never by
    hiding one and showing the other on the same frame.

26. **Measure, don't eyeball, any connector between two elements.** Arrows and rings drawn to
    hand-guessed coordinates read as wrong the moment a font or a label length changes.

## Audio

27. **Generated SFX and music come back near-silent surprisingly often.** Always `volumedetect`;
    regenerate or gain-boost if `max_volume < -30 dB`. Boosting with an `alimiter` is usually cheaper
    than re-rolling.

28. **Generated music beds are flat** — no timed drop. Align the bed by offset so its beat grid lands on
    the moment you care about, and let SFX carry the transitions.

29. **Short music endpoints cap out** (commonly ~150 s). Crossfade-loop (`acrossfade`) to reach a longer
    target, or build the bed in sections.

30. **One-pass `loudnorm` is dynamic and pumps.** Always two-pass: measure with `print_format=json`,
    then apply with the measured values and `linear=true`.

31. **Word timestamps from a slow or expressive TTS model read far slower than the fast model** (as much
    as 1.8–2.4×) and may include emotion-tag characters in the alignment — never anchor a cue on a tag.
    Budget scene durations from the actual clip length, not from a word count.

32. **The alignments file is the only copy for takes recorded straight into the take folder.** If you
    re-record a few lines into a second folder, rebuild the merged alignments from the take folders
    rather than editing the merged file by hand.

## Process

33. **Subagent spend limits stop a builder mid-round.** When a parallel builder dies on a budget error,
    re-dispatch the same brief to another model rather than restarting the round; the brief is the
    contract, not the agent.

34. **Two agents editing one file clobber each other.** Give each owner an exclusive file set in the
    brief, and put shared files (the token sheet, the HTML script tags) under a single named owner with
    everyone else forbidden to touch them.

35. **The decision log is the deliverable that survives.** Every round's client decisions, deviations the
    builders made, and the reason a frame looks the way it does belong in one dated bullet in `SPEC.md`.
    Without it, round 8 re-litigates round 3.
