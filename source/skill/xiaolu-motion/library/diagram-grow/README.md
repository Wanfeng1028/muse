# diagram-grow · 示意图生长 · Diagram Grow

A scattering diagram builds itself on screen: a sun and atmosphere shell appear, a beam of light travels to a molecule, and the impact bursts into a ring of colored scatter lines.

## Source
`scene.js:261-284` (`buildScatter()` — the diagram's static geometry) and `scene.js:562-589` (its animation), demo `kepu_demo.mp4`, t=4.9-8.6s of the finished video (card-in through beam, molecule pop-in, and burst). Depends on the shared runtime in `../_shared/kepu-scene-runtime/` (see its README).

## How it works
`buildScatter()` lays out an SVG scene local to the card: an Earth arc, a translucent atmosphere shell, a small sun, a set of "molecule" markers, and a pool of pre-allocated (initially invisible) scatter-line paths. The animation function drives all of it off `t`: a card-entry spring, then a white beam path grown with an `outCubic` ease from the sun to a fixed impact point, then each molecule scales in with an `outBack` overshoot on a staggered per-molecule delay, and finally — once the beam "hits" — a ring of scatter-line paths grows outward from the impact point with randomized angle/length/color (mostly blue, a few red/green), fading after a short hold.

## Notes
This preview runs close to the 4-second upper bound to show the full build sequence (card-in through burst) in one clip — it still trims to a small file (well under budget) at 360p, so no need for the tighter fallback crop. Presenter is on camera throughout, by design (this demo's whole format is a talking-head explainer; see `../_shared/kepu-scene-runtime/`).
