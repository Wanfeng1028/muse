# QA and troubleshooting

## Required repository checks

1. `npm test`
2. `npm run typecheck`
3. `npm run build`
4. `npm run verify:public`
5. `npm audit --omit=dev`

## Required artifact checks at Gate D

1. ffprobe output facts: dimensions, duration, fps, codecs, audio, size;
2. complete FFmpeg decode;
3. black-segment detection;
4. eight frames from eight distinct semantic structures;
5. 4×2 contact sheet;
6. SHA-256 for output and frames;
7. manifest read-back.
8. stable review frames sampled at 72% of each beat;
9. manual visual checklist from `visual-quality-gates.md` with no failures.

## Common failures

- **Chromium cannot decode HEVC:** create an H.264/AAC proxy with identical duration and no timeline changes.
- **Duplicate subtitles:** use `--captions burned-in` when the source already contains captions.
- **Everything looks like the same card:** inspect `data-structure-identity`; each semantic contract must use its own DOM/composition hierarchy, not just another palette.
- **Presenter is covered:** intentional full, partial or translucent coverage is allowed. Review its semantic purpose and reveal; repair only accidental occlusion, misaligned contact or broken subject mattes.
- **Side card is mostly empty:** remove fixed top-to-bottom sizing, use content-fit height, and collapse two sparse rails into one compact rail when the semantics allow it.
- **Subtitle is covered:** check the explicit brief keyword handoff and restoration. Adjust opacity/position or redraw only where needed; fixed bottom margins are not a universal stage constraint.
- **Black SVG block:** put `fill="none"` directly on open SVG elements; do not rely only on CSS.
- **Evidence claim without proof:** supply an approved source asset or downgrade to `thesis-and-proof`.
- **Motion works only during playback:** remove timers, live unseeded randomness, transitions, and runtime state; derive motion from the current frame and persisted seed.
- **Mixed looks change after reopening:** load the saved `styleMix` and each beat's `visualStyle`; do not rerun the shuffle during Gate B/C/D.
- **Random style hides meaning:** keep the semantic structure, move the effect behind content, reduce intensity, and inspect the frame again. A new look does not count as a new structure.
- **Legacy project unexpectedly changes:** leave absent style fields absent. Do not upgrade saved boards automatically. HyperFrames uses legacy style/presentation only.
- **Component preview mistaken for a finished job:** label `demo:styles` output synthetic, verify the three preview MP4s/stills/gallery, and keep the real video at its current gate.
- **Build passes but output is wrong:** inspect the actual Gate C stills and Gate D artifact. Build status is not visual proof.
