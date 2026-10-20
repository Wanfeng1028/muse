"""Ghep video cuoi: nen + card + voice + nhac nen + watermark.

Chay trong thu muc project (co content.json, cards/, voice/, work/bg.mp4).
Bien moi truong:
  MUSIC  duong dan file nhac nen (mac dinh: file dau tien trong assets/music)
  PAD    dem sau moi doan voice, giay (mac dinh 0.9)
"""
import glob
import json
import os
import shutil
import subprocess

from PIL import Image

FPS = 30
PAD = float(os.environ.get("PAD", "0.9"))
LEAD = 0.5        # thoi gian mo dau
VOICE_OFF = 0.35  # voice vao sau khi card hien
FI = 0.45         # fade in card
FO = 0.45         # fade out card
OUT = "output/video-hoan-chinh.mp4"

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pick_music():
    m = os.environ.get("MUSIC")
    if m and os.path.exists(m):
        return m
    cands = sorted(glob.glob(os.path.join(SKILL_DIR, "assets", "music", "*.mp3")))
    if not cands:
        raise SystemExit("Khong tim thay nhac nen. Chay fetch_assets.py hoac dat MUSIC=<file>")
    return cands[0]


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    data = json.load(open("content.json", encoding="utf-8"))
    timings = json.load(open("voice/timings.json", encoding="utf-8"))
    os.makedirs("output", exist_ok=True)
    os.makedirs("work", exist_ok=True)
    music = pick_music()

    # font cho drawtext: copy ve thu muc lam viec de tranh escape duong dan Windows
    font_local = "work/wm.ttf"
    if not os.path.exists(font_local):
        shutil.copy(r"C:\Windows\Fonts\segoeuib.ttf", font_local)
    open("work/wm1.txt", "w", encoding="utf-8").write(data["watermark"])
    open("work/wm2.txt", "w", encoding="utf-8").write(data["watermark_sub"])

    total = dur("work/bg.mp4")

    plan, t = [], LEAD
    for i, tm in enumerate(timings, 1):
        d = tm["dur"] + PAD
        plan.append({"i": i, "st": t, "en": t + d, "dur": d,
                     "voice": tm["file"], "voice_st": t + VOICE_OFF})
        t += d
    print(f"Nen: {total:.2f}s | Timeline card ket thuc: {t:.2f}s | Nhac: {os.path.basename(music)}")

    inputs = ["-i", "work/bg.mp4"]
    for p in plan:
        img = f"cards/card{p['i']:02d}.png"
        p["h"] = Image.open(img).size[1]
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{p['dur']:.3f}", "-i", img]
    n_img = len(plan)
    for p in plan:
        inputs += ["-i", p["voice"]]
    inputs += ["-stream_loop", "-1", "-i", music]
    music_idx = 1 + n_img * 2

    # ---- video ----
    fc, last = [], "0:v"
    for k, p in enumerate(plan, start=1):
        st, en = p["st"], p["en"]
        base_y = (1920 - p["h"]) / 2 - 30
        fc.append(
            f"[{k}:v]format=rgba,setpts=PTS-STARTPTS+{st:.3f}/TB,"
            f"fade=in:st={st:.3f}:d={FI}:alpha=1,"
            f"fade=out:st={en - FO:.3f}:d={FO}:alpha=1[c{k}]"
        )
        # card truot len khi xuat hien, roi troi len rat cham suot thoi gian hien
        # (card doc lau tren anh tinh se bi don neu dung yen)
        drift = min(20.0, 6.0 + p["dur"] * 0.22)
        yexpr = (f"{base_y:.1f}+28*(1-min(1\\,(t-{st:.3f})/{FI}))"
                 f"-{drift:.1f}*min(1\\,(t-{st:.3f})/{p['dur']:.3f})")
        fc.append(
            f"[{last}][c{k}]overlay=x=(W-w)/2:y='{yexpr}':"
            f"enable='between(t,{st:.3f},{en:.3f})'[v{k}]"
        )
        last = f"v{k}"

    fc.append(
        f"[{last}]drawtext=fontfile=work/wm.ttf:textfile=work/wm1.txt:"
        f"fontcolor=white@0.95:fontsize=42:x=(w-text_w)/2:y=1640:"
        f"shadowcolor=black@0.5:shadowx=0:shadowy=2[w1]"
    )
    fc.append(
        f"[w1]drawtext=fontfile=work/wm.ttf:textfile=work/wm2.txt:"
        f"fontcolor=white@0.72:fontsize=21:x=(w-text_w)/2:y=1696:"
        f"shadowcolor=black@0.5:shadowx=0:shadowy=1,"
        f"fade=in:st=0:d=0.6,fade=out:st={total - 0.8:.3f}:d=0.8,format=yuv420p[vout]"
    )

    # ---- audio ----
    for k, p in enumerate(plan):
        idx = 1 + n_img + k
        delay = int(p["voice_st"] * 1000)
        fc.append(f"[{idx}:a]aresample=48000,adelay={delay}|{delay},volume=1.0[a{k}]")
    mixin = "".join(f"[a{k}]" for k in range(len(plan)))
    # apad: keo dai track giong bang do dai video, neu khong nhac se bi cat theo giong
    fc.append(
        f"{mixin}amix=inputs={len(plan)}:normalize=0:dropout_transition=0,"
        f"apad,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[vo]"
    )
    fc.append("[vo]asplit=2[vo1][vosc]")
    fc.append(
        f"[{music_idx}:a]aresample=48000,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
        f"dynaudnorm=f=250:g=7:p=0.72:m=8,volume=0.30,"
        f"afade=in:st=0:d=2,afade=out:st={total - 3.5:.3f}:d=3.5[mu]"
    )
    fc.append(
        "[mu][vosc]sidechaincompress=threshold=0.08:ratio=4:attack=15:release=280[muduck]"
    )
    fc.append(
        f"[vo1][muduck]amix=inputs=2:normalize=0:dropout_transition=0,"
        f"alimiter=limit=0.95,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[aout]"
    )

    cmd = (["ffmpeg", "-v", "error", "-stats"] + inputs +
           ["-filter_complex", ";".join(fc),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", f"{total:.3f}", "-movflags", "+faststart", OUT, "-y"])

    open("work/ffmpeg_cmd.txt", "w", encoding="utf-8").write("\n".join(cmd))
    print("Dang render video cuoi...")
    subprocess.run(cmd, check=True)
    print(f"\nXONG -> {OUT}  {dur(OUT):.2f}s  {os.path.getsize(OUT)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
