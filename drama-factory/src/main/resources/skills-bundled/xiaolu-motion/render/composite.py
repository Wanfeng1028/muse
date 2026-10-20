"""Layered compositor (ffmpeg, one pass) -> H.264 MP4.

  L0 base footage     clips trimmed by source frame numbers, cover-fit to the canvas, gaps black
  L1 behind graphics  transparent ProRes (premultiplied), under the person
  L2 person           base x person matte (grey video aligned with the clip's src; white = person)
  L3 front graphics   transparent ProRes (premultiplied), over everything
  L3i invert HUD      transparent ProRes (premultiplied) of the shots marked `invert: true`,
                      difference-blended over L3 (reads on light and dark footage alike)
  L4 camera           global keyframes (resolved["camera"]) applied to the footage and the matte
                      here, and to graphics inside the engine by their depth (parallax)
  L5 finish           eq (contrast / saturation / brightness / gamma) + grain on the whole picture

Premultiplied blending is done in planar RGB as  out = bg*(1-a) + O  with
maskedmerge(bg, black, a) + blend=addition, because ffmpeg's own
overlay=alpha=premultiplied subtracts a limited-range offset (16 levels in gbrp) and
mis-weights semi-transparent pixels — measured by qa/alpha_selftest.py.

The invert layer uses the W3C separable `difference` blend in premultiplied form:
  out = bg*(1-a) + a*|bg - C| = bg*(1-a) + |bg*a - O|        (O = a*C, premultiplied rgb)
i.e. maskedmerge(black, bg, a) -> bg*a, blend=difference with O, plus bg*(1-a). Swapping
`addition` for `difference` in premul_over would give |bg*(1-a) - O|, which is 1 for any opaque
white pixel (always white, never inverted); grainextract drops white ink on black to 0, and
exclusion does not factor through premultiplied alpha. Pixels with a≈0 but rgb>0 (additive glow)
degrade to bg + O, the same as premul_over.

Camera: `perspective` with eval=frame + cubic sampling (sub-pixel; crop's size is fixed at
init, so crop/scale zooms snap to whole pixels). See render/camera.py.
"""
import math
import subprocess
import time
from pathlib import Path

from .camera import is_static, perspective_filter
from .common import load_json, video_info

BASE_TO_RGB = "scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=gbrp"
OV_TO_RGBA = "scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=gbrap"
TO_BT709 = "scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p"


def premul_over(bg, ov_rgba, out, tag):
    """filters for out = bg*(1-a) + O  (bg: gbrp label, ov_rgba: gbrap label)"""
    return [
        f"[{ov_rgba}]split[{tag}c][{tag}a]",
        f"[{tag}c]format=gbrp[{tag}rgb]",
        f"[{tag}a]extractplanes=a,split=3[{tag}m1][{tag}m2][{tag}m3]",
        f"[{tag}m1][{tag}m2][{tag}m3]mergeplanes=0x001020:gbrp[{tag}mask]",
        f"[{bg}]split[{tag}bg][{tag}bz]",
        f"[{tag}bz]lutrgb=r=0:g=0:b=0[{tag}black]",
        f"[{tag}bg][{tag}black][{tag}mask]maskedmerge[{tag}keep]",
        f"[{tag}keep][{tag}rgb]blend=all_mode=addition[{out}]",
    ]


def premul_diff(bg, ov_rgba, out, tag):
    """filters for out = bg*(1-a) + |bg*a - O|  (premultiplied difference; bg: gbrp, ov_rgba: gbrap)"""
    return [
        f"[{ov_rgba}]split[{tag}c][{tag}a]",
        f"[{tag}c]format=gbrp[{tag}rgb]",
        f"[{tag}a]extractplanes=a,split=3[{tag}m1][{tag}m2][{tag}m3]",
        f"[{tag}m1][{tag}m2][{tag}m3]mergeplanes=0x001020:gbrp,split[{tag}mask][{tag}mask2]",
        f"[{bg}]split=3[{tag}bg][{tag}bg2][{tag}bz]",
        f"[{tag}bz]lutrgb=r=0:g=0:b=0,split[{tag}black][{tag}black2]",
        f"[{tag}bg][{tag}black][{tag}mask]maskedmerge[{tag}keep]",
        f"[{tag}black2][{tag}bg2][{tag}mask2]maskedmerge[{tag}under]",
        f"[{tag}under][{tag}rgb]blend=all_mode=difference[{tag}diff]",
        f"[{tag}keep][{tag}diff]blend=all_mode=addition[{out}]",
    ]


