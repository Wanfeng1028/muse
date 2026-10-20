---
name: whiteboard-video-edit
description: Edit a filmed 4K whiteboard talk (one presenter, a board behind them, a locked camera) into a finished long form video plus a vertical reel. Rough cut from a word level transcript (fillers, dead air, false starts and retakes out), eased zooms onto each board item as the presenter names or writes it, a color grade measured from the take, a sub pixel 4K to 1080p render, audio mastered to -14 LUFS, then a 1080x1920 reel in 3 headline versions with word timed captions and 3 covers, with a gate at every step. Use when the user hands over a recorded whiteboard take and says "edit the video", "edit my whiteboard video", "cut a reel from this", "make the reel", "3 headlines for the reel", "the reel covers", or wants a video edited with this skill re-cut, re-rendered or fixed. Not for screen recordings, phone selfie clips, multi camera shoots, motion graphics, thumbnails or uploading.
---

Turns one 4K whiteboard take into a long form master with no captions, and a vertical reel in three headline versions with covers, all in one color grade. The work is done by the scripts in `scripts/`, in a fixed order, with a gate after every step. You (Claude) make the judgement calls: what to cut, where the board items are, when to zoom, which 30 seconds make the reel, and the three headlines.

## When to use

- The user sends or names a filmed whiteboard take and wants it edited, or wants a reel cut from it.
- A reel made here needs new headlines, captions or covers.
- A video edited here needs a re-cut, a re-render or a failed gate fixed.

Skip for: screen recordings, phone clips, footage with a moving camera, anything that needs motion graphics, and publishing.

## What the footage must be

- One presenter, one whiteboard, a camera on a tripod that does not move during the take.
- 3840x2160 at 23.976 fps (24000/1001). The scripts assume both. Convert other footage first, or stop and tell the user.
- One audio track with the presenter's voice (or a polished WAV of the same take, see step 2).

## Requirements

- macOS (the pose tracking, the OCR read back and the cover expression gate use Apple Vision).
- `ffmpeg` and `ffprobe` (version 8 was used), `node` (18 or newer), `python3` with Pillow, the Xcode command line tools (`swiftc`), `curl`.
- `ELEVENLABS_API_KEY` in the environment: the transcripts come from ElevenLabs Scribe. The key is read from the environment only.
- Optional: `whisper-cli` (whisper.cpp) with a large-v3 model, as a tie breaker for a disputed caption word.
- Tested with ffmpeg 8.0, Node 22 and Python 3.12 on macOS 26 (Apple Silicon). Other versions are untested: if a step fails on one, say so instead of working around it silently.

## Setup (once per machine)

```bash
~/.claude/skills/whiteboard-video-edit/scripts/setup.sh
```

It checks the tools, compiles the three Apple Vision helpers (`pose`, `ocr`, `face-screen`) next to their sources, and reports the caption font it found. It must end with `READY`.

In the steps below:

- `S` is the scripts folder: `S=~/.claude/skills/whiteboard-video-edit/scripts` (or wherever the skill is installed).
- `py` means `python3`. If the Mac's `python3` runs under Rosetta and cannot import Pillow, use `arch -arm64 python3`.
- `E` is the work folder for this video. Ask the user where it goes, or make `<folder of the source>/edit-<name>/`. Never write next to the footage itself, and never into a downloads folder.
- `L` is a short label for the video (`talk1`). It becomes part of the file names.
- Run every command from `E`, after `mkdir -p tools audio checks captions previews covers rough-cut grade`.
- `.sh` and `.mjs` files run as written (`node` for `.mjs`).

## Rules (defaults; the user can overrule any of them)

