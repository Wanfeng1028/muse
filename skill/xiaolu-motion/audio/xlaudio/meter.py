"""ITU-R BS.1770-4 / EBU R128 loudness measurement (K-weighting, gated
integrated loudness, momentary / short-term, LRA, 4x true peak).

Used for iteration inside the library. Reports quote ffmpeg's ebur128 filter as
the authoritative number and this meter as a cross-check (they agree to
~0.1 LU on the test material).
Buffers are (2, n) float at 48 kHz (mono (n,) is accepted).
"""
import numpy as np
from scipy import signal

SR = 48000
_B1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
_A1 = [1.0, -1.69065929318241, 0.73248077421585]
_B2 = [1.0, -2.0, 1.0]
_A2 = [1.0, -1.99004745483398, 0.99007225036621]


def _2d(x):
    x = np.asarray(x, dtype=np.float64)
    return x[None, :] if x.ndim == 1 else x


def kweight(x):
    y = signal.lfilter(_B1, _A1, x, axis=-1)
    return signal.lfilter(_B2, _A2, y, axis=-1)


def _power(x):
    z = kweight(_2d(x))
    return np.sum(z * z, axis=0)


def _windows(p, win, hop):
    """mean power over windows ending at k*hop (window [end-win, end))."""
    c = np.concatenate([[0.0], np.cumsum(p)])
    ends = np.arange(hop, len(p) + 1, hop)
    starts = np.maximum(ends - win, 0)
    return (c[ends] - c[starts]) / win, ends / SR


def lufs(pw):
    return -0.691 + 10.0 * np.log10(np.maximum(pw, 1e-20))


def integrated(x):
    """gated integrated loudness (LUFS); -inf if everything is below -70."""
    p = _power(x)
    pw, _ = _windows(p, int(0.4 * SR), int(0.1 * SR))
    pw = pw[3:]
    if len(pw) == 0:
        return -np.inf
    lk = lufs(pw)
    m = lk > -70.0
    if not np.any(m):
        return -np.inf
    rel = lufs(np.mean(pw[m])) - 10.0
    m2 = m & (lk > rel)
    return float(lufs(np.mean(pw[m2])))


def short_term(x, hop=0.1):
    p = _power(x)
    pw, t = _windows(p, int(3.0 * SR), int(hop * SR))
    return t, lufs(pw)


def momentary(x, hop=0.1):
    p = _power(x)
    pw, t = _windows(p, int(0.4 * SR), int(hop * SR))
    return t, lufs(pw)


def max_momentary(x, hop=0.01):
    """maximum momentary loudness (400 ms window, 10 ms hop), zero padded so
    sounds shorter than 400 ms are measured as heard (energy / 400 ms)."""
    x = _2d(x)
    pad = np.zeros((x.shape[0], int(0.4 * SR)))
    _, m = momentary(np.hstack([pad, x, pad]), hop)
    return float(np.max(m))


def lra(x):
    t, s = short_term(x, 0.1)
    s = s[t >= 3.0]
    s = s[s > -70]
    if len(s) == 0:
        return 0.0
    pw = 10 ** ((s + 0.691) / 10)
    rel = lufs(np.mean(pw)) - 20
    s = s[s > rel]
    return float(np.percentile(s, 95) - np.percentile(s, 10))


def ungated(x, t0=None, t1=None):
    """ungated loudness (energy mean of the K-weighted power) of [t0, t1)."""
    x = _2d(x)
    a = 0 if t0 is None else int(t0 * SR)
    b = x.shape[1] if t1 is None else int(t1 * SR)
    return float(lufs(np.mean(_power(x[:, a:b]))))


def true_peak_db(x):
    """4x oversampled true peak (dBTP), BS.1770-4 style."""
    up = signal.resample_poly(_2d(x), 4, 1, axis=-1)
    return float(20 * np.log10(np.max(np.abs(up)) + 1e-20))


def sample_peak_db(x):
    return float(20 * np.log10(np.max(np.abs(x)) + 1e-20))