def matte_merge(under, person, matte_gray, out, tag):
    """out = under*(1-m) + person*m  (matte grey, full range)"""
    return [
        f"[{matte_gray}]split=3[{tag}m1][{tag}m2][{tag}m3]",
        f"[{tag}m1][{tag}m2][{tag}m3]mergeplanes=0x001020:gbrp[{tag}mask]",
        f"[{under}][{person}][{tag}mask]maskedmerge[{out}]",
    ]


def _cover(sw, sh, W, H):
    if sw == W and sh == H:
        return ""
    s = max(W / sw, H / sh)
    w2, h2 = max(W, 2 * round(sw * s / 2)), max(H, 2 * round(sh * s / 2))
    return f",scale={w2}:{h2}:flags=lanczos,crop={W}:{H}"


def segments(res):
    """clips and black gaps covering [0, duration) in output frames"""
    FPS, N = res["canvas"]["fps"], res["frames"]
    out, f = [], 0
    for c in sorted(res["base"], key=lambda c: c["t0"]):
        a, b = round(c["t0"] * FPS), min(N, round(c["t1"] * FPS))
        if a > f:
            out.append({"gap": True, "f0": f, "f1": a})
        if b > a:
            out.append({"gap": False, "clip": c, "f0": a, "f1": b})
        f = max(f, b)
    if f < N:
        out.append({"gap": True, "f0": f, "f1": N})
    return out


