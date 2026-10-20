#!/usr/bin/env python3
"""Self-verify a rendered video: ffprobe checks, checkpoint frames, one contact sheet, report.

USAGE
  verify.py RUN_DIR [--video draft.mp4|edited.mp4|final.mp4] [--cols 4]
Default video: final.mp4, else edited.mp4, else draft.mp4. Writes RUN_DIR/verify/:
  contact.png (look at it), frames/*.png, report.md, report.json.
Exit code 1 when a hard check fails. The contact sheet still needs your eyes: this script cannot judge
whether a caption covers the clicked element, whether a click had a visible effect, or how audio sounds.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import font, load_json, need, probe_summary, run_paths, save_json  # noqa: E402

GITHUB_FREE_MB = 10
MANUAL = {
    "feature-demo": [
        "Each step frame shows its caption, readable at this size, not covering the clicked element.",
        "Each click+0.3 frame shows the effect of the click (menu open, field focused, page changed).",
        "Zoomed frames are centred on the action and not blurry; the cursor is visible.",
        "Intro and outro text are correct (title, spelling, diacritics).",
        "No frame shows real customer data, secrets or a cookie banner.",
    ],
    "bug-report": [
        "The bug frame shows the actual failure, with the red box on the right element.",
        "EXPECTED and ACTUAL in the panel match the storyboard and what the video shows.",
        "The steps list highlights the step the video is showing.",
        "The REC timestamp is visible and keeps running across cuts.",
        "No frame shows secrets, tokens or personal data.",
    ],
}


def frame_at(video: pathlib.Path, t: float, out: pathlib.Path, height: int = 360):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", f"scale=-2:{height}", str(out)], check=True)


def stats(png: pathlib.Path, crop_w_frac: float = 1.0) -> dict:
    from PIL import Image, ImageStat
    im = Image.open(png).convert("RGB")
    if crop_w_frac < 1.0:
        im = im.crop((0, 0, int(im.width * crop_w_frac), im.height))
    luma = ImageStat.Stat(im.convert("L"))
    px = [p for p in im.getdata() if sum(p) > 600]          # bright pixels: white UI should stay neutral
    tint = 0.0
    if len(px) > 50:
        tint = sum(g - (r + b) / 2 for r, g, b in px) / len(px)
    return {"luma_std": round(luma.stddev[0], 2), "luma_mean": round(luma.mean[0], 1), "green_tint": round(tint, 2)}


def contact_sheet(frames: list[tuple[pathlib.Path, str]], out: pathlib.Path, cols: int):
    from PIL import Image, ImageDraw, ImageFont
    thumbs = [Image.open(p).convert("RGB") for p, _ in frames]
    tw = 420
    th = max(int(t.height * tw / t.width) for t in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 34) + 8), (24, 24, 27))
    try:
        fnt = ImageFont.truetype(font(), 16)
    except Exception:
        fnt = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for k, (im, (_, label)) in enumerate(zip(thumbs, frames)):
        x = 8 + (k % cols) * (tw + 8)
        y = 8 + (k // cols) * (th + 34)
        sheet.paste(im.resize((tw, int(im.height * tw / im.width))), (x, y + 26))
        d.text((x, y + 4), label, fill=(250, 204, 21), font=fnt)
    sheet.save(out)


def loudness(video: pathlib.Path) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--video")
    ap.add_argument("--cols", type=int, default=4)
    a = ap.parse_args()
    need("ffmpeg")
    p = run_paths(a.run)
    if not p["edl"].exists():
        sys.exit(f"error: {p['edl']} missing; run edl.py first")
    plan = load_json(p["edl"])
    if a.video:
        video = a.run / a.video
    else:
        video = next((p[k] for k in ("final", "edited", "draft") if p[k].exists()), None)
    if not video or not video.exists():
        sys.exit("error: no video to verify (final.mp4 / edited.mp4 / draft.mp4)")
    vdir = p["verify"]
    if vdir.exists():
        shutil.rmtree(vdir)
    (vdir / "frames").mkdir(parents=True)

    checks = []

    def check(name, ok, detail, hard=True):
        checks.append({"check": name, "status": "PASS" if ok else ("FAIL" if hard else "WARN"), "detail": detail})

    pr = probe_summary(video)
    pred = plan.get("predicted_duration") or plan.get("body_duration")
    check("file exists and plays", pr["duration"] > 0 and pr["size_bytes"] > 0,
          f"{pr['duration']:.2f}s, {pr['size_bytes'] / 1e6:.2f} MB")
    check("duration matches EDL (±10%)", abs(pr["duration"] - pred) <= 0.1 * pred + 0.1,
          f"actual {pr['duration']:.2f}s vs predicted {pred:.2f}s")
    check("H.264 yuv420p (plays in Slack/GitHub/Jira)", pr["video_codec"] == "h264" and pr["pix_fmt"] == "yuv420p",
          f"{pr['video_codec']} {pr['pix_fmt']}")
    check("30 fps", pr["fps"] is not None and abs(pr["fps"] - 30) < 0.5, f"{pr['fps']} fps", hard=False)
    want_audio = bool(plan.get("narration"))
    check("audio stream as planned", bool(pr["audio_codec"]) == want_audio or plan.get("edit_only"),
          f"audio={pr['audio_codec']} narration={want_audio}")
    mode = plan["mode"]
    if mode == "bug-report":
        check("bug-report under 60 s", pr["duration"] <= 60, f"{pr['duration']:.1f}s", hard=False)
    else:
        check("feature-demo 10-120 s", 10 <= pr["duration"] <= 120, f"{pr['duration']:.1f}s", hard=False)
    if video.name == "final.mp4":
        check(f"size under {GITHUB_FREE_MB - 1} MB (GitHub free limit {GITHUB_FREE_MB} MB)",
              pr["size_bytes"] <= (GITHUB_FREE_MB - 1) * 1024 * 1024, f"{pr['size_bytes'] / 1048576:.2f} MB",
              hard=False)
    lufs = None
    if pr["audio_codec"]:
        lufs = loudness(video)
        check("loudness -24..-12 LUFS", lufs is not None and -24 <= lufs <= -12, f"{lufs} LUFS", hard=False)

    frames, fstats = [], []
    w_app = plan.get("viewport", [1, 1])[0]
    crop = 1.0
    if mode == "bug-report" and pr["width"]:
        crop = min(1.0, w_app / (w_app + 440))           # ignore the side panel for colour checks
    cps = plan.get("checkpoints", [])
    for k, c in enumerate(cps):
        f = vdir / "frames" / f"{k:02d}_{c['label']}.png"
        frame_at(video, c["t"], f)
        st = stats(f, crop)
        label = f"{c['t']:.2f}s {c['label']}"
        frames.append((f, label))
        fstats.append({**c, **st, "file": str(f.relative_to(a.run))})
    blank = [s for s in fstats if s["luma_std"] < 2.0]
    check("no blank frames", not blank, ", ".join(f"{s['label']}@{s['t']}" for s in blank) or "none")
    raw = p["raw"] if p["raw"].exists() else None
    tinted = []
    for s in fstats:
        if s["green_tint"] > 6:
            ref = None
            if raw and s.get("raw_t") is not None:
                rf = vdir / "frames" / f"raw_{s['label']}_{s['t']}.png"
                frame_at(raw, s["raw_t"], rf)
                ref = stats(rf)["green_tint"]
            if ref is None or s["green_tint"] - ref > 6:
                tinted.append(f"{s['label']} tint {s['green_tint']} (raw {ref})")
    check("no colour tint (ffmpeg overlay pixel format)", not tinted, "; ".join(tinted) or "neutral whites")
    for w in plan.get("warnings", []):
        check("EDL warning", False, w, hard=False)
    if frames:
        contact_sheet(frames, vdir / "contact.png", a.cols)

    hard_fail = any(c["status"] == "FAIL" for c in checks)
    report = {"video": str(video.name), "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
              "probe": pr, "loudness_lufs": lufs, "checks": checks, "frames": fstats,
              "manual_checks": MANUAL[mode], "not_checked": ["audio content and voice quality (listen to it)",
                                                           "motion smoothness between checkpoints"]}
    save_json(vdir / "report.json", report)
    lines = [f"# Verify: {video.name}", "", f"{pr['duration']:.2f}s · {pr['width']}x{pr['height']} · "
             f"{pr['size_bytes'] / 1048576:.2f} MB · {pr['video_codec']}/{pr['audio_codec']}", "",
             "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {c['check']} | {c['status']} | {c['detail']} |" for c in checks]
    lines += ["", "## Look at contact.png and confirm", ""] + [f"- [ ] {m}" for m in MANUAL[mode]]
    lines += ["", "## Not checked", ""] + [f"- {m}" for m in report["not_checked"]]
    (vdir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for c in checks:
        print(f"{c['status']:4}  {c['check']}: {c['detail']}")
    print(f"contact sheet: {vdir / 'contact.png'}  ({len(frames)} frames)")
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
