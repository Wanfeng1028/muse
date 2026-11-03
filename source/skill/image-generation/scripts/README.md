# image-generation scripts

Two uv scripts (no installs: `uv` resolves the inline dependencies on first run). Run them from the project root;
outputs default to `public/img/`. Private helpers `_gen_image_*.py` are imported by `gen_image.py`; never run them
directly. Model facts were checked against the vendors' docs on 2026-10-06; re-check before a new project.

## gen_image.py

Generates or edits images from a prompts file with a locked style suffix, references with roles, variants, masks, a
version archive and a JSON sidecar per output. OpenAI by default; Gemini, BFL FLUX and Recraft behind `--provider`.

```bash
gen_image.py PROMPTS.json [NAMES...] [--out public/img] [--dry-run]              # all images, references first
gen_image.py PROMPTS.json cast --draft --contact-sheet out/review/cast-drafts.png  # low quality, n=4, ~1 MP, <out>/drafts/
gen_image.py pick cast b --dir public/img/drafts                                   # promote cast.b.png to cast.png
gen_image.py PROMPTS.json shot-kitchen --final --aspect 16:9 --overscan 1.2 --budget 2
gen_image.py PROMPTS.json shot-fix --composite-back                                # masked edit, pixel-exact paste
gen_image.py PROMPTS.json --batch --final                                          # OpenAI Batch API, half price, <= 24 h
gen_image.py batch-fetch BATCH_ID --out public/img
gen_image.py contact-sheet public/img/cast.png public/img/shot-*.png --out out/review/cast.png [--columns 4] [--cell 320]
gen_image.py check-alpha public/img/cut/*.png                                      # exit 1 if any file lacks real alpha
```

Flags: `--provider openai|gemini|bfl|recraft`, `--model ID`, `--quality low|medium|high|auto|xhigh|max`, `--final`,
`--draft`, `--aspect 16:9|9:16|1:1|4:5`, `--overscan F`, `--composite-back`, `--feather PX` (default 2),
`--moderation auto|low`, `--regenerate`, `--concurrency N` (default 2), `--ipm N` (default 20, OpenAI Build tier),
`--budget USD`, `--batch`, `--contact-sheet PNG`, `--env-file PATH`, `--dry-run`.

Keys come from the environment or `--env-file` (KEY=VALUE lines): `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BFL_API_KEY`,
`RECRAFT_API_KEY`. Only the providers the selected images use are required.

### What it sends

- Prompt: `[Image 1: <role> (<name>).\nImage 2: ...]\n\n<prompt>\n\nStyle: <style> <backdrop line>`. The Image lines
  are written only when at least one reference has a role or `edit_of` is set (old files send the old prompt).
- Image order: `edit_of` first (role "the image to edit; keep everything this prompt does not change"), then references
  whose role mentions "identity", then the rest in file order. With a `mask` and no `edit_of`, file order is kept
  because the mask applies to Image 1.
- Endpoint: any reference or `edit_of` means `/v1/images/edits` (multipart `image[]`, plus `mask`); otherwise
  `/v1/images/generations` (JSON). `--batch` sends the same bodies as JSONL (edits as JSON with data-URL `images`).
- Model: `--model` > `--final` (gpt-image-2.5-sunburst) > image `model` > file `model` > provider default
  (openai `gpt-image-2.5-flare`, gemini `gemini-nano-banana-2.1`, bfl `flux-2-pro`, recraft `recraftv4_1`).
- Quality: `--quality` > `--draft` (low) > `--final` (high) > image > file (default high).
- Size: `--aspect` > image `aspect` > image `size` > file `aspect` > file `size`; then overscan (`--overscan` > image
  `overscan`), then `--draft` shrinks to about 1 MP. Overscan keeps the exact aspect when it can (2048x1152 x1.2 ->
  2560x1440) and is capped by the limits.

### Prompts-file schema (all new fields optional; old files work unchanged)

