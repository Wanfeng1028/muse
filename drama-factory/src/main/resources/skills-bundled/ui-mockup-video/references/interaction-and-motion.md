# Interaction and motion

## Event model

Keep the schedule in frames at one explicit FPS. Each event should have a visible cause and result. For example, in a 12-second illustration:

| Time | Event | Visible proof |
| --- | --- | --- |
| 0–2 s | Request enters | User text appears in the input |
| 2–4 s | Submit, then response | User bubble plus streaming answer |
| 4–7 s | Draft card | Actual contents that can be reviewed |
| 7–9 s | Approval | Cursor reaches the control before it changes |
| 9–12 s | Saved result | Receipt and resulting page remain readable |

These are editable timings, not a product latency claim. Shorten idle time, not comprehension. If there is thinking/status UI, show information the app actually exposes; don't invent a hidden model thought process.

Drive text slicing, cursor position, pressed state, streaming, scroll offset, and card mounting from the same schedule. Precompute any random placement with a fixed seed. Do not use `setTimeout`, CSS transitions, or `Date.now()` to drive rendered scenes. Test frame 250 directly; it should match frame 250 after sequential playback.

## Cursor and state

Move to a real control, settle briefly, press, then reveal the result. A small click pulse is enough. Don't flash random ripples around the screen. Keep the pointer tip inside the actual button bounds and move it away from important text when it would obscure the result.

Text entry should be fast enough to hold attention but slow enough to understand. Prefer word-based streaming for a dense response. Long paragraphs rarely make good motion subjects; a short useful answer plus an artifact is easier to read.

Render author/message content before subordinate tool/status details. Blank author rows with a large invisible reserved card make a chat look broken. Mount new blocks at their event frame; compute scroll from visible content. Avoid sudden full-window jumps when a result card arrives.

## Geometry

At 1080p, use 26–36 px for the important UI text as a starting point. Recheck a 960×540 preview and a mobile feed view. Small secondary chrome can be quieter, but critical labels, code, decisions, and output need to survive downscaling.

Define rectangles for panels and controls, then derive cursor targets, clipping masks, connector ports, and highlights from those rectangles. Avoid repeated independent coordinate guesses. Draw shared connector buses once; branches meet on a consistent axis. Animate pulses using the same path geometry at uniform distance per frame. Do not offset elbows row-by-row unless the topology actually requires separate lanes.

For long labels or a new aspect ratio, relayout. A portrait variant often needs fewer simultaneous panels and stacked content. Scaling a landscape dashboard to fit a phone is usually unreadable.

## Style and loops

Choose purposeful motion: quiet settles for developer tools, springier motion if the brand calls for playful characters. Keep most movements small; animate the meaningful change. Avoid independently floating every connected card.

For an architecture loop, make all labels readable on frame 0 and limit motion to explanatory traffic. Periods must divide the total length. A one-shot UI workflow need not loop; don't call a hard reset from a saved result to an empty input seamless.
