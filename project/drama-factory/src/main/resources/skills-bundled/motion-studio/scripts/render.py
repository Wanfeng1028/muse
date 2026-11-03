"""Frames out of a film: stills, contact sheets, drafts and finals.

A film is any folder with film.html exposing window.seek(t) and window.DUR. Frame size comes from
window.STUDIO.format when the film was built with kit.js, else from the #stage element (older films).
Chrome is the system Chrome via Playwright (no browser download needed).
"""
import os
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

FPS = 30


class Film:
    """An open headless page on a film; use as a context manager."""

    def __init__(self, project: Path):
        self.project = Path(project).resolve()

    def __enter__(self):
        self._pw = sync_playwright().start()
        # the installed Chrome by default; MS_CHROMIUM=/path/to/chromium for machines without it (CI, cloud sandboxes)
        kw = {"executable_path": os.environ["MS_CHROMIUM"]} if os.environ.get("MS_CHROMIUM") else {"channel": "chrome"}
        self.browser = self._pw.chromium.launch(headless=True, args=["--allow-file-access-from-files"], **kw)
        page = self.browser.new_page(viewport={"width": 2000, "height": 2000}, device_scale_factor=1)
        self.errors = []
        page.on("pageerror", lambda e: (self.errors.append(str(e)), print("PAGE ERROR:", e, flush=True)))
        page.goto((self.project / "film.html").as_uri())
        page.evaluate("document.fonts.ready")
        page.evaluate("window.STUDIO && window.STUDIO.ready")   # panel images decoded (long-form panel scenes)
        page.wait_for_timeout(250)
        info = page.evaluate("""() => {
            const s = window.STUDIO, st = document.getElementById('stage').getBoundingClientRect();
            return { dur: window.DUR, studio: s || null, w: s ? s.format.w : Math.round(st.width), h: s ? s.format.h : Math.round(st.height) };
        }""")
        if info["dur"] is None:
            raise SystemExit(f"{self.project}/film.html does not set window.DUR (is window.seek defined?)")
        self.dur, self.studio, self.w, self.h = info["dur"], info["studio"], info["w"], info["h"]
        for warning in (self.studio or {}).get("warnings", []):
            print("LINT:", warning, flush=True)
        page.set_viewport_size({"width": self.w, "height": self.h})
        self.page = page
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()

    def shot(self, t):
        self.page.evaluate(f"window.seek({min(max(t, 0), self.dur - 1e-4):.6f})")
        return self.page.locator("#stage").screenshot(type="png", animations="disabled")

    def bar_times(self, at=0.72):
        """One time per bar, `at` of the way through it (captions have landed by then)."""
        s = self.studio
        if not s:
            raise SystemExit("this film has no window.STUDIO (bpm/bars); pass explicit times instead")
        bar = 4 * 60 / s["bpm"]
        return [round(k * bar + at * bar, 3) for k in range(s["bars"])]


def stills(project, times, out_dir, bars=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with Film(project) as f:
        ts = f.bar_times() if bars else [float(t) for t in times]
        for i, t in enumerate(ts):
            name = f"{i:02d}-t{t:06.2f}.png" if bars else f"t{t:06.2f}.png"
            (out / name).write_bytes(f.shot(t))
        return out, len(ts), f.errors


def sheet(src_dir, dest, cols=6, tile_w=300):
    """Stack a folder of PNGs into one contact sheet (videos: verify.beat_sheet)."""
    src = Path(src_dir)
    files = sorted(src.glob("*.png"))
    if not files:
        raise SystemExit(f"no PNGs in {src}")
    from struct import unpack
    with open(files[0], "rb") as fh:
        head = fh.read(24)
    w, h = unpack(">II", head[16:24])
    th = round(tile_w * h / w)
    inputs = sum([["-i", str(p)] for p in files], [])
    scales = "".join(f"[{i}:v]scale={tile_w}:{th}[v{i}];" for i in range(len(files)))
    layout = "|".join(f"{(i % cols) * tile_w}_{(i // cols) * th}" for i in range(len(files)))
    if len(files) == 1:
        graph = f"[0:v]scale={tile_w}:{th}"
    else:
        graph = scales + "".join(f"[v{i}]" for i in range(len(files))) + f"xstack=inputs={len(files)}:layout={layout}:fill=0x333333"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, str(dest)], check=True)
    return dest


def probe_size(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")
    return int(w), int(h)


def film(project, dest, scale=1.0, sub=1, fps=FPS):
    """Render the whole film to a silent mp4. sub > 1 averages sub-frames for motion blur (sub=4 ≈ 270° shutter)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Film(project) as f:
        n = int(-(-f.dur * fps // 1))          # ceil: a whole-bar film ends on its last bar, not a frame short
        blur = f"tmix=frames={sub},select='not(mod(n+1\\,{sub}))',setpts=N/({fps}*TB)," if sub > 1 else ""
        # even dimensions for libx264, BT.709 limited range, tagged, fast start
        vf = blur + f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2:out_color_matrix=bt709:out_range=tv,format=yuv420p"
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps * sub), "-i", "-",
                               "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                               "-movflags", "+faststart", str(dest)], stdin=subprocess.PIPE)
        for i in range(n):
            for k in range(sub):
                ff.stdin.write(f.shot((i + k / sub) / fps))
            if i % 150 == 0:
                print(f"frame {i}/{n}", flush=True)
        ff.stdin.close()
        if ff.wait() != 0:
            raise SystemExit("ffmpeg failed")
        if f.errors:
            print(f"WARNING: {len(f.errors)} page error(s) during render", flush=True)
    return dest


def mux(silent, mix, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mix), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-shortest", "-movflags", "+faststart", str(dest)], check=True)
    return dest
