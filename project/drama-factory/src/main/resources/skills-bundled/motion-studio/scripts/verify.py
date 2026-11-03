"""Checks on an encoded film, and the blind-read packet.

verify: specs, even dimensions, fast start, clean decode, loudness, frame-0 background, single-frame pops,
and a per-beat contact sheet. Every check prints PASS/FAIL/INFO; the exit code is non-zero if anything failed.
blindpack: one still per bar from the encode + every piece of on-screen text (from window.STUDIO.text),
plus the reader prompt, in a folder a blind reader may read and nothing else.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

SKILL = Path(__file__).resolve().parent.parent


def _ffprobe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,pix_fmt,color_range,sample_rate,channels",
                          "-show_entries", "format=duration", "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def verify(video, bpm=None, sheet_dest=None, bg=(11, 11, 11), allow=None):
    video = Path(video)
    fails = []
    def report(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    info = _ffprobe(video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    w, h = v["width"], v["height"]
    print(f"INFO {w}x{h} {v['codec_name']} {v['pix_fmt']} range={v.get('color_range')} {v['r_frame_rate']} fps, "
          f"{v.get('nb_frames')} frames, {float(info['format']['duration']):.3f} s" + (f", audio {a['codec_name']} {a['sample_rate']} Hz x{a['channels']}" if a else ", no audio"))
    report(w % 2 == 0 and h % 2 == 0, "even dimensions")
    report(v["pix_fmt"] == "yuv420p", "yuv420p")
    head = video.read_bytes()[:400000]
    moov, mdat = head.find(b"moov"), head.find(b"mdat")   # a long film's moov can outgrow the window: no mdat seen yet is fine
    report(moov >= 0 and (mdat < 0 or moov < mdat), "fast start (moov before mdat)")
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    report(dec.returncode == 0 and not dec.stderr.strip(), "clean decode")

    # frame 0 background, decoded back to full range: catches the limited-range grey lift
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "select=eq(n\\,0),scale=in_range=tv:out_range=pc,format=rgb24",
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    px = tuple(raw[:3])
    report(all(abs(p - q) <= 4 for p, q in zip(px, bg)), f"frame-0 corner {px} ≈ background {bg}")

    if a:
        loud = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        tail = loud[loud.rfind("Summary:"):]
        lufs = float(tail.split("I:")[1].split("LUFS")[0])
        peak = float(tail.split("Peak:")[1].split("dBFS")[0])
        report(-15.0 <= lufs <= -13.0, f"loudness {lufs} LUFS (target -14)")
        report(peak <= -1.0, f"true peak {peak} dBFS (≤ -1)")

    # single-frame pops: a frame whose difference from its neighbours spikes 3x
    sw, sh = max(2, w // 4 // 2 * 2), max(2, h // 4 // 2 * 2)
    gray = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={sw}:{sh},format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(gray, np.uint8).reshape(-1, sh, sw).astype(np.int16)
    d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    pops = [(i + 1, round((i + 1) / 30, 2)) for i in range(1, len(d) - 1) if d[i] > 1.0 and d[i] > 3 * max(d[i - 1], d[i + 1])]
    if allow:                                               # intended hits: scene wipes, stamps, hard cuts the film declares
        pops = [p for p in pops if not any(a0 - 0.05 <= p[1] <= a1 + 0.05 for a0, a1 in allow)]
    report(not pops, "no single-frame pops" + (f": {pops}" if pops else ""))

    if bpm and sheet_dest:
        beat_sheet(video, bpm, sheet_dest)
        print(f"INFO per-beat contact sheet: {sheet_dest}")
    print("RESULT:", "all checks passed" if not fails else f"{len(fails)} failed")
    return not fails


def beat_sheet(video, bpm, dest, tile_w=180, cols=12):
    w, h = _size(video)
    th = round(tile_w * h / w / 2) * 2
    step = max(1, round(30 * 60 / bpm))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"select='not(mod(n\\,{step}))',scale={tile_w}:{th},tile={cols}x{-(-_nframes(video) // step // cols)}:padding=4:color=0x333333",
                    "-frames:v", "1", "-fps_mode", "vfr", str(dest)], check=True)
    return dest


def _size(video):
    v = next(s for s in _ffprobe(video)["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"]


def _nframes(video):
    v = next(s for s in _ffprobe(video)["streams"] if s["codec_type"] == "video")
    return int(v.get("nb_frames") or 0) or 1


def blindpack(project, video, studio, dest):
    """Build a blind-read packet: frames/ (one per bar, from the encode), onscreen-text.md, prompt.md."""
    dest = Path(dest)
    (dest / "frames").mkdir(parents=True, exist_ok=True)
    bar = 4 * 60 / studio["bpm"]
    w, h = studio["format"]["w"], studio["format"]["h"]
    for k in range(studio["bars"]):
        t = k * bar + 0.72 * bar
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={w // 2 // 2 * 2}:{h // 2 // 2 * 2}", str(dest / "frames" / f"{k:02d}-t{t:05.2f}.png")], check=True)
    rows = ["# All on-screen text, in order", "", "| Time (s) | Where | Text |", "|---|---|---|"]
    for item in sorted(studio["text"], key=lambda x: x["t0"]):
        span = f"{item['t0']:.1f}" + (f"–{item['t1']:.1f}" if item.get("t1") is not None else "")
        where = "caption" if item["where"] == "caption" else "text in the scene"   # never the author's description of what happens
        rows.append(f"| {span} | {where} | {item['text']} |")
    (dest / "onscreen-text.md").write_text("\n".join(rows) + "\n")
    prompt = (SKILL / "references/prompts/blind-read.md").read_text()
    prompt = prompt.replace("{DURATION}", f"{studio['bars'] * bar:.0f}").replace("{N_FRAMES}", str(studio["bars"]))
    (dest / "prompt.md").write_text(prompt)
    return dest
