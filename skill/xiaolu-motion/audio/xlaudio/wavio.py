"""WAV read / write without soundfile/librosa.

* ``write_wav(path, y, bits=24)``  -- PCM 16/24-bit or 32-bit float ('float')
* ``read_audio(path)``              -- any WAV (PCM 16/24/32, float 32/64, incl.
  WAVE_FORMAT_EXTENSIBLE) parsed directly; any other container/codec (mp3,
  m4a, mp4, mov ...) or a sample rate other than 48 kHz is decoded by ffmpeg
  (soxr resampler). Always returns float64 (2, n) at 48 kHz.
"""
import struct
import subprocess

import numpy as np

SR = 48000


def _stereo(y):
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = np.vstack([y, y])
    if y.shape[0] != 2 and y.shape[1] == 2:
        y = y.T
    if y.shape[0] != 2:
        raise ValueError('expected mono (n,) or stereo (2, n) audio, got %r' % (y.shape,))
    return y


def write_wav(path, y, bits=24, sr=SR):
    """Write (2, n) float audio. bits=24/16 -> PCM (clipped to +-1 with a
    warning-free hard clip; check peaks before), bits='float' -> IEEE float32."""
    y = _stereo(y)
    ch, n = y.shape
    inter = np.empty(ch * n, dtype=np.float64)
    inter[0::2] = y[0]
    inter[1::2] = y[1]
    if bits == 'float' or bits == 32:
        data = inter.astype('<f4').tobytes()
        fmt_tag, bps = 3, 32
    elif bits == 24:
        q = np.round(np.clip(inter, -1.0, 1.0) * 8388607.0).astype('<i4')
        data = q.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        fmt_tag, bps = 1, 24
    elif bits == 16:
        data = np.round(np.clip(inter, -1.0, 1.0) * 32767.0).astype('<i2').tobytes()
        fmt_tag, bps = 1, 16
    else:
        raise ValueError(bits)
    block = ch * bps // 8
    fmt = struct.pack('<HHIIHH', fmt_tag, ch, sr, sr * block, block, bps)
    riff = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    if fmt_tag == 3:
        riff += b'fact' + struct.pack('<II', 4, n)
    riff += b'data' + struct.pack('<I', len(data)) + data
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', len(riff)) + riff)
    return path


def _parse_wav(raw):
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        return None
    pos = 12
    fmt = None
    data = None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        size = struct.unpack('<I', raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b'fmt ':
            tag, ch, sr, _, _, bps = struct.unpack('<HHIIHH', body[:16])
            if tag == 0xFFFE and len(body) >= 26:
                tag = struct.unpack('<H', body[24:26])[0]
            fmt = (tag, ch, sr, bps)
        elif cid == b'data':
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        return None
    tag, ch, sr, bps = fmt
    if tag == 1 and bps == 16:
        v = np.frombuffer(data[:len(data) // 2 * 2], '<i2').astype(np.float64) / 32768.0
    elif tag == 1 and bps == 24:
        b = np.frombuffer(data[:len(data) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / 8388608.0
    elif tag == 1 and bps == 32:
        v = np.frombuffer(data[:len(data) // 4 * 4], '<i4').astype(np.float64) / 2147483648.0
    elif tag == 3 and bps == 32:
        v = np.frombuffer(data[:len(data) // 4 * 4], '<f4').astype(np.float64)
    elif tag == 3 and bps == 64:
        v = np.frombuffer(data[:len(data) // 8 * 8], '<f8').astype(np.float64)
    else:
        return None
    v = v[: len(v) // ch * ch].reshape(-1, ch).T
    return v, sr


def _ffmpeg_decode(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-af', 'aresample=48000:resampler=soxr',
                          '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, '<f4').reshape(-1, 2).T.astype(np.float64)


def read_audio(path):
    """-> float64 (2, n) at 48 kHz."""
    path = str(path)
    if path.lower().endswith('.wav'):
        with open(path, 'rb') as f:
            parsed = _parse_wav(f.read())
        if parsed is not None:
            v, sr = parsed
            if sr == SR and v.shape[0] in (1, 2):
                return _stereo(v[0] if v.shape[0] == 1 else v)
    return _ffmpeg_decode(path)


def as_audio(x):
    """path or array -> float64 (2, n) at 48 kHz."""
    if isinstance(x, np.ndarray):
        return _stereo(x)
    return read_audio(x)
