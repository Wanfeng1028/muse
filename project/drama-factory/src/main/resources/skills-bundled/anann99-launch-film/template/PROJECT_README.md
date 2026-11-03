# <Company> — "<Title>" · <length> launch film

<One paragraph: what the film says, for whom, the one story it follows.>

## Deliverables
- `video/out/<name>.mp4`: 1920×1080 · 30 fps · H.264 · AAC 320 kbps · −14 LUFS · ≤ −1 dBTP.
- `video/out/<name>-4k.mp4`: 3840×2160 master.
- `video/out/<name>-poster.png`.
- `video/public/audio/score.wav`: original score (48 kHz / 24-bit).

## Story
| Time | Act | Beats |
|---|---|---|
| 0–12 | Tension | … |

Product footage: <public demo / sandbox>. No customer data is used. Demo numbers appear only inside UI shots.

## Re-render
```bash
cd video && npm i
./tools/qa.sh <name>                    # 1080p + contact sheet + loudness
npm run render:4k                       # 4K master
npx remotion studio                     # live preview / scrubbing
../.venv/bin/python ../audio/compose.py # rebuild the score (then re-render)
```

## What to check before release
- [ ] **Score:** listen on speakers and on a laptop (it was verified by measurement only).
- [ ] **Proof:** customer names/numbers and logos are approved for publication.
- [ ] **Privacy:** nothing private on screen (scrub the 1 fps contact sheet `video/out/qa/<name>_sheet.jpg`).

## Swapping the music
Drop a licensed 48 kHz WAV at `video/public/audio/score.wav`, ideally at <BPM> BPM so cuts stay on the beat. Section changes are at <…> s.
