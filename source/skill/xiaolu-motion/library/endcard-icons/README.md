# endcard-icons · 片尾互动图标 (endcard-icons, 镜20)

The closing end card: the live frame shrinks down into a taped photo on the right, four interaction icons (点赞/收藏/评论/关注 — like/favorite/comment/follow) pop in one by one, and a big-head "wink" sticker card slams in at bottom-left.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s20`.

## How it works
The live frame is progressively rescaled and repositioned (interpolating scale and offset over `ease_in_out_cubic`) from full-screen down into a small taped Polaroid-style card (`live_photo_img()`) parked on the right edge. As it settles, four icon stickers — each a circular card with an icon glyph and a caption — pop in one at a time with a bouncy `ease_out_back` overshoot, timed to their own spoken word. Last, a big-head "wink" photo card (`wink_card()`) slams in at bottom-left.

## Notes
The icon-popping part of this shot (what the preview shows) is fully self-contained. The closing wink-card flourish additionally needs an external sticker asset — `STICK / 'card-wink-blue.png'` — which is **not included**; `STICK` now resolves via the `XM_STICKER_DIR` env var (see `../_shared/video20-a0-shots/src/README.md`), defaulting to `assets/stickers`. Supply your own transparent big-head cutout named `card-wink-blue.png` there to render that flourish; everything else in this shot runs without it.
