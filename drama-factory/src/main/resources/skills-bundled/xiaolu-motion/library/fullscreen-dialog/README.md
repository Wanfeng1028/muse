# fullscreen-dialog · 全屏对话框 (fullscreen-dialog, 镜13)

A full-screen chat mockup plays out a conversation with an AI agent — attachments, typed messages with pinyin candidates, typing dots, and a reply — while the presenter stays visible in a bottom-right PiP.

## Source
`../_shared/video20-a2-shots/src/shot13.py`, class `Shot13`.

## How it works
On a dotted-paper background, a chat header, message thread and composer are built from this file's own local UI primitives (`chat_bubble`, `attach_chip`, `chat_input`, `ime_bar`, `chat_header` — see Notes) and driven beat-by-beat off word timings: a "STEP 1" header lands and settles top-left, attachment chips ("口播素材 4:35"/"文案") drop into the composer, the user's message sends with both attachments, the agent "types" (animated dots) and replies, the user types a follow-up (with a live pinyin IME candidate bar) and sends it, the agent asks for confirmation, and finally a red "确认" ink stamp lands between the chat and composer as the user confirms. The presenter's live face stays visible throughout via the shared bottom-right PiP mechanism, shrinking in and growing back out over 15 frames at the shot's in/out.

## Notes
This file's docstring describes its chat pieces as "same components as storyboard shot13a/13b (render_v2 chat_bubble / attach_chip / chat_input / ime_bar / chat_header...)," which reads like a dependency on `storyboard_v2/src/render_v2.py`. On inspection this is a design-lineage note, not an import: `shot13.py` defines complete local copies of every one of those functions itself, so it has no runtime dependency on `render_v2.py`. See `../_shared/video20-a2-shots/src/README.md` for the full explanation (that file, 1372 lines, was not ported here regardless — out of scope for this pass).
