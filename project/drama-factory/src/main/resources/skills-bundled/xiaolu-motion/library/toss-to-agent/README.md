# toss-to-agent · 抛给Agent (toss-to-agent, 镜11)

The closed "开源工具" box from the previous shot pops out beside the presenter's face and gets tossed across the frame into a waiting "你的 Agent" chip, which flips from "接收中…" to "已就绪" (ready) with a green check.

## Source
`../_shared/video20-a1-shots/src/boxshots.py`, class `Shot11`.

## How it works
The box (reusing the same closed-box art as `paper-box-3d`) pops out to the right of the presenter's face with a bouncy overshoot and a small idle wobble, while an Agent chip slides in from the top-right edge. On cue, the box is thrown along a fixed cubic-bezier path — shrinking in scale and rotating as it flies (`box_state()`), with a fading dashed trail drawn behind it (`trail_pts()`) — landing with a final snap into the chip's round badge. The chip itself briefly bounces on landing, then again slightly later, and its status line/icon are swapped from a "receiving" chip graphic to a hand-built "已就绪" + green-check version before both leave the frame.

## Notes
The box stays clear of the presenter's face box (offset +12px) while at head height, and rises above his hair once it crosses to the left — a manual keep-out rule specific to this shot's path, not a general collision system.
