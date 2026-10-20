"""Check finished promo files against platform specs and write a delivery report.

Usage:
  python deliver.py deliverables/feed_4x5.mp4 deliverables/reels_9x16.mp4 [--out deliverables/delivery.md]
      [--seconds 20] [--thumb-at 1.0] [--project film/]
For each file: resolution, aspect, fps, duration, video/audio codec, pixel format, file size, decoded audio peak.
Matches each file to a platform by aspect ratio. Problems fail the check (exit 1); warnings do not.
Saves a thumbnail next to each file. Vertical text placement is not checked here; run safe_zone.py.
"""
import argparse, json, os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import decode_audio, set_project, tool  # noqa: E402

PLATFORMS = {
    "4:5": ("Threads / Instagram feed", 1080, 1350),
    "9:16": ("Reels / Shorts / TikTok", 1080, 1920),
    "16:9": ("YouTube / web", 1920, 1080),
    "1:1": ("Square feed", 1080, 1080),
}
CONVERT = ('ffmpeg -i IN.mp4 -vf "scale=in_range=full:out_range=tv,format=yuv420p" -c:v libx264 -crf 16 '
           '-preset slow -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 '
           '-movflags +faststart -c:a copy OUT.mp4')


def probe(path):
    out = subprocess.run([tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
    return json.loads(out)


def audio_peak_db(path):
    x = decode_audio(path, 48000, 2)
    if not len(x):
        return None
    return 20 * np.log10(max(float(np.abs(x).max()), 1e-12))


def aspect_name(w, h):
    best, err = None, 9
    for k in PLATFORMS:
        a, b = map(int, k.split(":"))
        e = abs(w / h - a / b)
        if e < err:
            best, err = k, e
    return best if err < 0.02 else f"{w}:{h}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seconds", type=float, default=None, help="expected duration")
    ap.add_argument("--thumb-at", type=float, default=1.0)
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)

    rows, problems, warnings = [], [], []
    for f in a.files:
        j = probe(f)
        v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
        au = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
        name = os.path.basename(f)
        if not v:
            problems.append(f"{name}: no video stream")
            continue
        w, h = int(v["width"]), int(v["height"])
        num, den = v["r_frame_rate"].split("/")
        fps = float(num) / float(den)
        dur = float(j["format"]["duration"])
        size = os.path.getsize(f) / 1e6
        asp = aspect_name(w, h)
        plat = PLATFORMS.get(asp, ("unknown", w, h))
        peak = audio_peak_db(f) if au else None
        pix = v.get("pix_fmt")

        if asp in PLATFORMS and (w, h) != (plat[1], plat[2]):
            problems.append(f"{name}: {w}x{h}, expected {plat[1]}x{plat[2]} for {plat[0]}")
        if asp not in PLATFORMS:
            problems.append(f"{name}: aspect {w}:{h} does not match a common platform")
        if pix == "yuvj420p":
            warnings.append(f"{name}: yuvj420p (full-range color, Remotion's default). Some players shift colors. "
                            f"Convert: {CONVERT}")
        elif pix not in ("yuv420p", None):
            problems.append(f"{name}: pixel format {pix}; use yuv420p for phone playback")
        if v.get("codec_name") != "h264":
            problems.append(f"{name}: video codec {v.get('codec_name')}; h264 is the safest upload format")
        if au is None:
            problems.append(f"{name}: no audio stream")
        elif peak is not None and peak > -0.5:
            problems.append(f"{name}: audio peak {peak:.2f} dBFS; master the source to -4 dBFS and remux")
        if a.seconds and abs(dur - a.seconds) > 0.5:
            problems.append(f"{name}: duration {dur:.2f}s, expected about {a.seconds:g}s")
        if asp == "9:16":
            warnings.append(f"{name}: vertical. Check text placement with safe_zone.py on the busiest frames.")

        thumb = os.path.splitext(f)[0] + "_thumb.jpg"
        subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-ss", f"{min(a.thumb_at, dur - 0.1):.2f}", "-i", f,
                        "-frames:v", "1", "-q:v", "3", thumb], check=True)
        rows.append((name, plat[0], f"{w}x{h}", asp, f"{fps:g}", f"{dur:.2f}s",
                     f"{v.get('codec_name')}/{au.get('codec_name') if au else '-'}", pix or "-", f"{size:.1f}MB",
                     f"{peak:.2f} dBFS" if peak is not None else "-", os.path.basename(thumb)))

    lines = ["# Delivery", "",
             "| file | platform | size | aspect | fps | length | codec | pixel format | file size | audio peak | thumbnail |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    lines += ["", "## Problems", ""] + ([f"- {p}" for p in problems] if problems else ["- none found by automatic checks"])
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warnings]
    lines += ["", "Automatic checks do not replace watching the file with sound from start to end."]
    report = "\n".join(lines) + "\n"
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"wrote {a.out}")
    print(report)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

