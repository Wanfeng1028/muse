# -*- coding: utf-8 -*-
"""Assemble 26.08.08 Traffic nội sàn / ngoại sàn: scenes + splits + sticker + flash + SFX + outro."""
import os
import subprocess
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(ROOT, "clips")
ST = os.path.join(ROOT, "stick")
os.makedirs(ST, exist_ok=True)
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
SRC = P.src()
OUTRO = P.OUTRO
FINAL = P.out_file()
MAIN = os.path.join(ROOT, "main.mp4")
CAR = P.extra("carousel-hook-video-ban-hang")
W, H, DUR = 1080, 1920, 114.08

# ---------- sticker (illustration người bán) ----------
from scipy import ndimage


def sticker(path, target_h, out):
    im = Image.open(path).convert("RGBA")
    r = target_h / im.height
    im = im.resize((int(im.width * r), target_h))
    a = np.array(im.split()[3]) > 60
    dil = ndimage.binary_dilation(a, iterations=12)
    border = Image.fromarray((dil * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
    canvas = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", im.size, (255, 255, 255, 255)), (20, 20), border)
    canvas.alpha_composite(im, (20, 20))
    sh = Image.new("RGBA", (canvas.width + 60, canvas.height + 60), (0, 0, 0, 0))
    m = canvas.split()[3].point(lambda v: min(v, 70))
    sh.paste(Image.new("RGBA", canvas.size, (0, 0, 0, 255)), (36, 40), m)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    sh.paste(canvas, (30, 30), canvas)
    sh.save(os.path.join(ST, out))
    return sh.size


st_size = sticker(os.path.join(CAR, "illustration-2.png"), 820, "st-social.png")
print("sticker", st_size, flush=True)


def flash_png(peak, out):
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.42) / (H * 0.75)) ** 2)
    a = np.clip(1.15 - d, 0, 1) ** 1.6 * peak * 255
    img = np.zeros((H, W, 4), dtype=np.uint8)
    img[..., 0:3] = (255, 250, 235)
    img[..., 3] = a.astype(np.uint8)
    Image.fromarray(img, "RGBA").save(os.path.join(ST, out))


flash_png(0.85, "flash-s.png")
flash_png(0.38, "flash-w.png")

# ---------- SFX ----------
SR = 44100


def synth(expr, dur, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", expr,
                    "-t", str(dur), "-ar", str(SR), "-ac", "1", os.path.join(ROOT, out)], check=True)


synth("anoisesrc=d=0.5:c=pink:a=0.9,highpass=f=250,lowpass=f=3000,afade=t=in:d=0.1,afade=t=out:st=0.2:d=0.3", 0.5, "s-wh1.wav")
synth("anoisesrc=d=0.3:c=white:a=0.5,highpass=f=2500,afade=t=in:d=0.05,afade=t=out:st=0.1:d=0.2", 0.3, "s-wh2.wav")
synth("aevalsrc='0.8*sin(2*PI*(460+340*exp(-16*t))*t)*exp(-12*t)':s=44100", 0.34, "s-pop.wav")
synth("anoisesrc=d=0.03:c=white:a=0.9", 0.03, "s-click.wav")
synth("aevalsrc='0.5*(sin(2*PI*1318*t)+0.55*sin(2*PI*1976*t))*exp(-8*t)':s=44100", 0.55, "s-ding.wav")
synth("aevalsrc='0.55*sin(2*PI*930*t)*lt(mod(t,0.17),0.1)*exp(-4*t)':s=44100", 0.4, "s-alert.wav")
synth("aevalsrc='0.6*(sin(2*PI*196*t)+0.5*sin(2*PI*392*t))*exp(-3.2*t)':s=44100", 0.9, "s-boom.wav")


def lw(n):
    with wave.open(os.path.join(ROOT, n), "rb") as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


wh1, wh2, pop, click, ding, alert, boom = [lw(f"s-{n}.wav") for n in ("wh1", "wh2", "pop", "click", "ding", "alert", "boom")]
whoosh = np.zeros(len(wh1) + int(0.1 * SR), dtype=np.float32)
whoosh[:len(wh1)] += wh1
whoosh[int(0.08 * SR):int(0.08 * SR) + len(wh2)] += wh2 * 0.7
popc = np.zeros(len(pop), dtype=np.float32)
popc[:len(pop)] += pop
popc[:len(click)] += click * 0.5

