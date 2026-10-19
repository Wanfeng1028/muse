# Listening to the Source Audio (Phase 0.5)

Most screen recordings are silent, but some are **narrated live** — you talked through the
demo while recording. When that's the case, the audio is signal: it tells you what matters
and when. Phase 0.5 uses it to seed a smarter shot list. It's **gated** — on a silent
source it does nothing and the pipeline proceeds exactly as before.

## The gate

```bash
scripts/detect_silence.sh --video source.mov
```

This first checks for a meaningful audio track. If there's no audio stream, or the mean
volume is below the gate (default −50 dB — the real x402 demos measured ~−91 dB), it emits:

```json
{"has_audio": false, "reason": "effectively silent (...)", ...}
```

→ skip listening, go straight to the shot list. Only proceed with Phase 0.5 when
`has_audio` is `true`.

## Tier 1 — Silence detection (always available, zero extra deps)

Same command emits a segmentation when audio is present:

```json
{
  "has_audio": true,
  "mean_volume": -23.3,
  "duration": 15.0,
  "segments": [
    {"start": 0.00, "end": 4.00,  "kind": "speech",  "action": "keep"},
    {"start": 4.00, "end": 10.00, "kind": "silence", "dur": 6.00, "action": "cut"},
    {"start": 10.00,"end": 15.00, "kind": "speech",  "action": "keep"}
  ]
}
```

How to read the `action` hints when drafting the shot list:
- **keep** — a speech span; someone's talking, likely a real-time (1×) segment.
- **cut** — a long silent gap (≥ `--cut-threshold`, default 4 s); drop it.
- **speedup** — a short silent gap; montage / 8× candidate.

These are *suggestions* to pre-fill the shot list, not commands — you still decide the final
cuts against the visuals. Tune with `--noise` (silence threshold dB), `--min-silence`
(minimum gap length), and `--cut-threshold`.

## Tier 2 — Transcription (optional, whisper.cpp)

```bash
scripts/transcribe.sh --video source.mov --out-prefix mydemo-transcript
```

Emits `mydemo-transcript.json` (segments with `timestamps.from/to` + `text`) and a `.srt`.
If whisper.cpp or a model isn't installed, it prints setup steps and **no-ops** (exit 0) so
Tier 1 still carries the phase.

### Setup

```bash
brew install whisper-cpp
mkdir -p ~/.cache/whisper-cpp
curl -L -o ~/.cache/whisper-cpp/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```

`base.en` is a good default. Override with `--model PATH` or `$WHISPER_MODEL`; `--lang` for
non-English. The script resamples to 16 kHz mono WAV internally (whisper.cpp's requirement).

### How the transcript seeds the shot list

Read the transcript alongside the sampled frames. For each spoken segment you get *what was
said* and *when* — so you can:
- put segment boundaries where the narration changes topic, not just where the picture changes;
- pull the **Voice-over** column straight from what was actually said (tighten it, don't invent it);
- prioritise the moments the narrator emphasised.

### Scope note (v1)

This slice is **Tier 1 + transcript-seeded shot list**. Two deliberate non-goals, left as
clean follow-up increments:
- **Keep-the-live-narration as the soundtrack** — v1 still treats the final as silent and
  narration is added in Phase 5. Using the original track directly is a future option.
- **Word-accurate captions from the transcript** — transcript timestamps are in *source*
  time; after cutting and speed-ramping, they'd need remapping to *output* time through the
  shot list's per-segment `src in→out` + `speed`. v1 keeps captions segment-granular
  (Phase 5b); word-accurate remapping is the next increment.
