# -*- coding: utf-8 -*-
"""V6: birefnet-gated cutouts, alarm on title, badge logos, light flashes, richer SFX."""
import glob
import math
import os
import subprocess
import wave
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rembg import remove, new_session

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
ROOT = P.work()
B3, B5, ST = [os.path.join(ROOT, d) for d in ("build3", "build5", "stickers")]
FIX = P.FIX
LOGO = P.LOGO
FONTS = P.FONTS
F_BLACK = os.path.join(FONTS, "PS Anton - Regular V1.0.otf")
F_XBOLD = os.path.join(FONTS, "Big Shoulders ExtraBold Viet Hoa.otf")
SRC = P.src()
OUT = P.out_file()
W, H, FPS = 1080, 1920, 25
TEAL = (23, 217, 179, 255)
NAVY = (27, 37, 134, 255)
RED = (198, 0, 1, 255)
INK = (23, 23, 23, 255)
WHITE = (255, 255, 255, 255)
NEN = Image.open(os.path.join(FIX, "Nền.png")).convert("RGBA").resize((W, H))

# ================= 1. birefnet gate + re-clean persons =================
print("building birefnet gates...", flush=True)
biref = new_session("birefnet-portrait")
for w in ["w1", "w2", "w3"]:
    raw = sorted(glob.glob(os.path.join(ROOT, f"frames_{w}_raw", "*.png")))
    gate_path = os.path.join(ROOT, f"gate_{w}.npy")
    if not os.path.exists(gate_path):
        gate = None
        for f in raw[::18] + [raw[-1]]:
            m = remove(Image.open(f), session=biref, only_mask=True)
            arr = np.array(m) > 128
            gate = arr if gate is None else (gate | arr)
        gate = ndimage.binary_dilation(gate, iterations=22)
        np.save(gate_path, gate)
    print("gate", w, "ok", flush=True)

for w in ["w1", "w2", "w3"]:
    gate = np.load(os.path.join(ROOT, f"gate_{w}.npy"))
    dst = os.path.join(ROOT, f"frames_{w}_cut5")
    os.makedirs(dst, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(ROOT, f"frames_{w}_cut2", "*.png"))):
        o = os.path.join(dst, os.path.basename(f))
        if os.path.exists(o):
            continue
        img = Image.open(f).convert("RGBA")
        arr = np.array(img).astype(np.int16)
        a = arr[..., 3]
        hard = (a > 170) & gate
        opened = ndimage.binary_opening(hard, iterations=6)
        lab, n = ndimage.label(opened)
        if n >= 1:
            sizes = ndimage.sum(opened, lab, range(1, n + 1))
            seed = lab == (np.argmax(sizes) + 1)
            recon = ndimage.binary_propagation(seed, mask=hard)
        else:
            recon = hard
        a2 = np.where(recon, a, 0)
        rows = np.where(a2.sum(axis=1) > 0)[0]
        if len(rows):
            t0 = rows[0]
            zone = np.zeros_like(recon)
            zone[t0:t0 + 115, :] = True
            bright = np.maximum.reduce([arr[..., 0], arr[..., 1], arr[..., 2]]) > 68
            bad = ndimage.binary_dilation(bright & zone & recon, iterations=1)
            for c, v in zip(range(3), (28, 24, 22)):
                arr[..., c] = np.where(bad, v, arr[..., c])
        out = arr.clip(0, 255).astype(np.uint8)
        im2 = Image.fromarray(out, "RGBA")
        im2.putalpha(Image.fromarray(a2.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
        im2.save(o)
    print(w, "cut5 done", flush=True)

# ================= 2. S1 with alarm siren =================
def text_w(f, s):
    b = f.getbbox(s)
    return b[2] - b[0]


def fit_font(path, size, s, maxw):
    f = ImageFont.truetype(path, size)
    while text_w(f, s) > maxw and size > 20:
        size -= 2
        f = ImageFont.truetype(path, size)
    return f


def shadowed(img, blur=8, alpha=60, off=(0, 6)):
    sh = Image.new("RGBA", (img.width + 60, img.height + 60), (0, 0, 0, 0))
    mask = img.split()[3].point(lambda a: min(a, alpha))
    sh.paste(Image.new("RGBA", img.size, (0, 0, 0, 255)), (30 + off[0], 30 + off[1]), mask)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.paste(img, (30, 30), img)
    return sh


def capsule(s, size, fg, bg, padx=40, pady=22, radius=30, maxw=940, font=F_XBOLD):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw - 2 * padx)
    tw = text_w(f, s)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (tw + 2 * padx, asc + desc + 2 * pady), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=bg)
    d.text((padx, pady), s, font=f, fill=fg)
    return shadowed(img)


