# layered-compute · 层层计算 (layered-compute)

A tunnel of 26 WebGL-textured planes labeled L01 through L96 rushes toward the camera, visualizing the token stream passing through successive transformer layers, ending in an implosion and flash.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s56.js`, scene `S6`, t=26.0-32.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
Labeled planes are laid out in depth and fly toward the camera in sequence, each one representing a deeper layer of computation the token stream passes through. The sequence culminates in an implosion plus flash at 31.9-32.0s, marking the end of the forward pass.

## Notes
`s56.js` is shared with `attention-lines` (the previous scene in this library, S5 in the same source file). This scene's own stated window opens on the 3D hand-off from attention-lines, so the preview is trimmed to 29.0-32.0s, which skips that hand-off and keeps the climactic implosion/flash at the very end. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
