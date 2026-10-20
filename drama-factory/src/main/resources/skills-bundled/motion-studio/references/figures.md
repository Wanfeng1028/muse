# Figures (figure.js)

Flat, rigged people drawn in SVG, posed as a pure function of t. Load after kit.js. They are ours (no licensed art), so they can be used anywhere.

```js
const you = F.figure(parent, { skin: 2, hair: "short", hairColor: 1, shirt: K.C.ACCENT, face: "right" });
K.run(t => F.place(you, 700, 900, 540, F.idle(t, 1, F.at(t, [[0, "stand"], [2.1, "phone"], [4.0, "worried"]])), { glow: 0.8 }));
```

- `F.figure(parent, opts)`: `skin` 0–4 or a colour, `hair` (`short long bun curly cap hood bald`), `hairColor` 0–4 or a colour, `shirt`, `pants`, `shoes`, `face` (`right`/`left`), `kind: "silhouette"` for a person the story must not identify (a flat grey shape with no face).
- `F.place(fig, x, groundY, height, pose, {face, prop, glow})` draws it and returns `{head, hand}` screen points for bubbles and props.
- Poses (`F.POSES`): `stand relaxed phone read worried shocked shrug point present think angry happy cheer type sit sitphone slump`. A pose is joint angles plus face settings (`brow` -1 angry … 1 worried, `mouth` -1 frown … 1 smile, `open`, `look`, `lookY`), so `F.blend(a, b, p)` mixes any two, and you can pass a literal `{rs: 80, re: 10, mouth: 0.5}`.
- `F.at(t, [[t, pose], …])` moves between poses with a small overshoot so moves land instead of sliding. `F.idle(t, seed, pose)` adds breathing, a sway and a blink every few seconds. `F.walk(phase, pose)` is a walk cycle (phase in steps; about 2.4 steps a second reads as a normal walk).
- `F.crowd(parent, n, seed)` makes n varied people for crowd shots.

Craft notes: keep the protagonist in the accent colour and everyone else in muted shirts, so the eye finds them. Change pose on the spoken word (a `stage` beat with `at`), and keep a held pose alive with `F.idle`. Use silhouettes for criminals and anonymous actors, never a face or skin colour that could read as a group of people being blamed.
