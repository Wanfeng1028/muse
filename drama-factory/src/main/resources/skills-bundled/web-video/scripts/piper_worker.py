"""Piper (sherpa-onnx) synthesis worker. Not a CLI for people: tts.py runs it inside the piper venv.

Called as: <venv>/bin/python piper_worker.py MODEL_DIR JOBS.json
JOBS.json: {"sid": 0, "speed": 1.0, "jobs": [{"text": "...", "out": "/abs/path.wav"}]}
Prints one JSON line per clip: {"out", "duration", "sample_rate"}. One process per video: the model loads once.
"""
import glob
import json
import sys

import numpy as np
import sherpa_onnx
import soundfile as sf


def main():
    model_dir, jobs_path = sys.argv[1], sys.argv[2]
    spec = json.load(open(jobs_path, encoding="utf-8"))
    onnx = sorted(glob.glob(f"{model_dir}/*.onnx"))[0]
    cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=onnx, tokens=f"{model_dir}/tokens.txt",
                                                   data_dir=f"{model_dir}/espeak-ng-data"),
        num_threads=4, provider="cpu"))
    tts = sherpa_onnx.OfflineTts(cfg)
    for job in spec["jobs"]:
        audio = tts.generate(job["text"], sid=int(spec.get("sid", 0)), speed=float(spec.get("speed", 1.0)))
        samples = np.array(audio.samples, dtype=np.float32)
        if samples.size == 0:
            sys.exit(f"empty audio for: {job['text']}")
        sf.write(job["out"], samples, audio.sample_rate)
        print(json.dumps({"out": job["out"], "duration": round(samples.size / audio.sample_rate, 3),
                          "sample_rate": audio.sample_rate}), flush=True)


if __name__ == "__main__":
    main()
