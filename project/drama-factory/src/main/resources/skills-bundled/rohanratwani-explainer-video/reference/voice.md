# Voice

Run from `videos/<slug>/`. `python` below means whichever interpreter `engine/doctor.mjs` found.

## AI voice (Kokoro: local, free, about a minute for 40 lines)
```sh
node build.mjs                                            # writes vo/lines.json (say() fixes pronunciation)
python ../../engine/tts.py vo/lines.json vo/af_heart --voice af_heart
python ../../engine/align.py vo/af_heart                  # whisper word timings -> vo/af_heart/words.json
node build.mjs --voice af_heart                           # every animation snaps to the real words
python ../../engine/mix.py beats.json vo/af_heart $(cat total.txt) vo/master-raw.wav
python ../../engine/loudnorm.py vo/master-raw.wav vo/master.m4a   # -14 LUFS, one static gain
```
Voices: `npx hyperframes tts --list`. `am_michael` and `bm_george` are good male voices,
`af_heart` a good female one.

**Diff what Kokoro said against what whisper heard** (`words.json`) before rendering. If whisper
mishears a word, a listener probably will too: reword the line, don't just fix the spelling.
Re-voice only the lines you changed: put just those ids in a small json and run `tts.py` on it
(durations merge).

## The user's own voice
```sh
node ../../engine/read-aloud.mjs .                        # read-aloud.md: one paragraph per beat
```
They read it in one take at their own pace, pause between paragraphs, and when they fumble a
line, they say the whole sentence again. They do not need to match the video's speed: the video
matches them. Then:
```sh
python ../../engine/split-take.py vo/raw/take.m4a vo/lines.json vo/me   # keeps the last try of each line
node build.mjs --voice me
python ../../engine/mix.py beats.json vo/me $(cat total.txt) vo/master-raw.wav
python ../../engine/loudnorm.py vo/master-raw.wav vo/master.m4a
```
`split-take.py` prints a WARNING for any line it matched weakly. Listen to those clips.

## Render and mux
```sh
cd edit && npx --yes hyperframes render -o ../renders/<slug>-v1.mp4 --quiet
cd .. && ffmpeg -i renders/<slug>-v1.mp4 -i vo/master.m4a -map 0:v -map 1:a -c copy -shortest renders/<slug>-v1-voiced.mp4
ffmpeg -i renders/<slug>-v1-voiced.mp4 -af ebur128 -f null -     # Integrated should read about -14 LUFS
```
`loudnorm.py` uses `linear=true` on purpose: one static gain, so word timings never shift.
