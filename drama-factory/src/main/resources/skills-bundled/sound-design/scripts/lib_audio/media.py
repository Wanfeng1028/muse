"""ffmpeg resolution, decoding and two-pass loudnorm. Needs only numpy from the calling script."""
import functools
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_verbose = False


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


@functools.cache
def binary(name: str) -> str:
    env_var = name.upper()
    candidate = os.environ.get(env_var) or shutil.which(name)
    if not candidate and name == "ffmpeg":
        try:
            import imageio_ffmpeg  # only present when the calling script declares it

            candidate = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            candidate = None
    if not candidate:
        raise SystemExit(f"{name} not found: set ${env_var}, or install {name} on PATH (e.g. brew install ffmpeg).")
    if _verbose:
        print(f"[{name}] {candidate}")
    return candidate


def run_ffmpeg(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run([binary("ffmpeg"), "-hide_banner", *arguments], capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg failed ({' '.join(arguments[:6])} ...):\n{result.stderr.decode(errors='replace')[-1500:]}")
    return result


def decode(path: Path, rate: int, channels: int, filters: str | None = None) -> np.ndarray:
    if not Path(path).exists():
        raise SystemExit(f"audio file not found: {path}")
    arguments = ["-v", "error", "-i", str(path)]
    if filters:
        arguments += ["-af", filters]
    arguments += ["-f", "f32le", "-ac", str(channels), "-ar", str(rate), "-"]
    raw = run_ffmpeg(arguments).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).copy()


@dataclass(frozen=True)
class LoudnessTarget:
    integrated: float = -14.0
    true_peak: float = -1.0
    range: float = 11.0

    def filter(self) -> str:
        return f"loudnorm=I={self.integrated}:TP={self.true_peak}:LRA={self.range}"


def _last_json(stderr: str) -> dict[str, str]:
    return json.loads(stderr[stderr.rindex("{") : stderr.rindex("}") + 1])


def measure(path: Path, target: LoudnessTarget = LoudnessTarget()) -> dict[str, str]:
    arguments = ["-v", "info", "-i", str(path), "-af", f"{target.filter()}:print_format=json", "-f", "null", "-"]
    return _last_json(run_ffmpeg(arguments).stderr.decode(errors="replace"))


def loudnorm_two_pass(source: Path, destination: Path, target: LoudnessTarget, rate: int, codec: str) -> dict[str, str]:
    """Linear two-pass loudnorm. LRA is raised to the source's own LRA (ffmpeg reverts to dynamic mode otherwise)."""
    stats = measure(source, target)
    range_target = min(50.0, max(target.range, float(stats["input_lra"]) + 0.1))
    second = (
        f"loudnorm=I={target.integrated}:TP={target.true_peak}:LRA={range_target}:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}:linear=true:print_format=json"
    )
    arguments = ["-v", "info", "-y", "-i", str(source), "-af", second, "-ar", str(rate), "-c:a", codec, str(destination)]
    applied = _last_json(run_ffmpeg(arguments).stderr.decode(errors="replace"))
    return {**applied, "first_pass_input_i": stats["input_i"], "first_pass_input_tp": stats["input_tp"]}
