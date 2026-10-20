# Export and delivery

```bash
$PY $WV/scripts/export.py RUN/edited.mp4 RUN/final.mp4 [--max-mb 9] [--height 720] [--gif RUN/final.gif] [--gif-width 800]
```
H.264 `yuv420p`, AAC 128k (if audio), `+faststart`, height capped at 720. CRF 26 first; if over `--max-mb`, a 2-pass encode at the bitrate that fits (floor 150 kb/s). It warns when the target is still missed.

## Where it goes

| Destination | Format | Limit | Notes |
|---|---|---|---|
| GitHub issue/PR | MP4/MOV/WebM | 10 MB (free repo), 100 MB (paid) | default target 9 MB; `gh ... --attach` from gh 2.99, github.com only |
| Slack | MP4 H.264 + AAC | large (secondhand: up to 1 GB on paid plans) | faststart makes it play at once |
| Jira | MP4/WebM | admin-configured, often 10 MB | ask the user; keep a ≤ 10 MB version |
| Linear | MP4 | not confirmed | keep ≤ 10 MB |
| Email to a client | MP4 | attachments ~20-25 MB | or share a link the user chooses |
| GIF preview | GIF, 10 fps, 800 px | 2-5x larger than MP4 | only when asked or where video does not play |

Avoid WebM/VP9 for clients: Safari/iOS and many viewers handle it poorly.

## When the file is too big

1. `--height 540`, then check in the contact sheet that captions and the bug panel are still readable.
2. Shorten: fewer steps, less `wait`, split into two videos.
3. Lower `--max-mb` only if the platform demands it; quality drops fast below ~300 kb/s for UI text.

## Package

- feature-demo: `final.mp4` + `summary.txt` (steps and a suggested client message in the storyboard language) + optional `captions.srt` (soft subtitles or translation).
- bug-report: `final.mp4` + `bug-report.md` + `trace.redacted.zip` + `net.redacted.har` + `console.redacted.json`.

Give the user the folder path and the text. Posting, emailing or uploading is their call (Hard rule 2).
