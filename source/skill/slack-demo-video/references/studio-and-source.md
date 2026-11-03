# Studio and source map

Resolve the toolkit from the repository's `gtm-os` or this installed skill's `assets/gtm-os`. From that directory:

```sh
python3 tools/init-project.py /absolute/path/to/slack-demo
cd /absolute/path/to/slack-demo/05_Code
npm ci
npm run typecheck
npm run studio
```

Select `SlackThread`. It is a 31-second, 930-frame, 30 fps example on a 1920×1080 canvas. Studio's editable input props expose `clean`; true fills the viewport, false adds a title and disclosure wrapper. The clean default intentionally has no disclosure burn-in; preserve its illustrative status in delivery notes.

| File | Edit here |
| --- | --- |
| `src/slack-story.ts` | Synthetic text, event frames, send, thread, and approval centers |
| `src/SlackThread.tsx` | Native desktop layout, sliding thread, scroll, cursor, wrapper |
| `src/SlackUi.tsx` | Icons, avatars, messages, composers, and Block Kit-style primitives |
| `compositions.json` | Duration, dimensions, cadence, review frames |
| `remotion.config.ts` | CLI/Studio defaults |
| `public/asset-manifest.csv` | Imported asset sources and rights |

```sh
npm run review -- SlackThread
npm run render:slack
npm run render:slack:4k
npm run render:slack:prores
```

Outputs go to `out/`; stills go to a unique `review/` directory. Render commands protect existing exports. Choose a new filename for subsequent versions: `node render.mjs SlackThread out/slack-v2.mp4 1`. For a branded CLI cut, use `npx remotion render src/index.ts SlackThread out/slack-branded.mp4 --props='{"clean":false}'`, then decode/check that output with the toolkit media reporter; direct CLI rendering does not invoke the wrapper's verification.

This project requires Node 22+, npm, and FFmpeg/ffprobe. Remotion may download its browser on first use. It uses local fonts and synthetic content and needs no Slack account or token.