```jsonc
{
  "style": "locked style suffix (required)",
  "notes": "free text, ignored",
  "background": "white",          // white | grey | green | color:#RRGGBB | transparent | none | any literal backdrop sentence
  "size": "1536x1024",             // WxH or auto
  "aspect": "16:9",                // preset: 16:9=2048x1152, 9:16=1152x2048, 1:1=1536x1536, 4:5=1280x1600
  "quality": "high",
  "provider": "openai",            // openai | gemini | bfl | recraft
  "model": "gpt-image-2.5-flare",  // applies to images on the file's provider
  "output_format": "png",          // png | webp | jpeg
  "output_compression": 85,        // 0-100, webp/jpeg only
  "palette": ["#F2545B"],          // Recraft controls.colors only; write palette hex in "style" for the others
  "images": {
    "<name>": {
      "prompt": "subject block (required)",
      "notes": "free text, ignored",
      "size": "1024x1536", "aspect": "9:16", "overscan": 1.2,          // overscan 1.0-3.0
      "quality": "medium",
      "references": ["cast", "refs/photo.png",                           // plain strings still work
                     {"ref": "cast", "role": "identity and outfits"},    // name of an earlier output, or a path
                     {"ref": "set", "role": "layout and light only"}],   // relative to the prompts file
      "edit_of": "<name>",             // that output becomes Image 1; may be the image itself (use --regenerate)
      "mask": "masks/area.png",        // same size as Image 1; alpha (transparent = edit) or black/white (white = edit)
      "background": "transparent",
      "n": 4,                          // 1-10 variants -> name.a.png ... name.d.png
      "output_format": "webp", "output_compression": 85,
      "provider": "gemini", "model": "gemini-nano-banana-2.1"
    }
  }
}
```

Unknown keys are rejected (a typo such as `refrences` fails validation instead of being ignored).
Backdrop presets: `white` = "Plain flat solid pure white (#FFFFFF) background with nothing on it, no floor shadow.",
`grey` = #808080 and `green` = #00B140 (use them when the subject contains white, then run cutout.py), `none` = no
backdrop sentence (scenes and plates), `transparent` = native alpha (below).

### Outputs

- `<out>/<name>.<ext>` (or `<name>.a.<ext>` ... with `n` > 1), drafts in `<out>/drafts/`.
- `<file>.json` sidecar: prompt, provider, model, requested and written size, quality, background, format, references
  with path, role and SHA-256, mask path/SHA/composited flag, alpha report, `usage`, `x-request-id`, estimated cost,
  style hash, provider extras (revised prompt, BFL credits, Gemini interaction ids), UTC timestamp.
- Nothing is overwritten: old files and sidecars move to `<out>/raw/<name>.vN.<ext>`. Existing outputs are skipped
  unless `--regenerate`. After a run it warns when the set's sidecars carry different style hashes.
- `pick NAME LETTER` renames the chosen variant (and sidecar) to `NAME.<ext>` and archives the others to `raw/`.

### Gotchas

- OpenAI models: `gpt-image-2.5-flare` (fast, drafts) and `gpt-image-2.5-sunburst` (best editing, finals), snapshots
  `-2026-09-08`. `gpt-image-1` shuts down 2026-10-23 (refused from that day, warned before); `gpt-image-1.5`,
  `gpt-image-1-mini` and `chatgpt-image-latest` on 2026-12-01 (warned); DALL-E is refused.
- `xhigh` and `max` quality exist only on the 2.5 family. `input_fidelity` is never sent (2 and 2.5 reject it).
- Sizes: both edges multiples of 16, ratio at most 3:1, longest edge at most 3840, 655,360 to 8,294,400 px. Above
  2560x1440 is experimental (warned). The validator runs only for OpenAI; other providers map the size to their
  nearest aspect ratio and size tier (printed in `--dry-run`).
