# Syncing music & SFX to the video

Two ways to get audio in sync, depending on whether you control the timeline:

## A. You own the timeline (normal case)
Scene `dur`s == VO clip lengths, and you know each scene's internal choreography (button
press at +Xs, dissolve at +Ys) from the engine. Place SFX/cues from those known times and
use the VO word-timestamps (`alignments.json` from `elevenlabs.py tts`) to land lifts on
the spoken word. The `<audio>` master clock keeps playback aligned.

## B. You DON'T own the timeline — the user trimmed/edited the rendered MP4
This happened in real use: the user trimmed the render and asked for music + SFX synced to
*their* cut. Your original scene times no longer apply, and **`ffmpeg select=gt(scene,...)`
finds almost nothing** because the transitions are smooth crossfades/zooms (low scene
score). Solution — measure motion directly:

```
python3 scripts/analyze_motion.py "their_video.mp4"      # -> motion.json (+ printed table)
python3 scripts/build_events.py   motion.json 151.7 ui_events.json   # -> music_accents.json, sfx_events.json
python3 scripts/build_sfx.py      music_accents.json sfx_clips accents.mp3
python3 scripts/build_sfx.py      sfx_events.json   sfx_clips sfx.mp3
# music = generative bed + accents:
ffmpeg -y -i bed.mp3 -i accents.mp3 -filter_complex \
  "[0:a]volume=1.0[b];[1:a]volume=0.95[a];[b][a]amix=inputs=2:normalize=0,alimiter=limit=0.94[o]" \
  -map "[o]" -c:a libmp3lame -q:a 2 music.mp3
```

`analyze_motion.py` uses `tblend=all_mode=difference,signalstats` → per-frame YAVG (how much
moved). Sustained bursts = zooms/crossfades/scrolls; their **start** = camera-move begins,
**peak/end** = new content lands/settles. ~0.03s resolution.

### Placing the audio
- **Music "drops in sync":** generative music (ElevenLabs `/v1/music`) can't be beat-locked
  to arbitrary timestamps, so DON'T expect the bed to hit your marks. Instead layer placed
  **riser → impact (→ sub drop)** accents on the big motion bursts, and softer impacts on
  the rest, OVER the bed. The bed supplies the groove/claps; the accents supply the synced
  drops. Lead big drops with a riser ending ~1.6s before the hit.
- **SFX:** one **whoosh** per camera-move *start*; **swishes** through long scroll bursts
  (dur > 4s). Per-interaction sounds (button/pop/ding) are content-specific → pass via
  `ui_events.json` `[[t,"clip",gain],...]`.
- **Zoom sounds — taste:** a whoosh on the zoom-*in* reads well; a dedicated **zoom-out**
  sound on every settle gets annoying — omit it (learned from user feedback). Keep the
  **button** SFX quiet/subtle.

### Always verify before delivering
- Track length == video length; all event `t` ≤ total; no event in the 0→first-motion intro.
- `ffmpeg -af volumedetect` on each track (no clipping; SFX track is mostly quiet — that's
  expected). ElevenLabs occasionally returns near-silent clips — regenerate if `max < -30 dB`.
- Confirm a few whoosh times equal `motion.json` burst starts (±0.15s).
- `/v1/music` caps ~150s — if you need longer, crossfade-loop it (`acrossfade`) to length.
