#!/usr/bin/env python3
"""Speed up (or down) a talking-head edit while keeping voice pitch natural.

  python3 scripts/speed.py --video clip.mp4 --speed 1.1 -o clip.fast.mp4
  python3 scripts/speed.py --audio voice.wav --speed 1.1 -o voice.fast.wav
  python3 scripts/speed.py --video clip.mp4 --speed 1.1 --bgm bed.mp3 --bgm-gain-db -14 -o clip.fast.mp4

Generalized from a real project's 1.1x delivery pass (see `library/_shared/video20-a0-pipeline/`
for that project-specific version, which times sfx cues and captions to the same speed change).

Picture: `setpts=PTS/speed` at the source frame rate — ffmpeg then naturally drops whichever source
frames don't line up with an output tick (nearest-neighbour, matches `round(k*speed)`); nothing is
interpolated or blended, so motion looks the same, just faster.

Voice: time-stretched with ffmpeg's `rubberband` filter (`pitch=1` keeps pitch fixed — this is what
makes speaking faster sound natural instead of chipmunked); falls back to the `atempo` filter if
`rubberband` isn't available in your ffmpeg build (that one does *not* preserve pitch as cleanly —
a warning is printed when this happens).

BGM (`--bgm`, optional): laid under the sped-up voice at its OWN original speed and trimmed/looped
to the new (shorter) total duration, not time-stretched with the voice — a bed sped up 10% along
with the voice would drift off its own beat grid. This is a plain gain-mixed reference, not a
mastered mix: for loudness-matched ducking under the voice, use `audio/xlaudio` (see
`audio/README.md`) — pass the sped-up voice this script produces as its `voice` argument.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def sh(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw)


def ffprobe_duration(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(r.stdout.strip())


def ffprobe_fps(path):
    r = sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1", path])
    s = r.stdout.strip()
    if not s:
        return None
    num, _, den = s.partition("/")
    return float(num) / float(den or 1)


def has_stream(path, kind):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", kind[0], "-show_entries", "stream=index",
                         "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


RUBBERBAND_ARGS = ("tempo={speed}:pitch=1:transients=crisp:detector=compound:phase=laminar:"
                    "window=standard:smoothing=off:formant=preserved:pitchq=quality:channels=together")


def stretch_audio(src, speed, out_wav):
    """time-stretch src's audio to `out_wav` (48kHz stereo PCM), pitch kept. Returns 'rubberband' or 'atempo'."""
    try:
        sh(["ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:a:0", "-ar", "48000", "-ac", "2",
            "-af", f"rubberband={RUBBERBAND_ARGS.format(speed=speed)}", "-c:a", "pcm_f32le", out_wav])
        return "rubberband"
    except subprocess.CalledProcessError:
        print("warning: ffmpeg has no usable `rubberband` filter (needs librubberband) -- "
              "falling back to `atempo`, which does not preserve pitch as cleanly.", file=sys.stderr)
        # atempo only accepts factors in [0.5, 100.0] individually but is fine chained; a single
        # 1.1x is already in range, so one pass is enough for the speeds this tool is meant for.
        sh(["ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:a:0", "-ar", "48000", "-ac", "2",
            "-af", f"atempo={speed}", "-c:a", "pcm_f32le", out_wav])
        return "atempo"


def bgm_bed(bgm_path, target_dur, gain_db, fade_s=1.0):
    """trim/loop bgm_path to target_dur seconds at its own speed, with a short fade in/out and a gain,
    returned as a temp wav path."""
    dur = ffprobe_duration(bgm_path)
    tmp = Path(bgm_path).with_suffix(".bed.wav")
    loops = max(1, -(-int(target_dur // dur + 1)))  # enough loops to cover target_dur
    filt = (f"aloop=loop={loops - 1}:size={int(dur * 48000) + 1},atrim=0:{target_dur:.6f},"
            f"afade=t=in:d={min(fade_s, target_dur / 4):.3f},afade=t=out:st={max(0, target_dur - fade_s):.3f}:d={min(fade_s, target_dur / 4):.3f},"
            f"volume={gain_db}dB")
    sh(["ffmpeg", "-y", "-v", "error", "-i", bgm_path, "-map", "0:a:0", "-ar", "48000", "-ac", "2", "-af", filt, "-c:a", "pcm_f32le", str(tmp)])
    return tmp


def read_wav(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", "48000", "-"],
                        check=True, capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.float32)
    return a.reshape(-1, 2).T  # (2, n)


def write_wav_ffmpeg(arr, sr, out_path):
    """arr: (channels, n) float32 in [-1, 1]."""
    raw = np.clip(arr, -1.0, 1.0).T.astype(np.float32).tobytes()
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(arr.shape[0]), "-i", "-",
                         "-c:a", "pcm_f32le", str(out_path)], input=raw, capture_output=True)
    if p.returncode != 0:
        sys.exit(p.stderr.decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="video file to speed up (picture + voice)")
    ap.add_argument("--audio", help="audio-only file to speed up (voice, no picture)")
    ap.add_argument("--speed", type=float, default=1.1, help="tempo factor, e.g. 1.1 = 10%% faster (default: 1.1)")
    ap.add_argument("--bgm", help="optional music bed, laid separately at its own speed under the result")
    ap.add_argument("--bgm-gain-db", type=float, default=-14.0, dest="bgm_gain_db")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if not a.video and not a.audio:
        sys.exit("need --video or --audio")
    if a.video and a.audio:
        sys.exit("pass only one of --video / --audio")
    src = a.video or a.audio

    voice_wav = Path(str(a.out) + ".voice.wav")
    how = stretch_audio(src, a.speed, voice_wav)
    new_dur = ffprobe_duration(voice_wav)

    dia = voice_wav
    if a.bgm:
        bed = bgm_bed(a.bgm, new_dur, a.bgm_gain_db)
        v = read_wav(voice_wav)
        b = read_wav(bed)
        n = min(v.shape[1], b.shape[1])
        mixed = v[:, :n] + b[:, :n]
        peak = float(np.abs(mixed).max())
        if peak > 0.98:  # simple safety limiter so a loud bed can't clip the mix; not loudness-matched mastering
            mixed *= 0.98 / peak
        dia = Path(str(a.out) + ".mix.wav")
        write_wav_ffmpeg(mixed, 48000, dia)
        bed.unlink(missing_ok=True)

    part = Path(str(a.out) + ".partial" + Path(a.out).suffix)
    if a.video:
        fps = ffprobe_fps(a.video) or 30.0
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.video, "-i", dia,
               "-filter_complex", f"[0:v]setpts=PTS/{a.speed}[v]",
               "-map", "[v]", "-map", "1:a:0", "-r", f"{fps}", "-c:v", "libx264", "-crf", "16",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(part)]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(dia),
               "-c:a", "pcm_s16le" if Path(a.out).suffix.lower() == ".wav" else "aac", str(part)]
    subprocess.run(cmd, check=True)
    part.replace(a.out)
    voice_wav.unlink(missing_ok=True)
    if dia != voice_wav:
        Path(dia).unlink(missing_ok=True)

    old_dur = ffprobe_duration(src)
    print(json.dumps({"speed": a.speed, "stretch": how, "original_duration_s": round(old_dur, 3),
                       "new_duration_s": round(new_dur, 3), "bgm": bool(a.bgm), "out": str(a.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
