# Face bookends — a to-camera video without a green screen

Load this when the input is a to-camera video and `style` is `bookends` (the default for a video):
the opening line and the sign-off stay on camera as face shots, and everything between is animated
over the voice from the same take.

---

## Which lines stay on camera

The `script` input marks them: sections start on their own line with exactly `[FACE]` or `[VOICE]`.
The hook runs from 0 to the last word of the first `[FACE]` section, the sign-off from the first
word of the last `[FACE]` section to the end. With no script, the first sentence is the hook and the
last one the sign-off. In the shot list (Step 4), the first and last rows are face shots (*Face
hook*, *Face sign-off* in `scene-blocks.md`); a series badge goes on shot 02.

## Trim applies here too

Run `trim_take.py` (Step 2a) for bookends as for every mode: it cuts the dead air before the first
word and after the last, writes `voice.wav`, shifts the word times to 0 and records the cut in
`take.json`. `extract_face.sh` reads `take.json` and shifts its source seek, so the face shots are
cut from the trimmed edit and the lips stay in sync — after trimming, every time you handle is an
edit time. From here on, `<audio>` is `"$work"/voice.wav` and `<duration>` is the length the trim
printed, never past the recording's length.

## Extracting the face shots (Step 6)

```bash
bash SKILL_DIR/scripts/extract_face.sh <video> "$work" <vertical|landscape> <hook-in> <hook-out> <signoff-in> <signoff-out>
```

The in/out times come from the shot list, in pairs, as edit times. It writes `face/fNNNNN.jpg`,
numbered by edit frame, so frame N of the edit shows frame N of the recording. In the composition,
`faceCam(in, out)` plays a face shot; its in/out times must exactly match the `extract_face.sh`
range — never re-time a face shot alone. Face shots are full-bleed; check the stills for a crop that
cuts off the head.

---

## Failure states

| Symptom | Cause | Fix |
|---|---|---|
| Face shots look grey and washed out | HDR (HLG) phone recording, tone-mapped without metadata | record in SDR (iPhone: Settings › Camera › Formats, HDR Video off) |
| `missing frame face/…` stops the render | a `faceCam()` range is wider than the extracted one | re-run `extract_face.sh` with that shot's in/out |
| Voice and lips drift apart | `faceCam()` re-timed after extraction | restore the exact `extract_face.sh` range |
