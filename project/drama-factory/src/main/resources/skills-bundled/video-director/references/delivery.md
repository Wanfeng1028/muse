# Delivery: render, encode, poster, platforms, hand-off

Remotion API truth: `~/.claude/skills/remotion-render/SKILL.md`, `transparent-videos.md`.

Contents
1. Master render
2. Encoding details
3. Poster frame
4. Platform exports
5. Hand-off package

---

## 1. Master render

`scripts/render_masters.sh` renders every composition × variant with these flags, names outputs per variant, holds a
machine-wide render lock and runs the QA scripts on each file:

```
npx remotion render <entry> <Comp> out/final/<name>-<comp>-<variant>.mp4 \
  --props='{"voice":"<variant>"}' --codec=h264 --crf=16 --audio-bitrate=320k --color-space=bt709 --log=error
```

- CRF 16 for upload masters (platforms re-compress, so give them headroom). Remotion's default is 18; drafts 28.
- Frames: jpeg q95 by default (`remotion.config.ts`). Use `--image-format=png` for heavy blur stacks, transparency, or to
  stop banding on gradients.
- fps 30 by default; 60 only for heavy fast motion.
- WebGL, light leaks or 3D: `Config.setChromiumOpenGlRenderer("angle")` (headless WebGL otherwise renders black).
- Remotion parallelises internally (`--concurrency`); never run two renders at once.
- Partial renders for review: `--frames=a-b`.
- Chromium missing in a sandbox: `--browser-executable=<path>`; "Old Headless mode has been removed" means a
  `headless_shell` binary is needed.
- Write into a fresh directory or pass `--overwrite`; never inspect a stale file.

Transparent overlays for editors: ProRes 4444 (`--codec=prores --prores-profile=4444 --image-format=png
--pixel-format=yuva444p10le`). For browsers: VP9 WebM with `yuva420p`.

## 2. Encoding details

- Delivery pixel format yuv420p with explicit BT.709 colour. When encoding RGB frames yourself with ffmpeg:
  `-vf scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p -color_range tv -colorspace bt709
  -color_primaries bt709 -color_trc bt709`. Without it ffmpeg uses a BT.601 matrix and hues shift.
- Audio AAC 320k at 48 kHz. `-movflags +faststart` for the web; verify it on Remotion output (`qa_video.py` reports it)
  and remux with `-c copy -movflags +faststart` if missing.
- Don't mux with `-shortest` blindly: it can trim the last frames when the audio is shorter. Check the frame count.
- Loudness is measured on the encoded file (sound-design's `audio_qa.py final.mp4`); AAC can raise the true peak.
- Side-by-side or stacked QA videos for X: set `setsar=1` or the platform distorts them.

## 3. Poster frame

- WhatsApp, X, Slack and Discord use frame 0 as the thumbnail and ignore cover images.
- Design frame 0 as a poster for someone who has never heard of the product: the payoff image, a question that selects
  the right viewer, an invitation to watch. No price or feature list; its only job is the tap. Keep the centre clear for
  the play button, and make sure the vertical survives a 4:5 crop.
- In Remotion: render `<Poster />` when `frame === 0`, and register `<Still>` compositions for poster PNGs. After the
  fact: `scripts/poster_check.py in.mp4 --burn poster.png --burn-out out/final/film-poster.mp4` overlays the poster on
  frame 0 (it re-encodes the whole video once, so prefer doing it inside Remotion).
- Check it as a thumbnail: `scripts/poster_check.py` simulates ~300 px wide with a play button and a duration badge.
- The flash detector flags frame 0; that's expected.

## 4. Platform exports

`scripts/export_platforms.sh out/final/master.mp4 youtube x linkedin web gif poster` derives deliverables from the master.

| Target | Recipe (defaults) |
|---|---|
| YouTube | libx264 `-preset slow -crf 18 -profile:v high`, AAC 192k 48 kHz, faststart |
| X | crf 24, main profile, ≤ 1280×720 (or 1080×1080 / 1080×1350), AAC 128k |
| LinkedIn | crf 22, ≤ 1920×1080, AAC 192k; 4:5 preferred in feed |
| Web embed | crf 26 720p MP4 plus VP9 WebM (`-crf 30 -b:v 0`, Opus 128k) |
| GIF preview | `fps=15,scale=480:-1:flags=lanczos` with palettegen/paletteuse |

- Rasters: 16:9 1920×1080; 9:16 1080×1920; 4:5 1080×1350; 1:1 1080×1080.
- Platform duration and size caps change often; the script warns at configurable caps, but check current limits when
  delivering instead of trusting stored numbers.
- Captions for X and LinkedIn usually go in the post text; burned-in captions follow the film's caption identity.
- Accessibility: deliver an SRT or VTT next to any burned-in captions when the film will be posted on platforms that
  support them (`serializeSrt()` from `@remotion/captions`).

## 5. Hand-off package

- Masters per format and variant (16:9 plus a re-laid-out 9:16; VO and no-VO; per language), platform exports, poster
  PNGs, WAV stems, SRT/VTT, README.
- Copy finals where the user wants them (for example a Desktop folder) with the variant in the filename.
- Reveal the folder (`open -R` on macOS) and give the paths.
- Write a true caption for the post: what the film says and, if asked, how it was made, without exaggeration.
- Update `CREATIVE.md`: final timing table, decision log (what changed after review and why), open issues.
- Licences and honesty notes in the README: music track and licence URL, SFX sources, generated people and images, which
  assets are real product assets.
