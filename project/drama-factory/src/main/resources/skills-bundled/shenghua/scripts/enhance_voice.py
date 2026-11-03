#!/usr/bin/env python3
"""Clean a voice take with DeepFilterNet.

  enhance_voice.py <work-dir>

Runs the deepFilter CLI on <work>/voice.wav and writes <work>/voice-clean.wav; the raw take is
never touched, so you can compare the two and mix whichever sounds better. deepFilter is optional:
setup.sh --enhance installs it, and nothing else in the pipeline needs it.
"""

import argparse
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    args = parser.parse_args()

    voice = args.work / "voice.wav"
    if not voice.is_file():
        print(f"No voice.wav in {args.work}", file=sys.stderr)
        print("Next: copy the recording in as voice.wav, or run trim_take.py", file=sys.stderr)
        return 1

    cli = shutil.which("deepFilter")
    if cli is None:
        scripts = Path(__file__).resolve().parent
        print(f"deepfilternet not installed — run: bash {scripts}/setup.sh --enhance", file=sys.stderr)
        return 1

    # deepFilter names its own output, so it writes into a scratch dir and the result is moved back
    scratch = args.work / ".enhance_tmp"
    scratch.mkdir(exist_ok=True)
    try:
        result = subprocess.run([cli, str(voice), "--output-dir", str(scratch)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"deepFilter failed on {voice}: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}", file=sys.stderr)
            print("Next: check that voice.wav plays, and that setup.sh --enhance completed", file=sys.stderr)
            return 1
        enhanced = sorted(scratch.glob("*.wav"))
        if not enhanced:
            print(f"deepFilter produced no WAV for {voice}", file=sys.stderr)
            print("Next: run deepFilter on it by hand and check its output", file=sys.stderr)
            return 1
        out = args.work / "voice-clean.wav"
        shutil.move(str(enhanced[0]), out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    with wave.open(str(out), "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()
    print(f"voice-clean.wav · {seconds:.1f}s · {out.stat().st_size / 1e6:.1f} MB (voice.wav kept)")
    print("Next: listen to both; if voice-clean.wav sounds better, pass it as <audio> to mix-encode.sh and mix-audio.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
