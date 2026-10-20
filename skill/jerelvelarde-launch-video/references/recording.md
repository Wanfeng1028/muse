# Record the application, at a useful size

## Choose the real scenario

Inspect the current app or referenced PR and confirm the relevant behavior exists. A video of an older version can misrepresent a new feature. Record an explicit task with a visible beginning, meaningful action, and clear result. Use a disposable/demo account and data appropriate for sharing.

Do not substitute synthetic assistant outputs for a requested actual recording. Genuine tool calls, approval, document creation, terminal results, and file receipts should come from the application. If a live run fails, preserve the take, fix the actual issue within scope or explain the limitation; don't paint a success over it.

## UI size versus editorial zoom

When asked to make the UI 135–150%, enlarge the UI **before recording**. Prefer the app's own density/text settings or real browser zoom. A temporary CSS `zoom` on a dedicated recording page can provide layout reflow, but it is not identical to native browser zoom; inspect fixed headers, portals, hit targets, and responsive breakpoints. Do not modify the app's source merely to improve a recording unless authorized.

The helper `gtm-os/tools/capture.mjs` offers explicit layout zoom in a fresh Playwright context. It saves a preflight screenshot so the result can be inspected. It does not crop a finished video. Device scale factor affects capture pixels and is not a substitute for making text and components larger.

For desktop, start with a 1920×1080 capture viewport and enough UI zoom for the intended in-film panel. For genuinely native 4K source, use and verify a 3840×2160 recorder; adjust the layout/text sizing so the doubled viewport does not merely show twice as much tiny UI. Mobile needs its own responsive layout, not a desktop crop.

## Capture mechanics

- Use a separate browser context. Never export a normal browser profile or credentials with media.
- Hide notifications and irrelevant chrome. Keep meaningful cursor motion and short pauses around actions.
- Wait on actual UI states rather than assuming the agent finishes after a fixed delay. Explicit hold durations are for readability, not evidence of successful completion.
- Close the recording context to flush the video before probing or copying it. Playwright's recorder typically produces 25 fps WebM; check the actual output. A 30 fps transcode does not add motion detail.
- A screenshot sequence sampled at 4 fps remains a 4 fps source even inside a 30 fps file. Prefer a new continuous capture for smooth UI.
- Keep raw takes. Derive edits with documented in/out points and speed changes. Avoid speeding an approval or receipt so much that it disappears.

Record native width/height, recorded frame rate, known acquisition cadence, capture tool, UI zoom, duration, trimming, and speed in the media manifest. Use `media-report.py --decode` to probe and decode the actual file. Its container FPS cannot establish the original acquisition cadence by itself.
