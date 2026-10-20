# live-montage · 现场制造蒙太奇 (live-montage)

The remaining characters of the response are generated one by one, each replaying a different one of 7 rotating visual motifs drawn from the earlier scenes, closing with a red seal stamp.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s910.js`, scene `S10`, t=44.0-50.6s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The source code literally comments this section "montage": each subsequent generated character cycles through one of 7 motifs — blade cut, heat-strips, converging stars, arc fan, rushing frames, flickering grid, or probability-column with laser-lock — compressing the earlier scenes' full pipeline into a quick per-character beat. The sequence closes with a red seal stamp at approximately 47.9-48.2s.

## Notes
`s910.js` is shared with `falling-text` (the previous scene in this library, S9 in the same source file). The preview is trimmed to 46.5-49.5s to capture a couple of motif beats plus the closing seal stamp, comfortably inside this scene's own 44.0-50.6s window. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
