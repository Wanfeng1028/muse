"""Tao track nen doc 1080x1920 lien tuc, xfade giua cac canh.

Chay trong thu muc project (noi co content.json va voice/timings.json).
Bien moi truong:
  BG_DIR  thu muc chua clip nen (mac dinh: assets/bg cua skill)
"""
import glob
import json
import os
import subprocess
import sys

FPS = 30
XF = 1.0  # do dai crossfade

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _default_bg():
    base = os.path.join(SKILL_DIR, "assets", "bg")
    # uu tien bo "nature" neu co thu muc con, khong thi lay thang assets/bg
    for name in ("nature", "city"):
        d = os.path.join(base, name)
        if os.path.isdir(d) and glob.glob(os.path.join(d, "*.mp4")):
            return d
    return base


BG_DIR = os.environ.get("BG_DIR") or _default_bg()


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def total_needed():
    t = json.load(open("voice/timings.json", encoding="utf-8"))
    pad = float(os.environ.get("PAD", "0.9"))
    return 0.5 + sum(x["dur"] + pad for x in t) + 1.2


def normalize(src, out):
    """Crop doc 9:16, chinh mau, lam toi nhe, them vignette."""
    vf = (
        "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,fps=30,"
        "eq=brightness=-0.07:saturation=0.82:contrast=1.04,"
        "gblur=sigma=1.2,vignette=PI/4.2,format=yuv420p"
    )
    subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-an", "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out, "-y"],
                   check=True)


def main():
    need = total_needed()
    print(f"Can nen dai: {need:.1f}s  (clip nen: {BG_DIR})")
    os.makedirs("work", exist_ok=True)

    srcs = sorted(glob.glob(os.path.join(BG_DIR, "*.mp4")))
    if not srcs:
        print(f"!! Khong co clip nen trong {BG_DIR}. Chay fetch_assets.py truoc.")
        sys.exit(1)

    norm = []
    for i, s in enumerate(srcs):
        o = f"work/n{i}.mp4"
        if not os.path.exists(o):
            normalize(s, o)
        norm.append(o)
        print(f"  chuan hoa {os.path.basename(s)} -> {o} ({dur(o):.1f}s)")

    # lap lai chuoi canh cho du do dai
    seq, acc, i = [], 0.0, 0
    while acc < need + XF * 2:
        p = norm[i % len(norm)]
        seq.append(p)
        acc += dur(p) - XF
        i += 1
    print(f"Dung {len(seq)} canh, tong ~{acc:.1f}s")

    inputs, fc = [], []
    for p in seq:
        inputs += ["-i", p]
    prev_label, cum = "0:v", dur(seq[0])
    for k in range(1, len(seq)):
        off = cum - XF
        out_label = f"x{k}"
        fc.append(f"[{prev_label}][{k}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[{out_label}]")
        prev_label = out_label
        cum = off + XF + (dur(seq[k]) - XF)
    fc.append(f"[{prev_label}]trim=duration={need:.3f},setpts=PTS-STARTPTS,format=yuv420p[out]")

    cmd = ["ffmpeg", "-v", "error", "-stats"] + inputs + [
        "-filter_complex", ";".join(fc), "-map", "[out]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
        "work/bg.mp4", "-y"]
    print("Dang ghep nen...")
    subprocess.run(cmd, check=True)
    print(f"OK -> work/bg.mp4  {dur('work/bg.mp4'):.2f}s")


if __name__ == "__main__":
    main()
