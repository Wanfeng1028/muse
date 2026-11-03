# Failures: symptom → cause → fix

Collected from building this skill and from issues reported against other video skills (playwright-recast, video-use, HyperFrames, Remotion skills, demo-video-skill, testreel).

## Recording

| Symptom | Cause | Fix |
|---|---|---|
| `'fill' has no arguments` | unquoted `#` in YAML started a comment | quote the action: `- 'fill #email \| a@b.c'` |
| `matches N elements` | selector not unique (strict mode) | use `--discover` output; add `data-testid`, `>> nth=0` only as last resort |
| `is covered by another element` | modal, toast, sticky header or cookie banner on top | hidden step to close it; scroll; wait for the overlay to leave |
| `centre … is outside the viewport` | element off-screen after scroll (sticky layouts) | `scroll SEL` before, or larger viewport |
| exit 3, no video | context never closed (crash) or disk full | re-run; the script always closes in `finally`, check stderr |
| cursor missing after navigation | new document; cursor appears on first move | record.py re-moves the mouse after navigations; if still missing, add `hover` |
| `offset_method: none` | `--no-flash`, or the app painted over the flash | re-take without `--no-flash`; or `calibrate.py RUN --set 0.1` after checking a click frame |
| native dropdown/file picker not visible | DOM cursor and video see only the page | caption it, or record that part with the OS recorder (`references/record.md`) and use edit-only |
| SSO page in a profile take | profile signed out, or import could not decrypt cookies | `browser_profile.py check`; then `login NAME URL` |
| `ProcessSingleton` / profile in use | another take or `login` window still holds the profile | close it; one process per profile |
| Keychain prompt during a take (macOS) | first use of the Chrome Safe Storage key | allow it once, or use `login` instead of `import` |
| password in trace | Playwright records `fill()` values | always run `redact.py`; prefer `storage_state` over typed logins |

## Editing and rendering

| Symptom | Cause | Fix |
|---|---|---|
| sped-up clip not shorter | missing `fps=30` after `concat` | edl.py adds it; keep it in hand recipes |
| empty clip after `trim … tpad` / `select … tpad` | tpad on a filtered stream with no frames | hold with `trim=start_frame=K:end_frame=K+1, loop=…, setpts=N/(30*TB)` |
| `xfade` timebase error | inputs differ in timebase | `settb=AVTB,fps=30` on both |
| whole frame tinted green | ffmpeg 8.x `overlay` chose yuva444p | `format=yuv420` on overlay, `format=yuv420p` after; verify.py detects it |
| zoom off target | wrong offset, or viewport differs from event `w/h` | calibrate; keep storyboard viewport = take viewport |
| zoom shaky | integer pixel steps in zoompan | final render supersamples 2x (draft does not) |
| boxes instead of letters | font lacks glyphs (Vietnamese, CJK) | `WEB_VIDEO_FONT=/path/to/font.ttf` |
| `No such filter: drawtext` | ffmpeg built without freetype (Homebrew `ffmpeg` 8+) | macOS: `brew install ffmpeg-full` and put `$(brew --prefix ffmpeg-full)/bin` first on PATH; elsewhere a full build |
| `Error splitting the argument list: Option not found` | ffmpeg 8 removed `-filter_complex_script` | use `-/filter_complex file`; edl.py picks the form by ffmpeg version |
| filter error mentioning quotes or `:` | text in the filter string | edl.py always uses textfiles; do the same in hand edits |
| micro-stutter | hold shorter than 0.2 s | edl.py skips those (`MIN_HOLD`) |
| clicks/pops in narration | `-c copy` concat of AAC | re-encode continuously, 30 ms fades (edl.py does) |
| `loudnorm` crash or silence boosted | loudnorm on silent audio | edl.py does not use loudnorm |

## Narration

| Symptom | Cause | Fix |
|---|---|---|
| `piper voice not installed` | first use on this machine | `scripts/install_tts.py` (needs network once) |
| English word unintelligible | Vietnamese-only model, eSpeak fallback | Vietnamese label or phonetic spelling in `say:` |
| a tone or word comes out wrong | model error on that phrase | rephrase `say:`, or `--voice` another speaker |
| speech too fast | Piper default pace | `--speed 0.8` |
| number read digit by digit or wrong | unusual format (dates, versions) | write it out in `say:` ("phiên bản hai chấm ba") |
| narration much quieter/louder than before | old clips without loudnorm | re-run tts.py (clips are normalised to −16 LUFS) |

## Verification and delivery

| Symptom | Cause | Fix |
|---|---|---|
| duration check fails | graph changed without edl.json, or speed math off | re-run edl.py (it rewrites both) |
| blank frame at start (edit-only) | the recording starts black or with the sync flash | trim by hand: `ffmpeg -ss 1.2 -i …` before edit-only |
| `final.mp4` over 9 MB | long video or busy page | `--height 540`, shorten, split |
| `gh: unknown flag --attach` | gh < 2.99 or GHES | give the user files to drag in |

## Windows

| Symptom | Cause | Fix |
|---|---|---|
| `python3` not found | Windows installs `python` / `py` | `PY=$(command -v python3 \|\| command -v python)` as in SKILL.md, or `py -3` |
| `UnicodeEncodeError` printing Vietnamese | cp1252 console | scripts reconfigure stdout to UTF-8; for other tools set `PYTHONIOENCODING=utf-8` |
| fonts or the source file copied into the run folder | symlinks need Developer Mode | harmless: `link_or_copy` falls back to hard link, then copy |
| `ffmpeg` not found after `winget install Gyan.FFmpeg` | PATH refreshed only in new shells | open a new terminal |
| narration fails with `say` | macOS only | `install_tts.py` (Piper works on Windows) |

## Process

- Do not trust `requestAnimationFrame` timing under headless capture for frame-accurate work (fine for paint flushes).
- Do not detect blank lead-ins from PNG file sizes; use the sync flash.
- Quality depends on the model following prose; that is why timing, filters and redaction live in tested scripts. Run `selftest.py` after any script change and `lint_skill.py` after any doc change.
