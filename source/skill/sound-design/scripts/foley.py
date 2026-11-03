#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "scipy>=1.11", "soundfile>=0.12"]
# ///
"""Deterministic synthesized SFX kit (licence-free foley), tunable to the music's key.

Importable (mix.py uses render()) and a CLI that writes WAVs plus a peak manifest for Remotion.
Every sound is a pure function of (kind, note, key, length, variant, seed): same inputs, same samples."""
import argparse
import json
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

RATE = 48000
NOTE_INDEX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True)
class Spec:
    note: float = 0.0
    key: str = "C"
    length: float | None = None
    rng: np.random.Generator = np.random.default_rng(0)


def parse_key(text: str) -> tuple[int, bool]:
    """'F', 'F#', 'Bb', 'Fm', 'F minor', 'A min' -> (pitch class, is_minor)."""
    cleaned = text.strip().replace(" ", "")
    if not cleaned or cleaned[0].upper() not in NOTE_INDEX:
        raise ValueError(f"unknown key {text!r}; use e.g. F, F#, Bb, Fm, 'A minor'")
    pitch = NOTE_INDEX[cleaned[0].upper()]
    rest = cleaned[1:]
    if rest[:1] in ("#", "♯"):
        pitch, rest = pitch + 1, rest[1:]
    elif rest[:1] in ("b", "♭"):
        pitch, rest = pitch - 1, rest[1:]
    minor = rest.lower().startswith("m") and not rest.lower().startswith("maj")
    return pitch % 12, minor


def tonic_hz(key: str, reference_hz: float) -> float:
    """Frequency of the key's tonic in the octave centred on reference_hz."""
    pitch, _ = parse_key(key)
    frequency = 440.0 * 2 ** ((pitch - 9) / 12)
    while frequency < reference_hz / np.sqrt(2):
        frequency *= 2
    while frequency >= reference_hz * np.sqrt(2):
        frequency /= 2
    return frequency


def _pitch(spec: Spec, reference_hz: float, extra: float = 0.0) -> float:
    return tonic_hz(spec.key, reference_hz) * 2 ** ((spec.note + extra) / 12)


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE)) / RATE


def _noise(spec: Spec, seconds: float) -> np.ndarray:
    return spec.rng.standard_normal(int(seconds * RATE)).astype(np.float32)


def _lowpass(signal: np.ndarray, cutoff: float) -> np.ndarray:
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    return lfilter([alpha], [1, alpha - 1], signal).astype(np.float32)


def _bandpass(signal: np.ndarray, low: float, high: float) -> np.ndarray:
    return _lowpass(signal, high) - _lowpass(signal, low)


