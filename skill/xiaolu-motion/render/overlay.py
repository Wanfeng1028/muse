"""Render the overlay layer of a resolved storyboard.

  python3 -m render overlay resolved.json --out overlay.mov [--workers 4] [--formats prores,hevc]

- N workers = N headless Chrome pages, each renders a contiguous frame range and streams
  raw premultiplied RGBA straight into its own ffmpeg (no PNG sequence on disk).
- ProRes 4444 (prores_ks, yuva444p10le, 16-bit alpha, premultiplied, BT.709 tags) segments
  are concatenated losslessly (-c copy; ProRes is intra-only).
- HEVC with alpha (hevc_videotoolbox, MOV/hvc1, premultiplied — VideoToolbox default, which
  writes alpha_channel_use_idc=1) is transcoded from the finished ProRes in one hardware
  pass, fed as AYUV so the BT.709 matrix/primaries/transfer tags are all written.
  (Adding VUI tags afterwards with hevc_metadata breaks the alpha layer for AVFoundation.)
- stills(): render chosen times to numpy arrays (RGBA, premultiplied in overlay mode).
"""
import asyncio
import json
import math
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from .browser import launch, open_engine, page_config
from .common import load_json, save_json
from .fonts import resolve_faces
from .server import Sink

TAGS = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
TO_YUV = "scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format={fmt},setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def prores_cmd(W, H, fps, out):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
            "-vf", TO_YUV.format(fmt="yuva444p10le"), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
            "-alpha_bits", "16", "-vendor", "apl0", *TAGS, "-movflags", "+write_colr", "-an", str(out)]


def hevc_alpha_from(src, out, alpha_quality=0.9, quality=None, bitrate="24M"):
    """ProRes 4444 (premultiplied) -> HEVC with alpha (premultiplied) in MOV."""
    rate = ["-q:v", str(quality)] if quality else ["-b:v", bitrate]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-vf", "scale=in_color_matrix=bt709:in_range=tv:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=ayuv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-c:v", "hevc_videotoolbox", "-alpha_quality", str(alpha_quality), *rate, "-tag:v", "hvc1", *TAGS,
           "-movflags", "+write_colr", "-an", str(out)]
    subprocess.run(cmd, check=True)


async def _segment(p, res, faces, i0, i1, out, mode, tag, verbose, layer=None):
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    sink = Sink(faces)
    proc = subprocess.Popen(prores_cmd(W, H, FPS, out), stdin=subprocess.PIPE)
    lock = threading.Lock()
    nxt = {"i": i0}

    def handler(path, data):
        i = int(path.split("i=")[1])
        with lock:
            if i < nxt["i"]:            # duplicate delivery after a client retry: already written
                return
            assert i == nxt["i"], (i, nxt["i"])
            assert len(data) == W * H * 4, len(data)
            proc.stdin.write(data)
            nxt["i"] += 1
    sink.handler = handler
    browser = await launch(p)
    t0 = time.time()
    page, info = await open_engine(browser, sink, page_config(res, res["tokens"], faces, mode, layer=layer), verbose)
    boot = time.time() - t0
    CH = 30
    t1 = time.time()
    for a in range(i0, i1, CH):
        b = min(i1, a + CH)
        await page.evaluate("([a,b,u]) => window.XM.renderRange(a,b,u)", [a, b, "/frame"])
        if verbose:
            el = time.time() - t1
            print(f"[{tag}] {b - i0}/{i1 - i0} frames {el:.1f}s {(b - i0) / max(el, 1e-6):.1f} fps", flush=True)
    st = await page.evaluate("window.XM.stats()")
    wall = time.time() - t1
    try:
        await asyncio.wait_for(browser.close(), timeout=20)
    except Exception as e:  # noqa: BLE001
        print(f"[{tag}] browser close: {e!r}", flush=True)
    proc.stdin.close()
    proc.wait()
    sink.close()
    if proc.returncode:
        raise RuntimeError(f"[{tag}] ffmpeg exited {proc.returncode}")
    return {"tag": tag, "frames": i1 - i0, "boot_s": round(boot, 2), "wall_s": round(wall, 2), "gl": info["gl"],
            "fonts": info["fonts"], "probes": info["probes"], "js": st}


async def _render(res, faces, out, workers, mode, verbose, layer=None):
    from playwright.async_api import async_playwright
    N = res["frames"]
    per = math.ceil(N / workers)
    segs, jobs = [], []
    async with async_playwright() as p:
        for k, s in enumerate(range(0, N, per)):
            e = min(N, s + per)
            fp = out.with_name(f"{out.stem}.seg{k:02d}.mov")
            segs.append(fp)
            jobs.append(_segment(p, res, faces, s, e, fp, mode, f"w{k}", verbose, layer))
        results = await asyncio.gather(*jobs)
    return segs, results


