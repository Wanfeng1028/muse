# X (Twitter) live search (headless / project-independent)

Ask anything about **posts, news, people, trends, or media on X/x.com in natural language** with the
`x_search` tool. A server-side Grok agent (xAI grok-4.3 + the `x_search` server-side tool) runs the
actual X keyword/semantic/user searches and thread fetches, then answers the query with **citations
(x.com post URLs)**. This tool is **standalone** — it does **not** use a Shorz project, `projectType`,
`settings.json`, PromptBar, Create Video, or any sidebar panel. Do **not** call `create_project` or
`read_project_settings` first.

**Prerequisites:** Shorz running + MCP connected (per `../../SKILL.md`) **and signed in to Shorz**.
The xAI API key lives server-side on the Shorz proxy; the tool attaches the signed-in user's token,
so a signed-out call returns `{ success:false, status:401, error:"Sign in to Shorz to search X." }`.

**⚠ Spends Shorz credits.** Unlike the free Pexels tools, `x_search` is **metered**: tokens
(input/cached/output) **plus a per-search fee** for every X search Grok runs — typically **a few
credits per call**. The response reports `usage`, `credits_charged`, and the remaining `balance`.
Check `get_shorz_credits` first if unsure, and mention the cost when the user asks for many searches.
The weekly **free tier does not extend here** — it only zero-rates a free render's own main-AI chat
and transcription, so a zero-balance user gets a 402 on `x_search`.

**Async by default.** `x_search` returns `{ started, jobId }` immediately (Grok agentic runs can
exceed MCP request timeouts, especially with video understanding). Poll `get_job_status { jobId }`
until `lastStatus` is `completed` — `result` then carries the same shaped payload as the blocking
form (`text`, `citations`, `searches_run`, `usage`, credits) — or `error`. Pass
`awaitCompletion: true` for the old blocking single response only if your tool-call timeout exceeds
~5 minutes. **Never re-call `x_search` because a poll timed out — the job is still running and a
retry bills again.**

## Tool

| Tool | Purpose | Required | Optional args |
|---|---|---|---|
| `x_search` | Natural-language X search with citations | `query` | `allowedHandles`, `excludedHandles`, `fromDate`, `toDate`, `enableImageUnderstanding`, `enableVideoUnderstanding`, `includeMediaUrls`, `maxOutputTokens`, `instructions`, `awaitCompletion` |

## Parameters (the full xAI x_search filter set)

- **`query`** — the natural-language ask. This carries almost everything: topic, "latest news
  about …", sentiment, people ("what is @user posting about?"), media-only posts, thread lookups,
  result count ("give me 10 posts"), language, etc. Grok decides which X searches to run from it.
- **`allowedHandles`** — search **only** posts from these X handles (max 20, `@` optional).
- **`excludedHandles`** — never include posts from these handles (max 20). **Mutually exclusive**
  with `allowedHandles`; the tool errors client-side (no credits spent) if both are set.
- **`fromDate`** / **`toDate`** — ISO `YYYY-MM-DD` bounds on the post date range. Unset = no bound
  (Grok favors recency on "latest/news" queries anyway; set them for a precise window).
- **`enableImageUnderstanding`** — let Grok analyze the **images inside** the posts it finds and
  describe/compare them. Costs extra tokens; leave unset for text-only queries.
- **`enableVideoUnderstanding`** — same for **videos** in posts (X-search exclusive). Extra tokens.
- **`includeMediaUrls`** — ask Grok to also write the **direct CDN media file URL** for each cited
  post's image/video (`pbs.twimg.com/media/...` for images, `video.twimg.com/.../*.mp4` for
  videos), not just the `x.com/i/status/<id>` post link. **Off by default** — by default Grok only
  cites the post link, even with media understanding enabled; set this whenever the caller needs a
  downloadable/embeddable URL (e.g. to hand to a downstream fetch/import step) rather than a link to
  browse. Under the hood this appends a fixed instruction to the request — you can get the same
  effect by asking for "direct video/image file URLs" in the query yourself, but the flag is
  more reliable than remembering the exact phrasing. **Best-effort, not guaranteed** — Grok
  sometimes still cites only the post link (e.g. for media it can't resolve a direct link for);
  if `citations` are only `x.com/.../status/<id>` links, re-ask more explicitly or accept the post
  link and resolve media separately.
- **`maxOutputTokens`** — cap on answer + reasoning tokens (default 8192, min 256, max 32768).
  A cap too low for the work truncates the answer: `status` comes back **not** `"completed"` and
  `incomplete_details` is populated — raise `maxOutputTokens` and re-ask if you see that.
- **`instructions`** — optional answer-style steering, e.g. `"Answer as a dated bullet list"`.
  Combined with `includeMediaUrls`'s instruction when both are set.

## Response shape

```jsonc
{
  "success": true,
  "text": "…the answer, grounded in the posts found…",
  "citations": ["https://x.com/i/status/2072342809034789088", "…"],  // deduped x.com post URLs
  "searches_run": [                       // the X searches Grok actually executed (auditable)
    { "name": "x_keyword_search", "input": { "query": "from:xai", "mode": "Latest" } }
  ],
  "usage": { "input_tokens": 3973, "cached_input_tokens": 2944, "output_tokens": 538, "x_search_calls": 1 },
  "status": "completed",       // != "completed" (+ incomplete_details set) if maxOutputTokens truncated it
  "credits_charged": 2,
  "balance": 998
}
```

Surface the `citations` links when presenting results so the user can open the underlying posts.
`searches_run` shows what was searched — useful when refining a follow-up query. If `status` is not
`"completed"`, the answer was cut short (usually `maxOutputTokens`); `incomplete_details` says why.

## Query patterns

- **News:** `query: "What's the latest news about <topic> on X this week?"` (+ `fromDate`/`toDate`).
- **A person/account:** `allowedHandles: ["handle"]`, `query: "Summarize what they posted about <topic>."`
- **Sentiment/trends:** `query: "What are people saying about <topic>? Summarize overall sentiment with examples."`
- **Posts with images/videos:** ask for media posts in the query and set
  `enableImageUnderstanding` / `enableVideoUnderstanding` so Grok can describe what the media shows.
  Add `includeMediaUrls: true` when you need the **direct file URL** of each image/video (to fetch,
  embed, or import), not just a link to the post.
- **Noise control:** `excludedHandles` for spam/parody accounts you want filtered out.

## Not a downloader

`x_search` **finds and summarizes** — even with `includeMediaUrls`, it returns URLs (post links or
direct CDN file links), not downloaded media files. To reuse a video/image from a found post in
Shorz, fetching that URL and importing it (e.g. `import_frontend_assets`) is a **separate** step;
`download_social_video` covers some platforms but X/Twitter is not currently one of them.
