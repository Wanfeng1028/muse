# Render Recipes

These recipes capture reusable patterns from the project. They are implementation hints, not the only correct way to render.

## Vertical Gameplay Layout

Use this when landscape source footage needs to remain readable in a `9:16` edit:

1. Split source into background and foreground.
2. Background: scale/crop to `1080x1920`, blur, slightly darken, increase saturation.
3. Foreground: scale to a stable width, sharpen lightly, place around the visual center/lower-center.
4. Add subtle separators only if the foreground edge needs definition.
5. Trim, force `fps=30`, and reset timestamps.

Typical FFmpeg filter shape:

```text
setpts=PTS/SPEED,split=2[bgsrc][fgsrc];
[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=26,eq=contrast=1.05:saturation=1.35:brightness=-0.035[bg];
[fgsrc]scale=FG_SCALE:-2:flags=lanczos,setsar=1,eq=contrast=1.12:saturation=1.18:brightness=0.005,unsharp=5:5:0.55:3:3:0.25[fg];
[bg][fg]overlay=(W-w)/2:FG_Y,trim=0:DURATION,fps=30,setpts=PTS-STARTPTS
```

## Full-Bleed Accent Layout

Use for lasers, crowd, festival, nature, and other accent clips:

```text
setpts=PTS/SPEED,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,eq=contrast=1.16:saturation=1.34:brightness=0.006,unsharp=5:5:0.45:3:3:0.2,trim=0:DURATION,fps=30,setpts=PTS-STARTPTS
```

Tune contrast/saturation by role. Nature usually needs less saturation than lasers.

## Audio Excerpt

Extract the chosen song window and add tiny fades:

```bash
ffmpeg -y -ss START -t DURATION -i song.mp3 \
  -af "afade=t=in:st=0:d=0.05,afade=t=out:st=OUT_START:d=0.5" \
  excerpt.wav
```

## Concatenate Segments

Write an FFmpeg concat list:

```text
file '/absolute/path/seg_000.mp4'
file '/absolute/path/seg_001.mp4'
```

Then:

```bash
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy silent.mp4
```

## Attach Audio

```bash
ffmpeg -y -i silent.mp4 -i excerpt.wav \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -preset medium -crf 18 \
  -c:a aac -b:a 192k -shortest -movflags +faststart \
  final.mp4
```

## Contact Sheet

Vertical:

```bash
ffmpeg -y -i final.mp4 -vf "fps=1/4,scale=270:480,tile=4x4" -frames:v 1 contact_sheet.jpg
```

Landscape:

```bash
ffmpeg -y -i final.mp4 -vf "fps=1/4,scale=480:270,tile=4x4" -frames:v 1 contact_sheet.jpg
```
