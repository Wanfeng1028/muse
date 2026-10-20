# Render and QA

The loop that makes a 3600-frame render affordable: render small, measure, look, then commit.
A full 1080x1920 master is ~9 minutes plus encoding; the quarter-scale pass is ~1 minute.

## 1. Proxy pass

```powershell
npx remotion render src/index.ts TianyuanOrigin qa\r01\motion `
  --sequence --scale=0.25 --image-format=png
powershell -File scripts\analyze-frames.ps1 -Dir qa\r01\motion -OutCsv qa\r01\motion.csv
```

`--sequence` writes `element-NNNN.png` into a directory (the starter's `remotion.config.ts` already
forces PNG, which is what you want at this scale too). Numeral padding changes with frame count, so
the analyzer sorts by the numeric suffix rather than the filename.

Delay this until the source is stable - the point of the proxy is to be cheap enough that you can
afford to re-run it after every change.

## 2. Read the CSV

`scripts/analyze-frames.ps1` writes `frame,luma,mean_abs_diff,changed_pixels,peak_diff`, computed in
C# over a 24bpp lock of each frame. `mean_abs_diff`, `changed_pixels` and `peak_diff` are zero on the
first row and after any gap in the sequence, so a discontinuity in the file does not silently read
as a still frame.

| column | what it is | what it catches |
|---|---|---|
| `luma` | mean Rec.601 luma of the frame, 0-255 | holes and unintended flashes |
| `mean_abs_diff` | mean per-pixel change against the previous frame | a near-zero run means the film is frozen even though the tracks say it is moving |
| `changed_pixels` | % of pixels changing by more than 3 luma | a frame that is mostly identical to the last one is a stall, not a shot |
| `peak_diff` | max single-pixel change | the strobing signature |

Two rules of thumb from tuning this film:

- A frame whose `luma` differs from both neighbours by more than a few units is a flash you probably
  did not author. Sort by `luma` descending and check the top rows are the beats you intended.
- `peak_diff` has a floor from the composite dither and the moving point sprites; it is normally
  30-250. What matters is *clustering* - bursts of high `peak_diff` across a stretch that should be
  smooth are flicker. The fix is more motion-blur taps, not a lower frame rate.

### Reference numbers from the shipped film

Useful as a sanity baseline rather than a target:

| metric | value |
|---|---|
| `luma` min | 1.12 (blackout frames 2994-3080, and the deep starfield opening) |
| `luma` max | 69.99 (frame 3217, the rebirth burst) |
| `luma` mean | 4.90 |
| `changed_pixels` at the wave | ~3.1% by frame 3599 |
| frames | exactly 3600 for 60 s at 60 fps |

## 3. Look at it

Metrics do not show composition. `scripts/contact-sheet.ps1` builds a labelled grid from a
semicolon-separated `label|path` list, which is how the sheets in `media/contact-sheets/` were made:

```powershell
powershell -File scripts\contact-sheet.ps1 -OutPath qa\r01\sheet.png -Cols 4 `
  -Items "f0|qa\r01\motion\element-0000.png;f470|qa\r01\motion\element-0470.png" -TileWidth 520
```

Sheet the beats that carry the film - each act's settled frame, the moment just before and after a
deliberate discontinuity, and the last frame. Do not sheet every 100 frames; the sheet stops being
legible exactly when you need it most.

## 4. Master export

```powershell
npx remotion render src/index.ts TianyuanOrigin output.mp4 `
  --codec=h264 --crf=16 --pixel-format=yuv420p
```

Reference result for 1080x1920 / 60 fps / 3600 frames:

| field | value |
|---|---|
| codec / profile | h264 / High (profile 100) |
| pixel format | yuv420p |
| bitrate | ~28.2 Mbps |
| size | ~211 MB (221.6 MB decimal in the CLI summary) |
| duration | 60.000 s, 3600 frames, single video stream, no audio |

CRF 16 is deliberately generous. The composite dither described in `particle-pipeline.md` puts noise
on every frame, so the encoder has no easy work to do; a CRF 20 master saves ~35% and starts to show
banding in the blackout ramp on a good display. If you need a smaller file, downscale before you
raise CRF.

## 5. Verify the master against the proxy

```powershell
powershell -File scripts\verify-export-vs-qa.ps1 -Movie output.mp4 `
  -ReferenceCsv qa\r01\motion.csv -Width 270 -Height 480
```

This decodes the finished MP4 back down to the proxy size, recomputes per-frame luma, and diffs the
two curves. It answers the one question a render log cannot: *is the file I am about to ship the cut
I approved?*

Thresholds, from the reference run:

| result | meaning |
|---|---|
| mean abs delta ~0.9 / 255, max ~1.3 / 255, correlation > 0.9995 | pass - points rasterise at different pixel sizes at different scales |
| a constant offset across the whole film | normal, for the same reason |
| correlation below ~0.999 | stop - the master is not the approved cut |
| identical to the last decimal | suspicious - check you are not diffing a file against itself |

The reference run: mean 0.9287, max 1.2560 at frame 3217, correlation 0.999954, and the brightest
frame is 3217 in both curves. Note that "darkest frame" is *not* a usable comparison - the proxy and
the master sit on different absolute floors (1.12 vs 0.17 luma at the blackout), which is exactly why
the check uses correlation rather than extrema.

## Cutting a web-playable preview

GitHub rejects files over 100 MB, so ship a preview in the repo and publish the master as a release
asset:

```powershell
$ff = "node_modules\@remotion\compositor-win32-x64-msvc\ffmpeg.exe"
& $ff -y -i output.mp4 -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p `
      -movflags +faststart preview.mp4
```

`+faststart` puts the moov atom first so the file starts playing before it is fully downloaded. Test
the actual size rather than assuming - CRF 27 of this footage lands well under the limit, but the
noise floor makes it less predictable than a normal film.

## Environment notes

- **Sandboxed shells fail to render.** Remotion spawns its own bundled Chrome, and a sandbox that
  blocks process creation returns `spawn EPERM` with no other diagnostic. Run renders with elevated
  execution; the failure is the sandbox, not the project.
- **Use the ffmpeg that ships with the CLI** at
  `node_modules\@remotion\compositor-<platform>-<arch>\ffmpeg.exe`. There is no need for a system
  install, but that build is deliberately trimmed: it has `libx264`/`libx265`/`libaom` and image2 in
  and out, no `rawvideo` muxer, and no default encoder for the `null` muxer. Decode-to-nowhere needs
  an explicit `-c:v`, e.g. `-an -vf scale=64:64 -c:v libx264 -f mpegts -y NUL`.
- **Piping render output through a formatter hides progress.** `... | Out-String` buffers the whole
  run, so a nine-minute render shows nothing until it finishes. Either let it stream, or watch the
  frame directory count instead - Remotion renders all frames before encoding, so the sequence
  directory is an accurate progress bar.
- Concurrency defaults to half the logical cores (8x on an 18-core box). Raising it past that buys
  little on a WebGL-bound render and costs memory.
