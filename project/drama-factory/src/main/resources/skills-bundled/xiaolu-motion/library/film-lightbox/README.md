# film-lightbox · 胶片灯箱 (film-lightbox, 镜15)

The presenter's live footage is treated as a single frame gate on a film strip lightbox — the camera pulls back to reveal it sitting in a rotated, film-strip-styled resting view, then pushes back in to full screen.

## Source
`../_shared/video20-a3-shots/src/shot15.py`.

## How it works
The scene is modeled as a small "world" with the presenter's live frame as a fixed gate at the origin; a virtual camera maps that world to the screen. At rest, the camera sits at a reduced scale, rotated a few degrees clockwise, framing the gate off-centre with film-strip chrome around it (a yellow gate frame, a "实拍·正在说" (live footage · currently speaking) pill, a yellow transition arrow, a green audio-wave badge, all drawn with the shared storyboard kit). On the cue word "在这个步骤" the camera pulls out from full screen to that resting framing; on "才会继续往下做" it pushes back in until the gate exactly fills the 1080x1920 screen again, indistinguishable from the untouched source frame. Outside those two camera moves, the shot is simply the presenter's frame-exact source footage.

## Notes
Word onsets are read directly off a 10ms audio energy envelope (not just Whisper's own timestamps, which the file notes run early after pauses) — see the `ONSET_SRC` table's comments for the reasoning behind each adjustment.
