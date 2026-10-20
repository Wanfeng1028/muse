"""Shared ffmpeg/ffprobe I/O: decode audio and video frames into numpy arrays."""
import json
import subprocess

import numpy as np


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate,start_time:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    info = {"duration": float(d["format"]["duration"]), "audio_start": 0.0, "video_start": 0.0}
    for s in d["streams"]:
        if s["codec_type"] == "video":
            n, _, m = s["r_frame_rate"].partition("/")
            info.update(fps=float(n) / float(m or 1), width=s["width"], height=s["height"],
                        video_start=float(s.get("start_time", 0) or 0))
        elif s["codec_type"] == "audio":
            info["audio_start"] = float(s.get("start_time", 0) or 0)
            info["has_audio"] = True
    return info


def load_audio(path, sr=22050):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy(), sr


def load_gray_frames(path, width=None, crop=None):
    """Return (frames[N,H,W] uint8, fps). Optional crop 'w:h:x:y' then scale to width."""
    info = probe(path)
    vf = []
    if crop:
        vf.append(f"crop={crop}")
    if width:
        vf.append(f"scale={width}:-2")
    vf.append("format=gray")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", ",".join(vf),
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    # derive output size from a single probe frame
    one = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", ",".join(vf), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "pgm", "-"], capture_output=True, check=True).stdout
    header = one.split(b"\n", 3)
    w, h = map(int, header[1].split())
    frames = np.frombuffer(r.stdout, dtype=np.uint8)
    n = frames.size // (w * h)
    return frames[: n * w * h].reshape(n, h, w), info["fps"]
