# GIPHY GIF and sticker search (headless / project-independent)

Search the [GIPHY](https://developers.giphy.com/) library of animated GIFs and transparent-background
stickers by keyword, browse the trending feeds, fetch one item by id, and download a pick into the
**Downloaded GIFs** library (My Assets → Downloaded GIFs) — the same folder the automatic GIF b-roll
pipeline fills. The search tools are **standalone** — they do **not** use a Shorz project, `projectType`,
`settings.json`, PromptBar, Create Video, or any sidebar panel. Do **not** call `create_project` or
`read_project_settings` first.

**Prerequisites:** Shorz running + MCP connected (per `../../SKILL.md`) **and signed in to Shorz**.
The GIPHY API key lives server-side on the Shorz proxy (`/v1/proxy/giphy/*`); the tools attach the
signed-in user's token, so a signed-out call returns
`{ success:false, status:401, error:"Sign in to Shorz to search GIPHY." }`. GIPHY usage is **free** —
no Shorz credits are spent.

The same catalogue is available without an agent: the B-roll lane's **SEARCH** button in Your Library
has **GIFs** and **Stickers** toggles next to Videos / Photos (see `../panel-workflows/your-library-assets.md`).

## Tools

| Tool | Purpose | Required | Key optional args |
|---|---|---|---|
| `giphy_search_gifs` | Keyword GIF search (opaque animated clips: reactions, memes, footage loops) | `query` (≤50 chars) | `maxResults`, `rating`, `lang`, `minWidth`/`maxWidth`/`minHeight`/`maxHeight`, `maxSizeBytes` |
| `giphy_search_stickers` | Keyword STICKER search (animated GIFs with a transparent background: arrows, emoji-style reactions, text callouts, cut-out characters) | `query` (≤50 chars) | same as `giphy_search_gifs` |
| `giphy_trending_gifs` | Trending GIF feed (no keyword) | — | `maxResults`, `rating`, size filters |
| `giphy_trending_stickers` | Trending sticker feed (no keyword) | — | `maxResults`, `rating`, size filters |
| `giphy_get_gif` | One GIF or sticker by GIPHY `id` — trimmed shape in `gif` plus `images_full` with every rendition | `id` | — |
| `download_giphy_gif` | Save a result's `download_url` into Downloaded GIFs; returns the asset with its absolute `filePath` | `url` (https://*.giphy.com only) | `fileName` |

## GIFs vs stickers

- **GIFs** are opaque rectangles. As b-roll they behave like any dropped `.gif`: an animated, looping
  clip placed and sized by the B-roll panel / placement LLM.
- **Stickers** have a transparent background. The render checks the downloaded file's real pixels
  (`gif_has_transparency`) and composites a see-through GIF as a **cut-out over the video**, never as a
  black rectangle — the same alpha path the automatic GIF b-roll uses for its sticker type. A sticker
  is also never chroma-keyed and never gets an overlay effect (both would paint over the transparency).
  Prefer stickers for reactions and callouts that should sit *on* the footage; prefer GIFs for
  full-frame reaction clips.

## Result count (no pagination)

Pagination is hidden. Pass **`maxResults`** (default 15, max 100) and the tool gathers that many
results itself — fetching one or more GIPHY pages (offset-based, 50 per request max) and stopping when
it has enough or GIPHY runs out. There are **no `page`/`offset` args**. `maxResults` is the *fetch
budget*; the response's `fetched` is what was gathered and `returned` is what survived the client-side
filters, so `returned` can be lower. If `returned` is low, raise `maxResults` and/or loosen the filters.

## Rating

`rating` defaults to **`g`** — the same rating the automatic GIF b-roll pipeline uses, so an agent
choosing GIFs unattended stays safe by default. Pass `pg`, `pg-13` or `r` only when the user asks for
it. (The in-app SEARCH panel, where a person is choosing from tiles, uses `pg-13`.)

## Filtering model — native vs client-side

GIPHY's search only takes `q`, `rating`, `lang`, `limit` and `offset` natively. Width, height and
byte size are reported **per rendition in the response**, so the tools apply those bounds
client-side after fetching, all measured on the **`original`** rendition:

- **`minWidth`/`maxWidth`/`minHeight`/`maxHeight`** — pixel bounds on the original.
- **`maxSizeBytes`** — drops items whose original `.gif` is larger, **or whose size GIPHY did not
  report**.
- **`lang`** — 2-letter language code for non-English queries (native).

Queries over 50 characters are rejected (GIPHY answers 414 above that); one or two words rank best
(`mind blown`, `facepalm`, `thumbs up`).

## Which rendition downloads

Every result carries **`download_url`** — the `.gif` to fetch. It is the `original` rendition when
that is **≤ 8 MB**, otherwise the largest of GIPHY's own size-capped renditions that fits
(`downsized_large` ≤ 8 MB → `downsized_medium` ≤ 5 MB → `downsized` ≤ 2 MB), and as a last resort the
smallest GIF rendition there is. `download_rendition` names which one was chosen and `download_size`
its byte size. Items with no GIF rendition at all (mp4-only clips) are dropped. The in-app SEARCH
panel picks the same rendition, so the tools and the UI agree.

## Response shape

Search/feed tools return:

```jsonc
{
  "success": true,
  "attribution": "Powered by GIPHY",
  "requested": 15,       // your maxResults (the fetch budget)
  "total_count": 4820,   // total available on GIPHY for this query (trending: the feed size)
  "fetched": 15,         // raw results gathered across auto-paged requests
  "returned": 12,        // results kept AFTER client-side filtering
  "gifs": [
    {
      "id": "xT0xeJpnrWC4XWblEk",
      "type": "gif",                      // or "sticker"
      "title": "Mind Blown GIF",
      "url": "https://giphy.com/gifs/…",  // landing page — link back to it where results are shown
      "rating": "g",
      "username": "…",                    // uploader, when GIPHY reports one
      "source": "…",
      "import_datetime": "2016-06-02 20:20:36",
      "width": 480, "height": 270, "size": 1048576, "frames": 36,   // the ORIGINAL rendition
      "download_url": "https://media.giphy.com/media/…/giphy.gif",
      "download_rendition": "original",
      "download_size": 1048576,
      "preview_mp4": "https://…mp4",
      "images": {                          // trimmed renditions; every number parsed from GIPHY's strings
        "original": { "url": "…gif", "width": 480, "height": 270, "size": 1048576, "mp4": "…", "webp": "…", "frames": 36 },
        "downsized_large": { "url": "…", "width": 480, "height": 270, "size": 1048576 },
        "downsized_medium": { "…": "…" }, "downsized": { "…": "…" },
        "fixed_height": { "…": "…" }, "fixed_height_small": { "…": "…" }, "preview_gif": { "…": "…" }
      }
    }
  ]
}
```

GIPHY has **no duration field** — only `frames` on the original. `giphy_get_gif` returns `{ success,
attribution, gif, images_full }`, where `images_full` is GIPHY's untrimmed `images` object (fixed
widths, looping mp4s, stills, …). A failed call returns `{ success:false, status, error }`; a 429 means
the proxy's hourly GIPHY quota is exhausted on every configured key — wait, don't retry in a loop.

## Attribution

GIPHY's API terms ask for a "Powered by GIPHY" mark wherever its results are shown (every response
carries the `attribution` string) and that results link back to their landing `url`. There is no
attribution obligation on the finished video.

## Using a result downstream

1. Search: `giphy_search_stickers { query: "thumbs up", maxResults: 10 }` and pick a `gif`.
2. Download: `download_giphy_gif { url: <gif.download_url>, fileName: "thumbs-up" }` → the saved
   asset (`filePath`, `mimeType: "image/gif"`, `sizeBytes`). Only `https://*.giphy.com` URLs are
   accepted, and the body must be a real GIF (mp4/webp rendition URLs are rejected by a magic-number
   check). `get_downloaded_gifs` lists everything in the folder.
3. Use it as b-roll: `import_frontend_assets` with `assetType: "BROLL"` and
   `overridePaths: [<filePath>]` (without `overridePaths` the tool opens a native file dialog and hangs
   headless runs), then place it through the B-roll panel / PromptBar like any imported b-roll asset.
   A sticker composites as a cut-out; a GIF as an opaque clip (see *GIFs vs stickers*).
