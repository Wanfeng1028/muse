# live-selfcheck-redo · 实拍自检含重做小卡 (live-selfcheck-redo, 镜16)

An automated self-check runs directly on top of the presenter's live frame: a scan line sweeps down, flags a caption sitting on his mouth, and either fixes it in place or spins up a "redo" card to regenerate it.

## Source
`../_shared/video20-a3-shots/src/shot16.py`.

## How it works
All of the UI draws straight onto the presenter's untouched, never-retimed live footage. A red scan line sweeps down the frame; when it crosses a caption sitting over the presenter's mouth, a red box and cross mark it with a "压到脸" (sitting on the face) label, then the caption slides down into a green dashed "safe band" and the box turns green with "已挪到安全区" (moved to the safe zone). Later, a sticker is shown covering a different caption ("挡住字幕"/blocking the subtitle) — this time the box flashes red and, instead of an in-place fix, a "redo" card appears beside the presenter's head: it plays a thumbnail of the offending frame, shows a spinning loop-arrow with "重新生成中…" (regenerating…) and a 0-100% progress readout, and finishes with a green "自检通过" (self-check passed) checkmark before leaving frame. This shot draws its own two caption strips directly (`sb_lib.subtitle_c`, matching A0's global caption styling exactly) rather than relying on the outer render loop's caption layer, so the hand-off between the two is invisible.

## Notes
The preview captures the self-check scan-and-fix sequence (local 10.2-13.9s). The "redo card" half of the shot is a separate beat later in the same segment (local ~16.7-18.9s) — worth a second look if you want to see that part of the mechanism, though the scan sequence is the more representative single clip.
