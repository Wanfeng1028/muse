#!/usr/bin/env python3
"""Render escena.html to MP4 frame by frame, calling window.render(t) for each frame.

Usage:
  python3 render.py escena.html [--audio voz.wav] [--musica musica.mp3] [--vertical]
                    [--fps 30] [--desde 12 --hasta 16] [--workers 3] [--salida video.mp4]

Set CHROME_PATH to use an installed Chrome instead of Playwright's Chromium.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import ffmpeg, require_ffmpeg


def open_page(p, html, w, h):
    kw = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
    browser = p.chromium.launch(args=["--allow-file-access-from-files"], **kw)
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    errors, warnings = [], set()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: warnings.add(m.text) if m.type in ("warning", "error") else None)
    page.goto(Path(html).resolve().as_uri() + "?render=1")
    page.wait_for_function("typeof window.render === 'function'", timeout=30000)
    page.evaluate("async () => { await document.fonts.ready; if (window.LISTO) await window.LISTO; }")
    if errors:
        sys.exit("La escena tiene errores de JavaScript:\n" + "\n".join(errors))
    return browser, page, errors, warnings


def scene_duration(html, w, h):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, _, _ = open_page(p, html, w, h)
        d = page.evaluate("window.DURACION")
        browser.close()
    if not d:
        sys.exit("La escena no define window.DURACION (segundos).")
    return float(d)


def render_chunk(job):
    html, w, h, fps, first, last, out = job
    from playwright.sync_api import sync_playwright
    enc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate",
         str(fps), "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser, page, errors, warnings = open_page(p, html, w, h)
        for i in range(first, last):
            page.evaluate("t => window.render(t)", i / fps)
            enc.stdin.write(page.screenshot(type="jpeg", quality=92))
            if errors:
                enc.stdin.close()
                enc.wait()
                return f"error en t={i / fps:.2f}s: {errors[0]}", warnings
        browser.close()
    enc.stdin.close()
    enc.wait()
    return (None if enc.returncode == 0 else "ffmpeg falló al codificar"), warnings


def mix_audio(video, voice, music, dur, out):
    if voice and music:
        # Music ducks under the voice, fades out, whole mix normalized to -14 LUFS.
        filt = (f"[2:a]volume=0.35,afade=t=out:st={max(dur - 2, 0)}:d=2[m];"
                "[1:a]asplit=2[v][sc];[m][sc]sidechaincompress=threshold=0.03:ratio=8:release=400[md];"
                "[v][md]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1[a]")
        ffmpeg("-i", video, "-i", voice, "-stream_loop", -1, "-i", music, "-filter_complex", filt,
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", dur, out)
    else:
        src = voice or music
        fade = f",afade=t=out:st={max(dur - 2, 0)}:d=2" if music else ""
        loop = ["-stream_loop", -1] if music else []
        ffmpeg("-i", video, *loop, "-i", src, "-filter_complex", f"[1:a]loudnorm=I=-14:TP=-1{fade}[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", dur, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("escena")
    ap.add_argument("--audio")
    ap.add_argument("--musica")
    ap.add_argument("--vertical", action="store_true")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--desde", type=float, default=0.0, help="start at second N (quick checks)")
    ap.add_argument("--hasta", type=float, help="stop at second N (quick checks)")
    ap.add_argument("--workers", type=int, default=max(1, min(3, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--salida")
    a = ap.parse_args()
    require_ffmpeg()

    html = Path(a.escena).resolve()
    w, h = (1080, 1920) if a.vertical else (1920, 1080)
    dur = scene_duration(html, w, h)
    if a.hasta:
        dur = min(dur, a.hasta)
    first = round(a.desde * a.fps)
    total = round(dur * a.fps) - first
    if total <= 0:
        sys.exit("--desde tiene que ser menor que --hasta y que la duración.")
    out = Path(a.salida).resolve() if a.salida else html.with_suffix(".mp4")

    start = time.time()
    print(f"Renderizando {total} cuadros ({total / a.fps:.1f} s a {a.fps} fps, {w}×{h}) con {a.workers} procesos…")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n = max(1, a.workers)
        bounds = [first + round(total * k / n) for k in range(n + 1)]
        jobs = [(str(html), w, h, a.fps, bounds[k], bounds[k + 1], str(tmp / f"part{k}.mp4"))
                for k in range(n) if bounds[k + 1] > bounds[k]]
        warnings = set()
        with ProcessPoolExecutor(len(jobs)) as pool:
            for err, warns in pool.map(render_chunk, jobs):
                warnings |= warns
                if err:
                    sys.exit(f"Falló el render: {err}")
        for warn in sorted(warnings):
            print(f"AVISO de la escena: {warn}")
        (tmp / "lista.txt").write_text("".join(f"file '{j[-1]}'\n" for j in jobs))
        silent = tmp / "video.mp4"
        ffmpeg("-f", "concat", "-safe", 0, "-i", tmp / "lista.txt", "-c", "copy", silent)
        voice = Path(a.audio).resolve() if a.audio else None
        music = Path(a.musica).resolve() if a.musica else None
        if a.desde and voice:
            cut = tmp / "voz_tramo.wav"
            ffmpeg("-ss", a.desde, "-i", voice, cut)
            voice = cut
        if voice or music:
            mix_audio(silent, voice, music, total / a.fps, out)
        else:
            ffmpeg("-i", silent, "-c", "copy", out)
    print(f"Listo: {out}  ({time.time() - start:.0f} s de proceso)")


if __name__ == "__main__":
    main()
