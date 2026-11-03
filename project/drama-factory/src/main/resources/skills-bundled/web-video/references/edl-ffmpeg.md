# EDL and ffmpeg

`scripts/edl.py RUN --render draft|final|none` turns `events.json` into `edl.json` + `filter.txt` and renders with one ffmpeg call that reads the graph from a file (`-/filter_complex filter.txt` on ffmpeg ≥ 7, `-filter_complex_script` before) (cwd = run folder, all paths relative).

## How the EDL is built

1. **Raw time** of each event = `t + video_offset` (the only place the offset is applied).
2. **Range:** from the first visible step − 0.5 s (never before the flash or the end of a leading hidden step) to the last event + 1.5 s (bug-report: bug + 3 s).
3. **Keep windows (1x):** click −0.6/+1.2 s, select −0.5/+1.2, hover −0.4/+0.8, typing from its start −0.5 to end +0.8, expect −0.3/+1.5, visible step start −0.1/+0.9, scroll −0.2/+0.8, press −0.3/+0.9; bug-report also errors −0.3/+1.0 and bug −1.0/+3.0.
4. **Hidden steps** are cut. Everything else is **idle**: speed 6x (bug-report 8x), raised further so no idle gap lasts more than 0.6 s. Idle gaps under 0.25 s stay at 1x.
5. All boundaries snap to the 30 fps grid; trims use frame indices (`trim=start_frame:end_frame`) after `fps=30` on the source.
6. **Holds** (frozen frame via `loop`): the bug moment 2 s (bug-report); any step shorter than its reading time (0.3 s/word, min 1.2 s) or its narration clip + 0.35 s. Holds under 0.2 s are skipped (they look like stutter).
7. `newt(raw)` maps every overlay time onto the edited timeline; `rawt()` is its inverse (used by verify).

Constants live at the top of `scripts/edl.py` (`WIN`, `IDLE_SPEED`, `MAX_IDLE_OUT`, `TAIL`, `BUG_FREEZE`, `MIN_HOLD`, `INTRO`, `OUTRO`). Change them there, not in prose.

## Graph shape

```
[0:v] fps=30, setpts, format=yuv420p (+ REC timestamp in bug-report) → split
  → per segment: trim(frames) + setpts/(speed)   or   trim(1 frame) + loop (hold)
  → concat, fps=30                          ← fps after concat, or speed-ups do not shorten the clip
  → zoompan on a 2x upscale (feature-demo)  ← supersampling avoids integer-pixel jitter
  → captions (feature-demo) | pad + bug panel + red box (bug-report) → fade in
  → [intro][body][outro] concat (feature-demo) → (draft: scale 480p) → format=yuv420p
narration: each clip → aresample 48k stereo → 30 ms fades → adelay → amix normalize=0 → apad/atrim
```

`edl.json` holds `segments`, `captions`, `zooms`, `errors`, `bug`, `clicks`, `warnings`, `predicted_duration`, `checkpoints` (frames verify.py extracts).

## Render settings

| | draft.mp4 | edited.mp4 |
|---|---|---|
| size | 480p | viewport (bug-report + 440 px panel) |
| x264 | veryfast, CRF 30 | medium, CRF 20 |
| zoom supersample | 1x | 2x |

Then `export.py` makes `final.mp4` (CRF 26 or size-targeted 2-pass). Render takes seconds for a 1-minute clip.

## Edit-only (existing recording, no event log)

```bash
$PY $WV/scripts/edl.py --edit-only screen.mov --out video-out/<slug>/v1 --mode feature-demo --render draft
```
Idle = picture frozen (`freezedetect=n=-60dB:d=0.8`) and, if there is audio, also silent (`silencedetect=n=-35dB:d=0.8`). Trims frozen head/tail, speeds idle spans, keeps audio in sync (`atempo` on sped spans). No captions or zoom. A spinner or blinking caret counts as motion at −60 dB; raise to `n=-50dB` in the code if nothing is detected.

## Hand recipes (when you must deviate)

```bash
# exact cut by re-encode (copy cuts snap to keyframes)
ffmpeg -ss 2.0 -to 9.5 -i in.mp4 -c:v libx264 -crf 20 -pix_fmt yuv420p -an out.mp4
# whole clip 4x
ffmpeg -i in.mp4 -vf "setpts=PTS/4,fps=30" -an out.mp4
# burn an SRT (cd into its folder: colons and spaces in filter paths need escaping)
ffmpeg -i in.mp4 -vf "subtitles=captions.srt:force_style='Fontsize=24,BorderStyle=3'" out.mp4
# soft subtitle track instead
ffmpeg -i in.mp4 -i captions.srt -c copy -c:s mov_text out.mp4
# hold frame at 4.0 s for 2 s inside one graph
ffmpeg -i in.mp4 -filter_complex "[0:v]fps=30,split[a][b];[a]trim=0:4,setpts=PTS-STARTPTS[x];[b]trim=start_frame=120:end_frame=121,setpts=PTS-STARTPTS,loop=loop=59:size=1:start=0,setpts=N/(30*TB)[y];[x][y]concat=n=2:v=1:a=0[o]" -map "[o]" out.mp4
# crossfade two clips (both need the same timebase)
[a]settb=AVTB,fps=30[a1];[b]settb=AVTB,fps=30[b1];[a1][b1]xfade=transition=fade:duration=0.4:offset=4.6
```
Always write filters to a file and pass `-/filter_complex file` (ffmpeg ≥ 7; `-filter_complex_script` on 6.x, removed in 8); build argv lists, never shell strings from user input.
