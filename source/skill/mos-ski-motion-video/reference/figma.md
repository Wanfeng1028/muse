# From a Figma link to animated layers

The user often hands over a Figma design link. Goal: real, crisp product UI as layers you can
animate, never redrawn from imagination.

## With the Figma MCP (preferred)
Load the Figma skill first if one is listed (`figma:figma-use` or similar), and follow its rules.
1. `get_metadata` on the file/node from the link → list the frames (screens) and their main
   children (header, cards, buttons, inputs). Write `work/<name>/figma.md`: every frame, size,
   and the layers you plan to animate separately.
2. `get_screenshot` of each frame you'll use, for reference and contact sheets
3. `get_variable_defs` / `get_design_context` → brand colours, fonts, radii, spacing. Use these
   exact values in the motion code.
4. Export the **full frames at 2×** (`download_assets` with `defaultScale: 2`, or File → Export
   PNG @2x) into `studio/public/<name>/figma/`, plus SVG for the logo and icons. Note each PNG's
   pixel size: `Crop` needs `srcW`/`srcH`.
5. Animate the real screens with `figmaKit.tsx`, don't rebuild them:
   - `Crop` shows one card or region of a screen (box in 2× source px) anywhere on the canvas;
     the camera pushes, slides and scales the crop
   - `Field` types live text into a real input, covering its placeholder (same font and size)
   - `Option` redraws a real option exactly over itself so it can switch selected state
   - `Press` + `Cursor` give clicks a cause on real buttons
   Find boxes by opening the PNG and reading coordinates (or from `get_metadata` × 2). Check each
   overlay in a still: it must sit exactly on the element underneath.
   Only text and states that change are drawn in code; everything else is the real export.

If the Figma MCP needs auth or fails, tell the user. Fallback: ask them to export the frames
(File → Export, PNG @2x, plus SVG for the logo and icons) into `studio/public/<name>/figma/`.

## Without Figma (a live product)
Screenshot the real product or site in a browser at 2× (the full page plus key components),
collect the logo, colours and fonts from computed styles, and save everything to
`studio/public/<name>/assets/`. List what you found before animating.

## Asset rules
- Never invent screens, numbers or features that aren't in the design. Placeholder data shown
  in the design is fine.
- Keep text crisp: don't scale bitmap UI above 100% of its export size. Export at 2× if the camera
  will push in.
- Avoid `will-change` on anything the camera scales (blurry text)
