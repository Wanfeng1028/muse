# Style study: from `references/` to a style note

The user's `references/` folder is the standard to hit. Study it before writing a script or shot
list, and plan against what you saw, not against generic "motion graphics".

## Watch
For each clip in `references/` (mp4, mov, webm, gif):
```
mkdir -p work/<name>/ref
M sheet references/<clip> work/<name>/ref/<clip>_sheet.png --fps 4     # overview, 4 frames/s
M strip references/<clip> <t> work/<name>/ref/<clip>_<t>.png            # fast moments, frame by frame
ffprobe -v error -show_entries format=duration -of csv=p=0 references/<clip>
```
Look at every sheet. Use `strip` on the moments that move too fast to read at 4 fps (snaps,
montage bursts, transitions). If the folder is empty or missing, ask the user for 5–10 clips of
the motion they want before going further. Don't fall back to defaults silently.

## Write `work/<name>/style.md`
Short and concrete, with numbers wherever you can measure them:

- **Pace:** average shot length, fastest cuts, total length, how long text holds
- **Type:** weight, case, size relative to frame, how words arrive (line mask, pop, type-on)
- **Colour:** background vs accent, light or dark, how many colours on screen at once
- **Camera + layout:** flat or tilted UI, push-ins, crops, device frames or none, density
- **Motion moves:** the 4–6 signature moves, each named with the matching pattern in
  `motion-language.md` (or described if it's new)
- **Sound:** music-led or voice-led, where effects land, how dense
- **Avoid:** what the references never do (this is as useful as what they do)

Show the user a 3–5 line summary of the style note with the script, so they can correct the
read before the shot list.

## Rules
- References set the **grammar** (pace, type behaviour, moves). The **content** always comes from
  the user's product: their Figma frames, their `demos/` recordings, their copy.
- Never put reference footage, logos, characters, music or copy into the film.
- When references disagree, follow the ones the user named as favourites; otherwise the majority.
