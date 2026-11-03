# Review and verification

## Order (cheap to expensive)

1. **Stills per scene** (`stills <film> --bars`): does each bar read on its own? Is the chain visible in order?
2. **Handoffs at 0.05 s** (`stills <film> 12.35 12.4 12.45 …`) around every transition, flood, iris, drag and caption change. Contact sheets every 0.5 s miss what happens between beats: chips crossing captions, rows merging into one bar, a flood cutting across text.
3. **Preview** at full speed with sound (`serve`). Nothing replaces watching it move. The user's notes land in `notes.json`.
4. **Draft** (`draft`) and its per-beat contact sheet: every tile must differ from the last.
5. **Final** (`final`): verify must pass.
6. **Blind read** (`blindpack`): the gate. See `panel.md`.

## Checklist, every round

- The chain reads in order; each scene is made from the previous one.
- Something moves on every beat; no hold over ~1 s except the final card.
- Text is never covered, crossed or clipped (descenders included); no caption lint on the render.
- No fades; no translucent layers that look like render glitches in a still.
- Pictures agree with captions (a forest of branched trees under "fewer branches" contradicts it).
- Screen/time budget matches the contract.
- Sound: cues land on their events; the drop is on the turn.

## Timings the tools assume

- `stills --bars` and the blind packet take each bar's still at 0.72 of the bar: land captions and key poses before that.
- Captions rise in 0.26 s after `tIn` and leave in 0.22 s after `tOut`: end a caption ~0.26 s before the next one starts.
- `K.label(text, t0, t1, where)`: `where` is a short location ("title card"); the blind packet shows only "caption" or "text in the scene", never your description of what happens.

## verify (what it checks)

Even dimensions · yuv420p · fast start (moov before mdat) · clean decode · frame-0 background decodes to the film's ground colour (`K.C.BG`) (the limited-range grey lift shows up here) · loudness −14 ±1 LUFS and true peak ≤ −1 dBTP · no single-frame pops (a frame whose difference from its neighbours spikes 3×). A slow push-in can trip the pop scan faintly (text antialiasing shifting): check the flagged frame before "fixing" it.

## Traps already paid for

| Trap | Fix |
|---|---|
| zsh doesn't word-split `$VAR`; `$N:layout` is a zsh modifier | use the scripts, or `${=VAR}` / `${N}` |
| zsh: a word starting with `=` (`echo ====`) is expanded; an unmatched glob aborts the command | quote it; use `find` or Python instead of globs that may not match |
| The Write tool stores typographic characters (an ellipsis, a curly apostrophe) literally, even when you typed a backslash-u escape | match the literal character when editing a file, not the escape sequence |
| `window.seek` calling itself (recursion, nothing renders) | the kit's `K.run` wires it; don't redefine `seek` |
| `const` used before its declaration in film.html | page error on render; declare shared constants first |
| A mask clipping descenders ("g", "p") | mask rect extends ~0.25 em below the baseline |
| A strip turning into text reads as a strikethrough | the strip becomes the line the text rises from, then retracts below it |
| Panels or items summing wider than their container | compute widths from the space; check the last frame before the transition |
| Duplicate objects at a scene handoff | hide the source copy at the exact frame the next scene's copy appears |
| Captions wider than the frame | the kit prints `LINT:`; shorten the words |
| notes.json edits triggering a film reload | fixed in preview.py; keep notes out of the watched set |
| `preview_start` refuses to launch servers in a scheduled/unattended session | run `studio.py serve` from the shell, then `preview_start` with `url: http://localhost:4173` |
| Odd frame sizes break libx264 | the renderer rounds to even; keep formats even |
| A downbeat two beats off | `measure` corrects it from section changes; check by ear on loose grids |
| Session scratchpads are wiped between sessions | keep packets, prompts and reviews inside the film folder |
