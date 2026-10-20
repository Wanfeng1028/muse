"""Limit a 16-bit PCM WAV so it survives AAC encoding without clipping.

AAC overshoots sharp transients by about 3 dB, so the default ceiling is -4 dBFS.
Usage: python master_wav.py IN.wav OUT.wav [--ceiling -4] [--lookahead-ms 4] [--release-ms 80] [--lowpass 16000]
Set --lowpass 0 to skip the gentle high cut that tames click edges.
"""
import argparse, math, wave
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--ceiling", type=float, default=-4.0)
    ap.add_argument("--lookahead-ms", type=float, default=4.0)
    ap.add_argument("--release-ms", type=float, default=80.0)
    ap.add_argument("--lowpass", type=float, default=16000.0)
    a = ap.parse_args()

    with wave.open(a.inp, "rb") as w:
        ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if width != 2:
            raise SystemExit("only 16-bit PCM WAV is supported")
        x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64).reshape(-1, ch) / 32768.0

    if a.lowpass > 0:
        k = 1 - math.exp(-2 * math.pi * a.lowpass / sr)
        for c in range(ch):
            col = x[:, c].copy()
            st = 0.0
            for i in range(len(col)):
                st += k * (col[i] - st)
                col[i] = st
            x[:, c] = col

    ceil = 10 ** (a.ceiling / 20)
    peak = np.abs(x).max(1)
    need = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    win = max(1, int(a.lookahead_ms / 1000 * sr))
    g = sliding_window_view(np.pad(need, (win, win), mode="edge"), 2 * win + 1).min(1)[:len(x)]
    rel = 1 - math.exp(-1 / (a.release_ms / 1000 * sr))
    sm = np.empty_like(g)
    s = 1.0
    for i in range(len(g)):
        s = g[i] if g[i] < s else s + rel * (g[i] - s)
        sm[i] = s
    y = np.clip(x * sm[:, None], -ceil, ceil)

    with wave.open(a.out, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    before = 20 * math.log10(max(np.abs(x).max(), 1e-12))
    after = 20 * math.log10(max(np.abs(y).max(), 1e-12))
    rms = 20 * math.log10(max(np.sqrt((y ** 2).mean()), 1e-12))
    print(f"peak {before:.2f} -> {after:.2f} dBFS, rms {rms:.1f} dBFS -> {a.out}")


if __name__ == "__main__":
    main()