def textimg(s, size, color, font=F_XBOLD, maxw=960):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (text_w(f, s) + 8, asc + desc + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4, 4), s, font=f, fill=color)
    return img


def icon_siren(size=170):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.pieslice((14 * s, 18 * s, 50 * s, 54 * s), 180, 360, fill=RED)
    d.rectangle((14 * s, 36 * s, 50 * s, 42 * s), fill=RED)
    d.rounded_rectangle((8 * s, 42 * s, 56 * s, 52 * s), 5 * s, fill=NAVY)
    d.arc((20 * s, 24 * s, 36 * s, 40 * s), 160, 260, fill=(255, 190, 190, 255), width=int(3 * s))
    for ang in (-45, 0, 45):
        rad = math.radians(ang - 90)
        x0 = 32 * s + 22 * s * math.cos(rad)
        y0 = 34 * s + 22 * s * math.sin(rad)
        x1 = 32 * s + 30 * s * math.cos(rad)
        y1 = 34 * s + 30 * s * math.sin(rad)
        d.line((x0, y0, x1, y1), fill=RED, width=int(3.5 * s))
    return shadowed(img, blur=8, alpha=55)


def eob(p):
    c1, c3 = 1.70158, 2.70158
    p -= 1
    return 1 + c3 * p ** 3 + c1 * p ** 2


def eoc(p):
    return 1 - (1 - p) ** 3


