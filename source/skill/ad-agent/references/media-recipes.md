# Media recipes (run each with `composer_exec`)

Each line below is the exact `command` for `composer_exec(project_id, command=…)`. The cwd is the project working copy, so paths are relative (`assets/`, `gen/`, `out/`). There is no network, so inputs must already be project files (use each import's returned `path` exactly; it has a hash prefix). Every command is billed: 0.1 credit per minute, at least 0.1, with the timeout held up front and the unused part refunded. Anything written is saved to the project. After a command that writes an image, `composer_view` it. A command that runs past ~50 s returns a `task_id`; poll it with `composer_task_status`. Only one command runs per project at a time.

## Inventory and probe

```bash
ls assets/ && for f in assets/*; do [ -f "$f" ] && echo "== $f" \
  && ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration -of default=nw=1 "$f" 2>/dev/null \
  && ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$f" 2>/dev/null; \
  file -b "$f" | head -c 80; echo; done; true
```

`composer_import_asset` already returns each asset's probe, and generation results carry `probe`. Use this when you need a fresh inventory (for example, after resuming a project).

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 gen/music.mp3
```

## Frames

```bash
# last frame (i2v chaining, a2v segment continuation)
ffmpeg -v error -y -sseof -0.2 -i gen/s1.mp4 -frames:v 1 gen/s1_last.png

# a speaker frame from a reference video (pick a time where the face is visible and centered)
ffmpeg -v error -y -ss 0.1 -i assets/<hash>_ref.mp4 -frames:v 1 gen/speaker_frame.png

# a frame at time t (middle of a clip, for a fidelity crop)
ffmpeg -v error -y -ss 4.0 -i gen/s1.mp4 -frames:v 1 out/check/s1_mid.png

# downscaled peek (composer_view with max_edge does this for you; use it for a saved copy)
ffmpeg -v error -y -i assets/<img> -vf scale=640:-2 out/peek_<n>.jpg
```

## Crops and keyframe prep

```bash
# full-resolution crop of a label/logo region, to compare with the same crop of the reference
ffmpeg -v error -y -i out/check/s1_mid.png -vf "crop=W:H:X:Y" out/check/s1_label.png
ffmpeg -v error -y -i assets/<hash>_packshot.png -vf "crop=W:H:X:Y" out/check/ref_label.png

# anchored push-in END frame: crop around the detail the move lands on, upscaled to the canvas (0.4 = 2.5x travel)
ffmpeg -v error -y -i gen/kf.png -vf "crop=iw*0.4:ih*0.4:iw*0.4:ih*0.4,scale=W:H:flags=lanczos" gen/kf_end.png

# pad a flat-background reference to the output aspect with its own background colour (e.g. 9:16 at 1080x1920)
ffmpeg -v error -y -i assets/<hash>_packshot.png -vf "scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=<#bg>" gen/kf1.png
```

Sample the background colour first (`python3 -c "from PIL import Image; print(Image.open('assets/<hash>_packshot.png').convert('RGB').getpixel((5,5)))"`). A textured background is an outpaint with `composer_edit_image`, not a pad.

## Contact sheets and strips

```bash
# a clip's own contact sheet (generation results already carry one at result.sheet)
ffmpeg -v error -y -i gen/shot1.mp4 -vf "fps=1,scale=480:-2,tile=4x3" -frames:v 1 gen/shot1_sheet.jpg

# every frame of a stretch of one clip (motion, morphs, lip movement)
ffmpeg -v error -y -ss 2.0 -t 0.6 -i gen/shot1.mp4 -vf "scale=320:-2,tile=6x3" -frames:v 1 out/check/shot1_strip.jpg

# the composed page: sheet at chosen times, strip of a stretch, full-res crop
python3 -m lib.compose sheet index.html --at 1,3,5 -o out/check/sheet.jpg
python3 -m lib.compose strip index.html --range 3.8:4.4 -o out/check/seam1.jpg
python3 -m lib.compose sheet index.html --at 12.5 --crop 80,1200,920,400 --width 900 -o out/check/cta.jpg
```

## Audio

```bash
# quiet sentence boundaries in a dialogue track (candidate split points for a2v segments)
ffmpeg -i assets/<hash>_dialogue.wav -af silencedetect=noise=-35dB:d=0.25 -f null - 2>&1 | grep silence_

# cut a segment at those boundaries (<=13 s each)
ffmpeg -v error -y -i assets/<hash>_dialogue.wav -ss 0.00 -to 12.40 gen/dlg_1.wav
ffmpeg -v error -y -i assets/<hash>_dialogue.wav -ss 12.40 -to 24.10 gen/dlg_2.wav

# beat map of the music bed / an SFX transient
python3 -m lib.beats gen/music.mp3 --out gen/beats.json

# provided-track preservation on a clip or the rendered video
python3 -m lib.audio_check gen/shot1.mp4 --reference assets/<hash>_dialogue.wav
python3 -m lib.compose render index.html -o out/video.mp4 && python3 -m lib.audio_check out/video.mp4 --reference assets/<hash>_dialogue.wav
```

Never retime footage or audio with ffmpeg (`setpts`, `atempo`, `asetrate`). ffmpeg is for probing, frames, crops, keyframes and cutting provided audio at sentence boundaries. Trimming happens in the page.

## Screen replace

```bash
python3 -m lib.screen_replace gen/shot.mp4 --screen assets/<app.png> [--anchor <the screenshot the keyframe used>] \
  [--screen2 assets/<next.png> --switch-at <s>] [--screen-video assets/<recording.mp4> --screen-in <s>] \
  --out gen/shot_screen.mp4 --sheet out/check/shot_screen.jpg
```

See product-fidelity.md rule 5 for how to read its sheet.
