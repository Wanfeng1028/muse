# Qianrong AI · Book-Breakdown Video Pipeline

`qianrong-video-skill` — a code-only book-breakdown video pipeline with narration, beat-sync, and
machine-verified adversarial audit.

> **中文说明见 [README.zh-CN.md](README.zh-CN.md)** ｜ A Chinese guide is available at [README.zh-CN.md](README.zh-CN.md).
>
> **两条演示成片全程由 AI 对话驱动完成。** (Both demo films were produced entirely through AI conversation — no manual editing, no editing software.)

## Demo Films

### Density Flow + TTS Narration · *Awakening Creativity*

<p align="center">
  <a href="demo/qianrong-creative-60s.mp4">
    <img src="assets/demo-creative-poster.jpg" alt="Awakening Creativity — 60s density flow with TTS narration" width="42%">
  </a>
</p>

*60.0s · 1080×1920 vertical · 30fps · full Chinese narration — 直接下载：[demo/qianrong-creative-60s.mp4](demo/qianrong-creative-60s.mp4)*

17 card groups + 1 closing claim · BGM auto-ducks 8.4dB under voice · narration 47.28s (79% of runtime)

### Information Density Flow · *The Almanack of Naval Ravikant*

<p align="center">
  <a href="demo/qianrong-naval-60s.mp4">
    <img src="assets/demo-naval-poster.jpg" alt="The Almanack of Naval Ravikant — 60s information density flow" width="42%">
  </a>
</p>

*60.0s · 1080×1920 vertical · 30fps · BGM only — 直接下载：[demo/qianrong-naval-60s.mp4](demo/qianrong-naval-60s.mp4)*

22 card groups · ~2.7s per screen · purely visual, read from on-screen text

---

Build a product promo / feature / book-breakdown video **entirely from code plus real assets** —
no editor, no timeline scrubbing, no manual cutting. Built for people who can write code but don't
edit video.

The point is not the finished film. The point is that **every judgment about the film can be
disproven by a command**: "the motion feels weak" becomes a frame-difference number, "it looks like a
PPT" becomes a shot-length and in-shot-motion count, "the beat is off" becomes a millisecond offset,
"the narration doesn't fit" becomes a margin in seconds.

```text
1 Define pass line -> 2 Script -> 3 Real assets -> 3.5 Study references
      -> 4 Build composition -> 5 Render -> 6 Adversarial audit   (fail -> back to 4)
```

---

## Four Modes

One skeleton, four delivery modes. **Choose the mode before you start.**

| Mode | Duration | Cards | Audio | Use case |
|---|---|---|---|---|
| **A. 15s feed ad** | 15s | 4 shots × 1–2 cards | BGM | Douyin / WeChat Channels feed ads |
| **B. 60s minimal** | 60s | 6 groups | Mostly BGM | One concept, fully explained |
| **C. 60s density flow** | 60s | **22 groups** | BGM only | Book breakdown, self-read |
| **D. 60s density flow + TTS** | 60s | **17 groups + 1 claim** | **BGM + full narration** | Book breakdown, ear-led reading |

> **Within 60 seconds, "more cards" and "longer narration" are mutually exclusive.**
> At the measured 4.3 chars/sec, 22 card groups need ~100s of narration — 40% over runtime.
> To have both, extend to 75–90s. Otherwise pick one.
> Full derivation in `references/tts-narration.md`.

---

## Install

```bash
git clone https://github.com/yanghui960/qianrong-video-skill.git \
  ~/.agents/skills/qianrong-video-skill
```

The whole repo is then usable as the `qianrong-video-skill` skill. Entry point: `SKILL.md`.

### Dependencies

- **Node** (`npx hyperframes`) — default renderer. Renderer-agnostic; anything that outputs MP4 works.
- **Python 3.9+** with `numpy`, `scipy`, `librosa`, `Pillow`.
- **ffmpeg / ffprobe** on `PATH`.
- **Mode D additionally** needs `edge-tts` and `soundfile`.
- Optional: an OpenAI-compatible multimodal model for `vision_teardown.py`
  (set `VISION_ENDPOINT` / `VISION_MODEL` / `VISION_API_KEY`).

---

## Five-minute start

```bash
# 1. Copy the starter into your own film
cp -r assets/starter/qianrong-ai-promo ~/my-film && cd ~/my-film

# 2. Prove the toolchain works (0 errors out of the box)
npx hyperframes@0.8.147 check
npx hyperframes@0.8.147 render -o renders/smoke.mp4 --crf 24

# 3. Swap in your own copy / real covers / BGM, then run the six steps
```

The starter contains verified patterns: design tokens, real cover cards, "growing" entrances,
three-layer camera, and a closing beat of whitespace.

### Mode D (with TTS narration) — three extra steps

```bash
# 1. Write a narration script JSON (windows + copy), generate TTS, measure durations
python scripts/narration.py --script narrations/my-book.json --out-dir audio
#    -> exits 1 on any overflow; fix the copy or the window first

# 2. Lay narration into windows + duck the BGM, render the master
python scripts/mix_audio.py --vo audio/narration/vo_s1.mp3 ... --bgm assets/bgm.wav \
  --dur 60 --out assets/vo.wav --mix film/assets/mix.wav

# 3. Point film/index.html at mix.wav, then run check -> render -> audit
```

---

## The Six Steps