- **The long form gets no captions and no headline.** Only the reel carries text.
- **The reel is vertical only** (1080x1920).
- **The reel look:** a colored panel with light bold caps opens the reel. It is on screen from frame 0, pops in on a spring (scale 0.80 to 1 with a small overshoot, the words fading in one after another), holds, then scales down and fades, and is gone by 3.55 s (86 frames). After it come word timed caption chips: bold caps, 1 or 2 words per chip, a silver gradient on a soft shadow, no box, centred at x 540. A headline can have two sizes (`NN:line|NN:line`, the hook phrase big), for example `68:5 CHECKS|44:BEFORE YOU BUY|44:AN AI RECEPTIONIST`. The colors, the font and the sizes are defaults in `look.json` (see "The look").
- **Every reel ships in 3 versions that differ only in the opening headline** (H1, H2, H3: three different angles, for example a number hook, a question hook, a pain or bold claim hook). Each headline is 8 words or fewer and true to what the presenter says in the reel. One cover per version. Write them to `headlines.md` with the angle and where the presenter says it.
- **Zooms are eased, never linear:** a critically damped spring with no overshoot, onto the board item as the presenter names or writes it. The framing changes at every cut, a move never runs across a cut, and the scale never passes 2.0x (1.8x is a good ceiling for the long form).
- **Audio:** the camera audio (or the polished WAV the user supplies) mastered to about -14 LUFS integrated, with the true peak at most -1.0 dBTP measured on the ENCODED file. No music unless the user asks.
- **Color: the house grade "F", measured per take, never tuned by hand.** The white board goes neutral with a hint of warmth (a* +0.5, b* +2.0), lifted or tinted blacks go to a neutral black, light contrast is pivoted on the presenter's face, color gets +8 % while skin is left alone, a soft top end keeps the board from clipping, and the face gets more light only when it is too dark (lift only). The aim is real light in a real room: no stylised look, no teal and orange, no vignette. The long form, the reel and the covers of one take share ONE grade.
- **Never drop a line the presenter said once.** Only fillers, dead air, stutters, false starts and superseded retakes go, and each dropped retake must be restated in the words that stay.

## Long form

1. **Identify the take.** Transcribe the source: `py $S/transcribe.py --edit-dir $E/rough-cut --language en --num-speakers 1 <source>`. Read the transcript and match it to what the user says the video is before naming anything.
2. **Polished audio swap (only when the user supplies a WAV):** `$S/audio_swap.sh <camera.MP4> <polished.wav> $E/master-L-polished.mov $E/sync`. It cross correlates three windows and muxes with the video stream COPIED, only when every offset and the drift are under one frame (42 ms). Exit 2 means shift the WAV and run it again. The muxed master is then the rough cut source: transcribe IT into `rough-cut/` and plan on it (planning on the camera file would silently cut the camera audio).
3. **Rough cut:** `py $S/pack_transcripts.py --edit-dir rough-cut`, then read `rough-cut/takes_packed.md` (the phrases and the retake hints). Use `py $S/rough_cut.py words rough-cut "<name>" a b` on anything doubtful. Then:
   - `py $S/rough_cut.py plan --edit-dir rough-cut --source <src> --fps 24000/1001 --keep-events [--drop "<name>:a-b:why"]`
   - `py $S/rough_cut.py render --edit-dir rough-cut --fps 24000/1001 --height 1920` (landscape footage works with this value)
   - `py $S/rough_cut.py verify --edit-dir rough-cut`

   **Fix every flagged boundary before going on:** widen the drop to a clean pause, or revert it and keep the words.
4. `py $S/segments.py rough-cut`, then `py $S/phrases.py rough-cut` (it writes `output_transcript.txt` itself; do not redirect its output onto that file). Write `rough-cut/cut-notes.md` (every judgement drop, every reverted drop, what was kept on purpose), then `py $S/cut_list.py '<title>' "rough-cut/transcripts/<name>.json" rough-cut/cut-notes.md`.
5. **Pose:** `py $S/pose_track.py .` (Apple Vision face and joints every 0.25 s).
6. **Board items:** grab the final board frame, draw a 100 px grid on it, and measure each item's rectangle in 4K source pixels into `tools/board.json`: one entry per label or drawing the presenter makes during the take, plus `board` for the whole board. Keys use letters, digits and `_` only. Draw the rectangles back on the frame and look at them. `py $S/writing.py .` lists when the presenter's wrist is at which item.

   ```json
   { "price": [1130, 510, 1590, 860], "steps": [1860, 740, 2460, 925], "board": [778, 451, 2746, 1622] }
   ```
