# video-director scripts

Run from the video project root. Every script has `--help`. ffmpeg and ffprobe are resolved as `$FFMPEG` / `$FFPROBE`,
then PATH (Homebrew ffmpeg has the needed tile, loudnorm, silencedetect and libvpx). Remotion calls go through `npx remotion`.

## Review

```
stills.py <composition> <out.png> <t1> [t2 ...] [--fps 30] [--scale 0.5] [--props JSON] [--entry PATH] [--columns N]
strip.sh <composition> <start_s> <end_s> <out.png> [--fps 30] [--nth 2] [--scale 0.25] [--columns 6] [--props JSON] [--entry PATH]
sheets.sh contact|phone <video.mp4> <out.png> [--rate R] [--width PX] [--grid CxR]
sheets.sh around <video.mp4> <out.png> <t_seconds> [--count 12] [--width 320] [--grid 6x2]
sheets.sh beats <video.mp4> <out.png> <bpm> <offset_s> [--every 1] [--width 270] [--grid 8x4]
```

- `stills.py` renders all frames in one batched `remotion render --frames=a,b,c` call and labels tiles; `--fps` must be the
  composition's fps (it only converts seconds to frames).
- Remotion rejects an image-sequence folder whose name contains a dot, so the scripts render into a `frames/` subfolder.
- `sheets.sh` tiles carry no burned-in timestamps (Homebrew ffmpeg lacks `drawtext`); it prints a time legend per page and
  samples on an absolute time grid (tile 0 is frame 0).

## QA

```
qa_video.py <video> [--ignore 0,A-B] [--cuts t,...] [--beats BPM:OFFSET] [--beat-tolerance 2] [--expect-duration S]
    [--fps N] [--final-hold S] [--min-freeze 1.0] [--loop] [--expect-color bt709|none] [--expect-audio] [--skip-motion]
    [--strict] [--json] [--report-dir out/review/qa]
poster_check.py [images/videos ...] [--render StillA,StillB] [--entry PATH] [--props JSON] [--duration 1:13] [--width 300]
    [--out out/review/poster-chat.png] [--burn poster.png --burn-out out/final/x-poster.mp4 --crf 16]
```

- On a finished film most pops are intentional: whitelist the poster (`--ignore 0`), hard cuts (`--cuts`) and beat pulses
  (`--beats` with that section's grid), then inspect what remains with `sheets.sh around`.
- AAC padding makes audio ~15 ms longer than video on short renders; `qa_video.py` only warns past 0.1 s.
- `--burn` re-encodes the whole video once (CRF 16) and converts the PNG with a BT.709 matrix so hues don't shift; prefer
  putting the poster on frame 0 inside Remotion.

## Masters and exports

```
render_masters.sh <comp> [comp ...] [--name COMP=BASE]... [--variant NAME[=PROPS_JSON]]... [--entry PATH] [--out-dir out/final]
    [--crf 16] [--audio-bitrate 320k] [--image-format jpeg|png] [--jpeg-quality 95] [--frames A-B]
    [--qa-args "..."] [--audio-qa-args "..."] [--no-qa] [--lock-timeout 3600]
export_platforms.sh <master.mp4> [youtube x linkedin web gif poster] [--out-dir out/deliver] [--name BASE]
    [--gif-start 0] [--gif-seconds 6] [--gif-width 480] [--poster-time 0] [--max-seconds T=N]... [--max-mb T=N]...
```

Typical master run:

```
render_masters.sh Wide Tall --name Wide=film-16x9 --name Tall=film-9x16 \
  --variant sofia='{"voice":"sofia"}' --variant catalina='{"voice":"catalina"}' \
  --qa-args "--ignore 0 --cuts 20.43 --beats 95.0119:64.033 --expect-duration 73"
```

- The render lock is `${VIDEO_DIRECTOR_LOCK:-$TMPDIR/video-director-render.lock}` (per user on macOS), with stale-pid recovery.
- Audio QA runs `$AUDIO_QA` if set, else the sibling `sound-design/scripts/audio_qa.py`, else `~/.claude/skills/sound-design/scripts/audio_qa.py`.
- Platform caps in `export_platforms.sh` are starting points; check current limits and pass `--max-seconds` / `--max-mb`.
  X exports don't use `-fs` (it truncates video); colour tags are forced with `setparams` because output flags alone don't
  stick on filtered encodes in ffmpeg 8.

## Judging with audio/video models

```
media_judge.py vo-take takes/*.mp3 [--text "..."] [--brief "female, warm"] [--accent "Colombian Spanish"]
media_judge.py pairwise A.mp3 B.mp3 [--runs 2]
media_judge.py blind-splice edited.wav control.wav [--runs 5] [--margin 0.3]
media_judge.py music-fit music/*.mp3 --brief "60 s launch film, warm, female VO on top"
media_judge.py chunks track.mp3 [--chunk 8] [--offset <first downbeat>]
media_judge.py restate out/final/film.mp4 [--height 480]
media_judge.py ask files... --prompt "..." [--blind] [--with-audio]
   shared: --model <openrouter id> --concurrency 2 --out-dir DIR --json --env-file F --dry-run
```

- Needs `OPENROUTER_API_KEY`. Video is re-encoded to 480p before upload; `restate` always strips audio.
- Limits, stated in `--help`: video judges sample ~1 fps and invent details (verify motion with strips); audio judges need a
  blind setup, an untouched control and repeated runs; absolute scores hit a ceiling (30 VO takes all scored 8 to 10), so
  prefer pairwise and blind comparisons. A model's "great" is never a pass.
