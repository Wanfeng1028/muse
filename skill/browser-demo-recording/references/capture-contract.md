# Capture contract

## Prepare a real and repeatable take

- Verify the target, plan, viewport, browser, app readiness, and the exact output workspace before recording.
- Treat each action's `atMs` as a time relative to its scene, not a global timeline offset.
- Start with known, synthetic data whenever possible. Do not expose private records or persistent access links in frames, logs, manifests, or narration.
- Use stable accessible names, roles, or test IDs. Check uniqueness, visibility, enabled state, and unobscured hit targets before an action. Keep a catalog of stable anchors for shared chrome and prefer it to text or CSS selectors. A strict-mode duplicate often reveals a real app bug, such as a panel rendered twice; report it rather than picking the first match.
- Reset the demo data the plan changes before every take: restore changed rows, delete created ones, move date-anchored data to the recording day, and clear persisted preferences such as saved filters or pinned items. A take that passes once and fails on a re-run usually changed its own data.
- Record a production build on a fixed address, not a hot-reloading dev server, and do not change the served checkout during a run. A reload mid-capture puts an error page in the video.
- Type normally and let the app respond. If the expected result is absent, stop and repair the plan or app state; do not force a click, rewrite the page, or narrate around the failure.

## Frame for the viewer's screen

- The rendered video has the same pixel size as the plan's viewport; there is no high-DPI scaling. Course platforms expect at least 1280×720 at 16:9. A 1280×720 viewport keeps ordinary app text readable on a phone; use 1920×1080 only when the app's essential text stays legible after scaling a frame to phone size.
- Keep the screen clean: dismiss cookie banners, autofill and password prompts, tours, chat widgets, and notifications that are not part of the proof. Do this through demo data or app settings, not by rewriting the page.
- When captions are off, keep the proof away from the bottom edge, where player controls cover the frame. With captions on, the caption band sits below the recording and takes that space.
- Choose one pointing style per series and record it in the plan: a cursor that moves with purpose and rests on the target, or optional zoom. When narration describes an area without clicking it, use a `focus` action instead of wiggling the cursor; it zooms onto the area only if the plan enables zoom. Never circle or wiggle the cursor to point. Some channels forbid zoom, so check the brief before enabling it.

## Keep the interaction understandable

Use direct, purposeful cursor travel and pause briefly at the target. Avoid teleports, slow creeping during narration, excessive zooms, and motion that exists only to fill time. Maintain a continuous cursor position across scene cuts when the camera context is unchanged.

At each transition, hold the completed result long enough to read it, finish the thought while it is visible, leave a quiet gap, and orient the viewer to the next composition before acting. Keep the final third at the same human pace as the opening.

## Capture evidence

Bind the recording to the exact plan and record target version, viewport, scene order, semantic actions, assertions, and output hashes. For each state-changing action, verify the resulting product state, not merely that the browser dispatched an event. Review the full frame before and after a resize or layout change.

Watch the page for the whole take. An app error page, an error toast, or a server (5xx) response fails the take, even when the media audit later passes. Keep the noise allowlist short and tested, and refuse unexpected network origins: a new third-party request can be a privacy problem.

Keep capture and generated media inside the run workspace. Clean up only that declared workspace after review; never remove source files or user data as part of cleanup.

## Narration and optional providers

The default is captioned and does not need a paid API key. The user may choose their own recording or an optional voice provider; disclose any external service and follow its current data-handling and license terms. Keep natural speaking pace—no forced words-per-minute target or time-compression trick.
