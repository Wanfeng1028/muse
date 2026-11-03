"""Small numpy DSP helpers shared by mix.py and music_splice.py."""
import numpy as np


def db_to_gain(decibels: float) -> float:
    return float(10 ** (decibels / 20))


def gain_to_db(value: float) -> float:
    return float(20 * np.log10(max(value, 1e-12)))


def as_stereo(clip: np.ndarray) -> np.ndarray:
    if clip.ndim == 1:
        return np.repeat(clip[:, None], 2, axis=1)
    if clip.shape[1] == 1:
        return np.repeat(clip, 2, axis=1)
    return clip


def peak_index(clip: np.ndarray) -> int:
    magnitude = np.abs(clip).max(axis=1) if clip.ndim == 2 else np.abs(clip)
    return int(np.argmax(magnitude))


def place(track: np.ndarray, clip: np.ndarray, start: int, gain: float = 1.0) -> tuple[int, int]:
    """Add clip into track starting at sample `start` (may be negative). Returns the placed span."""
    clip = as_stereo(clip)
    if start < 0:
        clip = clip[-start:]
        start = 0
    end = min(len(track), start + len(clip))
    if end > start:
        track[start:end] += clip[: end - start] * gain
    return start, end


def _slice_padded(source: np.ndarray, start: int, end: int) -> np.ndarray:
    out = np.zeros((end - start, source.shape[1]), dtype=np.float32)
    lo, hi = max(start, 0), min(end, len(source))
    if hi > lo:
        out[lo - start : hi - start] = source[lo:hi]
    return out


def splice_segments(source: np.ndarray, segments: list[tuple[float, float]], rate: int, fade_seconds: float, curve: str = "power") -> tuple[np.ndarray, list[float]]:
    """Join source segments with crossfades centred on each join (equal-power by default; 'linear' = equal-gain,
    better when both sides are near-identical repeats). Segment n's end and n+1's start both map to the join time."""
    half = max(1, int(round(fade_seconds * rate / 2)))
    if curve == "linear":
        fade_in = np.linspace(0, 1, 2 * half, dtype=np.float32)[:, None]
        fade_out = 1 - fade_in
    else:
        angle = np.linspace(0, np.pi / 2, 2 * half, dtype=np.float32)[:, None]
        fade_in, fade_out = np.sin(angle), np.cos(angle)
    pieces: list[np.ndarray] = []
    joins: list[float] = []
    for index, (start_seconds, end_seconds) in enumerate(segments):
        start, end = int(round(start_seconds * rate)), int(round(end_seconds * rate))
        lead = half if index > 0 else 0
        trail = half if index < len(segments) - 1 else 0
        piece = _slice_padded(source, start - lead, end + trail)
        if index > 0:
            previous = pieces[-1]
            overlap = previous[-2 * half :] * fade_out + piece[: 2 * half] * fade_in
            pieces[-1] = previous[: -2 * half]
            pieces.append(overlap)
            piece = piece[2 * half :]
            joins.append(sum(len(p) for p in pieces) / rate - half / rate)
        pieces.append(piece)
    return np.concatenate(pieces).astype(np.float32), joins


def envelope_follower(signal: np.ndarray, rate: int, attack: float, release: float, window: float = 0.02, control_rate: int = 1000) -> np.ndarray:
    """RMS level over `window`, smoothed with separate attack/release time constants, at sample rate."""
    magnitude = np.abs(signal).max(axis=1) if signal.ndim == 2 else np.abs(signal)
    hop = max(1, rate // control_rate)
    blocks = len(magnitude) // hop + 1
    power = np.pad(magnitude.astype(np.float64) ** 2, (0, blocks * hop - len(magnitude))).reshape(blocks, hop).mean(axis=1)
    span = max(1, int(window * rate / hop))
    level = np.sqrt(np.convolve(power, np.ones(span) / span, mode="same"))
    up = 1 - np.exp(-hop / (attack * rate))
    down = 1 - np.exp(-hop / (release * rate))
    smoothed = np.empty_like(level)
    state = 0.0
    for index, value in enumerate(level):
        state += (up if value > state else down) * (value - state)
        smoothed[index] = state
    centres = np.arange(blocks) * hop + hop / 2
    return np.interp(np.arange(len(magnitude)), centres, smoothed).astype(np.float32)


def apply_fade_in(signal: np.ndarray, rate: int, seconds: float) -> None:
    count = min(len(signal), int(seconds * rate))
    if count > 0:
        signal[:count] *= np.linspace(0, 1, count, dtype=np.float32)[:, None] ** 2


def apply_tail_fade(signal: np.ndarray, rate: int, seconds: float, curve: float = 1.3) -> None:
    count = min(len(signal), int(seconds * rate))
    if count > 0:
        signal[-count:] *= np.linspace(1, 0, count, dtype=np.float32)[:, None] ** curve


def rms_db(signal: np.ndarray) -> float:
    if signal.size == 0:
        return float("-inf")
    return gain_to_db(float(np.sqrt(np.mean(signal.astype(np.float64) ** 2))))
