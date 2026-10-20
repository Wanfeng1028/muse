# page-turn-transition · 翻页转场 · Page Turn Transition

A page turns away around its left spine in perspective, like a physical notebook page flip, revealing the next page underneath.

## Source
`engine.py:trans_flip()`, demo `vlog_demo.mp4`, t=2.0-4.3s of the finished video. Depends on the shared runtime in `../_shared/vlog-collage-runtime/` (see its README — this is a Python/PIL/OpenCV frame compositor, not a browser renderer).

## How it works
`trans_flip(old, new, p)` warps the old page with a perspective transform (`cv2.getPerspectiveTransform` / `warpPerspective`) that rotates it around its left edge by up to 90°, with `p` (0-1 progress) driving the rotation angle. A brightness falloff shades the turning page as it foreshortens, and a soft cast shadow is painted onto the new page just ahead of the turning edge, strongest at grazing angles. Once the page has rotated past roughly 90° (`xr < 2`), the function just returns the new page outright.

## Notes
A face is visible in this preview because it plays over a real selfie-style clip — this is demo footage the presenter recorded specifically to showcase the system for this open-source project, not incidental personal exposure, but worth noting plainly since a person is on camera. `trans_flip()` is one of several page-transition functions in `engine.py` (`trans_sweep()`, `trans_tearoff()`, `trans_swipe()` are siblings, not ported as separate entries here).