7. **Focus events:** write `tools/focus_L.json` from `output_transcript.txt` (rough cut times). An `item` event when the presenter names or writes an item (scale 1.6 to 1.8), a `close` event (a close up on the presenter) on key lines. An item with writing in it gets its event only once it has been written.

   ```json
   [
     { "t0": 0.1, "t1": 5.4, "kind": "close", "why": "the hook" },
     { "t0": 7.3, "t1": 13.0, "kind": "item", "item": "price", "scale": 1.6, "why": "names the price question" }
   ]
   ```
8. **Plan before any render:** `py $S/plan_zooms.py . L`, then `py $S/fix_cuts.py . L`. Gates:
   - `py $S/cut_change_check.py . L > checks/cut-change.json`: N of N cuts change the framing, `fail` is empty.
   - `py $S/face_cut_audit.py . camera_L.json 16/9 lf > checks/face-audit-lf.json`: 0 half cut faces.
   - Look at `py $S/preview_sheet.py . camera_L.json zoom-plan.json /tmp/sheet.png`.
9. **Grade (automatic):** `py $S/grade.py measure . L <source>` reads 24 frames spread over the take (the board white from every flat, unclipped board cell inside `board`, the shadow cast, the black point, the skin hue and the face luma) and writes `grade/measure_L.json`. Then `py $S/grade.py lut . L` writes `grade/house_L.cube` (65^3) and `grade/params_L.json`. There is nothing to tune: if the numbers look wrong, the `board` rectangle is wrong.
10. **Render:** `py $S/make_props.py . L <source>`, then `py $S/grade.py props grade/house_L.cube props_L_abs.json` (it stamps the grade into the props; the renderer then resamples in float and grades before rounding). Then `$S/render_range.sh props_L_abs.json render/parts A B P` in chunks that each finish in under 10 minutes (about 400 frames per process). Join `render/parts/r_*.mp4` with the concat demuxer and check the frame count.
11. **Audio:** `py $S/master_audio.py rough-cut/rough_cut_master.mov audio/L_master_audio.wav`, then mux with `-c:v copy -c:a aac -b:a 320k -ar 48000 -movflags +faststart` into `L-<name>-v1.mp4`, and measure `ebur128=peak=true` ON THAT FILE.
12. **Gates on the encoded master:**
    - Color: `py $S/grade.py gates L-<name>-v1.mp4 props_L_abs.json . L --out checks/grade-gates-L.json` must exit 0. The five gates are listed under "The gates".
    - Smoothness, on one slow eased move: `node $S/measure_motion.mjs <master> f0 f1 camera_L.json 1920 1080 > checks/smoothness-f.txt`, then `py $S/smooth_table.py checks/smoothness-f.txt '<title>' > checks/smoothness.md` must exit 0.
    - Nothing lost: transcribe the master into `checks/`, then `py $S/line_check.py rough-cut/cut_words.json checks/transcripts/<master>.json` and `py $S/word_diff.py` with the same two files. Every LOW line must be number formatting or a transcription difference, never a missing line.
    - Loudness: within 1 LU of -14 LUFS, true peak at most -1.0 dBTP.
13. **Preview:** a 720p copy (`-crf 21 -maxrate 2.4M -bufsize 4.8M`) into `previews/`. Give the user the path of the master and of the preview.

## Vertical reel

