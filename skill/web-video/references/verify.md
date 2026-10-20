# Self-verify

A video is not done until you have looked at it. `scripts/verify.py RUN [--video draft.mp4|edited.mp4|final.mp4]` does the mechanical part; you do the visual part.

## Automatic checks (verify/report.md)

| Check | Hard? | Why |
|---|---|---|
| file exists, duration > 0 | yes | ffmpeg can exit 0 and leave nothing useful |
| duration within ±10% of `edl.json.predicted_duration` | yes | catches missing `fps` after concat, broken holds |
| H.264 + yuv420p | yes | Slack, GitHub, Jira, Safari play it inline |
| 30 fps | warn | — |
| audio stream present iff narration was planned | yes | — |
| length: bug-report ≤ 60 s, feature-demo 15-120 s | warn | purpose of the video |
| final.mp4 ≤ 9 MB | warn | GitHub free limit 10 MB |
| loudness −24…−12 LUFS (if audio) | warn | `ebur128` |
| no blank frames (luma σ < 2) | yes | black/white flashes, failed renders |
| no colour tint on white UI vs the raw frame | yes | ffmpeg overlay pixel-format bug |
| EDL warnings (caption may cover click) | warn | — |

Frames come from `edl.json.checkpoints`: start, each step caption (+0.35 s), each click (+0.3 s), the bug moment, the first frame after each sped-up span, the end. They are tiled into **`verify/contact.png`** with time labels.

## Your visual pass

Read `verify/contact.png`, then confirm each item of the checklist printed in `verify/report.md`:
- feature-demo: caption readable and not covering the clicked element; each `click*+0.3` frame shows the click's effect; zoom centred on the action; intro/outro spelled right; no real customer data, secrets or cookie banners.
- bug-report: the `bug` frame shows the failure inside the red box; EXPECTED/ACTUAL match the storyboard and the picture; the highlighted step matches; REC time visible; no secrets.
If a frame is ambiguous, extract a larger one: `ffmpeg -ss 7.4 -i RUN/edited.mp4 -frames:v 1 /tmp/f.png` and Read it.

## Fix loop

| Symptom | Fix |
|---|---|
| zoom or caption off by a few frames | `calibrate.py RUN --show`; `--set <s>`; re-run edl.py |
| caption covers the target | shorter caption, or a step that clicks in the other half |
| click had no visible effect | wrong selector or covered target: rehearse again, new take |
| too long | fewer steps, shorter `wait`, split into two videos |
| too fast to follow | add `wait` to the step, or narration (holds are automatic) |
| bug not visible at the box | set `bug_target`, increase that step's `wait` |

At most **3** fix passes, then report what remains. Each pass: edit → (re-take if the storyboard changed) → edl.py → verify.py → look again.

## Optional reviewer (client-facing feature-demo)

Spawn one fresh-context subagent with only `contact.png`, the storyboard and this instruction: "You are reviewing a product walkthrough for a client. List concrete problems (unreadable text, wrong order, confusing step, missing result, data that should not be shown). Do not praise." Apply what is right; mention what you rejected.

## Report to the user

Path of the draft, duration and size, the check table, what you looked at, what you could **not** check (you cannot hear audio; motion between checkpoints), wall time. Then wait for approval before the final render.
