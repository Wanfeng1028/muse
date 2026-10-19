---
name: long-video-to-shorts-config
version: 1.0.0
description: 'Interactive configurator for the long-video-to-shorts skill. Use when the user types /long-video-to-shorts-config or asks to "configure/change the shorts style", "change the caption style / accent colour / font / hook duration", "règle le style des shorts", "change la couleur des sous-titres". Walks through the options (keep-or-change each), then writes config.json for them.'
metadata:
  tags: config, captions, style, accent-color, font, shorts, configurator
---

# long-video-to-shorts — configurator

Interactively edit the `config.json` of the **long-video-to-shorts** skill. Ask the
user what to change (each option offers "keep current"), then **write the file yourself**
and confirm. Optionally render a tiny preview so they see the result.

## Step 0 — locate + read the current config

The target file is the main skill's config:
`~/.claude/skills/long-video-to-shorts/config.json` (adjust if installed elsewhere;
find it with a glob for `**/long-video-to-shorts/config.json`).

Read it and note the CURRENT values — you will show them as the "keep current" option
in each question and only overwrite the keys the user changes.

## Step 1 — ask (batch with AskUserQuestion)

Ask these with **"Keep current (<value>)" as the FIRST option** each. Batch up to 4 per
AskUserQuestion call. Do NOT ask about anything the user already told you in their message.

1. **Caption style** — options: Keep current · `word-pop` (active word pops) ·
   `capcut` (UPPERCASE, punchy) · `label` (dark bar). Mention in the question that the
   other styles (`clean`, `karaoke`, `one-word`, `boxed`, `bicolor`) are available if
   they ask — offer them via "Other".
2. **Accent colour (brand colour)** — options: Keep current · Yellow `#FFFF00` ·
   Green `#39FF14` · Cyan `#00E5FF` · plus "Other" for a custom hex. (Drives the popped
   word AND the hook accent word.)
3. **Hook duration** — options: Keep current · 3s · 4s · 5s.
4. **Font** — options: Keep current · one of the `.ttf` files already in
   `~/.claude/skills/long-video-to-shorts/assets/fonts/` · "Download a font" (see Step 2).

If the user wants finer control, also offer (second AskUserQuestion, optional):
- **Caption vertical position** (`caption_pos_y`, default 1360) and **hook position**
  (`hook_pos_y`, default 175) — usually keep default.
- **Safe zone** margins — usually keep default.

## Step 2 — font download (only if they pick "Download a font")

Offer a few short-friendly fonts and fetch the chosen one into the skill's
`assets/fonts/` with `curl`, then **verify it is a real TTF** (first 4 bytes are
`00 01 00 00` or `OTTO`/`true`), then set both `font` and `font_family`:

| Font | family | URL |
|---|---|---|
| Anton (condensed caps) | `Anton` | `https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf` |
| Bebas Neue (tall caps) | `Bebas Neue` | `https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf` |
| Poppins Bold (rounded) | `Poppins` | `https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf` |
| Oswald Bold (narrow) | `Oswald` | `https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf` |

```bash
DEST=~/.claude/skills/long-video-to-shorts/assets/fonts/<File>.ttf
curl -fsSL "<url>" -o "$DEST"
head -c4 "$DEST" | xxd | head -1   # must look like a font (00010000 / 4f54544f)
```
If the download fails or isn't a valid TTF, tell the user to drop a `.ttf` into
`assets/fonts/` themselves and give you its family name — don't guess.

## Step 3 — write config.json

Take the current config, apply ONLY the changed keys, and write valid JSON back to
`~/.claude/skills/long-video-to-shorts/config.json`. Keep the existing keys/comments you
didn't touch. Valid keys:

```
caption_style, accent_color, hook_accent_color, font, font_family,
caption_max_chars, caption_pos_y, hook_seconds, hook_pos_y, safe_zone{top,bottom,left,right}
```

By default set `hook_accent_color` = `accent_color` unless the user wants them different.

Validate the JSON parses (e.g. `node -e "JSON.parse(require('fs').readFileSync('<path>','utf8'))"`).

## Step 4 — confirm + optional preview

Summarize what changed (old → new). Then offer a **preview**: if a recent job dir exists
(look under `~/shorts-jobs/*/work/` for a `source.mp4` + `transcript.json`), render a ~4s
sample with the new config and show a frame:

```bash
MAIN=~/.claude/skills/long-video-to-shorts
bash "$MAIN/scripts/build_clip.sh" <job-dir> \
  --start 00:00:33.4 --end 00:00:37.4 --kind facecam \
  --title "Preview *style*" --hook true --caption-mode ass --face-cx 0.5 \
  --out <job-dir>/work/_cfg_preview.mp4
# then: ffmpeg -y -ss 2 -i .../_cfg_preview.mp4 -vframes 1 preview.png  and Read it
```

If no job dir exists, just confirm the saved values and tell them it'll apply on the next
run of `long-video-to-shorts`.

## Rules

- Never overwrite keys the user didn't change.
- Always write **valid JSON** (no trailing commas).
- "Keep current" must be a real option for every setting.
- Colours are hex (`#RRGGBB`); if the user gives a name ("orange"), convert to a sensible hex.