- Transparent: sent only to gpt-image-2.5 models (gpt-image-2's preview was withdrawn and its edits reject it). The
  backdrop sentence becomes "Transparent background.", jpeg switches to png, and the decoded file must have an alpha
  channel with more than 1% fully transparent pixels or the image FAILs (the file is kept for inspection). Any backdrop
  wording in the prompt or style overrides the parameter. Use `check-alpha` on files from elsewhere.
- Masks are guidance: the model may repaint outside them. `--composite-back` pastes only the masked region of the result
  over the original (feathered by `--feather`), so everything else stays pixel-identical. A non-PNG Image 1 is sent as
  PNG when a mask is used.
- Errors: 429, 5xx and network errors retry up to 3 times with backoff (honouring `Retry-After`).
  `moderation_blocked` / `image_generation_user_error` never retry; `moderation_details` is printed. Non-JSON bodies and
  outputs under 1 KB or that do not decode are failures, never written as images.
- Cost: actual cost per request from `usage` ($30/M image output, $8/M image input, $5/M text input; Batch half).
  `--dry-run` prints a rough estimate from the gpt-image-2 per-image table scaled by megapixels plus about $0.03 per
  reference (2.5 token use differs; xhigh/max are guesses) and a running total. `--budget` stops starting requests once
  actual spend plus the next rough estimate would pass it, so one request bigger than the budget never starts.
  Gemini and Recraft report no USD cost here; BFL credits go in the sidecar.
- Concurrency defaults to 2 and never exceeds `--ipm`; a limiter keeps image starts (n counts) under `--ipm` per minute.
- `--batch`: OpenAI only; one batch per endpoint (generations, edits); a manifest goes to `<out>/batches/<id>.json` and
  `batch-fetch` needs the same `--out`. Waves that reference outputs of the same run are not batched: fetch, then run
  `--batch` again for the next wave. Reference images are inlined in every JSONL line, so big reference sets make big batch files.
- Gemini: uses the Interactions API (`POST /v1beta/interactions`, `response_format.aspect_ratio` and `image_size`),
  up to 14 references, one image per call (n calls). Its terms forbid apps directed at or likely used by under-18s; the
  script prints that warning. No negative prompts: write positives. No masks, no transparency.
- BFL: `flux-2-*` uses `width`/`height` (capped at 4 MP), `input_image` ... `input_image_8` (base64) and `disable_pup:
  true` so the prompt is not rewritten; `flux-3-image` uses `aspect_ratio` + `resolution` and `images` (up to 10).
  The result URL expires after 10 minutes and is downloaded at once. No negative prompts.
- Recraft: text-to-image only here (references are rejected), `size` as the nearest `w:h`, `n` up to 6, `palette` sent
  as `controls.colors`. `*_vector` models write `.svg`.
- The Gemini, BFL and Recraft adapters follow the vendors' published request shapes but have not been run against the
  live APIs; check the first result of a new provider by hand.

## cutout.py

Cuts subjects out of a plain backdrop with BiRefNet (`birefnet-general`, MIT licence) via rembg, for compositing.
Do not swap in BRIA RMBG-2.0 (CC BY-NC) without a commercial licence.

```bash
cutout.py IMAGES... [--out-dir DIR] [--check-dir DIR] [--check-color '#8342C9'] [--backdrop auto|#RRGGBB]
          [--no-decontaminate] [--erode PX] [--feather PX] [--margin 12] [--alpha-floor 0.08] [--alpha-span 0.84]
          [--force-matte] [--model birefnet-general] [--json]
cutout.py public/img/hero.png public/img/cast.png --erode 1 --json
```

Per image: BiRefNet matte (skipped when the input already has real alpha, unless `--force-matte`), alpha remap
`clip((a - floor) / span)`, optional erode and feather, edge colour decontamination against the backdrop colour
(`C = (C_obs - (1 - a) * B) / a` on semi-transparent edge pixels; `auto` takes the median of the image border), trim to
the alpha box plus `--margin`, and a review copy over saturated violet.

Outputs: `<out-dir>/<name>.png` (RGBA, trimmed; default `<image dir>/cut/`), `<check-dir>/<name>.png` (RGB review;
default `<image dir>/check/`), and with `--json` `<out-dir>/cutout-report.json` (method, size, opaque share, edge pixels
cleaned, backdrop, warnings).

Gotchas:
- Review the check copies, never the cutouts over white: halos and holes only show on colour.
- Subject containing the backdrop colour (white shirt, white mug on white): it warns with the share; regenerate on
  `grey` (#808080) or `green` (#00B140) in gen_image.py and cut again. BiRefNet often keeps such areas, but check.
- Enclosed transparent holes are reported with their area: fine between arms or legs, a defect inside garments or eyes.
- A remaining thin halo: add `--erode 1` (and `--feather 0.5` to soften). Thin details lost (hair, glass, reeds):
  generate with native alpha on gpt-image-2.5 instead.
- The first run downloads the model (about 1 GB) into `~/.rembg/models`. Requires Python 3.11 or 3.12 (onnxruntime).
