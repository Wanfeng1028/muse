# Connectra promo video (Remotion) — v2 (dark), v3 (light, editorial), v4 (polished v3 + sound)

Silent, code-rendered promo for Connectra: **one person controls a whole fleet of machines from one place, through any AI agent.**
1920×1080 @ 60fps, 3000 frames (50s). Flat, hairline, Linear/Vercel-style look; every UI is rebuilt as React components.

v2 keeps v1's scene order, copy intent and timing, but rebuilds the components from the **real Connectra Desktop UI**
(`connectra/desktop-tauri/src/App.tsx` + `styles.css`) and x-connectra.com's panels (Inter + Geist Mono, neutral surfaces).

## Preview

```bash
npm install
npm run studio        # Remotion Studio
```

`ConnectraPromo` is the full video; each scene is also registered as `Scene-<id>`.

## Render

```bash
npm run render        # → out/connectra-v2.mp4 (h264 yuv420p, 1080p60, muted, crf 18)
npm run stills        # → out/stills-v2/*.png (13 stills)
```

v1 output (`out/connectra-draft.mp4`, `out/stills/`) is left untouched; v1 source is commit `77cfeb9`.

## Structure

```
src/
  theme.ts            colors, desk (real app dark tokens), fonts, SCENES durations, DEVICES  ← retime here
  copy.ts             ALL on-screen copy; title lines are {text, muted} (muted = gray line)  ← edit text here
  anim.ts             spring / typing helpers
  components/
    Desk.tsx          Connectra Desktop replica: DeskWindow, topbar + Live chip, bento, hero card,
                      status orb, approval banner (run_command, RISK, cwd, Deny / Allow Once), activity + Undo
    DeviceTable.tsx   flat hairline list of list_devices results (offline / online / running / updated)
    Chat.tsx          neutral chat primitives: user msg, assistant msg, tool-call row, exit result, stdout, composer
    Window.tsx        macOS window chrome (optional URL bar)
    Terminal.tsx, MacMini.tsx, Cursor.tsx, Spinner.tsx, Logo.tsx, Headline.tsx, Backdrop.tsx, SceneFade.tsx
  scenes/
    S1Problem.tsx     10 minis (readable first) → 10 terminals with real-looking logs → "10 machines. 10 terminals. One you."
    S2Connect.tsx     Desktop app goes Idle → Connected on mini-01; the device list fills in → "Every device."
    S3Command.tsx     chat: list_devices, then one run_command per device; device list running → updated
    S4AnyAgent.tsx    web assistant / IDE agent / CLI copilot cuts → triptych converging on Connectra
    S5Anyone.tsx      4 different panels: eval shards chat, fleet table, cargo test terminal, phone chat
    S6Trust.tsx       "Cloud requests. Local decides." + real approval banner, Allow Once → activity log
    S7Close.tsx       "Every agent. Every device. Connected by Connectra." + x-connectra.com
```

## Tweaking

- **Copy:** `src/copy.ts`. Muted title lines render gray; there is no per-word violet any more.
- **Timing:** `SCENES` in `src/theme.ts`; in-scene beats are constants at the top of each scene. If scene lengths change, update frames in `scripts/stills.mjs`.
- **Accent:** violet (`C.violet`) is used only for the logo, the running-row marker and the key action. Keep it that way.
- **Icons:** Phosphor (`@phosphor-icons/react`, the same set the desktop app uses). No emoji.

## Notes

