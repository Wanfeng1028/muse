#!/usr/bin/env python3
"""Install the local Vietnamese voice for `tts.py --provider piper` (macOS, Windows, Linux).

USAGE
  install_tts.py            # venv + model into ~/.cache/web-video/tts (override: WEB_VIDEO_TTS_HOME)
  install_tts.py --check    # report what is installed, change nothing

Voice: Piper "csa-voice v3" by CakeByVPBank (MIT, 5 speakers, 77 MB), run by sherpa-onnx (Apache-2.0).
Downloads: sherpa-onnx, numpy, soundfile, onnx (PyPI); the model from HuggingFace at a pinned commit;
espeak-ng-data (7 MB) from the sherpa-onnx GitHub release. Safe to re-run: finished parts are skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
TTS_HOME = pathlib.Path(os.environ.get("WEB_VIDEO_TTS_HOME", "~/.cache/web-video/tts")).expanduser()
VENV = TTS_HOME / "venv-piper"
MODEL = TTS_HOME / "piper-cake-v3"
REPO = "CakeByVPBank/piper-pgl-v4-vi_VN-version39_epoch39"
REV = "8ea50134bea762f6a1faac671e1a33c41871289c"
NAME = "vi_VN-csa-voice-piper-v3-medium"
ESPEAK_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2"
PKGS = ["sherpa-onnx==1.13.8", "numpy", "soundfile", "onnx"]
SPEAKERS = {"ngoclan": 0, "minhanh": 1, "quanghuy": 2, "thuha": 3, "yennhi": 4}


def venv_python(venv: pathlib.Path = VENV) -> pathlib.Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def installed() -> bool:
    return (venv_python().exists() and (MODEL / f"{NAME}.onnx").exists() and (MODEL / "tokens.txt").exists()
            and (MODEL / "espeak-ng-data").is_dir() and (MODEL / "MODEL_INFO.json").exists())


def fetch(url: str, dest: pathlib.Path):
    if dest.exists() and dest.stat().st_size > 0:
        return
    print(f"== download {dest.name}", flush=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "web-video-skill"})
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    part.replace(dest)


PREPARE = r"""
import hashlib, json, pathlib, sys
import onnx
model, name, repo, rev, speakers = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
cfg = json.loads((model / f"{name}.onnx.json").read_text(encoding="utf-8"))
onx = model / f"{name}.onnx"
m = onnx.load(str(onx))
if not {"model_type", "comment"} <= {p.key for p in m.metadata_props}:
    meta = {"model_type": "vits", "comment": "piper", "language": "Vietnamese", "voice": cfg["espeak"]["voice"],
            "has_espeak": 1, "n_speakers": cfg.get("num_speakers", 1), "sample_rate": cfg["audio"]["sample_rate"]}
    for k, v in meta.items():
        e = m.metadata_props.add(); e.key = k; e.value = str(v)
    onnx.save(m, str(onx))
with open(model / "tokens.txt", "w", encoding="utf-8", newline="\n") as f:
    for sym, ids in cfg["phoneme_id_map"].items():
        f.write(f"{sym} {ids[0]}\n")
info = {"engine": "piper (sherpa-onnx)", "repo": repo, "revision": rev, "license": "MIT (model card)",
        "speakers": speakers, "sample_rate": cfg["audio"]["sample_rate"],
        "sha256": hashlib.sha256(onx.read_bytes()).hexdigest()}
(model / "MODEL_INFO.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        print(f"installed: {MODEL}" if installed() else "not installed (run install_tts.py)")
        sys.exit(0 if installed() else 1)

    MODEL.mkdir(parents=True, exist_ok=True)
    py = venv_python()
    if not py.exists():
        print(f"== venv {VENV}", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    probe = subprocess.run([str(py), "-c", "import sherpa_onnx, soundfile, numpy, onnx"], capture_output=True)
    if probe.returncode != 0:
        print("== pip install " + " ".join(PKGS), flush=True)
        if shutil.which("uv"):
            subprocess.run(["uv", "pip", "install", "-q", "--python", str(py), *PKGS], check=True)
        else:
            subprocess.run([str(py), "-m", "pip", "install", "-q", *PKGS], check=True)

    base = f"https://huggingface.co/{REPO}/resolve/{REV}"
    fetch(f"{base}/{NAME}.onnx", MODEL / f"{NAME}.onnx")
    fetch(f"{base}/{NAME}.onnx.json", MODEL / f"{NAME}.onnx.json")
    if not (MODEL / "espeak-ng-data").is_dir():
        tb = TTS_HOME / "espeak-ng-data.tar.bz2"
        fetch(ESPEAK_URL, tb)
        with tarfile.open(tb, "r:bz2") as t:
            members = [m for m in t.getmembers() if m.name.startswith("espeak-ng-data")
                       and not m.issym() and not m.islnk() and ".." not in m.name]
            t.extractall(MODEL, members=members)
        tb.unlink()

    print("== sherpa-onnx metadata + tokens.txt", flush=True)
    subprocess.run([str(py), "-c", PREPARE, str(MODEL), NAME, REPO, REV, json.dumps(SPEAKERS)], check=True)

    print("== smoke test", flush=True)
    with tempfile.TemporaryDirectory() as td:
        jobs = pathlib.Path(td) / "jobs.json"
        wav = pathlib.Path(td) / "t.wav"
        jobs.write_text(json.dumps({"sid": 0, "speed": 1.0, "jobs": [
            {"text": "Xin chào, đây là giọng Ngọc Lan.", "out": str(wav)}]}, ensure_ascii=False), encoding="utf-8")
        subprocess.run([str(py), str(HERE / "piper_worker.py"), str(MODEL), str(jobs)], check=True,
                       capture_output=True)
        if not wav.exists() or wav.stat().st_size == 0:
            sys.exit("smoke test failed")
    size = sum(f.stat().st_size for f in TTS_HOME.rglob("*") if f.is_file()) / 1e6
    print(f"installed: {MODEL} ({size:.0f} MB total). Use: tts.py RUN --provider piper --voice ngoclan")


if __name__ == "__main__":
    main()
