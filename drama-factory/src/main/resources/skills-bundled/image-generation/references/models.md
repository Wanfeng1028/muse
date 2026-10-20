# Models and APIs

Checked 2026-10-06. Model ids churn monthly: re-check the vendor changelog before a new project and pin dated snapshots for a running one.

Contents
1. OpenAI image API (verified 2026-10-06)
2. Model chooser (late 2026)

---

## OpenAI image API (verified 2026-10-06)

Models:
- `gpt-image-2.5-sunburst` (snapshot -2026-09-08): best quality and most precise editing. It is the default model for `/v1/images/edits`.
- `gpt-image-2.5-flare` (-2026-09-08): fast. OpenAI says its quality is "comparable to GPT Image 2".
- `gpt-image-2` (-2026-04-21): the previous model; what Repitis shipped with.
- Shutdowns: `gpt-image-1` on 2026-10-23; `gpt-image-1.5`, `gpt-image-1-mini` and `chatgpt-image-latest` on 2026-12-01. DALL-E 2/3 were removed on 2026-05-12.
- OpenAI's migration advice: if a gpt-image-2 workflow already passes, try Flare for speed; if it falls short, try Sunburst first.

| Topic | Fact |
|---|---|
| Endpoints | `/v1/images/generations` (text only, JSON); `/v1/images/edits` (1-16 input images, optional mask; multipart `image[]` or JSON `images:[{image_url|file_id}]`); Responses API `image_generation` tool for multi-turn |
| References | up to 16 images on edits. Older models favoured the first image (gpt-image-1 richest detail on image 1; 1.5 first 5 at high fidelity): put the identity sheet first anyway. A mask applies to the first image |
| input_fidelity | gpt-image-2 and 2.5: omit it; inputs are always high fidelity and the API rejects changing it. Only 1/1.5 (`low|high`), mini (`low`). High fidelity = more input tokens |
| Masks | PNG with alpha, same size and format as the image, under 50MB. "Masking with GPT Image is entirely prompt-based": the model may not follow the mask shape exactly. For pixel-exact regions, composite the approved edit back over the original in code |
| Sizes | 2.5 and 2: any `WxH` with both edges multiples of 16, ratio between 1:3 and 3:1, max edge 3840, total 655,360 to 8,294,400 px; above 2560x1440 is "experimental". Presets: 1024x1024, 1536x1024, 1024x1536, 2048x2048, 2048x1152, 3840x2160, 2160x3840. 16:9 safe picks: 1536x864, 2048x1152, 2560x1440 |
| Quality | `low, medium, high, auto` (gpt-image-2); 2.5 adds `xhigh, max`. Default `auto`. Use low for drafts; climb only when an unmet requirement needs it; "A higher setting doesn't guarantee a better result" |
| Background | `transparent|opaque|auto`. 2.5 family supports transparent (PNG/WebP only). gpt-image-2: preview announced 2026-08-20, staff said "Transparency preview in gpt-image-2 is discontinued" (forum, 2026-10-01) and edits now return `Transparent background is not supported for this model`; docs still say preview. Locally it worked on generations 2026-09-30 (113 cards with real alpha) and failed 2026-10-04 on edits |
| Formats | png (default), jpeg (fastest), webp; `output_compression` 0-100 for jpeg/webp only. Response is base64 (`b64_json`); no URLs for GPT image models |
| n | 1-10 per request. Use it for variants instead of separate calls |
| Streaming | `partial_images` 0-3; each partial costs +100 output tokens |
| Moderation | `moderation: auto|low`. Errors with `error.type = image_generation_user_error` or `code = moderation_blocked` (with `moderation_details.moderation_stage` input/output and coarse categories) must not be auto-retried unchanged; retry only 429/5xx with backoff. Organization verification may be required before using GPT Image |
| Latency | "Complex prompts may take up to 2 minutes"; set client timeouts of 600 s (as both local scripts do) |
| Rate limits | 2.5 and 2: Build tier 20 images/min (250k TPM); Launch 150 IPM; Grow 250 IPM. Two to four in flight is plenty |
| Cost | Token-priced: $30 per 1M image output tokens, $8 per 1M image input, $5 per 1M text input; Batch API half price. Per image, gpt-image-2 at 1024-class sizes: low $0.005-0.006, medium $0.041-0.053, high $0.165-0.211. OpenAI states 2.5 token use differs and its calculator doesn't cover it. Read `usage` per response. Reference images add input tokens on every edit. Cached-input pricing applies only via the Responses tool, not `/images/edits` |
| Responses tool | top-level mainline model (gpt-5.5 etc.) + tool `{type:"image_generation", model:"gpt-image-2.5-sunburst", size, quality, background, action:"auto|generate|edit"}`. Multi-turn via `previous_response_id` or image ids; forcing `edit` without an image in context errors |
| Provenance | API images carry C2PA and a SynthID watermark (exceptions: gpt-image-1, 1.5); verify with `POST /v1/content_provenance_checks` or openai.com/verify |

