"""Shared helpers for the promo scripts: locate ffmpeg/ffprobe, decode audio, find a label font.

ffmpeg and ffprobe come from the FFMPEG / FFPROBE environment variables, then PATH, then the copy that
Remotion installs inside a project (node_modules/@remotion/compositor-*). Pass --project or set
REMOTION_PROJECT to point at that project when the system ffmpeg is missing or blocked.
"""
import glob, os, shutil, subprocess, sys, tempfile, wave
import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Korean file names on Windows consoles
    except (AttributeError, ValueError):
        pass

_FOUND = {}


def _remotion_copy(name):
    roots = [os.environ.get("REMOTION_PROJECT"), os.getcwd()]
    exe = name + (".exe" if os.name == "nt" else "")
    for root in [r for r in roots if r]:
        for d in glob.glob(os.path.join(root, "node_modules", "@remotion", "compositor-*")):
            p = os.path.join(d, exe)
            if os.path.exists(p):
                return p
    return None


def _runs(path):
    try:
        subprocess.run([path, "-version"], capture_output=True, timeout=20, check=True)
        return True
    except Exception:  # noqa: BLE001 - any failure means this copy is unusable
        return False


def tool(name):
    """Return a working ffmpeg or ffprobe executable, or exit with a clear message."""
    if name in _FOUND:
        return _FOUND[name]
    candidates = [os.environ.get(name.upper()), shutil.which(name), _remotion_copy(name)]
    for c in candidates:
        if c and os.path.exists(c) and _runs(c):
            _FOUND[name] = c
            return c
    sys.exit(f"{name} not found or not runnable. Install ffmpeg, set {name.upper()}, "
             f"or set REMOTION_PROJECT to a Remotion project (its bundled copy is used).")


def set_project(path):
    if path:
        os.environ["REMOTION_PROJECT"] = os.path.abspath(path)


def decode_audio(path, sr=48000, channels=2):
    """Decode any audio or video file to float64 samples, shape (n, channels), via a temporary WAV."""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-i", path, "-vn", "-ac", str(channels),
                            "-ar", str(sr), "-c:a", "pcm_s16le", tmp], capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[:400] or f"cannot decode {path}")
        with wave.open(tmp, "rb") as w:
            raw = w.readframes(w.getnframes())
        if not raw:
            return np.zeros((0, channels))
        return np.frombuffer(raw, "<i2").reshape(-1, channels).astype(np.float64) / 32768.0
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def write_wav(path, x, sr):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def probe_video(path):
    import json
    out = subprocess.run([tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames:format=duration",
                          "-of", "json", path],
                         capture_output=True, check=True).stdout.decode("utf-8", "replace")
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    # The container duration includes audio, which can run past the last video frame.
    if s.get("nb_frames", "N/A") not in ("N/A", None, "0"):
        dur = int(s["nb_frames"]) / fps
    elif s.get("duration", "N/A") not in ("N/A", None):
        dur = float(s["duration"])
    else:
        dur = float(j["format"]["duration"])
    return int(s["width"]), int(s["height"]), fps, dur


def grab_frame(video, frame, fps, out_png, width=None):
    """Save one frame as an image. Steps back a frame or two when a seek lands past the last frame."""
    for f in (frame, frame - 1, frame - 2):
        if f < 0:
            break
        if os.path.exists(out_png):
            os.remove(out_png)
        args = [tool("ffmpeg"), "-v", "error", "-y", "-ss", f"{f / fps + 0.001:.4f}", "-i", video, "-frames:v", "1"]
        if width:
            args += ["-vf", f"scale={width}:-2"]
        subprocess.run(args + [out_png], check=True)
        if os.path.exists(out_png) and os.path.getsize(out_png) > 0:
            return f
    raise RuntimeError(f"could not read frame {frame} from {video}")


def label_font(size=18):
    from PIL import ImageFont
    for p in (os.environ.get("LABEL_FONT"), "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