### 1. Define acceptance (most skipped, most expensive)

Write `ACCEPTANCE.md` first: one sentence defining "excellent," weighted scoring dimensions, and
**hard vetoes** (violating any one fails outright). Template: `references/acceptance-rubric.md`.

### 2. Write the creative brief

Produce a one-sentence core claim + per-shot copy table + visual language + shot list.
The opening 3 seconds must answer "why should I care" **in the viewer's own words**;
each shot does exactly one thing. See `references/creative-brief.md`.

### 3. Produce real assets

Iron rule: **if the product has real UI, capture the real UI; if there's real data, use the real numbers.**
Capture with Playwright at `deviceScaleFactor=2`; anything that "lives" must be recorded as real video.
See `references/asset-production.md`.

### 3.5. Tear down reference films (twice)

Tear down at least **3** major-studio films (one is a style, three is a pattern):

- **Quantitative**: `references/reference-teardown.md` — shot count/duration, intra-shot motion, beat offsets.
- **Semantic**: `references/multimodal-teardown.md` — timestamped keyframe sheets to a multimodal model,
  7 perspectives, finishing with `improve_ours` (reference vs. your film side by side).

The **four cross-film rules** live in `references/design-rules.md`. Read them before you start.

### 4. Build the composition

One master timeline; scenes explicitly declare start/end; **snap every beat to the music's real pulses** —
don't trust the labeled BPM; interpolate numbers per-frame; give every scene an ambient motion layer.
Never let the HUD layer ride the camera transform, or edge text gets pushed off-canvas.

**Three density-flow hard rules** (learned the hard way — see `references/tts-narration.md`):

- Cards must carry `min-height` to fill the layout (verified **13.5–22cqw**), otherwise short cards leave
  the lower half blank. `check` cannot detect whitespace — **extracting frames is the only way**.
- `.wall` uses `align-content:space-between` + `flex:1` with a flex-column parent, so grid rows spread out.
- Card entrances must complete within the **first 60% of the shot window**, or mid-shot frame extraction
  reveals "reserved blank" gaps.

### 5. Render

```bash
npx hyperframes@0.8.147 check                       # must be 0 errors
npx hyperframes@0.8.147 render -o renders/xxx.mp4 --crf 20
```

For slow full-screen push-ins, too low a CRF multiplies file size; CRF 20 is visually indistinguishable.

### 6. Adversarial audit (the real core)

Don't ask "does it look good." Ask **"which frame proves it's dead / fake / wrong"**, then measure.

```bash
python scripts/audit_video.py renders/xxx.mp4 \
  --total 60 --expect-res 1080x1920 --dur-tol 0.3 \
  --grid-json assets/beat-grid.json --bgm assets/bgm.wav \
  --countup "t0:t1:x:y:w:h" --typing "..." \
  --json evidence/audit.json        # exit 0 = pass, 1 = fail
```

It measures: spec, opening audio energy ratio, blocked motion (**frozen and low-motion reported separately**),
blank/black frames, beat offsets, push-in factor (in-region template matching), whether real video is playing,
and whether numbers progress continuously.

Details and thresholds: `references/audit-method.md`.

---

## Directory Structure

```text
qianrong-video-skill/
├── SKILL.md                     Skill entry: workflow, hard rules, which doc to read when
├── README.md                    This file (English)
├── README.zh-CN.md              Chinese documentation
├── demo/
│   ├── qianrong-creative-60s.mp4  Awakening Creativity — density flow + TTS narration
│   └── qianrong-naval-60s.mp4     Naval Ravikant — information density flow
├── references/
│   ├── acceptance-rubric.md     Acceptance criteria (dimensions + hard vetoes)
│   ├── creative-brief.md        Brief / shot list / visual language format
│   ├── asset-production.md      How to make real assets and not fake them
│   ├── design-rules.md          Four rules distilled from five reference films (with measurements)
│   ├── multimodal-teardown.md   Semantic teardown (call format + two pitfalls)
│   ├── reference-teardown.md    Quantitative teardown
│   ├── audit-method.md          Every check, threshold, and "how metrics lie"
│   ├── tts-narration.md         TTS narration pipeline, time-budget formula, seven pitfalls
│   └── pipeline-checklist.md    Shortest end-to-end checklist
├── scripts/
│   ├── audit_video.py           Adversarial auditor (exit 0/1 + JSON evidence)
│   ├── make_beat_grid.py        Real pulse beat grid from music
│   ├── make_frame_sheets.py     Video -> timestamped keyframe sheets
│   ├── vision_teardown.py       Keyframe sheets -> 7-perspective semantic teardown
│   ├── teardown_video.py        Six-axis quantitative teardown
│   ├── narration.py             Narration script -> TTS + duration measurement (exit 1 on overflow)
│   └── mix_audio.py             Narration into windows + BGM ducking -> master
└── assets/
    ├── demo-creative-poster.jpg Demo poster
    ├── demo-naval-poster.jpg    Demo poster
    ├── fonts/                   JetBrains Mono (OFL)
    └── starter/qianrong-ai-promo/  Runnable 15s skeleton (0 errors out of the box)
```

---

## License

MIT. Third-party components and font licenses: see `THIRD_PARTY_NOTICES.md`.

---

**By Qianrong AI** · WeChat Official Account「千容AI」· Book-Breakdown Video Pipeline
