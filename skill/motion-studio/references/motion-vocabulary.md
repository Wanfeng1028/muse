# Motion vocabulary

## Rules

- **Every scene is made from the previous one.** An object of scene N becomes the frame, container or path of scene N+1 (window → vessel → laptop; a lid's closed edge → the trail; strips → document rows). No crossfades.
- **No fades.** Things enter and leave through a mask line, a flood, an iris, a push or a magic move. Banned: crossfades, blur-ins, particles, glows, 3D flips, template looks (centred text on a gradient, everything fading in).
- **Something moves on every beat.** A bar where nothing moves reads as slow. Holds over ~1 s only on the final card.
- **Text is never covered or crossed** by a moving shape, and never re-centres while it builds. Scene groups go in `K.banded()` so they stop above the caption band.
- **One signature move per film,** named in the storyboard and the ledger, and not the last film's.
- **Nothing reads as an accident in a still:** translucent overlays, half-drawn strokes and strips turning into text all do. Deliberate texture is fine (a Bayer-dither dissolve with coarse, even cells in the film's colours, done within ~0.5 s): the test is whether a still looks designed or broken.

## The kit (`kit.js`, global `K`)

| Call | Use |
|---|---|
| `K.setup({format, bpm, bars, title, palette})` | frame, beat grid `K.b(bar, beat)`, colours `K.C`, caption band `K.CAP_TOP`/`K.BAND` |
| `K.scene(name, fromBar, toBar)` | a named step of the argument chain (preview timeline, ledger) |
| `K.caption(parts, tIn, tOut, {top,size})` | whole phrase rising out of a mask line; auto-registered for the blind read |
| `K.label(text, t0, t1, where)` | register in-scene text (titles, speech, labels) for the blind read; `where` is a short location, not a description of what happens |
| `K.step(t, t0, w, z)` | closed-form spring 0→1 (z < 1 overshoots) |
| `K.kf(t, keys)` / `K.kfLog(t, keys)` | keyframes; use `kfLog` for zoom |
| `K.prog`, `K.eio`, `K.eout`, `K.ein`, `K.lerp`, `K.mix`, `K.bump`, `K.rng(seed)` | timing, easing, colour, pulses, seeded layout |
| `K.el`, `K.set`, `K.show`, `K.rect`, `K.text`, `K.group`, `K.banded` | SVG building |
| `K.cam(g, cx, cy, z)` / `K.toScreen(view, x, y)` | camera on a group; world → screen for handoffs |
| `K.clipRect(id)` / `K.clipCircle(id)` | clip paths you animate each frame (apertures, irises, mask lines) |
| `K.cursor(parent)` | a macOS arrow; squash to 0.85 for 0.15 s on a click |
| `K.run(render)` | wires `render(t)` to `window.seek`, then updates captions |

## Moves that have worked (and where)

| Move | How | Film |
|---|---|---|
| Mask-line caption | `K.caption` | all |
| Black flood → iris | a shape (a black speech bubble) grows past the corners, holds a beat, then a `clipCircle` opens the next scene from a point | Walk to Digest v2 |
| Aperture | the next scene shows through a `clipRect` that grows from an element of this one (a squeezed draft column → the woods) | v2 |
| Shape becomes geometry | a laptop lid shuts to a line; the line stretches into the trail; trees grow up from it | v3 |
| Magic move with arc | lerp a rect from source to target with `-80·sin(πp)` of lift | v2, v3 |
| Unspool | spoken strips lying on a trail fly into document rows; text rises out of each row's line | v2, v3 |
| Camera whip + shake | `kf` on cx/cy, `kfLog` on zoom, decaying sine shake | v2 |
| Tracking walk | walker fixed on screen, world scrolls by distance; parallax by layer factor | v2, v3 |
| Pressure shove | panels enter from alternating sides and squeeze the content (their widths must fit the space) | v2 |
| Strain | wobble on radius + tint toward the accent while overfull | v1, v3 |
| Cluster / discard / collide | dots move to clusters; discards fall out; a collision gets one ring | v1, v3 |
| Drag and backspace | cursor grabs a margin handle, the lifted row goes brighter and offset; a repeat turns accent and is clipped from the right | v2, v3 |
| Motion blur | `studio.py final --sub 4` (four subframes per frame) | v2, v3 |

Used once: Bayer-dither dissolve (smoke test). Not yet used (candidates for the next film's signature): goo merge (blur + alpha threshold), liquid glass (SVG displacement over a cloned scene), iris blades, a single continuous camera move through one world.

## Techniques from the source threads

- Name a reference style rather than describing one; without a reference the model falls back to centred text on a gradient.
- Real components beat invented ones (21st.dev for product UI; real screenshots for real material).
- Stills per scene before anything moves; director notes in camera words ("hard cut here", "slow this push to 0.7x").
