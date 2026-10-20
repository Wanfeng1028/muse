# ticket-stamp · 票根盖章 (ticket-stamp, 镜4)

A paper ticket stub drops in above the presenter's head and two ink stamps — "免费" (free) and "开源" (open source) — thump down onto it one after another.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s04`.

## How it works
A perforated ticket-stub graphic (`ticket_stub()`, drawn with a dashed tear-line and "OPEN SOURCE" print) falls in from above with an ease-out-back bounce. Each stamp (`ink_stamp()`) is rendered once per text/colour combination with per-pixel random alpha dropout so the ink reads as slightly worn rather than a flat vector fill, then slams onto the ticket in sync with its word, rotated a few degrees off-axis like a real rubber stamp. The whole group lifts up and out of frame before the cut.

## Notes
None beyond the shared batch notes.
