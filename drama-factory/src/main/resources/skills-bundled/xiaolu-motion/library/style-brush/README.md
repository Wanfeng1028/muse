# style-brush · 风格刷 (style-brush, 镜14b)

A brush stroke wipes across the live frame, leaving a warm paper "collage" treatment behind it — complete with tape, a date card, cut-out letter stickers, and small heart/star icons.

## Source
`../_shared/video20-a2-shots/src/shot14.py`, `Shot14.frame14b()` (a module-level function monkey-patched onto the `Shot14` class at the bottom of the file, following the same pattern used by `shot14a2.py`'s `Shot14a._cell_face`).

## How it works
A `Brush` object precomputes, once, a fixed per-column "bristle" profile and a set of colour streaks from a seeded random generator, so the stroke's edge always has the same organic, hand-brushed silhouette rather than a hard wipe line. Each frame, the stroke position determines how much of the frame shows the plain live footage versus a "collage" treatment (`collage()`) — a warm, faded print rendered onto a dotted paper texture with a white photo border — with paper stickers (washi tape, a date card, individually cut-out letter tiles spelling "开源剪辑", a heart and a star icon) revealed underneath as the brush passes over them. Before/after tags ("原样" / "拼贴包装") mark which side of the stroke is which.

## Notes
`shot14.py` also contains an earlier "14a" design (`Shot14.frame14a()`, a card-table layout with the presenter behind a cutting mat) that the presenter asked to be redesigned ("像我的人头被砍掉"/felt like his head was cut off) — it was superseded by `shot14a2.py`'s `Shot14a` class. Confirmed against the source project's own `render.py`: the live render path only ever calls `Shot14.frame14b()` (this shot) for frames after the 14a/14b jump cut, and `Shot14.frame14a()` is only reachable from an unported stills-preview tool. It's dead code if you read the file, not part of any live path. This file shares the same missing-`assets/`-folder caveat as `style-quick-cut-grid` (a `style_collage.jpg` chip thumbnail) — see that entry and `../_shared/video20-a2-shots/src/README.md`.