# scenes: (name, start, dur)
scenes = [
    ("S_HOOK", 1.50, 2.45), ("S_ONE", 4.10, 3.65), ("S_TWO", 8.00, 3.55),
    ("S_SHOPEE", 14.55, 6.30), ("S_TIKTOK", 21.00, 5.15), ("S_PRO", 26.35, 4.45),
    ("S_RISK", 33.95, 4.45), ("S_OUT", 42.10, 5.05), ("S_OWN", 51.05, 6.50),
    ("S_TEST", 58.00, 8.70), ("S_50A", 67.10, 4.65), ("S_50B", 71.85, 3.60), ("S_DEP", 75.70, 3.40),
    ("S_ORDER", 79.25, 5.10), ("S_CHK1", 84.65, 5.55), ("S_CHK2", 90.30, 6.25),
    ("S_EXP", 96.65, 4.40), ("S_KEEP", 101.15, 6.20), ("S_CTA", 107.55, 3.30),
    ("S_SAVE", 111.05, 3.00),
]
# splits: (clip, seqdir, start, dur)
splits = [("P_COLD", "cut_q1b", 47.25, 3.60)]
# sticker window
stick = ("st-social.png", 38.70, 41.80)
pips = [("pip-shopee.png", 11.80, 14.45), ("pip-analytics.png", 31.10, 33.85), ("pip-tiktok.png", 0.25, 1.45)]
labels = [("lbl-noisan.png", 11.70, 14.50), ("lbl-noisan.png", 30.95, 33.90), ("lbl-ngoaisan.png", 38.55, 42.05)]
punches = [3.95, 11.55, 30.80, 38.40]
flash_at = [s for _, s, _ in scenes] + [s for _, _, s, _ in splits] + [stick[1]]
events_extra = []

# ding timings: capsule pops per scene (offsets added to scene start)
ding_off = {
    "S_ONE": [0.30, 1.35, 2.10], "S_TWO": [0.40, 0.85],
    "S_SHOPEE": [0.85, 1.90, 3.10, 4.20], "S_TIKTOK": [0.80, 1.60, 2.50, 3.40],
    "S_PRO": [1.10, 2.10], "S_RISK": [0.65, 1.35, 2.10, 2.85],
    "S_OUT": [2.20, 3.30], "S_OWN": [0.35, 1.60, 3.50],
    "S_TEST": [1.70, 3.60, 6.10], "S_50A": [0.50, 1.50, 2.50],
    "S_DEP": [1.10], "S_ORDER": [0.50, 1.30, 2.60],
    "S_CHK1": [0.30, 2.10, 3.60], "S_CHK2": [0.50, 2.10, 3.40, 5.00],
    "S_EXP": [1.50, 2.60], "S_KEEP": [0.45, 1.90, 3.30, 4.90],
    "S_CTA": [1.00], "S_SAVE": [0.28],
}
events = []
for name, s, d in scenes:
    events.append((s, whoosh, 0.42))
for name, sd, s, d in splits:
    events.append((s, whoosh, 0.28))
events.append((stick[1], whoosh, 0.26))
for _pt in (11.80, 31.10, 0.25):
    events.append((_pt, whoosh, 0.22))
for t in punches:
    events.append((t, popc, 0.44))
for name, s, d in scenes:
    for off in ding_off.get(name, []):
        events.append((s + off, ding, 0.30))
for t in [1.52, 33.97, 75.72]:
    events.append((t, alert, 0.5))
events.append((71.85 + 1.45, boom, 0.55))
events.append((114.10, boom, 0.5))

track = np.zeros(int((DUR + 1.2) * SR), dtype=np.float32)
for t, snd, vol in events:
    i0 = int(t * SR)
    if i0 >= len(track):
        continue
    track[i0:i0 + len(snd)] += snd[:len(track) - i0] * vol