- Remotion is pinned to **4.0.530** (4.0.531's `@remotion/cli` ships an empty `dist/render-queue/queue.js` that breaks the studio).
- Frames render as PNG so the H.264 output is standard `yuv420p`.
- Fonts load from Google Fonts via `@remotion/google-fonts` (network needed at render time).
- Honest behavior: agents call `list_devices`, then one `run_command` per device. `run_command` takes a structured argv + cwd
  (no shell chaining), so the commands shown are single argv commands, e.g. `./bin/agent-update --model latest --restart` in `~/agents`.
- Client UIs (web assistant, IDE, CLI copilot, phone) are generic, with no real product logos.

---

## v3 — light, editorial cut

A separate composition, **`ConnectraV3`**, with its own scenes and theme in `src/v3/`. v2 (`ConnectraPromo`) is untouched.
Same story beats and copy (`src/copy.ts`, reused), different mood: warm paper, near-black ink, huge type, soft shadows
instead of borders, slow eased camera moves and long cross-dissolves, one accent (Connectra violet) used sparingly.

```bash
npm run render:v3     # → out/connectra-v3.mp4 (h264 yuv420p, 1080p60, muted, 50s)
npm run stills:v3     # → out/stills-v3/*.png (14 stills)
```

In the Studio: `ConnectraV3` is the full cut; each scene is registered as `V3-<id>`.

```
src/v3/
  theme.ts            paper/ink palette, soft shadows, L = Connectra Desktop LIGHT tokens (styles.css :root),
                      SCENES3 durations + OVERLAP (scenes cross-dissolve; total = sum − 6 × OVERLAP = 3000)
  anim.ts             long ease-out entrances, ease-in-out camera keys
  Video3.tsx          overlapping Sequences + dissolve
  components/
    Fleet.tsx         isometric fleet: 10 aluminium minis (top face, two-tone sides, USB-C/jack/LED on the front),
                      Connectra as a violet puck in the middle, ground hairlines, accent pulses, status dots
    DeskLight.tsx     Connectra Desktop replica in the app's light theme (the app's default theme)
    Chrome.tsx        light macOS window, light terminal text, Hub
    ChatLight.tsx     neutral chat primitives (bubble, tool rows, composer)
    Type.tsx          Display (huge headline) + Lede; Paper.tsx (paper + Camera); Pointer.tsx
  scenes/             S1Problem … S7Close (same beats as v2)
```

Retime in `SCENES3`; in-scene beats are constants at the top of each scene. If scene lengths change, update `scripts/stills-v3.mjs`.

## v3 with sound — narration, music, SFX

Composition `ConnectraV3Sound` (`src/v3/Sound.tsx`) = the `ConnectraV3` picture plus:

- **Narration**: 7 lines from `src/v3/vo-script.json` (absolute start frames), ElevenLabs voice "George",
  `eleven_multilingual_v2`. Generate: `ELEVENLABS_API_KEY=… python3 scripts/vo-elevenlabs.py`
  (`--audition` renders every line for a few candidate voices; `--only 03-command` regenerates one line).
  It writes `public/audio/vo/<id>.mp3` and `src/v3/vo-manifest.json` (durations drive the music ducking).
  Fallback, no key needed: `.venv-tts/bin/python scripts/vo-kokoro.py` (Kokoro-82M, voice `af_heart`).
- **Music + SFX**: `npm run audio:v3` (= `scripts/make-audio.py`) synthesizes `public/audio/music-v3.wav`
  (one chord per scene, bloom on the logo) and `public/audio/sfx/*.wav`. Cue frames live in `CUES` in Sound.tsx.
- **Mix**: music bed 0.34, ducked to 0.095 under each VO line (12-frame down / 24-frame up ramps).
  VO sits ~9–14 dB above the bed. Stems for checking: `--props='{"vo":false}'` or `'{"bed":false}'`.
- **Render**: `npm run render:v3-sound` → `out/connectra-v3-sound.raw.mp4`, then
  `scripts/master-audio.mjs` does a two-pass EBU R128 loudnorm (−16 LUFS, −1.5 dBTP, video stream-copied)
  → `out/connectra-v3-sound.mp4`.
- Licences / attribution: see `CREDITS.md` (free-tier ElevenLabs voice = attribution, non-commercial).

## v4 — polished v3 with sound (`ConnectraV4`)

This builds on the v3 edit and v3-sound after design feedback. The v1/v2/v3/v3-sound compositions are unchanged. The v4 code lives in `src/v4/`, forked from `src/v3/`.

```bash
npm run render:v4     # -> out/connectra-v4.mp4 (1080p60, 50 s, AAC 320k, mastered to -16 LUFS / < -1.5 dBTP)
npm run stills:v4     # 14 named review stills -> out/stills-v4/
npm run audit:v4      # ~230 half-scale frames (every 15 f + mid-animation extras) -> out/audit-v4/
npm run check:fleet   # geometric overlap check for every fleet ring layout + morph in-betweens
```

Also registered: `ConnectraV4Picture` (muted) and `V4-<scene>` per-scene compositions.

**What changed vs v3-sound**
- **Design rules.** The rules come from Jakub Krehel's skills (`docs/skills/`): concentric radii (outer = inner + padding), shadow rings instead of borders, one filled primary action, spacing instead of dividers for grouping, tabular numbers, weight ≥ 400 below 18 px, and press scale 0.96.
- **Contrast.** `src/v4/theme.ts` holds tokens measured against the paper background `#f4f2ed`:
  - ink2 `#34343a` (11.1:1)
  - ink3 `#5c5850` (6.3:1; this was 3.2:1)
  - ink4 `#86817a` (3.45:1; large display text only)
  - text-safe accent tokens: violet `#6a3df0`, green `#047857` and amber `#b45309`
  - light-window muted/faint `#5f5f68` / `#6b6b73`

  All body and secondary text now meets WCAG AA.
- **Fleet.** The isometric fleet is rebuilt from pure geometry (`src/v4/components/fleetGeom.ts`, with layouts in `fleetCfgs.ts`):
  - 10 minis sit on an ellipse around the hub, with labels placed radially outward.
  - Boxes are depth-sorted.
  - `scripts/check-fleet.ts` asserts minimum gaps between boxes, labels, the hub and spokes, and keeps each layout inside its screen region.
  - In S1 the terminals form a 5×2 grid that no longer covers the ring.
  - In S2 the ring morphs smoothly to its captioned layout; the camera no longer pans.
- **Approval (S6).** The panel is redesigned as a single calm light card:
  - It shows the header ("Approval needed", who / which device / timeout) and a light inset band with `run_command`, the command, the working directory and a small amber "High risk" dot.
  - It ends with Deny (neutral) and Allow once (the only filled button).
  - The dark code block, stacked badges and nested borders are gone.
  - The activity feed uses hairline rows and an Undo button.
- **Narration.** The script is rewritten to be conversational (`src/v4/vo-script.json`). It is voiced by ElevenLabs "Liam" on `eleven_v4` with audio tags; see CREDITS.md. Each line gets its own trim (`VO_GAIN` in `src/v4/Sound.tsx`), and the music ducks to 0.085 under speech (0.34 otherwise).
