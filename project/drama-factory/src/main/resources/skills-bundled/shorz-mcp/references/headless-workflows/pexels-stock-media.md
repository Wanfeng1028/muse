# Pexels stock media search (headless / project-independent)

Search the free [Pexels](https://www.pexels.com/api/) stock photo and video library by keyword and
get back direct media URLs plus metadata (dimensions, photographer/attribution, per-rendition
download links). These tools are **standalone** — they do **not** use a Shorz project, `projectType`,
`settings.json`, PromptBar, Create Video, or any sidebar panel. Do **not** call `create_project` or
`read_project_settings` first.

**Prerequisites:** Shorz running + MCP connected (per `../../SKILL.md`) **and signed in to Shorz**.
The Pexels API key lives server-side on the Shorz proxy; the tools attach the signed-in user's token,
so a signed-out call returns `{ success:false, status:401, error:"Sign in to Shorz to search Pexels." }`.
Pexels usage is **free** — no Shorz credits are spent.

## Tools

| Tool | Purpose | Required | Key optional args |
|---|---|---|---|
| `pexels_search_photos` | Keyword photo search | `query` | `maxResults`, `orientation`, `size`, `color`, `locale`, `minWidth`/`maxWidth`/`minHeight`/`maxHeight` |
| `pexels_search_videos` | Keyword video search | `query` | `maxResults`, `orientation`, `size`, `locale`, `quality`, `fileType`, `minWidth`/`maxWidth`/`minHeight`/`maxHeight`, `minDuration`/`maxDuration` |
| `pexels_curated_photos` | Editor-curated photo feed (no keyword) | — | `maxResults`, width/height filters |
| `pexels_popular_videos` | Popular video feed (no keyword) | — | `maxResults`, `nativeMinWidth`/`nativeMinHeight`/`nativeMinDuration`/`nativeMaxDuration`, plus the same client-side filters as search |
| `pexels_get_photo` | One photo by numeric `id` (full src set) | `id` | — |
| `pexels_get_video` | One video by numeric `id` (all renditions) | `id` | — |

## Result count (no pagination)

Pagination is hidden. Pass **`maxResults`** (default 15, max 80) and the tool gathers that many
results from the endpoint itself — fetching one or more Pexels pages internally with a fixed page
size and stopping when it has enough or Pexels runs out. There are **no `page`/`perPage` args**.
`maxResults` is the *fetch budget* (raw results pulled before client-side filtering); the response's
`fetched` is what was gathered and `returned` is what survived the quality/size/duration filters, so
`returned` can be lower. If `returned` is low, raise `maxResults` and/or loosen the filters.

## Filtering model — native vs client-side

Pexels narrows **searches** only by `orientation`, `size`, `color`, and `locale`. Everything else
(exact width/height, video quality, file type, duration) is exposed **per result/per rendition in the
response**, so these tools apply those filters client-side after fetching:

- **`orientation`** — `landscape` | `portrait` | `square` (native).
- **`size`** — `large` | `medium` | `small`: a *minimum* resolution bucket (native).
- **`color`** (photos) — a named color (`red`, `turquoise`, …) or hex (`#ff0000`) (native).
- **`quality`** (videos) — `sd` | `hd` | `uhd`, single value or array (client-side, per rendition).
- **`fileType`** (videos) — e.g. `video/mp4` or just `mp4` (client-side, per rendition).
- **`minWidth`/`maxWidth`/`minHeight`/`maxHeight`** — pixel bounds. For **photos** they bound the
  photo's native size; for **videos** they bound each **rendition**, and a video with no rendition in
  range is dropped.
- **`minDuration`/`maxDuration`** (videos, seconds) — client-side on the clip duration.
- `pexels_popular_videos` also takes the **native** `nativeMin*`/`nativeMax*` params that Pexels'
  popular feed supports server-side; combine with the client-side filters to narrow further.

Note: Pexels sometimes returns `quality: null` on a rendition. With **no** `quality` filter those
renditions pass through normally; setting a `quality` filter keeps only renditions whose label
matches, so prefer `minWidth`/`minHeight` when you need a reliable resolution floor.

## Response shape

All tools return `{ success, rateLimit, ... }`. `rateLimit` carries Pexels' live quota
(`limit` / `remaining` / `reset`). Search/feed results add the result counts:

```jsonc
{
  "success": true,
  "rateLimit": { "limit": "25000", "remaining": "24987", "reset": "..." },
  "total_results": 8000,   // total available on Pexels for this query
  "requested": 40,         // your maxResults (the fetch budget)
  "fetched": 40,           // raw results gathered across auto-paged requests
  "returned": 12,          // results kept AFTER client-side filtering
  "videos": [
    {
      "id": 1234, "width": 4096, "height": 2160, "duration": 12,
      "url": "https://www.pexels.com/video/…",
      "image": "https://…preview.jpg",
      "user": { "name": "…", "url": "https://…" },
      "best_file": { "id": 1, "quality": "uhd", "file_type": "video/mp4", "width": 4096, "height": 2160, "fps": 30, "link": "https://…mp4" },
      "video_files": [ /* matching renditions, largest first */ ],
      "video_pictures": [ /* thumbnails */ ]
    }
  ]
}
```

Photo results use a `photos[]` array with `{ id, width, height, url, photographer, photographer_url, avg_color, alt, src: { original, large2x, large, medium, small, portrait, landscape, tiny } }`.
For downloads pick `best_file.link` (video) or the appropriate `src.*` size (photo).

If `returned` is `0` but `fetched` is high, your width/height/quality/duration filters were too
strict — loosen them or raise `maxResults`.

## Attribution

Pexels requires crediting the photographer/Pexels when media is shown publicly. Surface
`photographer` / `user.name` and the `url` from each result so the user can attribute correctly.

## Using a result downstream

These tools only **find** media and return URLs — they don't download into a project. To bring an asset
into Shorz, that's a **separate** step (e.g. download the `link`/`src` URL, then `import_frontend_assets`
or a project-specific path patch), exactly like other headless outputs.