class Layer:
    def __init__(self, img, cx, cy, t0, anim="pop", dur=0.34, dy=70, shake=0.0):
        self.img, self.cx, self.cy, self.t0 = img, cx, cy, t0
        self.anim, self.dur, self.dy, self.shake = anim, dur, dy, shake

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        img, cx, cy, alpha = self.img, self.cx, self.cy, 1.0
        if self.anim == "pop":
            sc = 0.6 + 0.4 * eob(p)
            if p < 1.0:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
            alpha = min(1.0, p * 3)
        elif self.anim == "slide":
            cy = cy + self.dy * (1 - eoc(p))
            alpha = min(1.0, p * 2.5)
        elif self.anim == "wipe":
            ww = max(1, int(img.width * eoc(p)))
            img = img.crop((0, 0, ww, img.height))
            cx = self.cx - (self.img.width - ww) // 2
        if self.shake and p >= 1.0 and (t - self.t0) < self.dur + 1.0:
            ang = self.shake * math.sin(2 * math.pi * 7 * (t - self.t0))
            img = img.rotate(ang, resample=Image.BICUBIC, expand=False)
        if alpha < 1.0:
            img = img.copy()
            img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def render_scene(name, dur, layers):
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast",
           "-crf", "18", "-pix_fmt", "yuv420p", os.path.join(B5, f"{name}.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        canvas = NEN.copy()
        for L in layers:
            L.draw(canvas, t)
        proc.stdin.write(canvas.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    print("scene", name, flush=True)


layers = [
    Layer(icon_siren(180), 540, 470, 0.05, "pop", 0.4, shake=5),
    Layer(capsule("5 LƯU Ý", 150, WHITE, TEAL, padx=60, pady=28, radius=44, font=F_BLACK), 540, 760, 0.4, "pop", 0.4),
    Layer(textimg("HÓA ĐƠN ĐIỆN TỬ", 96, NAVY), 540, 1000, 0.75, "slide"),
    Layer(textimg("CHO SHOP BÁN SÀN TMĐT", 56, INK), 540, 1120, 1.0, "slide"),
]
bar = Image.new("RGBA", (240, 12), (0, 0, 0, 0))
ImageDraw.Draw(bar).rounded_rectangle((0, 0, 239, 11), 6, fill=RED)
layers.append(Layer(bar, 540, 1250, 1.25, "wipe", 0.4))
render_scene("S1", 4.40, layers)

# ================= 3. badge logos =================
def badge(icon_img, out, size=176, icon_ratio=0.72):
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, size - 1, size - 1), 36, fill=WHITE, outline=(224, 227, 238, 255), width=2)
    im = icon_img.convert("RGBA")
    m = size * icon_ratio
    r = min(m / im.width, m / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    card.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    sh = shadowed(card, blur=10, alpha=70, off=(0, 8))
    sh.save(os.path.join(ST, out))
    print(out, sh.size, flush=True)


sh_full = Image.open(os.path.join(LOGO, "logo-shopee-mau-goc.png")).convert("RGBA")
sh_bag = sh_full.crop((0, 0, sh_full.width, int(sh_full.height * 0.76)))
sh_bag = sh_bag.crop(sh_bag.getbbox())
badge(sh_bag, "bdg-shopee.png")
badge(Image.open(os.path.join(LOGO, "logo-tiktok-icon.png")), "bdg-tiktok.png")
lz = Image.open(os.path.join(ROOT, "logo-lazada.png")).convert("RGBA")
lz_icon = lz.crop((0, 0, int(lz.width * 0.27), lz.height))
lz_icon = lz_icon.crop(lz_icon.getbbox())
badge(lz_icon, "bdg-lazada.png")

# ================= 4. light flash overlays =================
def flash_png(alpha_peak, out):
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H * 0.42
    dist = np.sqrt(((xx - cx) / (W * 0.75)) ** 2 + ((yy - cy) / (H * 0.75)) ** 2)
    a = np.clip(1.15 - dist, 0, 1) ** 1.6 * alpha_peak * 255
    img = np.zeros((H, W, 4), dtype=np.uint8)
    img[..., 0:3] = (255, 250, 235)
    img[..., 3] = a.astype(np.uint8)
    Image.fromarray(img, "RGBA").save(os.path.join(ST, out))


flash_png(0.85, "flash-strong.png")
flash_png(0.38, "flash-weak.png")
print("flash pngs ok", flush=True)

# ================= 5. SFX =================
SR = 44100


def synth(expr, dur, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", expr,
                    "-t", str(dur), "-ar", str(SR), "-ac", "1", out], check=True)


synth("anoisesrc=d=0.5:c=pink:a=0.9,highpass=f=250,lowpass=f=3000,afade=t=in:d=0.1,afade=t=out:st=0.2:d=0.3", 0.5, os.path.join(ROOT, "sx-wh1.wav"))
synth("anoisesrc=d=0.3:c=white:a=0.5,highpass=f=2500,afade=t=in:d=0.05,afade=t=out:st=0.1:d=0.2", 0.3, os.path.join(ROOT, "sx-wh2.wav"))
synth("aevalsrc='0.8*sin(2*PI*(460+340*exp(-16*t))*t)*exp(-12*t)':s=44100", 0.34, os.path.join(ROOT, "sx-pop.wav"))
synth("anoisesrc=d=0.03:c=white:a=0.9", 0.03, os.path.join(ROOT, "sx-click.wav"))
synth("aevalsrc='0.5*(sin(2*PI*1318*t)+0.55*sin(2*PI*1976*t))*exp(-8*t)':s=44100", 0.55, os.path.join(ROOT, "sx-ding.wav"))
synth("aevalsrc='0.55*sin(2*PI*930*t)*lt(mod(t,0.17),0.1)*exp(-4*t)':s=44100", 0.4, os.path.join(ROOT, "sx-alert.wav"))


def load_wav(p):
    with wave.open(p, "rb") as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


wh1, wh2, pop, click, ding, alert = [load_wav(os.path.join(ROOT, f"sx-{n}.wav")) for n in ("wh1", "wh2", "pop", "click", "ding", "alert")]
whoosh = np.zeros(len(wh1) + int(0.1 * SR), dtype=np.float32)
whoosh[:len(wh1)] += wh1
whoosh[int(0.08 * SR):int(0.08 * SR) + len(wh2)] += wh2 * 0.7
popc = np.zeros(len(pop), dtype=np.float32)
popc[:len(pop)] += pop
popc[:len(click)] += click * 0.5

