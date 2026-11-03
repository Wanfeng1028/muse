# numbering · 编号 (numbering)

Each freshly-cut token gets a rapidly rolling digit read-out that locks into a final token-ID, visualizing how a tokenizer maps text pieces to integer IDs.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s23.js`, scene `S2` (phase 2), t=10.0-12.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
Following the word-cut phase, a digit counter appears above each token and spins rapidly through random values before locking into a stable number, starting around t=10.5s and proceeding token by token. The end result is every token carrying a fixed numeric ID, mirroring a real tokenizer's vocabulary lookup.

## Notes
`s23.js` is shared by three sibling scenes in this library — `word-cut` (the previous phase of the same S2 scene), this one, and `vector-embed` (S3, right after) — so the full file is duplicated in all three `src/` folders rather than split up. The preview uses the full 10.0-12.0s window. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
