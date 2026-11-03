# Troubleshooting

## Transcription (ASR)

- **Backend:** the skill uses `scripts/transcribe.py` (faster-whisper, CPU int8) —
  NOT `hyperframes transcribe` (whisper-cpp is not built here). Verified working on
  Python 3.14. See `_fixtures/ENV_NOTES.md`.
- **First run downloads a model** (`small` ≈ 484 MB) to `~/.cache/huggingface`.
  Export `HF_HUB_DISABLE_SYMLINKS_WARNING=1` to silence the Windows symlink warning.
- **French accuracy:** default `--model small`. For hard/accented audio use
  `--model medium` or `--model large-v3`.
- **Wrong language detected:** pass `--lang fr` explicitly (default). Use
  `--lang auto` only when the source language is unknown.
- **faster-whisper missing:** `python -m pip install -U faster-whisper`.

## Bad-clip decision gate (refuse rather than ship garbage)

- **Near-silent / no speech:** whisper hallucinates ("Merci.", "Sous-titres…") over
  silence. If a segment has no real speech, don't caption fabricated words — drop it.
- **Transcript is gibberish:** heavy accent / noise can transcribe to confident
  nonsense. Sanity-read `transcript.json`; if it doesn't parse as French, try
  `--model medium`, else skip captions for that clip.
- **Source already has burned-in captions:** adding a second caption system
  conflicts — skip captions (reframe only) or refuse.
- **facecam with hard cuts / multiple speakers:** the embedded-captions matte
  flickers across cuts. Either split the segment per shot, or fall back to
  `--caption-mode ass` (no matte, just burned karaoke).

## Reframe

- **Face cut off:** re-check `face_center_x` on a sampled frame (see `reframe.md`).
  The crop is fixed; pick where the speaker spends most of the clip.
- **Output not 1080x1920:** all reframe scripts force it; if not, the source had an
  odd SAR — the scripts apply `setsar=1`, but verify with `ffprobe`.

## Captions burn-in

- **`subtitles` filter "Invalid argument" / colon error:** you are passing a
  drive-colon path to the filter. Use `captions_burn.sh` (chdir + relative paths);
  don't hand-escape. See `captions-gameplay.md`.
- **Wrong/missing font:** confirm `assets/fonts/*.ttf` exists and the family name
  matches (`CAPTION_FONT_FAMILY`, default `DejaVu Sans`).

## Intake

- **yt-dlp missing:** `python -m pip install -U yt-dlp`.
- **Age/region-locked YouTube:** pass cookies to yt-dlp, or download manually and
  feed the local file instead.

## Accents render as boxes

The bundled DejaVu Sans Bold covers Latin accents. If you swapped fonts, ensure the
new font has the glyphs, or accents will tofu.
