# Craft for the graphics layer (from the best Opus-made videos)

Everything here lives in `index.html` (edit with `composer_read_file` → `composer_edit_file`), so every fix is a reassemble, never a regeneration.

- **Storyboard the reads first.** Before writing the page, list each thing the viewer must understand (hook, product, benefit, proof, offer, CTA) with a start/end time. No two important reads overlap, and each holds long enough to read aloud once. Fast actions, slow meanings.
- **Beat grid.** Every timing decision comes from the measured beat map and word times (audio-sync.md), never from arithmetic on the BPM you asked for. Per-word or per-glyph reveals stagger by a sixteenth note (`beat / 4`).
- **One design system.** Use the brand's colors (one accent, used sparingly), one clean sans at 2–3 sizes, tight tracking on display type, generous empty space, and one idea per frame. Captions: one line, high contrast, inside the platform safe area (9:16: nothing important in the top 220px or bottom 380px, 60px side margins). Brand rules from the brief (casing, banned words, required disclaimer, CTA wording) are hard requirements. Copy the brief quotes is used word for word. A claim, statistic, price, guarantee or contact detail must come from the brief, an attachment, or a page the user linked (its real wording), never invented. Captions step aside while a full-screen text card or the end card is up.
- **Motion craft.** Use masked reveals (text slides up inside an `overflow:hidden` line box) and springs that settle without bounce. Content enters after its container starts moving and leaves before it closes, and nothing holds perfectly still for more than ~1s while it's on screen. End on the CTA / packshot, held ≥1.5s. A card that carries an action (price, offer, URL, phone, CTA) opens on its content, never an empty frame. It has the whole message on screen within 1.5s, then holds with light motion. A line the voice speaks is on screen no later than it is heard.
- **Banned:** particles, shockwave rings, RGB split, camera shake, lens flares, neon glow, bouncy/elastic easing, crossfades between shots, spinning 3D logos, stock lower-third templates.
- **Grade in the page (free colour fix, no generation).** When H3 footage drifts off the brand palette, grade it in `index.html` instead of regenerating: greyscale the footage and lay a brand-colour layer over it with `mix-blend-mode: color`, which keeps the footage's light and shade and replaces its hue. Keep the tint above the footage and below text and logos, so they keep their own colours; lower its `opacity` for a partial grade. Check a sheet against the brand colour afterwards.
  ```html
  <div class="shot" id="s1"></div><div class="tint"></div>
  <style>
    #s1 img { filter: grayscale(1); }
    .tint { position: absolute; inset: 0; background: #1E6BFF; /* brand colour */ mix-blend-mode: color; pointer-events: none; }
  </style>
  ```
- **Chromium gotchas:** opacity or filter on a `preserve-3d` element flattens it (fade a wrapper instead). `will-change` on anything you scale blurs its text. A child with `visibility: visible` shows through a hidden parent (use `inherit`).

After any graphics change, run `python3 -m lib.compose sheet index.html --at <each read's time> -o out/check/sheet.jpg` via `composer_exec` and `composer_view` it. For a small element like the CTA or a price, add a `--crop x,y,w,h --width 900` detail sheet.
