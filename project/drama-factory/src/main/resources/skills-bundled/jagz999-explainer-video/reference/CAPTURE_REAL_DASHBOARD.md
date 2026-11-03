# Capturing the real dashboard (for the "real screenshots" mode)

When the user wants the explainer to show their **actual product as-is** (not a stylized
recreation), capture real screens at high resolution from their logged-in session, then
animate over them (gentle zoom/pan + the crop-overlay 3D lifts in ARCHITECTURE.md).

Prefer **puppeteer** over the Claude-in-Chrome browser tools: the extension's screenshots
cap ~1456px and can't easily be saved to disk; puppeteer gives crisp 2x (2560×1440) PNGs
written straight to `screens/`.

## Workflow
1. **Identify the source Chrome profile** (chrome://version → Profile Path, e.g. `Profile 6`).
2. **Quit Chrome fully** (⌘Q — closing the window isn't enough), so the cookie DB unlocks.
3. **Seed a clean capture profile** (only auth, no extensions/tabs):
   ```
   ./scripts/seed_capture_profile.sh "Profile 6"      # → ./.capdir
   ```
   Copies `Cookies` (both legacy + `Network/Cookies`), `Local Storage`, `IndexedDB`,
   `Session Storage`, and the user-data-dir-root `Local State` (the cookie-encryption key,
   decryptable on the same machine/keychain).
4. **Edit `scripts/capture.js` CONFIG**: `BASE`, `LOGGED_IN_TEXT` (a string only present once
   signed in), and the **STEPS** (navigate / clickByText / typeInto / shot / scrollTo).
5. **Run it** (headful so a login is visible/possible):
   ```
   node scripts/capture.js          # writes screens/*.png, logs to capture.log
   ```
   If the copied session expired, the window waits up to 240s for a **manual login** — the
   user signs in once in that automation window; `.capdir` then persists for re-runs.

## Why these specific choices (don't "simplify" them away)
- **Clean seeded profile + `pipe:true` + `browser.newPage()`** — launching the user's *real*
  profile hangs on `Target.setDiscoverTargets timed out`. The clean profile launches instantly.
- **`clickByText` uses a real `page.click`** (tags the element, then clicks it) — in-page
  `el.click()` does NOT open custom/Radix comboboxes or fire some React buttons.
- **`typeInto` uses real `page.keyboard.type`** — setting `.value` often doesn't update React
  state, so the subsequent "Run/Generate" does nothing.
- **Patient login wait** polls the DOM without re-`goto` every tick (re-navigating interrupts
  an in-progress SSO redirect); it nudges `/` only every ~30s.
- **File logging + rejection handlers** — backgrounded `node` stdout is often not captured;
  read `capture.log` for progress/errors. (See PITFALLS.md.)

## What to capture
- Every screen full-frame, consistent theme (dark unless told otherwise).
- **Open the dropdowns** that list everything (scenarios, examples) and screenshot them open
  → lets the explainer say "…and N more".
- For interactive steps capture **before AND after** (type→encrypt, run→result, generate→
  artifact) so the explainer can crossfase between them.
- Tall pages: `scrollTo` + multiple shots.

## Finding selectors when a click misses
Dump the page's interactive elements once: `page.evaluate` over
`button,[role=button],[role=tab],[role=combobox],textarea` → log tag/role/innerText to a
file. That reveals whether "Generate" is a `tab` vs the action `button`, whether a control is
a native `<select>` (use `page.select`) or a custom `combobox` (click-to-open), etc.

## Then
Build the explainer in "real screenshots" mode (ARCHITECTURE.md → Two production modes), and
sync audio with AUDIO_SYNC.md.