def layer_items(res, layer):
    """shots/transitions drawn in a compositing layer: 'behind' | 'front' | 'invert'
    (transitions always go to 'front'; 'invert' holds the shots resolved from `invert: true`)"""
    shots = [s for s in res["shots"] if s.get("layer", "front") == layer]
    trans = res["transitions"] if layer == "front" else []
    return shots, trans


def render_overlay(res, out, workers=4, formats=("prores",), mode="overlay", verbose=True, layer=None):
    """layer: 'behind' | 'front' | 'invert' | None (everything in one layer). Returns None if the layer is empty."""
    res = load_json(res) if isinstance(res, (str, Path)) else res
    if layer and not any(layer_items(res, layer)):
        return None
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    faces = resolve_faces(res["tokens"])
    t0 = time.time()
    segs, results = asyncio.run(_render(res, faces, out, workers, mode, verbose, layer))
    t_render = time.time() - t0
    lst = out.with_name(out.stem + ".segments.txt")
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    "-movflags", "+write_colr", str(out)], check=True)
    for s in segs:
        s.unlink()
    lst.unlink()
    t_concat = time.time() - t0 - t_render
    outputs = {"prores": str(out)}
    t_hevc = 0.0
    if "hevc" in formats:
        th = time.time()
        hv = out.with_name(out.stem + ".hevc_alpha.mov")
        hevc_alpha_from(out, hv)
        outputs["hevc_alpha"] = str(hv)
        t_hevc = time.time() - th
    js = [r["js"] for r in results]
    fr = sum(j["frames"] for j in js)
    stats = {
        "frames": res["frames"], "fps": res["canvas"]["fps"], "canvas": res["canvas"], "workers": len(results), "mode": mode, "layer": layer or "all",
        "wall_render_s": round(t_render, 2), "wall_concat_s": round(t_concat, 2), "wall_hevc_s": round(t_hevc, 2),
        "per_frame_ms": {"render": round(sum(j["render"] for j in js) / fr, 2), "readback": round(sum(j["read"] for j in js) / fr, 2),
                         "post": round(sum(j["post"] for j in js) / fr, 2)},
        "subframes_per_frame": round(sum(j["subframes"] for j in js) / fr, 2),
        "workers_detail": [{k: r[k] for k in ("tag", "frames", "boot_s", "wall_s")} for r in results],
        "gl": results[0]["gl"], "fonts": results[0]["fonts"], "font_probes": results[0]["probes"], "outputs": outputs,
        "font_files": [{k: f[k] for k in ("key", "family", "weight", "source", "fallback", "distributable")} for f in faces],
        "bytes": {k: Path(v).stat().st_size for k, v in outputs.items()},
    }
    save_json(out.with_name(out.stem + ".render_stats.json"), stats)
    return stats


# ---------------------------------------------------------------- stills
async def _stills(res, faces, times, mode, overrides, tokens=None):
    from playwright.async_api import async_playwright
    C = res["canvas"]
    W, H = C["w"], C["h"]
    sink = Sink(faces)
    got = {}
    sink.handler = lambda path, data: got.__setitem__(path, data)
    out = []
    async with async_playwright() as p:
        browser = await launch(p)
        page, info = await open_engine(browser, sink, page_config(res, tokens or res["tokens"], faces, mode, overrides), False)
        for k, t in enumerate(times):
            url = f"/still?k={k}"
            await page.evaluate("([t,u]) => window.XM.renderAndPost(t,u)", [t, url])
            out.append(np.frombuffer(got.pop(url), np.uint8).reshape(H, W, 4).copy())
        await browser.close()
    sink.close()
    return out, info


def stills(res, times, mode="overlay", overrides=None, tokens=None):
    """-> (list of HxWx4 uint8 arrays, boot info). Overlay mode arrays are premultiplied RGBA."""
    res = load_json(res) if isinstance(res, (str, Path)) else res
    faces = resolve_faces(tokens or res["tokens"])
    return asyncio.run(_stills(res, faces, times, mode, overrides, tokens))


async def _bboxes(res, faces, times):
    from playwright.async_api import async_playwright
    sink = Sink(faces)
    async with async_playwright() as p:
        browser = await launch(p)
        page, _ = await open_engine(browser, sink, page_config(res, res["tokens"], faces, "overlay"), False)
        out = await page.evaluate("ts => ts.map(t => window.XM.bboxes(t))", times)
        await browser.close()
    sink.close()
    return out


def bboxes(res, times):
    res = load_json(res) if isinstance(res, (str, Path)) else res
    return asyncio.run(_bboxes(res, resolve_faces(res["tokens"]), list(times)))
