# title-card-behind-person · 人后标题卡 · Title Card Behind Person

A title card swings in behind the presenter with a 3D spring, its headline glowing and bursting on the key character, then rotates back out.

## Source
`scene.js:166-172` (`R.cTitle` construction) and `scene.js:461-491` (its animation), demo `kepu_demo.mp4`, t=0.0-2.0s of the finished video. Depends on the shared runtime in `../_shared/kepu-scene-runtime/` (see its README — this is an HTML/SVG/DOM scene, not a canvas renderer).

## How it works
`R.cTitle` is a `cardEl()` div positioned behind the presenter layer. Its entrance animates a CSS 3D transform — `translateY` eased in by a damped `spring()`, plus `rotateY`/`rotateZ` moving from an angled resting pose — so the card swings into place as if hinged just off its left edge (`transformOrigin: '6.8% 50%'`). The small kicker label fades out first as the card later exits, while the card itself swings away on an `inCubic`-eased reverse of the same transform. The headline's key character (蓝, "blue") gets its own small spring-driven scale pulse plus a `text-shadow` glow that ramps in with an exponential decay, alongside a procedurally-drawn burst of short SVG lines radiating around it.

## Notes
Presenter is on camera throughout, by design — this demo's whole format is a talking-head explainer. The title card sits in the same "room" DOM layer as the presenter's matted video plane (see `../_shared/kepu-scene-runtime/README.md` for what compositing isn't included).
