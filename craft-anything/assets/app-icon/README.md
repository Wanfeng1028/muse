# Craft Anything app icon

The **raven**: the Crafting Apps' shared icon, made by the ArtCraft team. An engraved raven head
in getartcraft.com's ink `#101014` with paper `#f2f1ee` highlights, on a rounded tile in
ArtCraft's mark blue `#4e7bfb`. It is not open source: see `LICENSE.txt`.

The interface follows getartcraft.com too (`theme.rs`): its warm near-black and paper
backgrounds and ink, its deep accent `#1659c4` (`theme::BRAND`) for filled controls so white text
on them passes WCAG AA, its bright accent `#2d81ff` for hover and its light accent `#74aaff` for
blue text on dark surfaces. Headings and text are DM Sans.

## Geometry

A 512-unit tile with 110-unit corners (the source's 21.5 %), the raven clipped to it. The macOS
icons pad the tile onto Apple's 824/1024 icon grid; every other render uses the full tile.

## Files

- `craft-anything.svg`: the master SVG (also the hicolor scalable icon), about 100 KB.
- `craft-anything-1024.png`: 1024 px render of the tile.
- `craft-anything.icns`: macOS bundle icon.
- `craft-anything.ico`: Windows icon (16, 20, 24, 32, 40, 48, 64, 128, 256).
- `hicolor/<size>/apps/ai.storyteller.craft-anything.png` (16–512) and
  `hicolor/scalable/apps/ai.storyteller.craft-anything.svg`: Linux icon theme.
- `trace.py`: traces the raven artwork (a 2000 px raster) into the SVG with vtracer.
- `packaging/icons.sh`: makes every other file above from the SVG. The app draws the SVG itself
  at the exact pixel size (title bar, welcome screen); the window icon is the 256 px PNG.

## Regenerate

```sh
# From the 2000 px raven artwork (needs numpy, Pillow and vtracer; svgo 3.3.2 shrinks the paths):
python trace.py raven.webp master.svg 1000 6 0
npx svgo@3.3.2 -p 1 master.svg -o craft-anything.svg
# Every render (needs resvg on PATH; the .icns needs macOS's iconutil):
packaging/icons.sh
```
