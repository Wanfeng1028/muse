# scoring · 打分 (scoring)

A dense 46x80 grid of candidate characters resolves into a ranked leaderboard, with the top 8 candidates flying out and displaying their probability percentages.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s78.js`, scene `S7`, t=32.0-36.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The full candidate-character grid (46x80 cells covering the model's vocabulary) is shown, then the top-8 highest-scoring candidates detach from the grid and animate into a vertical leaderboard with percentage labels: 凉 31%, 爽 17%, 黄 12%, 静 8%, 落 6%, 远 4%, 金 3%, 思 2%.

## Notes
`s78.js` is shared with `dice-roll` (the next scene in this library, S8 in the same source file). The preview is trimmed to 32.5-35.5s, just inside this scene's own 32.0-36.0s window, to clear any residual flash carried over from `layered-compute`'s ending. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
