#!/usr/bin/env python3
"""Fail a vertical reel that puts critical content in a platform-UI unsafe zone.

THE RULE it enforces: on a 1080x1920 reel the critical content box is
x 60-950, y 250-1560. Above 250 the Instagram username and audio row and the
TikTok tabs cover it; below 1560 the caption and comment bar does; right of
950 the like, comment and share rail does.

WHY THIS EXISTS: a reel once shipped with its headline panel at y=118, a
132px violation, because the position was typed by hand instead of read from
the spec. Prose did not prevent it. This does.

Detection: overlay graphics on this rail are hard-edged panels of near-uniform
colour against filmed footage. A row is "critical" when a long horizontal run
of near-identical pixels appears, which footage almost never produces.

    python3 check-reel-safe-zones.py video.mp4 [--frames 12] [--debug out.png]

Exit 0 clean, 1 violation, 2 usage/decode error.
"""
import subprocess, sys, tempfile, os, argparse

TOP_SAFE, BOTTOM_SAFE = 250, 1560
LEFT_SAFE, RIGHT_SAFE = 60, 950
RUN_MIN = 260          # px of near-uniform colour that marks a drawn panel
TOL = 10               # per-channel tolerance for "same colour"
EDGE_DELTA = 90        # per-pixel channel-sum jump that reads as a drawn edge
EDGE_FRAC = 0.55       # fraction of the row width that must jump together

def frame_times(path, n):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","csv=p=0",path],capture_output=True,text=True)
    try: dur = float(out.stdout.strip())
    except ValueError: sys.exit(2)
    return [dur*(i+0.5)/n for i in range(n)], dur

def panel_rows(px, w, y0, y1):
    """Rows inside [y0,y1) that look like a DRAWN overlay panel.

    A drawn panel has a hard horizontal edge: a wide span of x where the pixel
    changes abruptly from the row above. Real footage (walls, ceilings, skin,
    gradients) changes smoothly, so it does not produce this even when it is
    very uniform. An earlier version of this script hunted uniform runs instead
    and flagged a smooth ceiling at y=0 as content; that was wrong.
    """
    hits = []
    for y in range(max(1, y0), y1):
        abrupt = 0
        for x in range(LEFT_SAFE, min(w - LEFT_SAFE, RIGHT_SAFE), 4):
            a, b = px[x, y - 1], px[x, y]
            if sum(abs(a[i] - b[i]) for i in range(3)) > EDGE_DELTA:
                abrupt += 1
        span = (min(w - LEFT_SAFE, RIGHT_SAFE) - LEFT_SAFE) // 4
        if span and abrupt / span >= EDGE_FRAC:
            hits.append(y)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--frames",type=int,default=12)
    ap.add_argument("--debug")
    a = ap.parse_args()
    if not os.path.exists(a.video): sys.exit(2)
    try:
        from PIL import Image
    except ImportError:
        print("PIL missing. Install it: python3 -m pip install pillow"); sys.exit(2)

    times, dur = frame_times(a.video, a.frames)
    violations = []
    with tempfile.TemporaryDirectory() as td:
        for t in times:
            f = os.path.join(td,"f.png")
            subprocess.run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",a.video,
                            "-frames:v","1",f],check=False)
            if not os.path.exists(f): continue
            im = Image.open(f).convert("RGB"); w,h = im.size
            px = im.load()
            if (w,h) != (1080,1920):
                print(f"WARN not 1080x1920, got {w}x{h}; zones assume 1080x1920")
            rows = panel_rows(px, w, 0, min(TOP_SAFE, h)) + panel_rows(px, w, max(0, BOTTOM_SAFE), h)
            if rows:
                y = rows[0]
                zone = "TOP" if y < TOP_SAFE else "BOTTOM"
                violations.append((round(t, 2), y, zone))
    if violations:
        print(f"FAIL {os.path.basename(a.video)}: critical content in the unsafe zone")
        for t,y,z in violations[:8]:
            edge = f"{TOP_SAFE-y}px above the top-safe line" if z=="TOP" else f"{y-BOTTOM_SAFE}px below the bottom-safe line"
            print(f"  t={t}s  y={y}  {z} zone, {edge}")
        print(f"  rule: critical box is x {LEFT_SAFE}-{RIGHT_SAFE}, y {TOP_SAFE}-{BOTTOM_SAFE}")
        sys.exit(1)
    print(f"PASS {os.path.basename(a.video)}: {a.frames} frames, nothing critical outside y {TOP_SAFE}-{BOTTOM_SAFE}")
    sys.exit(0)

main()