def _env(count: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(count) / RATE
    return np.clip(t / max(attack, 1e-4), 0, 1) * np.exp(-np.maximum(0, t - attack) / decay)


def _fit(signal: np.ndarray, count: int) -> np.ndarray:
    return signal[:count] if len(signal) >= count else np.pad(signal, (0, count - len(signal)))


def _sweep(frequency: np.ndarray) -> np.ndarray:
    return np.sin(2 * np.pi * np.cumsum(frequency) / RATE)


def pop(spec: Spec) -> np.ndarray:
    t = _t(0.16)
    return _sweep(_pitch(spec, 700) * (1 + 0.9 * np.exp(-t / 0.02))) * _env(len(t), 0.002, 0.045)


def blip(spec: Spec) -> np.ndarray:
    t = _t(0.22)
    base = _pitch(spec, 523)
    tone = np.sign(np.sin(2 * np.pi * base * t)) * 0.35 + np.sin(2 * np.pi * base * 1.5 * t) * 0.4
    return _lowpass(tone.astype(np.float32), 2200) * _env(len(t), 0.004, 0.06)


def thump(spec: Spec) -> np.ndarray:
    t = _t(0.3)
    body = _sweep(55 + 90 * np.exp(-t / 0.03)) * _env(len(t), 0.002, 0.09)
    click = _bandpass(_noise(spec, 0.3), 800, 5000) * _env(len(t), 0.0005, 0.006) * 0.4
    return body + click


def slap(spec: Spec) -> np.ndarray:
    count = int(0.22 * RATE)
    paper = _bandpass(_noise(spec, 0.22), 600, 6000) * _env(count, 0.001, 0.025)
    return paper * 0.9 + _fit(thump(spec), count) * 0.3


def stamp(spec: Spec) -> np.ndarray:
    count = int(0.4 * RATE)
    rubber = _bandpass(_noise(spec, 0.4), 200, 2000) * _env(count, 0.001, 0.05)
    return _fit(thump(spec), count) * 0.8 + rubber * 0.45


def whoosh(spec: Spec) -> np.ndarray:
    seconds = spec.length or 0.42
    noise = _noise(spec, seconds)
    position = np.linspace(0, 1, len(noise))
    swept = _lowpass(noise, 900) * (1 - position) + _lowpass(noise, 3500) * position
    return swept * np.sin(np.pi * position) ** 2 * 1.6


def swell(spec: Spec) -> np.ndarray:
    seconds = spec.length or 1.2
    noise = _noise(spec, seconds)
    return _lowpass(noise, 700) * np.sin(np.pi * np.linspace(0, 1, len(noise))) ** 1.5 * 1.4


def tear(spec: Spec) -> np.ndarray:
    count = int(0.45 * RATE)
    noise = _bandpass(_noise(spec, 0.45), 1200, 9000)
    grains = (spec.rng.random(count) < 0.004).astype(np.float32)
    crackle = np.convolve(grains, np.exp(-np.arange(200) / 30), mode="same")
    position = np.linspace(0, 1, count)
    return noise * (0.35 + crackle * 0.8) * np.clip(position * 6, 0, 1) * np.exp(-position * 2.5)


def tick(spec: Spec) -> np.ndarray:
    return _bandpass(_noise(spec, 0.03), 2000, 9000) * _env(int(0.03 * RATE), 0.0003, 0.004)


def key(spec: Spec) -> np.ndarray:
    clicks = np.concatenate([tick(spec) * 1.2, np.zeros(int(0.07 * RATE), dtype=np.float32), tick(spec) * 0.6])
    return clicks + _fit(thump(spec), len(clicks)) * 0.25


def flip(spec: Spec) -> np.ndarray:
    seconds = 0.18
    flutter = 0.5 + 0.5 * np.sin(2 * np.pi * 38 * _t(seconds))
    return _bandpass(_noise(spec, seconds), 700, 4500) * flutter * np.sin(np.pi * np.linspace(0, 1, int(seconds * RATE)))


def pluck(spec: Spec) -> np.ndarray:
    t = _t(0.5)
    frequency = _pitch(spec, 700)
    tone = np.sin(2 * np.pi * frequency * t) + 0.35 * np.sin(2 * np.pi * frequency * 4 * t) * np.exp(-t / 0.03)
    return tone * _env(len(t), 0.001, 0.16)


def chime(spec: Spec) -> np.ndarray:
    out = np.zeros(int(0.9 * RATE), dtype=np.float32)
    for index, interval in enumerate((0, 7, 12, 14)):
        part = pluck(Spec(spec.note + interval, spec.key, None, spec.rng))
        start = int(index * 0.045 * RATE)
        out[start : start + len(part)] += part[: len(out) - start] * 0.6
    return out


def riser(spec: Spec) -> np.ndarray:
    """Builds to its loudest sample at the very end, so peak alignment lands the end on the cut."""
    seconds = spec.length or 1.0
    noise = _noise(spec, seconds)
    position = np.linspace(0, 1, len(noise))
    filtered = _lowpass(noise, 400) * (1 - position) + _lowpass(noise, 2500) * position * 0.8 + _bandpass(noise, 3000, 9000) * position**2 * 0.6
    base = _pitch(spec, 220)
    tone = _sweep(base * 2 ** (2 * position)) * 0.25
    return (filtered + tone) * position**2.2 * _fit(np.ones(len(noise) - 48), len(noise))


def bass_hit(spec: Spec) -> np.ndarray:
    t = _t(0.9)
    base = _pitch(spec, 55)
    body = np.tanh(1.6 * _sweep(base * (1 + 1.0 * np.exp(-t / 0.05))) * _env(len(t), 0.003, 0.32))
    click = _bandpass(_noise(spec, 0.9), 1500, 7000) * _env(len(t), 0.0005, 0.008) * 0.35
    return body * 0.9 + click


def shimmer(spec: Spec) -> np.ndarray:
    seconds = spec.length or 1.6
    t = _t(seconds)
    _, minor = parse_key(spec.key)
    intervals = (0, 7, 12, 15 if minor else 16, 19, 24)
    tones = sum(np.sin(2 * np.pi * _pitch(spec, 1400, i) * t + spec.rng.uniform(0, 2 * np.pi)) * (0.9 ** n) for n, i in enumerate(intervals))
    tremolo = 0.75 + 0.25 * np.sin(2 * np.pi * 6.5 * t)
    shape = np.clip(t / 0.25, 0, 1) ** 2 * np.exp(-np.maximum(0, t - 0.25) / (seconds * 0.35))
    air = _bandpass(_noise(spec, seconds), 5000, 12000) * 0.15
    return (tones / len(intervals) + air) * tremolo * shape


def reverse_swoosh(spec: Spec) -> np.ndarray:
    seconds = spec.length or 0.7
    noise = _noise(spec, seconds)
    position = np.linspace(0, 1, len(noise))
    body = _lowpass(noise, 1200) * (1 - position) + _bandpass(noise, 1500, 7000) * position
    return body * np.exp(4.5 * (position - 1)) * _fit(np.ones(len(noise) - 96), len(noise)) * 1.4


KINDS = {
    "pop": pop, "blip": blip, "thump": thump, "slap": slap, "stamp": stamp, "whoosh": whoosh, "swell": swell,
    "tear": tear, "tick": tick, "key": key, "flip": flip, "pluck": pluck, "chime": chime, "riser": riser,
    "bass-hit": bass_hit, "shimmer": shimmer, "reverse-swoosh": reverse_swoosh,
}
PITCHED = {"pop", "blip", "pluck", "chime", "riser", "bass-hit", "shimmer"}
SIZED = {"whoosh", "swell", "riser", "shimmer", "reverse-swoosh"}


def render(kind: str, note: float | None = None, key: str = "C", length: float | None = None, variant: int = 0, seed: int = 7) -> np.ndarray:
    if kind not in KINDS:
        raise ValueError(f"unknown foley kind {kind!r}; kinds: {', '.join(KINDS)}")
    rng = np.random.default_rng([seed, zlib.crc32(kind.encode()), variant])
    return np.asarray(KINDS[kind](Spec(note or 0.0, key, length, rng)), dtype=np.float32)


def _file_name(kind: str, note: float, variant: int) -> str:
    name = kind
    if note:
        name += f"-note{note:g}"
    if variant:
        name += f"-v{variant + 1}"
    return name + ".wav"


def main() -> None:
    import soundfile

    parser = argparse.ArgumentParser(
        description="Write deterministic synthesized SFX WAVs (48 kHz, peak -1 dBFS) plus sfx-manifest.json with peak offsets.",
        epilog=(
            f"Kinds: {', '.join(KINDS)}. Pitched (follow --key/--notes): {', '.join(sorted(PITCHED))}. "
            f"Length-aware (--length): {', '.join(sorted(SIZED))}.\n"
            "Manifest peakMs = transient offset; in Remotion use <Sequence from={eventFrame - round(peakMs/1000*fps)}>.\n"
            "Example: uv run foley.py pop pluck chime whoosh --key F --notes 0,5,7 --variants 2 --out public/sfx"
        ),
    )
    parser.add_argument("kinds", nargs="*", default=["all"], help="kinds to write, or 'all' (default)")
    parser.add_argument("--key", default="C", help="music key for pitched kinds, e.g. F, Bb, 'A minor' (default C)")
    parser.add_argument("--notes", default="0", help="comma list of semitones above the tonic for pitched kinds (default 0)")
    parser.add_argument("--length", type=float, default=None, help="seconds for length-aware kinds")
    parser.add_argument("--variants", type=int, default=1, help="noise variants per kind (default 1)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("public/sfx"))
    arguments = parser.parse_args()

    kinds = list(KINDS) if arguments.kinds == ["all"] else arguments.kinds
    unknown = [kind for kind in kinds if kind not in KINDS]
    if unknown:
        sys.exit(f"unknown kinds: {', '.join(unknown)}; available: {', '.join(KINDS)}")
    notes = [float(value) for value in arguments.notes.split(",") if value.strip()]
    arguments.out.mkdir(parents=True, exist_ok=True)
    manifest_path = arguments.out / "sfx-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for kind in kinds:
        for note in notes if kind in PITCHED else [0.0]:
            for variant in range(arguments.variants):
                clip = render(kind, note, arguments.key, arguments.length, variant, arguments.seed)
                clip = clip / (np.abs(clip).max() or 1) * 10 ** (-1 / 20)
                path = arguments.out / _file_name(kind, note, variant)
                soundfile.write(path, clip, RATE, subtype="PCM_16")
                peak_ms = round(float(np.argmax(np.abs(clip))) / RATE * 1000, 1)
                manifest[path.name] = {"kind": kind, "note": note, "key": arguments.key, "variant": variant, "peakMs": peak_ms, "durationMs": round(len(clip) / RATE * 1000, 1)}
                print(f"{path}  peak {peak_ms} ms")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(manifest_path)


if __name__ == "__main__":
    main()
