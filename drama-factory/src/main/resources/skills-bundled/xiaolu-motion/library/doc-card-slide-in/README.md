# doc-card-slide-in · 文档卡滑入 (doc-card-slide-in, 镜5)

A paper "document" card — a checklist reading 文档/工具清单 with three checked-off line items (动效库/音效库/风格包) — slides in from the upper right and settles next to the presenter.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s05`.

## How it works
The card (`doc_card()`) is drawn once as a dog-eared paper sheet with a torn top-right corner and a strip of tape, its three checklist rows each carrying a green checkmark icon. It slides in with an ease-out-back bounce, and the title word "文档" gets a yellow highlight bar that wipes in under the text in sync with the word being spoken (`ease_out_cubic` on the highlight width), plus a small pop-in scale bounce on the whole card at the same moment. It slides back out before the shot ends.

## Notes
None beyond the shared batch notes.
