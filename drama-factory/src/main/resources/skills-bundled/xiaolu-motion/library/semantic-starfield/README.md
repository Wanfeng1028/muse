# semantic-starfield · 语义星空 (semantic-starfield)

The flat embedding vectors erupt into a deterministic 3D starfield where each token floats among 16 thematic clusters, visualizing how nearby points in embedding space become nearby points in a semantic "sky".

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s4.js`, scene `S4`, t=15.5-20.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The flat 2D heat-strips from `vector-embed` hand off into a 3D word cloud during the first half-second of this scene, then the camera drifts through a fixed, deterministic arrangement of word tokens grouped into 16 thematic clusters — words with related meaning end up positioned near each other in the 3D field.

## Notes
`s4.js` is not shared with any other scene in this library. The first 0.5s of the scene's stated window (15.5-16.0s) is the 2D-to-3D hand-off from `vector-embed`, so the preview is trimmed to 16.2-19.2s to open after that hand-off has settled. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
