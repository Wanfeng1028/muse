[![中文](https://img.shields.io/badge/%E4%B8%AD%E6%96%87-ece9e7?style=for-the-badge&labelColor=ece9e7&color=8a8785)](README.md)
[![English](https://img.shields.io/badge/English-a02128?style=for-the-badge)](README.en.md)

# video-scrub

Rebuilds a video as a clean file: **the picture and the sound come across, not one byte of the
source's metadata.**

GPS, device model, account IDs, creation time, chapters, a GoPro telemetry track — all left behind.

## An allowlist, not a blocklist

There are two ways to strip metadata, and the difference matters:

| | How | The problem |
| --- | --- | --- |
| Blocklist | Enumerate the fields to delete (what exiftool does) | **You cannot delete what you do not know about** |
| **Allowlist** | Never say what to delete — say what comes across: one video stream, one audio stream, nothing else | — |

With an allowlist the source's metadata has **no channel** into the output. It is not "deleted";
it was never carried. The privacy guarantee comes from the structure, not from enumeration.

## The tags are the easy part

After `-map_metadata -1`, `ffprobe` goes quiet. **Three identity strings are still in the file:**

| Where it hides | What it says | Visible to ffprobe |
| --- | --- | --- |
| H.264 **SEI** | `x264 - core 165 ... cabac=1 ref=3 ... crf=23.0` | ✗ |
| AAC bitstream **DSE** | `Lavc62.28.102` | ✗ |
| `avc1` **compressorname** | `Lavc libx264` | ✗ |

With the container tag and `handler_name`, that is **five hiding places**, and missing any one of
them means the file is not clean. Every plug — plus the traps that look like they should work and
do not (`-flags:v +bitexact` and `-x264-params info=0` both fail to stop the SEI) — is written up
in [`references/residue-map.md`](references/residue-map.md).

One more that is not in those five and matters just as much: **GoPro and DJI do not put GPS in any
tag.** It rides on a separate `gpmd` timed-metadata track. Stripping tags does not touch it; only
"map exactly one video and one audio stream" keeps it out.

## Lossless by default

```bash
node scripts/video-scrub.mjs run <video> -o out.mp4
```

| Mode | Picture | Audio | Speed |
| --- | --- | --- | --- |
| **`copy`** (default) | **byte-for-byte** | re-encoded | **1.3 s** for a 53 s film |
| `encode` | re-encoded | re-encoded | much slower |

In copy mode the picture genuinely does not change a single bit — the H.264 bitstreams before and
after were `cmp`-checked and are identical apart from the SEI that was removed.

Audio is re-encoded in **both** modes: the AAC encoder writes its version into a DSE inside the
audio bitstream, and `-c:a copy` cannot reach it.

**On watermarks:** what `encode` kills that `copy` does not is bitstream-domain watermarking and
fragile steganography, both rare in real footage. The ones that actually matter — **robust pixel
watermarks** such as SynthID or forensic watermarking — are designed to survive re-encoding, and
**neither mode removes them**. Pick a mode on quality and speed; do not expect a re-encode to wash
out a watermark.

## Verification, not assertion

Everything above is "I passed the right flags" — a claim. This step is "I scanned it, it is gone" —
a proof.

Every metadata string in the source becomes a **needle** — tag keys and values, handler names,
chapter titles — and the output file is scanned **byte by byte**. One hit turns the gate red.

```
demo2.mp4 → clean.mp4  copy / obs
14 needles scanned

  ✓ byte-level residue   ✓ stream layout
  ✓ tag-level residue    ✓ chapters
  ✓ location             ✓ bitstream identity
  ✓ device and software  ✓ profile match
  ✓ source timestamp     ✓ duration
  – rotation matrix      ✓ decodable

✅ all 12 gates green — not one byte of the source's metadata survived
```

A **real run** lives in the repo: [`demo-scrub/`](../../demo-scrub/) — including the most
instructive counter-example, where the textbook recipe leaves `ffprobe` looking spotless and
the bitstream-identity gate still goes red.

Two details in picking needles: **≥5 bytes** (shorter strings collide at random inside compressed
data), and **generic strings are not needles** (`VideoHandler` is in every such file; `Lavf58.45.100`
pins one version, so it is a fingerprint).

## Four profiles

The layer written back after the file is wiped. Switch with `--profile <name>`:

| profile | What it writes |
| --- | --- |
| **`obs`** (default) | The look of an OBS Studio recording. OBS muxes with ffmpeg itself, so this is not a forgery |
| `quicktime` | macOS QuickTime screen recording: `Core Media Video` / `Core Media Audio` |
| `screencapture` | ScreenCaptureKit recording |
| `bare` | Writes nothing. **The strongest for privacy** — no claim that could be falsified |

A profile touches three things only: the muxing tool's trace, handler names, and creation time.
**It never writes a device model, never writes GPS, never writes an author or account.**
See [`references/profiles.md`](references/profiles.md).

## Commands

```bash
inspect <video>                    # what the source carries, including the invisible layers
scrub   <video> -o out.mp4         # clean it
verify  <src> <out>                # scan for residue, print the 12 gates
run     <video> -o out.mp4         # scrub + verify in one go — use this
```

Common flags:

```bash
--mode encode                  # full re-encode
--profile bare                 # write nothing
--crf 18                       # only meaningful in encode mode
--date 2026-01-01T00:00:00Z    # set the creation time
--json                         # JSON out of inspect / verify
```

## HDR and embedded captions: when the SEI knife stays in the drawer

ffmpeg only offers NAL-level granularity, so `remove_types=6` removes **every** SEI. Besides the
x264 junk, SEI also holds **HDR static metadata** (removing it wrecks the colour) and
**CEA-608/708 embedded captions** (removing it loses the subtitles).

So the knife comes out conditionally: **only when an identity string is actually found, and never
on an HDR source** — which is reported explicitly, with the reason.

## Boundaries (what it does not do)

Does not remove watermarks, does not alter the picture (no cropping, scaling or rotating), does not
fabricate device models or GPS, does not batch-scan directories, does not handle containers other
than mp4/mov.

## Requirements and self-test

Just `node` >= 18 and `ffmpeg` / `ffprobe`. No npm dependencies, no API keys.

```bash
node scripts/selftest.mjs
```

117 assertions, touching neither ffmpeg nor a real file. **Every one of the 12 gates has a breach
case** — proof that it actually stops things.
