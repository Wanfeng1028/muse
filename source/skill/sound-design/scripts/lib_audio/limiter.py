"""Look-ahead true-peak limiter, run before loudnorm so its second pass stays in linear mode (needs scipy)."""
import numpy as np
from scipy.ndimage import minimum_filter1d
from scipy.signal import resample_poly

BLOCK_SECONDS = 0.001


def true_peak_per_sample(signal: np.ndarray) -> np.ndarray:
    oversampled = np.abs(resample_poly(signal, 4, 1, axis=0)).max(axis=1)
    count = len(signal)
    return np.pad(oversampled, (0, max(0, 4 * count - len(oversampled))))[: 4 * count].reshape(count, 4).max(axis=1)


def limit(signal: np.ndarray, rate: int, ceiling_db: float, lookahead: float = 0.005, release: float = 0.08) -> float:
    """Reduce gain in place so the 4x-oversampled peak stays under ceiling_db. Returns the max reduction in dB."""
    ceiling = 10 ** (ceiling_db / 20)
    needed = np.minimum(1.0, ceiling / np.maximum(true_peak_per_sample(signal), 1e-9))
    if needed.min() >= 1.0:
        return 0.0
    block = max(1, int(BLOCK_SECONDS * rate))
    blocks = -(-len(needed) // block)
    padded = np.pad(needed, (0, blocks * block - len(needed)), constant_values=1.0)
    per_block = minimum_filter1d(padded.reshape(blocks, block).min(axis=1), size=2 * max(1, int(lookahead / BLOCK_SECONDS)) + 1)
    recovery = 1 - np.exp(-BLOCK_SECONDS / release)
    smoothed = np.empty_like(per_block)
    state = 1.0
    for index, target in enumerate(per_block):
        state = min(target, state + (1.0 - state) * recovery)
        smoothed[index] = state
    stepped = np.pad(np.repeat(smoothed, block), (block, block - 1), mode="edge")
    gain = np.convolve(stepped, np.ones(2 * block) / (2 * block), mode="valid")[: len(signal)]
    signal *= gain[:, None].astype(np.float32)
    return float(-20 * np.log10(gain.min()))
