---
name: ad-from-product-url
description: Start a Creatify video ad from a product page URL. Researches the page, creates an Ad Agent project seeded with the product's real images and logo, and returns the project_id, then hands off to the ad-agent workflow to generate, judge and ship the ad. Use when the user says "make an ad for this product" or pastes a store/product URL. Requires the creatify-ad-agent MCP server (composer_* tools).
---

# Ad from a product URL

Turns a product page into a seeded Creatify Ad Agent project. Creatify's hosted Ad Agent MCP does the work; this skill only decides the order of calls.

## Inputs to gather (ask only what is missing, max 3 short questions)

1. **Product page URL.**
2. **Placement → aspect ratio**: TikTok/Reels/Shorts/Stories → `9:16` (default); YouTube/website/TV → `16:9`; square feed → `1:1`.
3. **Duration**: default 15 s.

Don't ask for things the page answers (features, claims, colors). Assume, and say what you assumed in one line.

## Workflow

1. `composer_billing_state()`: report credits left and whether takes are watermarked. Use its `prices` for any cost estimate; prices change, so don't rely on hard-coded numbers. If credits look too low for a take, say so and stop. Don't push purchases or upgrades.
2. **Research the page** with your own web tools: what the product is, who it's for, its real features and wording, brand colors. Collect direct `https://` URLs for the logo and 2–5 clean product images.
3. `composer_project_create(aspect_ratio, duration, resolution="1080p")`. **Put the returned `project_id` in your reply** so the user can resume later.
4. `composer_import_asset(project_id, url, name)` for the logo and each product image. If the user attaches a local file instead, upload it first with `upload_file`, then import the returned `cdn_url`. Look at every preview it returns and write down each asset's role against the `path` the import returned, used exactly (paths get a hash prefix, for example "assets/4b42891a_logo_white.png = logo").
5. Tell the user in one line what you took from the page, then **continue with the `ad-agent` skill** (plan, generate, judge, fix, ship). Before assembling, read the ad-agent references it points to for that step: `references/dynamism.md`, `references/audio-sync.md` and `references/graphics-craft.md` (plus `stage-api.md` for the page).
   - **Optional cheap draft:** `composer_generate_clip(resolution="768P")` costs much less than 1088P (a 9 s clip was 4.0 vs 11.0 credits; check `prices`). It returns 768×1344, so keep the project canvas and accept the scale-up on drafts, or use a 720p project for draft-only checks. A 1088P re-render of an approved draft is a **new generation, not an upscale**: the result will differ, so judge it again before shipping, and tell the user it may not match the draft.
6. When `composer_ship` finishes, give the user `video_url` and `library_url` from its result, along with the `project_id` and take number.

## Do not

- Don't make up an `https://app.creatify.ai/ad-agent/<id>` link. Those URLs belong to web Ad Agent chat sessions, which these tools don't create. Share `library_url` from `composer_ship` instead.
- Don't generate the business's own venue, staff or customers. Build from real product imagery.
- Don't start paid generation before the user has confirmed the plan, unless they said "just make it".
