#!/usr/bin/env python3
"""Measure an inspiration video so the style read rests on numbers, not memory.

  inspect_inspiration.py <video> [out-dir]

Writes a contact sheet (preview/inspiration-sheet.jpg), a sheet of the frames
right after each cut, and prints: duration, size, cut count and average shot
length (cuts per second is the single best proxy for pace), and the music's
tempo when there is a soundtrack. Look at both sheets before writing the read:
the numbers say how fast, only the frames say what moves.
"""
import json, pathlib, subprocess, sys, wave, tempfile
import numpy as np

src = sys.argv[1]
if not pathlib.Path(src).is_file():
    sys.exit(f"{src}: not a local file. Download the video (or track) first, then pass its path.")
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "preview"); out.mkdir(parents=True, exist_ok=True)
run = lambda *c: subprocess.run(c, capture_output=True, text=True)

p = json.loads(run("ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                   "-of", "json", src).stdout)
dur = float(p["format"]["duration"])
v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
has_audio = any(s["codec_type"] == "audio" for s in p["streams"])
print(f"{dur:.1f}s  " + (f"{v['width']}x{v['height']}  {v['r_frame_rate']} fps  " if v else "audio only  ")
      + f"{'with' if has_audio else 'no'} audio")

step = max(0.5, dur / 24)
if v: run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"fps=1/{step:.3f},scale=320:-2,tile=6x4:padding=4",
    "-frames:v", "1", str(out / "inspiration-sheet.jpg"))
if v: print(f"{out/'inspiration-sheet.jpg'}  one frame every {step:.2f}s")

# cuts: frames where the picture changes abruptly. A continuous one-shape piece
# has almost none; a cut-driven edit has many.
log = "" if not v else run("ffmpeg", "-i", src, "-vf", "select='gt(scene,0.32)',showinfo", "-f", "null", "-").stderr
cuts = [float(l.split("pts_time:")[1].split()[0]) for l in log.splitlines() if "pts_time:" in l]
if v: print(f"{len(cuts)} hard cuts" + (f", average shot {dur / (len(cuts) + 1):.2f}s: " +
      " ".join(f"{c:.2f}" for c in cuts[:40]) if cuts else " (continuous motion: transitions are morphs, not cuts)"))
if v and cuts:
    run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
        "select='gt(scene,0.32)',scale=240:-2,tile=6x3:padding=4", "-frames:v", "1", "-vsync", "vfr",
        str(out / "inspiration-cuts.jpg"))
    print(f"{out/'inspiration-cuts.jpg'}  the frame after each cut")

if has_audio:
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        run("ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", "22050", tmp.name)
        w = wave.open(tmp.name); x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768.0
    hop, win, sr = 256, 1024, 22050
    fr = 1 + (len(x) - win) // hop
    S = np.abs(np.fft.rfft(x[np.arange(win)[None, :] + hop * np.arange(fr)[:, None]] * np.hanning(win), axis=1))
    flux = np.maximum(0, np.diff(S, axis=0)).sum(1); flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    fps = sr / hop; lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)
    bpm = 60 * fps / (lo + int(np.argmax(ac[lo:hi])))
    print(f"music tempo about {bpm:.0f} BPM (beat {60 / bpm:.3f}s); check it against the cut times above")
