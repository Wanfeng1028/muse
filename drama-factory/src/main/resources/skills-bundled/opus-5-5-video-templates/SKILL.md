---
name: opus-5-5-video-templates
description: Make a motion-graphics video — a product launch film, app promo, ad, product demo, explainer, logo reveal or brand film — from one of 30 free templates, rebranded with the user's name, copy and colors and rendered to MP4 on their machine with HyperFrames. Use when the user asks for a launch, promo, demo, explainer or social video, a logo animation, a video like the Claude Opus 5.5 ones, or names one of these templates.
---

# Opus 5.5 video templates

Thirty HTML motion-graphics templates, remade from widely shared Claude Opus 5.5
videos and rendered by [HyperFrames](https://github.com/heygen-com/hyperframes),
which runs headless Chrome and FFmpeg on the user's machine. Every template keeps
its copy and colors in variables, so a rebrand is a list of values. `SKILL_DIR`
below is this skill's base directory.

## 1. Check the machine (once)

```bash
npx hyperframes@0.8.96 doctor
```

It needs Node.js 22 or newer, FFmpeg and Chrome; follow its hints for anything
missing. Every command pins 0.8.96, the version the templates were tested with.

## 2. Pick a template

Read `SKILL_DIR/catalog.md`. Match what the video has to do, the format (16:9,
1:1 or 9:16) and the length, then offer one to three templates with their preview
links. If the user already named one ("the caption app one", "23"), use it. Each
template's scenes and notes are in `SKILL_DIR/templates/<id>/template.json`.

## 3. Copy it

```bash
node SKILL_DIR/scripts/new-video.mjs <id or number> <folder>
```

## 4. Rebrand it

1. List the variables: `node SKILL_DIR/scripts/vars.mjs <folder>`.
2. Gather what the copy needs: the product name, what it does, the URL, two or
   three brand colors. Read the user's website, README or brief when there is
   one; ask only for what you cannot find.
3. Write the new values in a JSON file. Keep each value in the format of its
   default: about the same length (the layouts are sized for it), the same
   number of `|`-separated items, and plain numbers where the default is a
   number (a currency symbol has its own variable). Colors are `#rrggbb`.
4. Apply them: `node SKILL_DIR/scripts/vars.mjs <folder> values.json`. The values
   become the composition's defaults, so preview, snapshot and render use them.

Demo brands, prices, stats, ratings and quotes are placeholders. Replace each one
with something true for the user, or remove it. Never ship a made-up number or
testimonial.

## 5. Check the frames

```bash
cd <folder>
npx hyperframes@0.8.96 snapshot --at 1,4,8,12
```

Pick times that cover the scenes in `template.json`, then look at every PNG in
`snapshots/`. Fix overflow by shortening the copy first; change sizes in the CSS
only when the copy cannot get shorter.

## 6. Render

```bash
npx hyperframes@0.8.96 render -f 60 -q high -w 4 -o out.mp4
```

Use `-f 30` for a quicker draft. A 15-second clip takes under a minute on an M1
Pro laptop.

## Photos and product shots

Templates with photos in the catalog (06, 20, 21, 23, 25 and 28) ship demo images
made with Claude Imagine. To show the user's own product or people:

- Use the user's own files, or generate images with the Claude Imagine MCP
  (`generate_image`, `edit_image`). The prompt behind each demo image is in
  `template.json` under `images`; adapt it to the product and keep the file name
  and aspect ratio. For one product across several shots, make one hero image
  and create the others as edits of it so the product stays the same.
- Quote the cost first with `quote_generation`; images use Claude Imagine credits.
- Phone and device screens in 21 and 23 are live HTML placed onto a photo whose
  screen is flat green. Generate the new photo with a flat #00FF00 screen, run
  `python3 tools/screen_quad.py photo.png assets/img/<name>.webp`, and paste the
  printed corners where that template's `template.json` notes say.
- If the MCP isn't connected, the user can add it with
  `claude mcp add --transport http claude-imagine https://claudeimagine.com/api/mcp`
  and restart Claude Code.

## Editing beyond the variables

- Every frame is drawn from the time `t` in one `render(t)` function. Keep it
  that way: no CSS animations or transitions, no `Math.random`, no timers.
  HyperFrames seeks frames out of order.
- Keep any new copy or color in `data-composition-variables`.
- Run `npx hyperframes@0.8.96 lint` after editing code. It should report 0
  errors; the "file too large" and "sub-composition" warnings are expected.
