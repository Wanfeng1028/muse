# Third-party notices

## TTS narration (Mode D)

- **`edge-tts`** — MIT License. Used to synthesize Chinese narration via Microsoft Edge's
  online TTS service. Narration audio is generated at runtime from your own script; no third-party
  audio is bundled in this repository.
- **Voices** — `zh-CN-YunyangNeural` (male, news/professional) is the recommended default for
  knowledge content; `zh-CN-XiaoxiaoNeural` (female, warm) is the recommended default for
  healing/emotional content. Voice availability is subject to the upstream service.

## BGM (synthesized)

- **`scripts/generate_bgm_longform.py`** synthesizes a royalty-free track from Python stdlib only
  (`wave`/`math`/`random`) — no samples, no third-party audio. The generated WAV is CC0.
  **Replace it with licensed music before commercial use if you prefer**, and record the license.

## Demo films (demo/)

- Both demo films are original works produced by Qianrong AI using this pipeline.
  Book titles and quoted concepts remain the property of their respective rights holders;
  on-screen cards explicitly mark `原书概念 · 释义` (concept, paraphrased — not verbatim quotation),
  and the composition carries a persistent "释义非原书引文" honesty notice.

## Fonts (assets/fonts/)

- **JetBrains Mono** — SIL Open Font License 1.1. Bundled subset used by the starter composition.
  If you add Noto Sans CJK SC, Smiley Sans, or others, keep their license files alongside.

## Starter assets (assets/starter/my-film/)

- **`assets/covers/*.jpg`** — generated placeholder art created by the packaging script, dedicated to
  the public domain (CC0). They are deliberately obvious placeholders; replace them with your own
  real covers.
- **`assets/bgm.mp3`** — a synthesized 12s tone generated with `ffmpeg -f lavfi` for the smoke test,
  dual-licensed CC0 / public domain. **It is not music.** Replace it before any real use, and record
  the license of the track you choose.

## Third-party geometry (if you reuse platform icons)

Any brand-icons you add stay the property of their owners. Use them only for identification —
never as your own brand, and never to imply endorsement.

## Provenance rule

Every non-original asset in a film you ship must have a recorded source and license. The starter
ships CC0-only so the smoke test is clean; everything you substitute is on you to clear.