events = []
for t in [2.50, 5.22, 18.30, 26.60, 32.26, 36.60, 58.64, 75.00, 92.60, 97.40, 101.94, 108.78, 118.30]:
    events.append((t, whoosh, 0.42))
for t in [12.60, 45.52, 68.62, 42.90, 53.40, 65.30, 83.60, 88.60, 115.60]:
    events.append((t, whoosh, 0.26))
for t in [9.62, 24.98, 42.40, 51.34, 82.30, 114.20, 0.50, 0.85, 1.20]:
    events.append((t, popc, 0.44))
for t in [19.30, 20.30, 21.20, 22.60, 75.70, 77.10, 79.50, 80.70,
          102.84, 103.94, 105.04, 106.14, 107.24, 109.68, 111.08, 112.68, 38.60]:
    events.append((t, ding, 0.30))
events.append((5.30, alert, 0.5))

track = np.zeros(int(122.2 * SR), dtype=np.float32)
for t, snd, vol in events:
    i0 = int(t * SR)
    track[i0:i0 + len(snd)] += snd[:len(track) - i0] * vol
track = np.clip(track, -0.9, 0.9)
with wave.open(os.path.join(ROOT, "sfx-track.wav"), "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(SR)
    f.writeframes((track * 32767).astype(np.int16).tobytes())
print("sfx track:", len(events), "events", flush=True)

# ================= 6. assembly =================
scenes = [
    (B5, "A1", 2.50, 2.62), (B5, "S1", 5.22, 4.40), (B5, "S2", 18.30, 6.68),
    (B3, "B1", 26.60, 3.60), (B5, "A2", 32.26, 4.34), (B5, "S3", 36.60, 5.80),
    (B5, "S4", 58.64, 5.30), (B5, "S5", 75.00, 7.30), (B5, "A3", 92.60, 3.30),
    (B5, "A4", 97.40, 3.40), (B5, "S6", 101.94, 6.50), (B5, "S7", 108.78, 5.42),
    (B5, "E1", 118.30, 3.70),
]
splits = [("P1", 12.60, 18.18, 0), ("P2", 45.52, 51.34, 1), ("P3", 68.62, 72.62, 2), ("P4", 72.62, 75.00, 3)]
stickers = [
    ("st-b7.png", 42.90, 45.30), ("st-b2.png", 53.40, 57.60), ("st-b3.png", 65.30, 68.50),
    ("st-b4.png", 83.60, 87.50), ("st-b5.png", 88.60, 91.90),
]
badges = [
    ("bdg-shopee.png", 70, 250, 0.50, 2.45),
    ("bdg-tiktok.png", 830, 250, 0.85, 2.45),
    ("bdg-lazada.png", 70, 1230, 1.20, 2.45),
]
flash_times = [2.50, 5.22, 12.60, 18.30, 26.60, 32.26, 36.60, 45.52, 58.64, 68.62, 75.00, 92.60, 97.40, 101.94, 108.78, 118.30]
punches = [9.62, 24.98, 42.40, 51.34, 82.30, 114.20]
terms = "+".join([f"0.12*gte(it,{t})*lt(it,{t + 0.35})*(1-(it-{t})/0.35)" for t in punches])
zexpr = f"1+{terms}"

cmd = ["ffmpeg", "-y", "-loglevel", "error", "-progress", os.path.join(ROOT, "progress6.txt"), "-i", SRC]
for d, name, s0, d0 in scenes:
    cmd += ["-i", os.path.join(d, f"{name}.mp4")]
for name, s0, e0, k in splits:
    cmd += ["-i", os.path.join(B5, f"{name}.mp4")]
for d0 in ["frames_w1_cut5", "frames_w2_cut5", "frames_w3_cut5"]:
    cmd += ["-framerate", "25", "-start_number", "1", "-i", os.path.join(ROOT, d0, "%04d.png")]
sizes = {}
pngs = [s[0] for s in stickers] + ["st-follow.png"] + [b[0] for b in badges] + ["flash-strong.png", "flash-weak.png"]
for fn in pngs:
    p = os.path.join(ST, fn)
    sizes[fn] = Image.open(p).size
    cmd += ["-framerate", "2", "-loop", "1", "-i", p]
cmd += ["-i", os.path.join(ROOT, "sfx-track.wav")]

n_sc, n_sp = len(scenes), len(splits)
seq_base = 1 + n_sc + n_sp
png_base = seq_base + 3
idx_of = {fn: png_base + i for i, fn in enumerate(pngs)}
sfx_idx = png_base + len(pngs)

fc = [f"[0:v]zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=25[base];"]
fc.append(f"[{seq_base}:v]setpts=PTS+12.60/TB,scale=979:1085[c0];")
fc.append(f"[{seq_base + 1}:v]setpts=PTS+45.52/TB,scale=979:1085[c1];")
fc.append(f"[{seq_base + 2}:v]setpts=PTS+68.62/TB,scale=979:1085,split=2[c2][c3];")
for i, (name, s0, e0, k) in enumerate(splits):
    idx = 1 + n_sc + i
    fc.append(f"[{idx}:v]setpts=PTS+{s0}/TB[pbg{i}];")
    fc.append(f"[pbg{i}][c{k}]overlay=50:835:shortest=0[sp{i}];")
cur = "[base]"
step = 0


def add(expr):
    global cur, step
    fc.append(expr.replace("CUR", cur).replace("STEP", f"[v{step}]"))
    cur = f"[v{step}]"
    step += 1


for fn, x, y, s0, e0 in badges:
    add(f"CUR[{idx_of[fn]}:v]overlay=x={x}:y='{y}-70*pow(max(0,1-(t-{s0})/0.35),2)':enable='between(t,{s0},{e0})'STEP;")
for j, (d, name, s0, d0) in enumerate(scenes):
    fc.append(f"[{1 + j}:v]setpts=PTS+{s0}/TB[sc{j}];")
    add(f"CUR[sc{j}]overlay=0:0:enable='between(t,{s0},{round(s0 + d0 - 0.02, 2)})'STEP;")
for i, (name, s0, e0, k) in enumerate(splits):
    add(f"CUR[sp{i}]overlay=0:0:enable='between(t,{s0},{e0})'STEP;")
for fn, s0, e0 in stickers:
    ow, oh = sizes[fn]
    xf = W - ow + 24
    y = H - oh + 34
    xin = f"({ow}+80)*pow(max(0,1-(t-{s0})/0.4),2)"
    xout = f"({ow}+80)*pow(max(0,(t-{e0 - 0.35})/0.35),2)"
    add(f"CUR[{idx_of[fn]}:v]overlay=x='{xf}+{xin}+{xout}':y={y}:enable='between(t,{s0},{e0})'STEP;")
fw, fh = sizes["st-follow.png"]
add(f"CUR[{idx_of['st-follow.png']}:v]overlay=x={(W - fw) // 2}:y='1450+80*pow(max(0,1-(t-115.60)/0.35),2)':enable='between(t,115.60,117.90)'STEP;")
en_strong = "+".join([f"between(t,{t - 0.06},{t + 0.02})" for t in flash_times])
en_weak = "+".join([f"between(t,{t + 0.02},{t + 0.10})" for t in flash_times])
add(f"CUR[{idx_of['flash-strong.png']}:v]overlay=0:0:enable='{en_strong}'STEP;")
add(f"CUR[{idx_of['flash-weak.png']}:v]overlay=0:0:enable='{en_weak}'STEP;")
fc.append(f"[0:a][{sfx_idx}:a]amix=inputs=2:duration=first:normalize=0[aout]")
graph = "".join(fc)
cmd += ["-filter_complex", graph, "-map", cur, "-map", "[aout]", "-t", "122", "-r", "25",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", OUT]
print("running assemble v6...", flush=True)
subprocess.run(cmd, check=True)
print("V6 DONE:", OUT, flush=True)
