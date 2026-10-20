# dice-roll · 掷骰子 (dice-roll)

The leaderboard from scoring collapses into a cumulative-probability column, then a roulette-style random draw spins and locks onto a result, visualizing sampling from the output probability distribution.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s78.js`, scene `S8`, t=36.0-40.6s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The 8 leaderboard percentages from `scoring` stack into cumulative probability bands. A roulette-style pointer spins and locks at r=0.2317, which falls inside 凉's [0, 0.31) band — i.e. 凉 is the character sampled to come next.

## Notes
`s78.js` is shared with `scoring` (the previous scene in this library, S7 in the same source file). This scene's stated window runs to 40.6s but fades out under `falling-text`'s warm front near the end, and falling-text's own impact frame lands exactly at t=40.0s, so the preview is trimmed to 36.8-40.0s to end cleanly at that hand-off rather than showing the crossfade. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
