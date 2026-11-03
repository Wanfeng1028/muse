"""code-film 音频脚本共用的工具函数。需要 numpy。"""
import shutil
import subprocess
import sys
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("缺少 numpy，请先执行：pip install numpy")


def setup_stdout():
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass


def to_stereo(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    return x


def write_wav(path, data, sr):
    data = np.clip(to_stereo(data), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def decode_audio(path, sr):
    """解码任意音频为单声道 float32。优先用 ffmpeg；没有 ffmpeg 时只支持 16 位 PCM wav。"""
    path = str(path)
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
        out = subprocess.run(cmd, capture_output=True)
        if out.returncode != 0:
            sys.exit(f"ffmpeg 解码失败：{out.stderr.decode(errors='replace')}")
        return np.frombuffer(out.stdout, dtype="<f4").astype(np.float64)
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            sys.exit("没有 ffmpeg 时只能读取 16 位 PCM wav，请安装 ffmpeg")
        ch, rate = w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    x = x.reshape(-1, ch).mean(axis=1)
    if rate != sr:
        idx = np.arange(0, len(x), rate / sr)
        x = np.interp(idx, np.arange(len(x)), x)
    return x


def db(x):
    return 10 ** (x / 20.0)


def normalize(x, peak_db=-1.0):
    m = np.max(np.abs(x))
    return x if m < 1e-9 else x * (db(peak_db) / m)


def fade(x, sr, fin=0.003, fout=0.01):
    x = np.array(x, dtype=np.float64)
    n = len(x)
    a, b = min(n, int(fin * sr)), min(n, int(fout * sr))
    shape = (n,) + (1,) * (x.ndim - 1)
    env = np.ones(n)
    if a > 0:
        env[:a] = np.linspace(0, 1, a)
    if b > 0:
        env[n - b:] *= np.linspace(1, 0, b)
    return x * env.reshape(shape)


def lowpass_gain(f, fc, order=2):
    return 1.0 / np.sqrt(1.0 + (f / fc) ** (2 * order))


def highpass_gain(f, fc, order=2):
    return 1.0 / np.sqrt(1.0 + (fc / np.maximum(f, 1e-3)) ** (2 * order))


def bandpass_gain(f, fc, width_oct=1.0):
    return np.exp(-0.5 * (np.log2(np.maximum(f, 1.0) / fc) / width_oct) ** 2)


def fft_filter(x, sr, gain_fn):
    """静态滤波：整段做 FFT，乘以频率响应。x 可以是单声道或 (n, 2)。"""
    x = np.asarray(x, dtype=np.float64)
    n = x.shape[0]
    X = np.fft.rfft(x, axis=0)
    g = gain_fn(np.fft.rfftfreq(n, 1.0 / sr))
    X *= g[:, None] if x.ndim == 2 else g
    return np.fft.irfft(X, n=n, axis=0)


def stft_filter(x, sr, gain_at, n_fft=2048, hop=512):
    """随时间变化的滤波。gain_at(freqs, t) 返回该时刻的频率响应。x 为单声道。"""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    win = np.hanning(n_fft)
    pad = np.concatenate([np.zeros(n_fft), x, np.zeros(n_fft)])
    out = np.zeros(len(pad))
    norm = np.zeros(len(pad))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    for s in range(0, len(pad) - n_fft + 1, hop):
        t = (s + n_fft / 2 - n_fft) / sr
        spec = np.fft.rfft(pad[s:s + n_fft] * win) * gain_at(freqs, t)
        out[s:s + n_fft] += np.fft.irfft(spec, n_fft) * win
        norm[s:s + n_fft] += win ** 2
    norm[norm < 1e-8] = 1.0
    return (out / norm)[n_fft:n_fft + n]


def fft_convolve(a, b):
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, nfft) * np.fft.rfft(b, nfft), nfft)[:n]


def reverb(x, sr, seconds=1.5, mix=0.2, seed=0, brightness=6000.0):
    """简单的卷积混响：指数衰减的噪声作为脉冲响应，左右声道去相关。"""
    x = to_stereo(x)
    rng = np.random.default_rng(seed)
    m = int(seconds * sr)
    t = np.arange(m) / sr
    decay = np.exp(-6.9 * t / seconds)
    wet = np.zeros((x.shape[0] + m - 1, 2))
    for ch in range(2):
        ir = rng.standard_normal(m) * decay
        ir = fft_filter(ir, sr, lambda f: lowpass_gain(f, brightness, 1))
        ir[: int(0.012 * sr)] *= np.linspace(0, 1, int(0.012 * sr))
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-12
        wet[:, ch] = fft_convolve(x[:, ch], ir)
    dry = np.zeros_like(wet)
    dry[: x.shape[0]] = x
    return dry * (1 - mix) + wet * mix


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def sweep_sine(freq_curve, sr):
    """频率随时间变化的正弦，freq_curve 是逐采样的频率数组。"""
    return np.sin(2 * np.pi * np.cumsum(freq_curve) / sr)


def trim_tail(x, sr, thresh_db=-60.0):
    """裁掉结尾低于阈值的静音，保留 20ms 余量并淡出。"""
    x = to_stereo(x)
    level = np.abs(x).max(axis=1)
    loud = np.nonzero(level > level.max() * db(thresh_db))[0]
    if len(loud) == 0:
        return x
    end = min(len(x), loud[-1] + int(0.02 * sr))
    return fade(x[:end], sr, 0.0, 0.02)


def peak_time(x, sr, win=0.01):
    """短时能量最大的时刻（秒）。"""
    mono = to_stereo(x).mean(axis=1)
    w = max(1, int(win * sr))
    energy = np.convolve(mono ** 2, np.ones(w) / w, mode="same")
    return float(np.argmax(energy)) / sr