def build(res, overlays=None, audio=True):
    """overlays: {"behind": path|None, "front": path|None, "invert": path|None} (a plain path means front)"""
    if isinstance(overlays, (str, Path)):
        overlays = {"front": overlays}
    overlays = {k: v for k, v in (overlays or {}).items() if v}
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    segs = segments(res)
    has_matte = any((not s["gap"]) and s["clip"].get("matte") for s in segs)
    srcs, args, fg = [], [], []

    def inp(path):
        path = str(path)
        if path not in srcs:
            srcs.append(path)
            args.extend(["-i", path])
        return srcs.index(path)
    for sg in segs:
        if not sg["gap"]:
            inp(sg["clip"]["src"])
            if sg["clip"].get("matte"):
                inp(sg["clip"]["matte"])
    ov_idx = {k: inp(v) for k, v in overlays.items()}
    for k, sg in enumerate(segs):
        n = sg["f1"] - sg["f0"]
        d = n / FPS
        if sg["gap"]:
            fg.append(f"color=c=black:s={W}x{H}:r={FPS}:d={d:.6f},format=yuv420p,setsar=1[v{k}]")
            fg.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.6f}[a{k}]")
            if has_matte:
                fg.append(f"color=c=black:s={W}x{H}:r={FPS}:d={d:.6f},format=gray[m{k}]")
            continue
        c = sg["clip"]
        info = c.get("src_info") or video_info(c["src"])
        sf = info["fps"]
        t_in = c["in"] + (sg["f0"] / FPS - c["t0"])     # first output frame of the segment shows this source time
        i0 = round(t_in * sf)
        i1 = i0 + math.ceil(n * sf / FPS) + 1
        cam = "" if is_static(c["camera"]) and c["camera"][0]["zoom"] == 1.0 else "," + perspective_filter(c["camera"], sg["f0"] / FPS, FPS, W, H)
        chain = f"trim=start_frame={i0}:end_frame={i1},setpts=PTS-STARTPTS,fps={FPS}{_cover(info['w'], info['h'], W, H)},setsar=1"
        fg.append(f"[{srcs.index(c['src'])}:v]{chain},format=yuv420p{cam},trim=end_frame={n}[v{k}]")
        if has_matte:
            if c.get("matte"):
                mi = video_info(c["matte"])
                rng = "pc" if mi.get("color_range") == "pc" else "tv"
                fg.append(f"[{srcs.index(c['matte'])}:v]{chain},scale=in_range={rng}:out_range=pc,format=gray{cam},trim=end_frame={n}[m{k}]")
            else:
                fg.append(f"color=c=black:s={W}x{H}:r={FPS}:d={d:.6f},format=gray[m{k}]")
        if audio and c.get("audio", True) and info.get("has_audio"):
            fg.append(f"[{srcs.index(c['src'])}:a]atrim=start={i0 / sf:.6f}:duration={d:.6f},asetpts=PTS-STARTPTS,aresample=48000,"
                      f"aformat=channel_layouts=stereo,apad=whole_dur={d:.6f}[a{k}]")
        else:
            fg.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.6f}[a{k}]")
    fg.append("".join(f"[v{k}][a{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[bv0][ba]")
    if has_matte:
        fg.append("".join(f"[m{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[bm0]")
    # L4 global camera on footage (+ matte); graphics got theirs in the engine
    gcam = res.get("camera") or []
    if gcam and not (is_static(gcam) and gcam[0]["zoom"] == 1.0):
        pf = perspective_filter(gcam, 0.0, FPS, W, H)
        fg.append(f"[bv0]{pf}[bv]")
        if has_matte:
            fg.append(f"[bm0]{pf}[bm]")
    else:
        fg.append("[bv0]null[bv]")
        if has_matte:
            fg.append("[bm0]null[bm]")
    cur = "L0"
    if has_matte:
        fg.append(f"[bv]{BASE_TO_RGB},split[L0][P0]")    # P0: person pixels for L2
    else:
        fg.append(f"[bv]{BASE_TO_RGB}[L0]")
    if "behind" in overlays:
        fg.append(f"[{ov_idx['behind']}:v]{OV_TO_RGBA}[ovb]")
        fg += premul_over(cur, "ovb", "L1", "b")
        cur = "L1"
    if has_matte:
        fg += matte_merge(cur, "P0", "bm", "L2", "p")
        cur = "L2"
    if "front" in overlays:
        fg.append(f"[{ov_idx['front']}:v]{OV_TO_RGBA}[ovf]")
        fg += premul_over(cur, "ovf", "L3", "f")
        cur = "L3"
    if "invert" in overlays:
        fg.append(f"[{ov_idx['invert']}:v]{OV_TO_RGBA}[ovi]")
        fg += premul_diff(cur, "ovi", "L3i", "i")
        cur = "L3i"
    fin = res.get("finish") or {}
    post = [TO_BT709]
    eqp = {k: fin[k] for k in ("contrast", "saturation", "brightness", "gamma") if k in fin}
    if eqp:
        post.append("eq=" + ":".join(f"{k}={v}" for k, v in eqp.items()))
    if fin.get("grain"):
        post.append(f"noise=alls={fin['grain']}:allf=t")
    fg.append(f"[{cur}]{','.join(post)}[vout]")
    return args, ";\n".join(fg)


def composite(res, overlays, out, crf=16, preset="medium", audio=True):
    res = load_json(res) if isinstance(res, (str, Path)) else res
    FPS, N = res["canvas"]["fps"], res["frames"]
    args, graph = build(res, overlays, audio)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gfile = out.with_name(out.stem + ".filtergraph.txt")
    gfile.write_text(graph, encoding="utf-8")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, "-/filter_complex", str(gfile),
           "-map", "[vout]", "-map", "[ba]", "-frames:v", str(N),
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv",
           "-r", str(FPS), "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    return {"out": str(out), "seconds": round(time.time() - t0, 2), "filtergraph": str(gfile)}
