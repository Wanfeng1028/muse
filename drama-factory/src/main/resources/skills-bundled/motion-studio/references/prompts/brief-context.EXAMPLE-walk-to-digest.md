# Review brief: "Walk to Digest" v1 (shared context for all reviewers)

## What this is

A 38-second, 1080×1350 (4:5) motion-graphics promo for the author's published Substack article "Write More Without Spending More Time on Your Computer" (brewblocks.substack.com). Full article text: `sources/article.md`. The article's only image is his real ChatGPT voice-transcript screenshot: `sources/article-image.jpg`.

Thesis (the article's own closing rule): **"Walk to digest. Sit to shape."** The piece is about where each stage of writing happens, not about quitting screens.

v1 was built in one self-contained HTML file (`film.html`): every style is a pure function of time via `seek(t)`, frames are captured with Playwright (system Chrome) and piped to ffmpeg. Sound (`sfx.py`) is synthesized from a reused palette (`../no-single-point-of-failure/sfx_b.py`: pen scratches, paper drops, wood knocks, a bell). No music. Storyboard with scene table: `storyboard.md`.

Images attached:
- `review/final-v1-contact.png`: the final encode, one frame every 0.5 s (read left to right, top to bottom; 13 per row).
- `review/v1-final-scenes.png`: 12 full scene stills at 2.5, 7.5, 11.5, 13.8, 16.6, 18.6, 22.8, 25.8, 29.8, 31.2, 33.8 and 36.5 s.

## The author's complaint (the reason for this review)

"Why are we always using the same damn sound effects and animation effects when I've just given you so many more tools to use?" This film and the previous one (*Bring Your Own*) both reused the same synthesized sound palette and the same motion vocabulary: SVG outlines, word-by-word caption rises, spring pops, stroke draw-ons, opacity fades and lerped positions. v2 must use the wider toolbox below, audibly and visibly.

## House rules that still hold

- Visual identity: `#0b0b0b` ground, Georgia, ink `#e8e6e1`, grey `#969691`; accent is brewblocks' own `#ee7835`. Other fonts may be added if they earn it (Google Fonts are downloadable).
- His series rules: one idea per video; a blunt one-line punchline; end on an honest handoff, not a bow ("Still an experiment" is true to the article).
- Honest claims only: nothing the article doesn't say. The article is already published, so its text and the transcript screenshot are free to use.
- Something happens on every beat; no hold longer than ~1 s except the final card; text is never covered or crossed by moving shapes.
- A prior note in his files: "Use licensed recorded music or a suitable AI music service. Do not default to locally synthesized beeps."

## Toolbox (verified available on this machine today)

From four X threads (@rexan_wong, @shiri_shh, @anthonyriera, @twoclipping):

1. **rexan_wong's workflow:** 1–2 reference videos to direct from (whatships.com is reachable); a code renderer (Remotion or HyperFrames); real UI components from 21st.dev instead of invented ones; brand plus screenshots plus braindump, then **3 storyboard variants**; stills before motion; director notes in camera words ("slow every zoom to 0.7x", "hard cut here", "push in on the button").
2. **latent-spaces/brag:** a Claude Code skill producing a motion teaser *with sound design* from a repo.
3. **Rieranthony/product-film-skill** (Remotion; read its guidance at https://github.com/Rieranthony/product-film-skill): a kit with `camera.ts` (screen-studio camera keys on springs, zoom in log space), `cursor.tsx` (curved cursor glides, click squash), `move.ts` (magic moves between rects), `punchlines.tsx` (word cards with kept slots, accent words), `dither.ts` (Bayer-matrix dithered reveals and floods), closed-form retargeting springs; music workflow: `beats.py` measures the song's beat grid and bar loudness per stem, `audio-edit.py` cuts the song on bars, SFX are placed on measured transient peaks; stories land the strongest moment on the song's drop; final render at 240 fps for motion blur.
4. **twoclipping's pure-code method:** no fades, blurs or hard cuts; every scene is *made out of* the previous one: text rises out of a mask line, icons pop from zero on a spring, bars draw across, pages push, a black shape floods the frame and contracts into the next scene, iris blades close and open; camera zooms screen-studio style so each moment fills the frame; SVG `feDisplacementMap` liquid glass; goo (blur + alpha threshold); motion blur from 4 subframes per frame blended with ffmpeg `tmix` at 60 fps; banned: crossfades, blur-ins, particles, glows, 3D flips, holds over 1 s, anything that looks like a template. Sound: a *recorded* SFX for every event, never synthesized, placed on measured peaks; a real song around 120 BPM with a drop and a quiet breakdown; loudnorm to −14 LUFS.

Also verified: **Remotion 4.0.529** and **HyperFrames 0.8.81** on npm (Node 23 installed; Remotion is free for individuals); **Mixkit** free music and SFX (commercial use allowed, no attribution) downloadable with curl; **Kenney** CC0 impact/interface packs; ffmpeg (full); Python numpy/scipy/opensimplex (librosa, pymunk, rough and skia-python are installable). Pexels blocks non-browser downloads. An earlier research pass (`../no-single-point-of-failure/research/sol-2026-09-24-animation-variety.md`, `sol-2026-09-24-sound-variety.md`) ranked OpenSimplex, rough.js-style hand-drawn strokes, Pymunk physics, SciPy modal impacts, CC0 foley and librosa time-stretching.

## Constraints on your answer

- Propose only what this toolbox can build. Name the tool or technique for each change.
- Be concrete: times, scene names, what moves where, what it sounds like. No generic advice.
- You are read-only: do not edit any file. Write your answer as your final message.
