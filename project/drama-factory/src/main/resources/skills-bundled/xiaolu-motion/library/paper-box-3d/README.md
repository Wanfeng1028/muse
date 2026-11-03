# paper-box-3d · 立体纸盒 (paper-box-3d, 镜10)

A paper page slides up over the presenter's live frame twice: first the three demo clips fly in and fold into a closed kraft box, then that box pops open into a three-tray toolbox that lights up one section at a time.

## Source
`../_shared/video20-a1-shots/src/boxshots.py`, class `Shot10`.

## How it works
A dotted paper page (`L.paper_bg`) slides up to cover the presenter's live footage for two short windows. In the first, three small demo-clip thumbnails (vlog/科普/不露脸, each rendered as a mini card with a name pill) fly in from off-screen along bezier trails (dashed guide lines drawn as they travel) and drop into a kraft-paper box one at a time on a staggered beat; the box's flaps then close and a tape "clack" seals it, after which the page slides away. In the second window, the same closed box squashes and pops open (an `Obl`/`draw_poly`-based 3D box built from the storyboard's own geometry constants) into a three-compartment tray labelled 动效库/音效库/风格包, each tray's contents rising and its label switching to a highlighted marker-underline as its word is spoken, before the page slides away again.

## Notes
Box/tray geometry, colours and contents come from the storyboard's own `v2_parts.py` (verbatim `render_v2.py` parts for shot10a/shot10b), which this file imports and animates rather than re-deriving. Live footage is only ever covered for {1.33s, 2.70s} at a time.
