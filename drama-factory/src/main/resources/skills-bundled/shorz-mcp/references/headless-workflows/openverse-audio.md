# Openverse public-domain audio search (headless / project-independent)

Search [Openverse](https://openverse.org/) for **CC0 / public-domain** sound effects and background
music, then download a pick into the Shorz audio library. These tools are **standalone** — no Shorz
project, `projectType`, `settings.json`, PromptBar, Create Video, or sidebar panel. Do **not** call
`create_project` or `read_project_settings` first.

**Prerequisites:** Shorz running + MCP connected (per `../../SKILL.md`). **Nothing else.** Unlike the
Pexels tools these need **no sign-in** — Openverse is a free public API with no key, so there is
nothing held server-side and no token to attach. **No Shorz credits are spent.** These are the only
search tools in the server that work signed out.

**Licence:** every result is **CC0**. `license=cc0` is forced in the desktop's main process and is
not a parameter you can pass — so results are public domain, usable commercially, and the user owes
**no attribution in their finished video**. Do not tell the user they need to credit anyone.

## Tools

| Tool | Purpose | Required | Key optional args |
|---|---|---|---|
| `openverse_search_sound_effects` | Keyword search for short effects (< ~30s) | `query` | `maxResults`, `minDuration`, `maxDuration` |
| `openverse_search_music` | Keyword search for background music | `query` | `length`, `maxResults`, `minDuration`, `maxDuration` |
| `download_openverse_audio` | Save one result into the audio library | `url`, `fileName` | — |

`url` for the download tool is the `url` field of a search result. The saved file lands in the
runtime audio folder and comes back with a local `filePath` you can then hand to
`import_frontend_assets` or a project's `ASSET_PATHS` patch — that is a **separate** step.

## Two things the schema cannot tell you

Both come from measuring the live catalogue, and both change what you should send:

1. **Single keywords beat phrases, badly.** `whoosh` returns hundreds of rows; `notification pop`
   returns nine. Openverse's relevance ranking collapses on multi-word queries. Send one strong
   word and use `minDuration`/`maxDuration` to narrow, rather than adding words.
2. **For music, genre words beat descriptive words.** `soundtrack` returns 178 usable cues,
   `documentary` returns 20, and the generic word `music` returns field recordings and room tone.
   Reach for `lofi`, `cinematic`, `soundtrack`, `ambient`, `electronic`, `synthwave`, `chill`,
   `piano`, `acoustic guitar`, `jazz`, `classical`, `orchestral`, `upbeat`, `chiptune`.

## Music length: intent, not bucket names

`openverse_search_music` takes **`length: 'tracks' | 'loops'`**:

- **`tracks`** (default) — full pieces, roughly 2–10 minutes.
- **`loops`** — shorter beds, roughly 30 seconds to 2 minutes.

This is deliberately *not* Openverse's own bucket vocabulary, because those names mislead: their
`short` bucket is 30s–2min and `medium` is 2–10min, so asking for "short" music gets you the
opposite of a short clip. The mapping is applied server-side; you never pass a raw bucket.

Sound effects have no length argument — that lane is pinned to clips under ~30s, and nothing it is
for lives outside that range.

## Result count and duration filtering

Pagination is hidden. Pass **`maxResults`** (default 20, max 100); the tool pages the underlying
endpoint internally, de-duplicating ids across page boundaries, and stops when it has enough or the
catalogue runs out. There are **no `page` args**.

`minDuration` / `maxDuration` are in **seconds** and applied client-side after fetching, so a tight
window can return fewer rows than `maxResults`. If `count` comes back low, raise `maxResults` or
widen the window. A row whose provider reported no duration is dropped only when a `minDuration`
was asked for.

## Result shape

```json
{
  "success": true, "requested": 20, "count": 18, "license": "cc0",
  "results": [
    {
      "id": "eab8a6e2-…", "title": "Deep Whoosh #1", "creator": "Kinoton",
      "duration_seconds": 3.2,
      "url": "https://cdn.freesound.org/previews/351/351256_2247456-hq.mp3",
      "provider": "freesound", "pack": "Transitions",
      "source_url": "https://freesound.org/people/Kinoton/sounds/351256",
      "filesize_bytes": 69196
    }
  ]
}
```

`url` is a 128 kbps MP3 on the provider's CDN — fine layered under video, but it is **not** a
mastered WAV, and the source WAV is behind the provider's OAuth download route and is not
fetchable. Say so if a user asks for lossless.

## Typical flows

**Add a transition whoosh to the sound library**

1. `openverse_search_sound_effects` — `{ query: "whoosh", maxResults: 20, maxDuration: 3 }`
2. Pick a result; `download_openverse_audio` — `{ url, fileName: "whoosh-transition" }`
3. Optionally `import_frontend_assets` to place it in a project's SOUND lane.

**Find a music bed for a 45-second clip**

1. `openverse_search_music` — `{ query: "lofi", length: "loops", maxResults: 30, minDuration: 45 }`
2. `download_openverse_audio` on the pick, then attach it to the project's MUSIC lane.

## What this is not

Community-uploaded public-domain music: good to decent, **not** a production library like Epidemic
Sound. Set that expectation rather than overselling it. For AI-composed music written to a brief,
that is the separate credit-metered music generation path (see `../../SKILL.md` → *Generation and
Rendering*), not this tool.

## Attribution notice

Openverse's terms require prominently indicating that a search was made using Openverse and is not
endorsed by it. The desktop panels carry that line. If you surface these results in your own UI or
document, carry it too.
