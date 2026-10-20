# Overlays

Built by `scripts/overlay.py`, assembled by `scripts/edl.py`. Every text goes through a UTF-8 file in `RUN/text/` with `expansion=none`, so quotes, colons, `%` and Vietnamese diacritics need no escaping. Fonts are symlinked into `RUN/text/` (default Arial Unicode on macOS, DejaVu on Linux; override with `WEB_VIDEO_FONT` / `WEB_VIDEO_MONO_FONT`).

## feature-demo

| Element | Look | Timing |
|---|---|---|
| Intro card | title 58 px centred on navy, optional `subtitle` | 2.0 s, fade in/out |
| Step caption | `N. caption`, 34 px white on black 68%, centred | from the step start to the next visible step |
| Caption side | bottom, or top when the step clicks below 55% of the height | per step |
| Click zoom | up to 1.5x centred on the click, 0.4 s ramps, pans between nearby actions | click −0.5 s → +1.3 s; typing for its whole duration |
| Outro card | `outro` text | 1.8 s, only if `outro` is set |
| Narration | per-step clip starts 0.15 s after the caption appears | step holds until the clip ends |

`edl.json.warnings` lists captions whose box may cover a clicked element (estimated before zoom). If one fires, shorten the caption or move the click target; verify.py repeats the warning.

Zoom options: `--zoom 1.3` (gentler), `--no-zoom`. Above 1.5x the 1x recording and the DOM cursor blur. Many actions close together give a continuous zoom that pans between them; that is intended. If it feels busy, add `wait` between steps or use `--zoom 1.25`.

## feature-demo with a theme

With `theme:` in the storyboard (the project's own theme from `theme.py init`; see `references/themes.md`) the layout changes: the recording is scaled into a frame on a 1920x1080 designed canvas, captions move to a band under the frame (no collision warnings, nothing covers the app), and the intro/outro cards come from the theme. Click zoom still runs inside the frame. Layers are PNGs in `RUN/theme/`. See `references/themes.md`.

## bug-report

| Element | Look | Timing |
|---|---|---|
| REC timestamp | `REC hh:mm:ss.mmm`, yellow mono, top-right of the app | burned in **before** cuts, so it shows true time and stops during holds |
| Side panel (440 px) | title, numbered steps, current step highlighted blue | whole video |
| Bug hold | frame frozen 2 s at the `bug` event | — |
| Red box + `BUG` tag | 5 px box around `bug_target` (or last clicked element) | bug moment → +4 s |
| EXPECTED / ACTUAL | green / red labels, wrapped text in the panel | from the bug moment to the end |
| Errors | up to 4 lines (HTTP status + method + URL tail, console text), red mono at the panel bottom | from the first error |

No zoom in bug-report: developers need the whole screen. The output is wider than the viewport (1280 + 440); export keeps the height.

## Narration audio

Providers (`tts.py --provider`):

| Provider | Where | Notes |
|---|---|---|
| `piper` (default for `lang: vi` once installed) | local, CPU, ~0.05 s per second of audio | Piper "csa-voice v3" by CakeByVPBank, MIT, 5 voices: `ngoclan` (default), `minhanh`, `thuha`, `yennhi` (nữ), `quanghuy` (nam). Installed by `scripts/install_tts.py` into `~/.cache/web-video/tts` (pinned HF commit, `MODEL_INFO.json` records repo, revision, licence, sha256). |
| `say` | local, macOS | `Linh` (vi) / `Samantha` (en); fallback when piper is not installed |
| `openai`, `elevenlabs` | cloud | only with `--allow-cloud` after the user agrees (Hard rule 2) |

Piper specifics:
- `--speed 0.9` is the default (about 3.5-4 words/s); `1.0` is brisk, `0.8` slow and clear.
- Numbers, `%`, `$`/`USD`, `đ`/`VND` are spelled out before synthesis (`1.500 USD` → "một nghìn năm trăm đô la"); `manifest.json` keeps both `text` and `spoken`.
- The model is trained on Vietnamese only: English words go through eSpeak and sound accented. "New invoice" is usually understood; short words like "Save" are not. Use the Vietnamese UI label, or spell it in `say:`.
- It can miss a tone now and then. Listen to the draft; rephrase the `say:` text if a word comes out wrong.

Mixing: every clip is converted to 48 kHz stereo AAC and normalised to −16 LUFS (`loudnorm`) in `tts.py`. `edl.py` then applies `aresample=48000, aformat=stereo, afade in/out 30 ms, adelay=<intro + caption start + 0.15 s>` per clip, `amix=normalize=0`, `apad`, `atrim` to the video length. Never `-c copy` concatenate audio pieces: AAC priming adds clicks and drift.

## Changing the look

Edit constants at the top of `scripts/overlay.py` (`CAPTION_SIZE`, `PANEL_W`, `CARD_BG`, `PANEL_BG`) and run `scripts/selftest.py`. Keep `format=yuv420p` after anything that overlays images: ffmpeg 8.x picks yuva444p for `overlay` and tints whites green (verify.py checks for this).
