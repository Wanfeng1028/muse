# Pitfalls (each cost real debugging time)

## Shell / process
- **`pkill -f "<pattern>"` self-kills the running shell.** `pkill -f` matches against the
  *full command line of every process* — including the very shell running your command, if
  the pattern text appears there (e.g. the launch command contains `.capdir` or
  `Google Chrome.*capdir`). Symptom: the command after the pkill silently never runs and
  the task "succeeds" with no output. Don't `pkill -f` a pattern that's present in the same
  command. Kill leftovers in a *separate* step, by PID, or clear locks inside Node instead.
- **A literal substring can make a whole command silently no-op** in some sandboxes (we saw
  commands containing a hidden-dir path like `.capdir` produce zero output / not execute).
  If a command mysteriously does nothing, remove unusual path tokens from the *shell* line
  (keep them inside the script file) and retry.
- **Background `node` stdout is often not captured.** A foreground `node -e` prints fine, but
  a backgrounded long script may show an empty log. Don't rely on `console.log` — write
  progress/errors to a file via `fs.appendFileSync`, and install
  `process.on('unhandledRejection'|'uncaughtException', e => log+exit)` so failures aren't
  swallowed (a rejected launch otherwise looks like "exit 0, no output").

## Puppeteer / browser capture (if you capture real UI)
- **Launching the user's *real* Chrome profile → `Target.setDiscoverTargets timed out`** (too
  many tabs/extensions/targets). Use a *clean* `userDataDir` seeded with only the auth you
  need (copy `Cookies`, `Local Storage`, `IndexedDB`, `Session Storage`, and the
  user-data-dir-root `Local State`). Launch with `pipe: true`, bumped `timeout`/
  `protocolTimeout`, and `browser.newPage()` (not a restored tab).
- **Cookie file path varies** — modern Chrome uses `Profile/Network/Cookies`, older uses
  `Profile/Cookies`. Copy to *both* locations in the clean profile.
- **Custom comboboxes / React buttons don't respond to in-page `el.click()`** (Radix/Headless
  open on pointer events). Use a real `page.click(selector)` (tag the element first), which
  dispatches pointerdown/up. Type with `page.keyboard.type` (updates React state) — setting
  `.value` often doesn't.
- **Patient login wait:** if auth didn't transfer, poll for the logged-in DOM WITHOUT
  re-navigating every tick (re-`goto` interrupts in-progress SSO). Nudge `/home` only every
  ~30s. The Claude-in-Chrome *extension* screenshots cap ~1456px and can't be filed easily —
  use puppeteer for high-res, saved-to-disk captures.

## ElevenLabs
- `/v1/music` caps around ~150s — crossfade-loop (`acrossfade`) to reach a longer target.
- TTS/SFX/music work even if the key lacks `user_read` (so `GET /v1/user` 401s) — validate
  with `GET /v1/voices`.
- Music/SFX occasionally come back near-silent — always `volumedetect`; regenerate if
  `max_volume < -30 dB`. Clap-type SFX often render quiet → boost their placement gain.

## Sync / rendering
- `select=gt(scene,...)` scene detection **fails on crossfades/smooth zooms** — use the
  motion-difference method in `AUDIO_SYNC.md` instead.
- Frame timing: tag frames by the player's logical `t`, never wall-clock (see ARCHITECTURE
  "Rendering & sync") — wall-clock drifts ~2%.