track = np.clip(track, -0.9, 0.9)
with wave.open(os.path.join(ROOT, "sfx.wav"), "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(SR)
    f.writeframes((track * 32767).astype(np.int16).tobytes())
print("sfx events:", len(events), flush=True)

# ---------- assemble main ----------
terms = "+".join([f"0.12*gte(it,{t})*lt(it,{t + 0.35})*(1-(it-{t})/0.35)" for t in punches])
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-progress", os.path.join(ROOT, "prog.txt"), "-i", SRC]
for name, s, d in scenes:
    cmd += ["-i", os.path.join(CLIPS, f"{name}.mp4")]
for name, sd, s, d in splits:
    cmd += ["-i", os.path.join(CLIPS, f"{name}.mp4")]
for name, sd, s, d in splits:
    cmd += ["-framerate", "25", "-start_number", "1", "-i", os.path.join(ROOT, sd, "%04d.png")]
pngs = [stick[0], "flash-s.png", "flash-w.png"] + [p[0] for p in pips] + sorted({l[0] for l in labels})
sizes = {}
for fn in pngs:
    sizes[fn] = Image.open(os.path.join(ST, fn)).size
    cmd += ["-framerate", "2", "-loop", "1", "-i", os.path.join(ST, fn)]
cmd += ["-i", os.path.join(ROOT, "sfx.wav")]

n_sc, n_sp = len(scenes), len(splits)
seq_base = 1 + n_sc + n_sp
png_base = seq_base + n_sp
idx = {fn: png_base + i for i, fn in enumerate(pngs)}
sfx_i = png_base + len(pngs)

fc = [f"[0:v]zoompan=z='1+{terms}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=25[base];"]
for i, (name, sd, s, d) in enumerate(splits):
    fc.append(f"[{seq_base + i}:v]setpts=PTS+{s}/TB,scale=760:842[c{i}];")
    fc.append(f"[{1 + n_sc + i}:v]setpts=PTS+{s}/TB[pb{i}];")
    fc.append(f"[pb{i}][c{i}]overlay=160:1074:shortest=0[sp{i}];")
cur, step = "[base]", 0


def add(e):
    global cur, step
    fc.append(e.replace("CUR", cur).replace("STEP", f"[v{step}]"))
    cur = f"[v{step}]"
    step += 1


for j, (name, s, d) in enumerate(scenes):
    fc.append(f"[{1 + j}:v]setpts=PTS+{s}/TB[sc{j}];")
    add(f"CUR[sc{j}]overlay=0:0:enable='between(t,{s},{round(s + d - 0.02, 2)})'STEP;")
for i, (name, sd, s, d) in enumerate(splits):
    add(f"CUR[sp{i}]overlay=0:0:enable='between(t,{s},{round(s + d - 0.02, 2)})'STEP;")
sw, sh_ = sizes[stick[0]]
xf, y = W - sw + 24, H - sh_ + 34
xin = f"({sw}+80)*pow(max(0,1-(t-{stick[1]})/0.4),2)"
xout = f"({sw}+80)*pow(max(0,(t-{stick[2] - 0.35})/0.35),2)"
add(f"CUR[{idx[stick[0]]}:v]overlay=x='{xf}+{xin}+{xout}':y={y}:enable='between(t,{stick[1]},{stick[2]})'STEP;")
for fn, s0, e0 in pips:
    ow, oh = sizes[fn]
    xf, y = W - ow + 30, H - oh - 120
    xin = f"({ow}+80)*pow(max(0,1-(t-{s0})/0.4),2)"
    xout = f"({ow}+80)*pow(max(0,(t-{e0 - 0.32})/0.32),2)"
    add(f"CUR[{idx[fn]}:v]overlay=x='{xf}+{xin}+{xout}':y={y}:enable='between(t,{s0},{e0})'STEP;")
    events_extra.append(s0)

for fn, s0, e0 in labels:
    ow, oh = sizes[fn]
    xin = f"({ow}+70)*pow(max(0,1-(t-{s0})/0.38),2)"
    add(f"CUR[{idx[fn]}:v]overlay=x='{60}-{xin}':y=250:enable='between(t,{s0},{e0})'STEP;")

en_s = "+".join([f"between(t,{t - 0.06},{t + 0.02})" for t in flash_at])
en_w = "+".join([f"between(t,{t + 0.02},{t + 0.10})" for t in flash_at])
add(f"CUR[{idx['flash-s.png']}:v]overlay=0:0:enable='{en_s}'STEP;")
add(f"CUR[{idx['flash-w.png']}:v]overlay=0:0:enable='{en_w}'STEP;")
fc.append(f"[0:a][{sfx_i}:a]amix=inputs=2:duration=first:normalize=0[aout]")
cmd += ["-filter_complex", "".join(fc), "-map", cur, "-map", "[aout]", "-t", str(DUR), "-r", "25",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", MAIN]
print("assembling main...", flush=True)
subprocess.run(cmd, check=True)
print("main done", flush=True)

# ---------- outro concat ----------
outro25 = os.path.join(ROOT, "outro25.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", OUTRO,
                "-vf", "fps=25,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1:color=white",
                "-af", "aresample=44100", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", outro25], check=True)
lst = os.path.join(ROOT, "concat.txt")
with open(lst, "w", encoding="utf-8") as f:
    f.write(f"file '{MAIN.replace(chr(92), '/')}'\nfile '{outro25.replace(chr(92), '/')}'\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", FINAL], check=True)
print("FINAL:", FINAL, flush=True)
