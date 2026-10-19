# Reframe to 9:16

Output is always **1080x1920**, `yuv420p`, even dimensions.

## Face-cam — fixed smart-crop (`reframe_facecam.sh`)

The window is the full source height, `9/16` as wide, centered on the face:

```
crop_w = round(height * 9 / 16)   # made even
x      = clamp( round(width * face_center_x - crop_w/2), 0, width - crop_w )
crop=crop_w:height:x:0, scale=1080:1920
```

### Setting `face_center_x` (agent, by vision — no ML)

1. Sample a representative frame from the clip's time range:
   `ffmpeg -ss <mid> -i work/source.mp4 -vframes 1 f.png`
2. Read `f.png`. Estimate the horizontal center of the face as a fraction of the
   full width (left edge = 0.0, right edge = 1.0). A face on the right third ≈ 0.66.
3. Put that in `clips.json` as `face_center_x`.

If the speaker drifts a lot across the clip, pick the position where they spend
most of the segment (this is a *fixed* crop by design — robust over pretty).

### Already-portrait / narrow sources

If `crop_w > width`, the script falls back to `scale=1080:-2` + top/bottom black
pad. Nothing is lost; you just get bars instead of a crop.

## Screen / gameplay — blurred pad (`reframe_gameplay.sh`)

Nothing is cropped off the content. The 16:9 frame is scaled to width 1080 and
centered; a blurred, scaled-to-cover copy fills the top/bottom:

```
[bg]=scale cover 1080x1920 -> crop 1080x1920 -> gblur sigma=24
[fg]=scale to width 1080
overlay fg centered on bg
```

Tune `sigma` (blur strength) in the script if the bars feel too busy or too flat.
