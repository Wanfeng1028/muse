"""A0 shared paths, the shot table and small ffmpeg helpers.

Timeline authority: 05_visual/storyboard_v2/src/timeline.py (read-only, imported, never copied).
Every v2 frame -> source frame goes through timeline.v2_to_src / PIECES.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

VP = Path(os.environ.get("XM_VIDEO_PROJECT_ROOT", "."))  # your own project's working dir
SB2 = VP / '05_visual/storyboard_v2'
sys.path.insert(0, str(SB2 / 'src'))
import timeline as T  # noqa: E402  (read-only authority)

A0 = VP / '05_visual/build/a0'
WORK = A0 / 'work'
SHOTS_DIR = VP / '05_visual/build/shots'
LOCKED = VP / '03_locked_master'
CAPS = VP / '04_captions'
AUDIO = VP / '06_audio'
SRC = T.SRC
DEMOS = T.DEMOS
XM = Path(os.environ.get("XM_REPO_ROOT", str(Path(__file__).resolve().parents[4])))  # this repo's own root
FONTS = XM / 'fonts'
FPS = 30
W, H = 1080, 1920
TOTAL = T.TOTAL_FRAMES          # 4857
SR_SRC, SPF_SRC = 44100, 1470   # source audio: 1470 samples / frame
SR, SPF = 48000, 1600           # mix / delivery audio: 1600 samples / frame

# shot table in v2 frames [f0, f1): owner; boundaries = storyboard v2 times (all on segment / insert edges,
# except 3|4 which sits in the pause between 不会剪辑 and 那你, see words_v2)
SHOTS = [
    ('01', 0, 72, 'A0'), ('02a', 72, 137, 'A0'), ('I1', 137, 227, 'A0'), ('02b', 227, 254, 'A0'),
    ('I2', 254, 354, 'A0'), ('02c', 354, 404, 'A0'), ('I3', 404, 491, 'A0'), ('03', 491, 584, 'A0'),
    ('04', 584, 662, 'A0'), ('05', 662, 752, 'A0'), ('06', 752, 831, 'A0'),
    ('07', 831, 1065, 'A1'), ('08', 1065, 1259, 'A1'), ('09', 1259, 1490, 'A1'), ('10', 1490, 1730, 'A1'),
    ('11', 1730, 1850, 'A1'), ('12', 1850, 1972, 'A0'), ('13', 1972, 2403, 'A2'), ('14', 2403, 2937, 'A2'),
    ('15', 2937, 3394, 'A3'), ('16', 3394, 3967, 'A3'), ('17', 3967, 4118, 'A0'), ('18', 4118, 4350, 'A2'),
    ('19', 4350, 4690, 'A0'), ('20', 4690, 4857, 'A0'),
]
INSERT_KEYS = {'I1': 'vlog', 'I2': 'kepu', 'I3': 'faceless'}


def shot_at(f):
    for s in SHOTS:
        if s[1] <= f < s[2]:
            return s
    raise ValueError(f)


def insert_frames():
    """{key: (v0, v1, demo_file, demo_first_frame)}"""
    out = {}
    for p in T.PIECES:
        if p['kind'] == 'insert':
            ins = T.INS[p['key']]
            out[p['key']] = (p['v0'], p['v1'], ins['file'], int(round(ins['t0'] * FPS)))
    return out


def src_frame_of(f):
    """v2 frame -> ('max', seg, src_frame) | ('insert', key, i)  (timeline.v2_to_src on the frame centre grid)"""
    return T.v2_to_src(f / FPS)


def fmt(t):
    m, s = divmod(t, 60)
    return f'{int(m)}:{s:05.2f}'


def sh(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def ffprobe_json(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def read_audio(path, sr, ch=1, start=None, dur=None, extra_af=None):
    """decode any file to float32 (n, ch) at sr via ffmpeg (soxr, 28-bit precision)"""
    cmd = ['ffmpeg', '-v', 'error']
    if start is not None:
        cmd += ['-ss', f'{start:.6f}']
    cmd += ['-i', str(path)]
    if dur is not None:
        cmd += ['-t', f'{dur:.6f}']
    af = [f'aresample={sr}:resampler=soxr:precision=28']
    if extra_af:
        af.insert(0, extra_af)
    cmd += ['-map', '0:a:0', '-af', ','.join(af), '-ac', str(ch), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, '<f4').reshape(-1, ch).astype(np.float64)


def write_wav(path, y, sr, bits='float'):
    """y: (n,) or (n, ch) float -> WAV (32-bit float default, or 24-bit PCM)"""
    y = np.asarray(y, np.float64)
    if y.ndim == 1:
        y = y[:, None]
    ch = y.shape[1]
    fmt = ['-f', 'f32le', '-ar', str(sr), '-ac', str(ch), '-i', '-']
    codec = ['-c:a', 'pcm_f32le'] if bits == 'float' else ['-c:a', 'pcm_s24le']
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *fmt, *codec, str(path)], input=y.astype('<f4').tobytes(), check=True)


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


class RawReader:
    """sequential raw frame reader from ffmpeg (rgb24 by default, BT.709 tv -> full range RGB)"""

    def __init__(self, path, start_frame=0, n=None, pix='rgb24', w=W, h=H, fps=FPS, vf_extra=None):
        self.w, self.h, self.pix = w, h, pix
        self.bpp = {'rgb24': 3, 'gray': 1, 'yuv420p': 1.5, 'rgba': 4}[pix]
        self.size = int(w * h * self.bpp)
        cmd = ['ffmpeg', '-v', 'error']
        if start_frame:
            cmd += ['-ss', f'{(start_frame - 0.5) / fps:.6f}']
        cmd += ['-i', str(path)]
        if pix == 'rgb24':
            vf = 'scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=rgb24'
        elif pix == 'yuv420p':
            vf = 'format=yuv420p'
        else:
            vf = f'format={pix}'
        if vf_extra:
            vf = vf_extra + ',' + vf
        vf += ',settb=1/30,setpts=N'
        cmd += ['-vf', vf, '-map', '0:v:0', '-fps_mode', 'passthrough']
        if n is not None:
            cmd += ['-frames:v', str(n)]
        cmd += ['-f', 'rawvideo', '-']
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=self.size * 2)

    def read(self):
        b = self.p.stdout.read(self.size)
        if len(b) < self.size:
            return None
        if self.pix == 'yuv420p':
            return b
        a = np.frombuffer(b, np.uint8)
        return a.reshape(self.h, self.w, -1) if self.pix != 'gray' else a.reshape(self.h, self.w)

    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
        try:
            self.p.stdout.close()
        except Exception:
            pass
        self.p.wait()


def encoder(out, crf=10, preset='slow', pix_in='rgb24', w=W, h=H, fps=FPS, extra=()):
    """ffmpeg H.264 High encoder fed raw frames on stdin (RGB full range -> BT.709 tv yuv420p)"""
    if pix_in == 'rgb24':
        vf = ['-vf', 'scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p']
    else:
        vf = []
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', pix_in, '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
           *vf, '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
           '-fps_mode', 'cfr', *extra, '-an', str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
