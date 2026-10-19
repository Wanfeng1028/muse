# Crop Geometry Reference

## The core idea

Source videos from screen recordings are landscape (typically 16:9 or wider).
To hit a vertical or square target, you crop a window out of the source frame.
The crop window is always `TARGET_W × TARGET_H` in source pixels, positioned
at an x,y offset that centers on the interesting content.

Target crop window size = source_height × (target_W / target_H)
  e.g. for 9:16 from a 2442×1734 source: width = 1734 × (9/16) = 975px

## Step 1 — Identify content zones

Probe a frame from the source and identify the x-ranges of the key panels:
- LEFT_X: x-offset where the left content panel starts (often 0 or small)
- RIGHT_X: x-offset where the right content panel starts
- ZOOM region: x,y,w,h of a specific UI area you want to zoom into

Example (2442×1734 source, browser left + agent chat right):
  LEFT_X = 12 (browser fills 0–997px)
  RIGHT_X = 1445 (agent chat fills 1445–2420px)
  Crop window width = 975px

## Step 2 — Choose crop technique per segment

### Hard crop (LEFT or RIGHT panel)
Simple: extract the 975×1734 window at the panel's x-offset.
```
crop=975:1734:LEFT_X:0,scale=1080:1920
crop=975:1734:RIGHT_X:0,scale=1080:1920
```

### Blurred backdrop (panel narrower than 9:16 window)
When the content panel is narrower than 975px (i.e. it won't fill the frame):
1. Split the stream into two copies
2. Blur + scale one copy to fill 1080×1920 (blurred background)
3. Scale + center the other copy on top (sharp foreground)
```
[in]split[a][b];
[a]crop=PANEL_W:SRC_H:PANEL_X:0,scale=1080:1920,boxblur=20[bg];
[b]crop=PANEL_W:SRC_H:PANEL_X:0,scale=-2:1920[fg];
[bg][fg]overlay=(1080-W)/2:0[out]
```
Use this when the content panel is a narrow sidebar or doesn't naturally fill 9:16.

### Zoom into a region
Crop a sub-region and scale it up to fill the output:
```
crop=W:H:X:Y,scale=1080:1920
```
The crop WxH must have the same aspect ratio as the target (within ±2%).
For a 9:16 target: H/W must equal 16/9 = 1.778.

Example (Cursor file tree sidebar, 9:16):
  crop=700:1244:990:60 → 1244/700 = 1.777 ≈ 9:16 ✓ → scale=1080:1920

Zoom factor = output_width / crop_width = 1080/700 = 1.54×

### Animated pan between panels
Use a crop filter with a time-varying x expression. After `setpts=PTS-STARTPTS`,
`t` is local to the segment (starts at 0).

```
# R→L: hold RIGHT for 2s, sweep 0.667s, hold LEFT
crop=CROP_W:SRC_H:if(lt(t\,2)\,RIGHT_X\,if(gt(t\,2.667)\,LEFT_X\,RIGHT_X-(RIGHT_X-LEFT_X)*((t-2)/0.667))):0

# L→R: hold LEFT for 2s, sweep 0.667s, hold RIGHT
crop=CROP_W:SRC_H:if(lt(t\,2)\,LEFT_X\,if(gt(t\,2.667)\,RIGHT_X\,LEFT_X+(RIGHT_X-LEFT_X)*((t-2)/0.667))):0
```

The 0.667s sweep is the sweet spot — fast enough to feel snappy, slow enough to
track. The `\,` escaping is required inside bash quoted strings.

## Format-specific crop window sizes

Given source height H, the crop window width for each target ratio:

| Target | Crop width formula | Example (H=1734) |
|--------|-------------------|-----------------|
| 9:16   | H × 9/16          | 975px |
| 1:1    | H × 1/1 = H       | 1734px (full height square) |
| 4:5    | H × 4/5           | 1387px |
| 16:9   | use full width     | no crop needed, just scale |

For 1:1 from a landscape source, center the crop: x = (source_W - H) / 2.

## Calculating crop offsets from a source frame

1. Screenshot or probe a frame: `ffmpeg -ss T -i video.mov -vframes 1 frame.jpg`
2. Open/view the frame and measure pixel positions of content boundaries.
3. For a two-panel layout, the split is usually visible as a clear vertical line or gutter.
4. Verify: LEFT_X + CROP_W ≤ source_W, RIGHT_X + CROP_W ≤ source_W.