Known limits per OpenAI: precise text placement, recurring-character consistency, layout-precise compositions.
Repeated edits drift: "Restate those constraints and inspect each result".

## Model chooser (late 2026)

| Task | First choice | Why | Fallback / note |
|---|---|---|---|
| Illustrated cast + 10-50 scenes in one locked style | gpt-image-2.5-sunburst edits with cast sheet as Image 1 | 16 refs, precise editing, subject preservation; proven pipeline on gpt-image-2 | Nano Banana Pro (5 character refs, 3 style refs), unless kids product (see `legal.md`) |
| Style exploration, many cheap drafts | gpt-image-2.5-flare `quality=low`, `n=4` | about half a cent per gpt-image-2 low draft | Recraft V4.1 Flash $0.007; Nano Banana 2.1 1K $0.034 |
| Cutouts with real alpha | gpt-image-2.5 `background=transparent` (no backdrop words in prompt) | native alpha keeps hair, glass, thin reeds | white + BiRefNet (MIT); Ideogram transparent endpoints; Recraft removeBackground $0.01 |
| Wide plates for pans/parallax | Nano Banana 2.1 at 4K 21:9 (6336x2688) or 8:1 | ultrawide ratios beyond OpenAI's 3:1 | Seedream 4.5 / 5.0 lite 4K, ratios to 16:1 |
| Pre-split layers for parallax | Seedream 5.0 pro layer decomposition (base + up to 16 alpha layers) | layers come out ready to move | generate layers separately (`motion-assets.md`) |
| Many consistent storyboard frames | Seedream 5.0 lite / 4.5 sequential mode (up to 15 images per call) | one call, shared identity | gpt-image grid "contact sheet" then regenerate picks |
| Flat vector explainer art, recolourable | Recraft V4.1 `*_vector` (real SVG) + `controls.colors` RGB | infinite zoom, edit fills in code | vectorize a raster ($0.01) |
| Style match from your own references | Recraft V4 Styles (`style_id` from 1-10 refs) | reusable style id, no training | Midjourney `--sref` (manual only: no API, automation forbidden by ToS) |
| Text-bearing imagery | Don't. Composite real type in Remotion | models still misspell and warp | if unavoidable: Ideogram 4.x, Nano Banana Pro, or GPT Image 2.5 high with quoted copy |
| Photoreal product | Real product photos/screens composited; generate only the environment plate | a generated product is a fabrication | GPT Image 2.5 edit with the product photo as reference, for mood boards only |
| Keyframes for image-to-video | same model and refs as the cast, at the video's exact size | identity continuity | see `motion-assets.md` |

Stay on one provider for an anchor and everything derived from it: switching gateways mid-film drifts skin tone and
softness. Never paste Midjourney/SD parameters into GPT or Gemini prompts.
