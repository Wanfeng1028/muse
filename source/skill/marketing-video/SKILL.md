---
name: marketing-video
description: "Makes a finished marketing video for any brand or product (feature launch, product ad, social loop) in a precise motion-design style: one morphing UI shape, a real cursor, springs, a camera that zooms, a soundtrack cut on the beat, rendered to MP4 from code. Starts by collecting the person's own context (subject, UI screenshots, design system, inspiration video), so anyone can use it. Use for '/marketing-video', 'make me a marketing video', 'a video like this one', 'fais-moi une vidéo marketing', 'vidéo de lancement', 'vidéo pub produit'."
argument-hint: "[what the video is about]"
---

# Marketing video

The video is one HTML page in which every pixel is a pure function of time, `seek(t)`, rendered frame by frame with motion blur and a soundtrack placed to the millisecond. Everything specific to a brand comes from the intake; nothing is assumed. Talk to the person in their language. `SKILL_DIR` below is the folder containing this file.

## 0. First run: the tools

```bash
bash SKILL_DIR/scripts/check_deps.sh
```

It lists what this machine lacks (node 18+, ffmpeg, python3, numpy) with the install commands for its system. If anything is missing, tell the person in plain words what each tool is for, show the commands, and ask once whether to install them. Install only on a yes, then rerun the check. A command that needs their password or opens its own installer (Homebrew, `sudo`) is one they run in their own terminal; give it to them and wait. Ask the intake questions meanwhile: nothing else depends on the tools until step 2.

## 1. Intake: ask for everything first

Send the questions in [references/intake.md](references/intake.md) in one message. Required before anything is built:

- **the subject**: what the video says, to whom, where it will be posted;
- **an inspiration video**: the single most useful input;
- **the design system**, or explicit permission to use neutral defaults;
- **UI screenshots** whenever the video shows a product.

Every input must end up as a local file: ask for a download, or fetch it yourself when a tool allows. Everything else has a stated default. If a required item is still missing after one reminder, start nothing that depends on it; for the inspiration only, offer the engine's own style (one continuous morphing shape) and continue once the person accepts it.

Create the project, then record the answers in its `brief.md`:

```bash
bash SKILL_DIR/scripts/setup.sh ~/marketing-videos/<slug>    # template, scripts, local Playwright
cd ~/marketing-videos/<slug>                                 # every later command runs from here
```

## 2. Read the inspiration, and confirm the read

```bash
python3 inspect_inspiration.py <video>      # contact sheets, cuts, shot length, music tempo
```

Look at both sheets, then write a style read of ten lines at most: continuous morph or cuts, events per beat and how long states hold, camera moves, easing, palette, type, sound. Show it and ask what to keep. A written direction from the person (rules, a banned list, a structure) overrides the read. If they supplied music, measure it now (`python3 inspect_inspiration.py track.mp3`) and set `CONFIG.bpm` to its tempo before the grid.

## 3. The state list on the beat grid, then wait

A table with one row per beat: time, state on screen, how it moves, what the cursor does, camera. [references/craft.md](references/craft.md#the-grid) gives the rules. **Build nothing until the person approves it.** Iterating here costs a minute; after the build it costs an hour.

## 4. Build

Edit `scene.html`: `CONFIG` (tempo, bars, loop or end card, tokens, fonts), then replace the example scene. Read [references/craft.md](references/craft.md) first: it owns the engine, the motion rules and the gotchas.

- Fonts: put the brand's files in `fonts/` (download Google Fonts as woff2) and list them in `fonts.json`; `CONFIG.font` names one of those families first. `python3 build.py` inlines them.
- Logo: paste the brand's SVG verbatim. Never retype a wordmark in a font.
- Screenshots are a reference for a simplified recreation in HTML, never pasted as images.
- Real footage: `python3 frames.py --src clip.mp4 --name <who> --sheet` to pick a clean window, then extract it cropped to the frame's aspect. Footage plays silent unless its sound is mixed in step 5.

## 5. Verify, then the sound

```bash
python3 build.py && node preview.mjs     # contact sheet per format, one frame per beat, console and font errors
node checks.mjs                          # clicks inside their buttons, pointer never over read text
```

Both default to 1440x1440 and 1080x1920; pass other sizes as `1920x1080`. Read every sheet and fix whatever is off the grid, cramped, unreadable at phone size, or mid-transition when it should have landed. `checks.mjs` must pass in every format; declare each new click and each text to protect in `window.CHECKS`.

`python3 audio.py` then synthesizes a bed on the scene's tempo and places each `window.CUES` sound by its measured peak. `--music track.mp3 --offset <s>` uses the person's track; `--voice clip.mp4:at:start:dur` mixes a filmed person's voice and lowers the music under it.

## 6. Render and deliver

```bash
node render.mjs scene.built.html 1440 1440 out/<slug>-v1-1x1.mp4 audio/bed.wav
node render.mjs scene.built.html 1080 1920 out/<slug>-v1-9x16.mp4 audio/bed.wav
```

Each delivered version gets new file names, and its sources are copied to `versions/v<N>/` at delivery. Never overwrite a delivered file until the new render has finished. Copy the MP4s where the person wants them and report what changed, which checks passed, and any judgement call made on their behalf.

## 7. Iterate

Follow [craft.md#iterating](references/craft.md#iterating): change only what was named, stretch time rather than re-choreograph, rerun `preview.mjs` and `checks.mjs` after every change.

## Requirements

The folder is self-contained. The scripts need node 18+, ffmpeg and python3 with numpy (step 0 finds and installs what is missing); `setup.sh` adds Playwright's Chromium in each project. If the project lives in a repository with its own rules, follow them, and keep renders, footage, frames and `node_modules` out of version control.
