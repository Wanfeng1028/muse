#!/usr/bin/env python3
"""Remove silent stretches from a talking-head video using a neural VAD.

The whole edit runs as one FFmpeg pass: we build a filter graph that trims
each speech span and concatenates the results, so the input is only decoded
once and no intermediate segment files are written.
"""

import argparse
import os
import subprocess
import tempfile
import time

# Encoding preferences -------------------------------------------------------
HW_ENCODER = "hevc_videotoolbox"
SW_ENCODER = "libx265"
HW_BITRATE = "17M"
SW_CRF = "18"
OUTPUT_FPS = 30

# We probe for the hardware encoder once and remember the answer.
_hw_available = None


def _probe_hardware_encoder():
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return HW_ENCODER in proc.stdout
    except Exception:
        return False


def _encoder_flags():
    global _hw_available
    if _hw_available is None:
        _hw_available = _probe_hardware_encoder()
        if _hw_available:
            print("🚀 Hardware HEVC encoder detected (hevc_videotoolbox)")
        else:
            print("💻 Falling back to software HEVC encoder (libx265)")

    if _hw_available:
        return [
            "-c:v", HW_ENCODER,
            "-b:v", HW_BITRATE,
            "-r", str(OUTPUT_FPS),
            "-tag:v", "hvc1",
        ]
    return [
        "-c:v", SW_ENCODER,
        "-preset", "fast",
        "-crf", SW_CRF,
        "-r", str(OUTPUT_FPS),
        "-tag:v", "hvc1",
    ]


def _probe_duration(path):
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def _dump_wav(video_path, wav_path, sr=16000):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-ar", str(sr), "-ac", "1",
            "-acodec", "pcm_s16le",
            "-loglevel", "error",
            wav_path,
        ],
        check=True,
        capture_output=True,
    )


def _run_silero(wav_path, min_speech_s, min_silence_s):
    """Return a list of (start_s, end_s) speech spans detected by Silero."""
    import torch

    model, helpers = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    get_speech_ts, _save, read_audio, _iter, _collect = helpers

    SR = 16000
    samples = read_audio(wav_path, sampling_rate=SR)

    raw = get_speech_ts(
        samples,
        model,
        sampling_rate=SR,
        threshold=0.5,
        min_speech_duration_ms=int(min_speech_s * 1000),
        min_silence_duration_ms=int(min_silence_s * 1000),
        speech_pad_ms=100,
    )

    return [(ts["start"] / SR, ts["end"] / SR) for ts in raw]


def _coalesce_nearby(spans, max_gap):
    if not spans:
        return []
    out = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = out[-1]
        if start - prev_end <= max_gap:
            out[-1] = (prev_start, end)
        else:
            out.append((start, end))
    return out


def _apply_padding(spans, pad_s, total_dur):
    if not spans:
        return []
    padded = [
        (max(0.0, s - pad_s), min(total_dur, e + pad_s))
        for (s, e) in spans
    ]
    out = [padded[0]]
    for start, end in padded[1:]:
        prev_start, prev_end = out[-1]
        if start <= prev_end:
            out[-1] = (prev_start, max(prev_end, end))
        else:
            out.append((start, end))
    return out


def _filter_graph(spans):
    """Build the trim+concat filter_complex string for the given spans."""
    n = len(spans)
    lines = []
    for i, (start, end) in enumerate(spans):
        lines.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]"
        )
    for i, (start, end) in enumerate(spans):
        lines.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{i}]"
        )
    joined_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    lines.append(f"{joined_inputs}concat=n={n}:v=1:a=1[outv][outa]")
    return ";".join(lines)


def _render_singlepass(video_path, spans, output_path):
    print(f"⚡ Rendering {len(spans)} kept spans in one pass...")
    t0 = time.time()

    graph = _filter_graph(spans)

    # Long graphs are safer passed via a filter-script file.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
        fh.write(graph)
        script_path = fh.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-filter_complex_script", script_path,
            "-map", "[outv]", "-map", "[outa]",
        ]
        cmd += _encoder_flags()
        cmd += [
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"   ffmpeg failed: {proc.stderr[:1000]}")
            return False
        print(f"   Encoded in {time.time() - t0:.1f}s")
        return True
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)


def main():
    ap = argparse.ArgumentParser(
        description="Single-pass VAD jump-cut editor (trim+concat)"
    )
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--min-silence", type=float, default=0.5,
                    help="Minimum silence length to cut (s)")
    ap.add_argument("--min-speech", type=float, default=0.25,
                    help="Minimum speech span to keep (s)")
    ap.add_argument("--padding", type=int, default=100,
                    help="Padding around speech (ms)")
    ap.add_argument("--merge-gap", type=float, default=0.3,
                    help="Merge spans separated by less than this (s)")
    ap.add_argument("--keep-start", action="store_true", default=True)
    ap.add_argument("--no-keep-start", action="store_false", dest="keep_start")
    args = ap.parse_args()

    t_start = time.time()
    print("🎬 Jump Cut Editor (single-pass VAD)")
    print(f"   in : {args.input}")
    print(f"   out: {args.output}")

    total_dur = _probe_duration(args.input)
    print(f"📏 duration: {total_dur:.2f}s ({total_dur/60:.1f} min)")

    # --- audio → VAD ---
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        print("🎵 extracting audio")
        _dump_wav(args.input, wav_path)
        print("🎯 running Silero VAD")
        spans = _run_silero(wav_path, args.min_speech, args.min_silence)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    print(f"   {len(spans)} raw speech spans")
    for i, (s, e) in enumerate(spans[:5]):
        print(f"     {i+1}. {s:.2f}–{e:.2f} ({e-s:.2f}s)")
    if len(spans) > 5:
        print(f"     … +{len(spans)-5} more")

    if not spans:
        print("⚠️  no speech detected; nothing to do")
        return

    spans = _coalesce_nearby(spans, args.merge_gap)
    print(f"📎 after merge: {len(spans)}")

    spans = _apply_padding(spans, args.padding / 1000.0, total_dur)
    print(f"🔲 after padding: {len(spans)}")

    if args.keep_start and spans and spans[0][0] > 0:
        first_start, first_end = spans[0]
        spans[0] = (0.0, first_end)
        print("📌 first span extended back to 0:00")

    kept = sum(e - s for s, e in spans)
    print(f"📊 expected output: {kept:.1f}s ({kept/60:.1f} min)\n")

    if not _render_singlepass(args.input, spans, args.output):
        return

    new_dur = _probe_duration(args.output)
    removed = total_dur - new_dur
    print(f"\n📊 stats")
    print(f"   original: {total_dur:.2f}s ({total_dur/60:.1f} min)")
    print(f"   new     : {new_dur:.2f}s ({new_dur/60:.1f} min)")
    print(f"   removed : {removed:.2f}s ({100*removed/total_dur:.1f}%)")
    print(f"   ⚡ total time: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
