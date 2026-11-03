# Launch film starter (Remotion 4.0.530)

A minimal, pinned starter for a code-rendered 1080p60 launch film. It comes from the
`product-launch-film` skill (see that skill's SKILL.md for the method).

```bash
npm install
npm run studio            # preview: Film, FilmPicture (muted), Scene-<id>
npm run check             # typecheck + layout geometry + WCAG contrast
npm run stills            # out/stills/*.png (named review frames)
npm run audit             # out/audit/*.jpg (every 15 f + mid-animation extras)
npm run render            # out/film.mp4: PNG frames → h264 yuv420p crf 18, AAC, mastered to -16 LUFS
```

Audio (optional; the film renders silent until these exist):

```bash
python3 scripts/make-audio.py                         # original music + SFX (numpy)
python3 scripts/vo/vo.py --voice <id> --name <name> --model eleven_v4 --stitch --stt --out vo-takes/take1
                                                       # needs ELEVENLABS_API_KEY in the environment
scripts/vo/process-vo.sh vo-takes/take1               # needs a full ffmpeg
python3 scripts/vo/prosody.py vo-takes/take1 vo-takes/take2
python3 scripts/vo/use-takes.py --pick 01-s1=vo-takes/take1
```

Where things live:

| File | What |
|---|---|
| `src/palette.ts` | colour tokens + which are text/surfaces (checked by `check:contrast`) |
| `src/theme.ts` | fonts, `NO_LIGATURES`, radii, video size |
| `src/copy.ts` | every on-screen string (paste real output verbatim; note its source) |
| `src/timeline.ts` | absolute scene frames: fit them to the measured VO takes |
| `src/layout.ts` | every positioned block (checked by `check:layout`) |
| `src/scenes/` | one component per scene; beats as named constants |
| `src/Sound.tsx` | VO, ducked music, SFX cues tied to on-screen beats |
| `docs/concept.md` | fill in: tagline, storyboard with sources, narration, honesty notes |

Pins: every `remotion`/`@remotion/*` package is at exactly 4.0.530 (4.0.531's `@remotion/cli` shipped a broken
Studio render queue). Bump them all together, and only after testing `studio`, `render` and `stills`.
Fonts come from Google Fonts at render time (network needed). Node ≥ 22.18 runs the `.ts` check scripts directly.
