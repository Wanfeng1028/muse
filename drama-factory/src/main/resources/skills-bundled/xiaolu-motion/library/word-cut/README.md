# word-cut · 切词 (word-cut)

Raw input text gets sliced into discrete tokens by a sequence of animated blade cuts sweeping across the line, visualizing the first step of turning continuous text into separate pieces.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s23.js`, scene `S2` (phase 1), t=8.0-10.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
A sequence of blade-cut wipes fires across the text at fixed intervals (8.50/8.75/9.00/9.25/9.50/9.75s). Each cut severs the string a little further, so by the end of the two-second window the continuous input line has been carved into discrete word/character tokens, ready to be numbered in the next phase.

## Notes
`s23.js` is shared by three sibling scenes in this library — this one, `numbering` (the next phase of the same S2 scene), and `vector-embed` (S3, right after) — so the full file is duplicated in all three `src/` folders rather than split up. The preview uses the full 8.0-10.0s window since all six scheduled blade-cuts land inside it. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