1. **Pick about 30 seconds** from `output_transcript.txt` and `rough-cut/cut_words.json`: a hook in the first 2 seconds, self contained, a clean end. Clip edges go on pauses (never inside a word), ideally on rough cut segment boundaries. Write `reel/clips.json`. In a `v` list, `null` is the clip start, a number is a time in seconds on the rough cut timeline, `"him"` frames the presenter, and `"item"` frames a board item (add `"solo"` to frame the item without the presenter). Keep the first 3.6 seconds on the presenter with no big move, or the headline has no clear zone.

   ```json
   { "label": "talk1", "clips": [
     { "o_start": 0.0, "o_end": 9.45, "label": "the hook", "v": [[null, ["him", 1.15]], [8.4, ["item", "price", 1.25]]] },
     { "o_start": 9.9, "o_end": 18.3, "label": "the answer", "v": [[null, ["him", 1.2]]] }
   ] }
   ```
2. **Build:** `py $S/reel_build.py . reel/clips.json audio/L_master_audio.wav <source>` (it drops, with a note, a move that cannot land before the shot ends, and never lets two moves overlap). Then `py $S/reel_md.py`, and look at a framing sheet. Then `py $S/reel_faces.py reel/props_reel_vertical_abs.json reel` (the face on every reel frame), and `py $S/grade.py props grade/house_L.cube reel/props_reel_vertical_abs.json` (the reel takes the long form's grade; the grade runs before the overlays, so the headline and the chips keep their exact colors).
3. **Caption words:** `py $S/reel_words.py . captions/expected_words.json`, transcribe `reel/reel_audio.wav` into `captions/`, then `py $S/caption_words.py captions/expected_words.json captions/transcripts/reel_audio.json captions/words_reel.json [captions/fix_reel.json]`. Settle every disagreement between the two transcripts: listen with a `whisper-cli` large-v3 pass on a tight window when it is installed (2 of 3 wins), otherwise ask the user. `fix_reel.json` also sets display forms (`2,000`, `24/7`, `$18.75.`); an empty replacement merges a word into the one before.
4. **Headlines:** three angles, written to `headlines.md`. Build the overlays for all three in one pass: `py $S/overlay_build.py . vertical captions/words_reel.json "H1||H2||H3" captions/vertical [captions/cap_override.json]`. Each headline is `NN:line|NN:line`. It refuses a line wider than 790 px, so shrink the big line. It must print 0 overlaps for the headline and the captions against the presenter's face and the item on screen, on every frame. It also prints the brightness under each shot's chips: over about 120, look at that shot. `cap_override.json` (`{"<shot start frame>": [540, 1440]}`; the shot starts are the keys of `caption_positions` in `audit.json`) pins one shot's captions, and a pinned position is audited like any other.
5. **Render once:** `$S/render_variants.sh reel/props_reel_vertical_abs.json captions/vertical captions/render N 86 6 all` (N is `total_frames` in `reel/reel-plan.json`; 86 is `headline_frames` in `audit.json`). The frames after the headline are rendered once, the first 86 once per variant, and the parts are joined without a re-encode. Mux each with `reel/reel_audio.wav` into `<reel>-h1.mp4`, `-h2.mp4`, `-h3.mp4`.
6. **Reel gates,** on each encoded variant:
   - Color: `py $S/grade.py gates <reel>-hK.mp4 reel/props_reel_vertical_abs.json . L --overlays captions/vertical/overlays_hK.json --skip-head 86 --out checks/grade-gates-reel-hK.json` exits 0 (the overlay boxes are masked out of every measurement).
   - Identity: the decoded `framemd5` of frames 86 to the end is the same in all three, and so is the audio md5.
   - Read back: `py $S/chip_readback.py <reel>-hK.mp4 captions/vertical <work> K` exits 0. Every chip and that variant's headline are read with OCR from frames decoded fresh from the file. Futura's "AI" read as "Al" counts as a match. Any other mismatch exits 3 and is a defect, for example a chip split by a lavalier microphone: pin that shot with `cap_override.json`.
   - Safe zones: `py $S/check-reel-safe-zones.py <reel>-hK.mp4 --frames 12` exits 0.
   - Faces: `py $S/face_cut_audit.py . reel/props_reel_vertical.json 9/16 reel`. A half cut face may only fall inside an eased move, never in a hold.
   - Loudness on the encoded file: true peak at most -1.0 dBTP.
7. **Covers, one per variant:** `py $S/reel_cover.py cands . vertical captions/vertical covers 2` renders every 2nd reel frame whose face sits inside the centred 3:4 window (1080x1440 at y 240, what a profile grid shows) and clear of the headline, sharp from the 4K source and in the same grade, then runs the expression gate (`face-screen`: both eyes open, mouth closed, facing the lens). Use step `1` when nothing passes. Look at the PASS frames in `covers/cands_pass.png`, pick the strongest (the face plus the board item that sells the headline), then `py $S/reel_cover.py compose . vertical captions/vertical covers <frame> <reel> [headline_cy]` (the settled headline at full size; `headline_cy` moves it on the cover only, inside the 3:4 window). Look at `<reel>-covers-grid-check.png`. Then delete `covers/cands/` (it is large); `cands.json` and `cands_pass.png` keep the record.
8. **Hand over:** the three reels, the three covers and `headlines.md`. For a small preview use `-crf 20 -maxrate 9M -bufsize 18M`. Tell the user what each headline is and which gates ran.

## The gates

A gate that fails stops the work. Fix the cause and run it again; do not hand over a file that failed one.

| Gate | Command | Passes when |
| --- | --- | --- |
| Cut boundaries | `rough_cut.py verify` | 0 boundaries flagged |
| Framing changes at cuts | `cut_change_check.py` | N of N, `fail` empty |
| Faces at cuts | `face_cut_audit.py` | long form: 0 half cut; reel: only inside an eased move |
| Frame count | `ffprobe -count_frames` | equals the plan |
| Loudness | `ebur128=peak=true` on the encoded file | long form -14 LUFS plus or minus 1; true peak at most -1.0 dBTP |
| Smoothness | `measure_motion.mjs`, `smooth_table.py` | exit 0 |
| Color G1, white board | `grade.py gates` | board C*ab at most 3.0 and never cool |
| Color G2, skin hue | `grade.py gates` | 123 degrees plus or minus 8, within 3 degrees of the source frames |
| Color G3, face luma | `grade.py gates` | 70 to 190 per frame, MEAN 100 to 165 |
| Color G4, board clip | `grade.py gates` | clipped board pixels at most 0.01 % |
| Color G5, cut jump | `grade.py gates` | board patch within dE 2.0 across every cut |
| Nothing lost | `line_check.py`, `word_diff.py` | no missing line |
| Overlay overlaps | `overlay_build.py` | 0 frames over the face, the item or outside the safe box |
| Variant identity | `framemd5`, audio md5 | identical after the headline |
| Caption read back | `chip_readback.py` | exit 0 |
| Reel safe zones | `check-reel-safe-zones.py` | exit 0 |
| Cover expression | `face-screen` | PASS |

## The look

`look.json` in the skill folder holds every color, font and size of the headline panel and the caption chips, and nothing else in `scripts/` does. Change a value there and every reel, variant and cover uses it. `py $S/look.py` prints what was resolved.

- Default headline: a burgundy panel `#5E1C28` with ivory text `#F0EEE6`.
- Default captions: a silver gradient `#FAFAF8` to `#AEB0B6`, capital letters 60 px tall.
- Default font: Futura Bold, which ships with macOS. If it is missing, the first of these that exists is used instead: Avenir Next Bold, Helvetica Neue Bold, Arial Bold. Add any font you own to `font.candidates`.
- `WHITEBOARD_LOOK=/path/to/other.json` uses another look file for one run.
- The headline timing (gone by 3.55 s) and the safe box are in `overlay_build.py`, because the gates depend on them.
- The grade is not in `look.json`: its targets and gate thresholds are at the top of `grade.py`.

## Traps that already cost time

- **A browser based renderer (Remotion) is too slow for 4K camera work:** 2 to 5 fps, and it copies the multi gigabyte source per render process. The Node renderers here (`subpixel_render.mjs`, `subpixel_render_ov.mjs`: a separable Catmull-Rom filter on the Y, U and V planes at the exact fractional viewport, overlays composited in the same pass) are the rail.
- **A raw pipe into ffmpeg 8 must be tagged, or every pixel is converted again.** Both renderers pipe raw yuv420p into an encoder that carries `-colorspace bt709 -color_range tv`. With an untagged input, ffmpeg 8 inserts a scale step: luma dropped 1.75 codes on a board frame and skin hue turned about 2 degrees. The renderers tag the raw input with the matrix and the range (bit exact at crf 0). Do not add primaries or transfer tags on that input: they change the H.264 header, and a clip with a different header can no longer be stream copied onto a reel.
- **The grade makes the board brighter behind the chips, and OCR can newly misread a chip** that read fine before (a hand or a marker cap under a word, an edge in a word gap). The chips themselves are unchanged and readable. The fix is `cap_override.json` for that shot, and a small move is enough (10 px up, or 60 px sideways on the same row). `overlay_build.py` refuses a position within 14 px of the face box. Check a position cheaply first: render the chip's middle frame alone with `subpixel_render_ov.mjs` and run `ocr` on the chip box plus 20 px. The real gate is still `chip_readback.py` on the encoded reel.
- **Face luma is often bimodal** (darker turned to the board, brighter facing the lens): the face gate uses the mean, because a median lands in the gap and flips with the sampling.
- **`alimiter` needs `latency=1`,** or it delays the audio by its attack time.
- **AAC overshoots the WAV's true peak by up to 1.5 dB:** limit the WAV at -3 dBTP and measure the encoded file.
- **Files in an iCloud Drive folder can fail to read (EDEADLK):** `brctl download <dir>` first, then retry.
- **`ffmpeg -frames:v` counts OUTPUT frames.** With a `select` filter, `-frames:v <segment length>` decodes to the end of the file; pass the number of selected frames.
- **Drops at tight word gaps clip words** (gaps of 20 to 40 ms): `verify` flags them. Widen the drop to the pauses around it, or keep the words.
- **A centre caption can land on a lavalier microphone** (its light splits a chip); the OCR read back catches it.
- **Keep every command under 10 minutes** (render in bounded chunks): the Bash tool stops at 10 minutes, and a killed render leaves no result.

## Proof run

```bash
$S/selftest.sh <4k_take.MP4> <start_s> <dur_s> <scratch_dir> <board.json> <focus.json> <clips.json> "<H1||H2||H3>"
```

With absolute paths, it runs the whole rail on a slice of a take into a scratch folder, stage by stage: `slice rough pose plan grade render audio reel cover`. `STAGE=<name>` resumes from a stage and `STOP=<name>` stops after one, so each run stays under 10 minutes. The `reel` stage is the longest: it took close to 9 minutes on a busy Mac, so run it on its own (`STAGE=reel STOP=reel`), and if it still nears 10 minutes, ask the user to run that stage in their own terminal; write `clips.json` after reading the slice's `output_transcript.txt`. `CAP_OVERRIDE=<json>` pins captions. Every mechanical gate is enforced. Exit 0 means every stage that ran passed; the last line counts the stages that are green so far, and `green so far: 9 of 9 stages` means the rail works on this machine. Exit 2 names the stage that failed and its log. It is also the reference command order for a real video. It costs one or two Scribe calls.

## Limits

- macOS only, 3840x2160 at 23.976 fps only, one presenter, a camera that does not move.
- English was the only language tested (the transcription step takes `--language`).
- The skin hue gate (G2), the face luma gate (G3) and the cover expression gate were tuned on one presenter. If they fail on a take that looks right, read the numbers the gate prints, look at the frames, and tell the user before changing a threshold at the top of `grade.py` or `face-screen.swift`.
- You measure the board item rectangles by eye on a grid. A wrong rectangle gives a wrong zoom and a wrong grade measurement, so always draw them back on the frame and look.
