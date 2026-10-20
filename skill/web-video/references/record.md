# Recording a take

`scripts/record.py` drives Chromium through the storyboard. Three modes share the same action code, so a passing rehearsal predicts a passing take.

| Mode | Video | Use |
|---|---|---|
| `--discover` | no | before each step, prints visible interactive elements with a suggested selector (also `discover.json` in the cwd) |
| `--rehearse` | no | runs everything fast; prints `ok step N` or `FAIL` plus the element list; for bug-report prints whether the bug step was reached and which errors fired |
| take (`--slug` or `--out`) | yes | full speed with cursor glide; writes the run folder |

Common options: `--headed` (watch it), `--timeout 15000` (slow apps), `--no-flash` (skip the sync flash; offset becomes unknown).

## What a take does

1. New context at the storyboard viewport with `record_video`, HAR (`embed` bodies in bug-report, `omit` in feature-demo), tracing (screenshots + snapshots), optional `storage_state`.
2. Injects a DOM cursor (arrow SVG) that follows `mousemove` and a red ripple on `mousedown`. Playwright video has no cursor of its own.
3. **Sync flash:** dark page 0.7 s, then magenta; logs a `flash` event. `calibrate.py` finds the first magenta frame and stores `video_offset = video time − event time` (typically −0.05 to +0.2 s).
4. Runs steps. Clicks: wait visible → exactly one match → scroll into view → centre inside viewport → `elementFromPoint` hits the element (not covered) → glide (12-45 mouse steps) → 250 ms → log `click` → click. Any failed check stops the take (exit 2) and keeps the artifacts.
5. Logs errors as they happen: console `error`, `pageerror`, HTTP ≥ 400, failed requests (except aborted navigations).
6. On a `bug: true` step logs `bug` after the settle wait, with the box of `bug_target` or the last clicked element.
7. Closes the context in `finally` (flushes video and HAR), moves the video to `raw.webm`, ffprobes it (exit 3 if missing or empty), calibrates, writes `meta.json`.

## Persistent profiles (signed-in user, SSO)

`--profile NAME` (or `profile:` in the storyboard) runs the take in `launch_persistent_context` on a Chromium
user-data dir under `~/.cache/web-video/profiles/NAME` (`WEB_VIDEO_PROFILE_ROOT` overrides; a path also works).
`scripts/browser_profile.py` manages them:

| Command | Does |
|---|---|
| `chrome-profiles` | list Chrome profiles on this machine (dir, name, account) |
| `import NAME --from-chrome "Profile 1" [--replace]` | copy cookies, site storage and `Local State` from that Chrome profile |
| `login NAME URL` | open a real Chrome window without automation flags; the user signs in and closes it |
| `check NAME URL [--expect-status-url URL]` | headless load; exit 1 when the status URL is not 200 |
| `list`, `delete NAME` | inventory and cleanup |

Rules and limits:

- The live Chrome profile is never used directly: Chrome locks it while running, and Chrome 136+ refuses
  automation on its default user-data dir. `import` makes a separate copy instead.
- The take uses installed Chrome (`channel: chrome`, the default when Chrome exists) and drops Playwright's
  `--use-mock-keychain` and `--password-store=basic`, so cookies copied from Chrome decrypt with the user's
  Keychain key (macOS). macOS may ask once for Keychain access to "Chrome Safe Storage".
- Windows: Chrome 127+ binds cookie encryption to the Chrome install (app-bound encryption); an imported copy
  can come up signed out. Use `login` there.
- `login` removes `--enable-automation` and sets `--disable-blink-features=AutomationControlled`, because
  Google sign-in rejects windows that announce automation. Takes keep the normal flags.
- The profile opens with a blank or restored tab; record.py closes it and records its own page.
- `import` copies cookies, site storage and preferences only. It never copies saved passwords (`Login Data`),
  autofill or payment data (`Web Data`), history or extensions, so a take cannot autofill personal data on camera.
- Session cookies (no expiry) are not written to disk when Chromium closes. `login` snapshots the cookies
  into `web-video-state.json` inside the profile every 2 s while the window is open, and every later launch
  re-adds the cookies the browser dropped. Wait a couple of seconds after signing in before closing the window.
- Each profile has a `web-video-profile.json` marker (source, keychain mode, channel). `delete` and
  `import --replace` refuse any folder outside the profile root that lacks it, so a mistyped path cannot wipe data.
- Keychain modes: `real` (default; imported or user sign-in, decrypts with the OS key) and `mock` (throwaway test
  profiles; never touches the OS keychain). `selftest.py` signs a `mock` profile into the fixture app and records
  a take with `--profile` and no login step.
- `meta.json` stores only the profile name. HAR and trace still contain cookies: run `redact.py` before
  sharing, and `delete` the profile when the video is done.

## Run folder

```
video-out/<slug>/v<N>/
  storyboard.yaml   copy used for this take
  raw.webm          VP8 ~25 fps at the viewport size
  events.json       {version, mode, viewport, video_offset, offset_method, secret_selectors, events[]}
  console.json      every console message with t
  net.har           all requests (bodies in bug-report)
  trace.zip         Playwright trace: open with `npx playwright show-trace trace.zip`
  meta.json         status ok/aborted, failed_step, versions, raw probe, offset, error count
```

Event kinds: `flash`, `flash_end`, `step {i, caption, hidden, bug}`, `step_end {i}`, `nav {url}`, `click {x,y,w,h,target,bbox}`, `hover`, `type {…, text (masked if secret), t_start}`, `fill`, `press {key}`, `select {…, value}`, `scroll {dy}`, `expect {target,bbox}`, `error {source: console|pageerror|http|network, …}`, `bug {i,bbox,errors_so_far}`, `fail {i,reason}`, `end`. `t` is seconds since the page was created (monotonic clock).

## Limits to tell the user

- `record_video` is about 25 fps VP8 at CSS-pixel size. Raising output fps only duplicates frames; zoom above 1.5x shows blur. For a crisper client video see `references/hifi-capture.md`.
- The DOM cursor cannot appear over native `<select>` lists, file pickers, print dialogs, browser permission prompts or OS windows. The video shows the result, not the open list. Say so in the caption, or record that part with the OS recorder (below) and edit it with `edl.py --edit-only`.
- Cross-origin iframes get the cursor only when the mouse is inside them.
- Animations and spinners play in real time; idle parts are sped up later, so do not add long `wait`s "for the video".
- Data changes during a take (the fixture app keeps added invoices until restart). Reset or seed data in hidden steps so every take looks the same.

## Recording something Playwright cannot drive

Record with the OS, always with a time limit so it stops on its own, then
`edl.py --edit-only out.mp4 --out video-out/<slug>/v1`:

| OS | Command |
|---|---|
| macOS | `screencapture -v -V 30 -k out.mov` (needs Screen Recording permission for the app that runs it) |
| Windows | `ffmpeg -f gdigrab -framerate 30 -t 30 -i desktop -pix_fmt yuv420p out.mp4`, or the user presses Win+Alt+R (Game Bar) |
| Linux (X11) | `ffmpeg -f x11grab -framerate 30 -t 30 -i :0.0 -pix_fmt yuv420p out.mp4` |

There is no event log, so no captions, zoom or bug panel: only idle speed-up and trimming.
