"""shotkit — render one library shot on its own: picture, sound, preview, thumbnail.

Every library/card-* and library/fusion-* entry carries an identical copy of this file, so each
folder re-renders by itself (the repo's engine/, render/ and audio/ are the only other code it uses).
An entry is an engine component (src/<component>.js, the same contract as components/*.js) plus
src/build.py, which describes the shot in a SHOT dict and calls shotkit.main(SHOT).

  python3 build.py stills --times 0.5 1.8 3.2 [--out DIR]      review frames (PNG)
  python3 build.py render --out DIR [--workers 2] [--no-entry]  <name>.mp4 (1080x1920, sound) in DIR,
                                                                plus preview.mp4 + thumb.jpg in the entry
  python3 build.py prep --plate PLATE.mp4                       fusion shots: plate frames, faces,
                                                                hands, person mattes -> work dir
Common options: --work DIR (intermediate files; default $XM_WORK or <entry>/out/work, git-ignored),
--plate / --voice (fusion inputs; defaults $XM_PLATE / $XM_VOICE).

Picture: headless Chrome loads the stock engine page (engine/index.html -> runtime.js) and the
entry's component through this kit's local server, which maps /components/<file> to the entry's
src/ first. The runtime does sub-frame motion blur, bloom, vignette and grain (engine/post.js) in
'opaque' mode; raw RGBA goes straight into ffmpeg (no PNG sequence). Up to 2 Chrome workers, each
encoding its own H.264 segment (x264 threads 2), joined losslessly.
Sound: xlaudio cues (render_cues) + optional voice stem, summed and true-peak limited at -1.3 dBTP.
Effects keep their catalogue reference levels (designed against a -16 LUFS voice); no loudness
normalisation, so a card and a talking shot sit at the same level when cut together.
Outputs are written as *.partial.*, verified (frame count, duration, streams) and then renamed.
"""
import argparse
import asyncio
import hashlib
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

SRC = Path(sys.modules['__main__'].__file__).resolve().parent if hasattr(sys.modules['__main__'], '__file__') else Path.cwd()
ENTRY = SRC.parent
REPO = ENTRY.parent.parent
for p in (REPO, REPO / 'audio'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from render.browser import launch, open_engine, page_config  # noqa: E402
from render.common import load_style  # noqa: E402
from render.fonts import resolve_faces  # noqa: E402

KIT_VERSION = '1.0'
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json',
        '.ttf': 'font/ttf', '.otf': 'font/otf', '.png': 'image/png', '.jpg': 'image/jpeg', '.bin': 'application/octet-stream'}
EXTRA_FACES = {  # faces present in fonts/ but not declared in styles/base.json (see fonts/SOURCES.md)
    'sans': [{'weight': 900, 'ps': 'SourceHanSansSC-Heavy', 'files': ['fonts/SourceHanSansSC-Heavy.otf']}],
    'kai': [{'weight': 500, 'ps': 'LXGWWenKai-Medium', 'files': ['fonts/LXGWWenKai-Medium.ttf']}],
}


def log(*a):
    print('[shotkit]', *a, file=sys.stderr, flush=True)


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


# ----------------------------------------------------------------------------------- server
class Sink:
    """Local HTTP server: engine/, the entry's src/ (as /components/), fonts, the work dir; frames POSTed back."""

    def __init__(self, faces, work):
        self.handler = None
        fonts = {f['key']: f['path'] for f in faces}
        roots = {'engine': [REPO / 'engine'], 'components': [SRC, REPO / 'components'], 'work': [Path(work)]}
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def _send(self, code, data=b'', ctype='application/octet-stream'):
                self.send_response(code)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_GET(self):
                path = self.path.split('?')[0].lstrip('/')
                head, _, rest = path.partition('/')
                fp = None
                if head == 'font':
                    fp = fonts.get(rest) and Path(fonts[rest])
                elif head in roots and rest and '..' not in rest.split('/'):
                    fp = next((r / rest for r in roots[head] if (r / rest).is_file()), None)
                if not fp or not fp.is_file():
                    return self._send(404)
                self._send(200, fp.read_bytes(), MIME.get(fp.suffix, 'application/octet-stream'))

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                code = 200
                try:
                    srv.handler(self.path, data)
                except Exception as e:  # noqa: BLE001
                    log('sink error:', repr(e))
                    code = 500
                self._send(code)

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def close(self):
        self.httpd.shutdown()


# ----------------------------------------------------------------------------------- config
def tokens_for(shot):
    """style tokens handed to the engine: base.json fonts (only the roles the shot uses, plus the
    extra local faces), the shot's colours, and post settings (bloom, vignette, grain, shutter)"""
    base = load_style('base')
    fonts = {}
    for role, weights in shot.get('fonts', {}).items():
        spec = json.loads(json.dumps(base['fonts'][role]))
        faces = spec['open']['faces'] + EXTRA_FACES.get(role, [])
        spec['open']['faces'] = [f for f in faces if f['weight'] in weights]
        spec.pop('system_fallback', None)            # library renders must use the open fonts
        fonts[role] = spec
    post = dict(base['post'])
    post.update({'vignette': {'opaque': 0.25, 'overlay': 0.0}, 'grain': {'opaque': 1.0, 'overlay': 0.0}})
    post.update(shot.get('post', {}))
    colors = {'bg': '#000000', 'bg_glow': '#000000'}
    colors.update(shot.get('colors', {}))
    return {'name': shot['name'], 'colors': colors, 'fonts': fonts, 'type': {}, 'motion': base.get('motion', {}), 'post': post}


def frames_of(shot):
    return int(round(shot['dur'] * shot.get('fps', 30)))


def engine_cfg(shot, tokens, faces, mode='opaque', params=None):
    W, H = shot.get('size', (1080, 1920))
    res = {'canvas': {'w': W, 'h': H, 'fps': shot.get('fps', 30)}, 'camera': None, 'transitions': [],
           'shots': [{'id': shot['name'], 'component': shot['component'], 't0': 0.0, 't1': shot['dur'],
                      'params': {**shot.get('params', {}), **(params or {})}}]}
    return page_config(res, tokens, faces, mode)


def work_dir(a, shot):
    w = Path(a.work or os.environ.get('XM_WORK') or ENTRY / 'out' / 'work')
    w.mkdir(parents=True, exist_ok=True)
    return w


def check_glyphs(shot, faces):
    """every character the shot draws must exist in the font it is drawn with (no tofu, no fallback)"""
    from fontTools.ttLib import TTFont
    bad = {}
    for role, text in (shot.get('glyphs') or {}).items():
        paths = sorted({f['path'] for f in faces if f['role'] == role})
        if not paths:
            raise SystemExit(f'glyph check: no font resolved for role {role}')
        for p in paths:
            cmap = TTFont(p, lazy=True, fontNumber=0).getBestCmap()
            miss = sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})
            if miss:
                bad[f'{role}:{Path(p).name}'] = ''.join(miss)
    if bad:
        raise SystemExit(f'glyph check failed (missing glyphs): {bad}')
    return True


# ----------------------------------------------------------------------------------- picture
TO_YUV = ('scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=bicubic+accurate_rnd+full_chroma_int,format=yuv420p,'
          'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv')
TAGS = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv']


def x264_cmd(W, H, fps, out, crf=14, noise=0):
    vf = TO_YUV + (f',noise=c0s={noise}:c0f=t+u' if noise else '')
    grain = 'aq-mode=3:deadzone-inter=6:deadzone-intra=6:no-dct-decimate=1:psy-rd=1.0,0.15:threads=2'
    return ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}',
            '-r', str(fps), '-i', '-', '-vf', vf, '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-crf', str(crf),
            '-g', str(2 * fps), '-sc_threshold', '0', '-pix_fmt', 'yuv420p', *TAGS,
            '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv:' + grain, '-an', str(out)]


# the component's own timing(params) (defaults merged), so sound cues use the picture's exact beats
JS_TIMING = '''async ([id, p]) => { const m = await import('/components/' + id + '.js');
  const d = {}; for (const [k, v] of Object.entries(m.params || {})) d[k] = v.default;
  const q = Object.assign(d, p || {});
  if (m.prepare) await m.prepare(q);                   // data-driven shots load their Vision data first
  return m.timing ? m.timing(q) : null; }'''


async def _segment(p, shot, cfg, faces, work, i0, i1, out, tag):
    W, H = shot.get('size', (1080, 1920))
    fps = shot.get('fps', 30)
    sink = Sink(faces, work)
    proc = subprocess.Popen(x264_cmd(W, H, fps, out, shot.get('crf', 14), shot.get('enc_noise', 0)), stdin=subprocess.PIPE)
    lock, nxt = threading.Lock(), {'i': i0}

    def handler(path, data):
        i = int(path.split('i=')[1])
        with lock:
            if i < nxt['i']:
                return                                   # duplicate after a client retry
            assert i == nxt['i'], (i, nxt['i'])
            assert len(data) == W * H * 4, len(data)
            proc.stdin.write(data)
            nxt['i'] += 1
    sink.handler = handler
    browser = await launch(p)
    page, info = await open_engine(browser, sink, cfg, verbose=True)
    timing = await page.evaluate(JS_TIMING, [shot['component'], cfg['shots'][0]['params']])
    t0 = time.time()
    CH = 15
    for a in range(i0, i1, CH):
        b = min(i1, a + CH)
        await page.evaluate('([a,b]) => window.__XM_PRELOAD ? window.__XM_PRELOAD(a,b) : null', [a, b])
        await page.evaluate('([a,b,u]) => window.XM.renderRange(a,b,u)', [a, b, '/frame'])
        log(f'[{tag}] {b - i0}/{i1 - i0} frames {time.time() - t0:.0f}s')
    st = await page.evaluate('window.XM.stats()')
    await _close(browser, page, tag)
    proc.stdin.close()
    proc.wait()
    sink.close()
    if proc.returncode or nxt['i'] != i1:
        raise RuntimeError(f'[{tag}] encoder rc={proc.returncode}, frames {nxt["i"] - i0}/{i1 - i0}')
    return {'tag': tag, 'gl': info['gl'], 'fonts': info['fonts'], 'probes': info['probes'], 'js': st, 'wall_s': round(time.time() - t0, 1),
            'timing': timing}


async def _close(browser, page, tag):
    # a GPU page can hang on close; close the page first, never wait long, never leave a dangling future
    for what, fut, tmo in (('page', page.close, 5), ('browser', browser.close, 10)):
        task = asyncio.ensure_future(fut())
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=tmo)
        except Exception as e:  # noqa: BLE001
            log(f'[{tag}] {what} close: {type(e).__name__}')
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def render_picture(shot, cfg, faces, work, out, workers=2):
    from playwright.async_api import async_playwright
    N = frames_of(shot)
    workers = max(1, min(2, workers))
    per = math.ceil(N / workers)
    segs = [(k, s, min(N, s + per)) for k, s in enumerate(range(0, N, per))]

    async def go():
        async with async_playwright() as p:
            return await asyncio.gather(*[_segment(p, shot, cfg, faces, work, s, e, Path(f'{out}.seg{k}.mp4'), f'w{k}') for k, s, e in segs])
    results = asyncio.run(go())
    lst = Path(f'{out}.segments.txt')
    lst.write_text(''.join(f"file '{Path(f'{out}.seg{k}.mp4').resolve()}'\n" for k, _, _ in segs))
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out])
    for k, _, _ in segs:
        Path(f'{out}.seg{k}.mp4').unlink()
    lst.unlink()
    return results


async def _stills(shot, cfg, faces, work, times):
    from playwright.async_api import async_playwright
    W, H = shot.get('size', (1080, 1920))
    fps = shot.get('fps', 30)
    sink = Sink(faces, work)
    got = {}
    sink.handler = lambda path, data: got.__setitem__(path, data)
    out = []
    async with async_playwright() as p:
        browser = await launch(p)
        page, info = await open_engine(browser, sink, cfg, verbose=True)
        info['timing'] = await page.evaluate(JS_TIMING, [shot['component'], cfg['shots'][0]['params']])
        for k, t in enumerate(times):
            i = int(math.floor(t * fps + 1e-6))
            await page.evaluate('([a,b]) => window.__XM_PRELOAD ? window.__XM_PRELOAD(a,b) : null', [i, i + 1])
            await page.evaluate('([t,u]) => window.XM.renderAndPost(t,u)', [t, f'/still?k={k}'])
            out.append(np.frombuffer(got.pop(f'/still?k={k}'), np.uint8).reshape(H, W, 4).copy())
        await _close(browser, page, 'stills')
    sink.close()
    return out, info


# ----------------------------------------------------------------------------------- sound
def render_sound(shot, work, out_wav):
    import xlaudio as xa
    from xlaudio.dsp import limiter
    if shot.get('sound_setup'):
        shot['sound_setup']()                            # registers the entry's own synthesised sounds
    dur = frames_of(shot) / shot.get('fps', 30)
    cues = shot['sfx'](shot) if callable(shot.get('sfx')) else list(shot.get('sfx') or [])
    y, cue_log = xa.render_cues(cues, dur, return_log=True)
    if shot.get('bed'):
        b = shot['bed'](shot, dur)
        y = y + b[:, :y.shape[1]]
    voice = work / 'voice.wav'
    if shot.get('plate', {}).get('voice') and voice.exists():
        v = xa.read_audio(str(voice))
        n = min(v.shape[1], y.shape[1])
        y[:, :n] += v[:, :n] * 10 ** (shot['plate'].get('voice_gain_db', 0) / 20)
    y, _ = limiter(y, ceiling_db=-1.3)
    xa.write_wav(str(out_wav), y, bits='float')
    return cue_log


# ----------------------------------------------------------------------------------- verify / deliver
def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def verify(path, frames, fps, audio=True):
    P = probe(path)
    v = [s for s in P['streams'] if s['codec_type'] == 'video']
    a = [s for s in P['streams'] if s['codec_type'] == 'audio']
    ok = len(v) == 1 and int(v[0]['nb_read_frames']) == frames and (bool(a) == audio)
    info = {'frames': int(v[0]['nb_read_frames']) if v else 0, 'expected': frames, 'size': [v[0]['width'], v[0]['height']] if v else None,
            'duration': float(P['format']['duration']), 'audio': bool(a), 'bytes': int(P['format']['size']),
            'color': v[0].get('color_space') if v else None}
    if not ok:
        raise SystemExit(f'verify failed for {path}: {info}')
    return info


def mux(video, wav, out):
    encs = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    ac = ['-c:a', 'aac_at', '-aac_at_mode', 'cbr'] if ' aac_at ' in encs else ['-c:a', 'aac']
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', video, '-i', wav, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
         *ac, '-b:a', '256k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', out])


def preview_and_thumb(shot, final, entry=ENTRY):
    fps = shot.get('fps', 30)
    for crf in (24, 27, 30, 33):
        tmp = entry / 'preview.partial.mp4'
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', final, '-vf', 'scale=202:360:flags=lanczos,format=yuv420p',
             '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-profile:v', 'high', *TAGS, '-x264-params', 'threads=4',
             '-c:a', 'aac', '-b:a', '96k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', tmp])
        if tmp.stat().st_size <= 1_500_000:
            break
    verify(tmp, frames_of(shot), fps)
    tmp.replace(entry / 'preview.mp4')
    t = shot.get('thumb_t', shot['dur'] * 0.75)
    tj = entry / 'thumb.partial.jpg'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{t:.3f}', '-i', final, '-frames:v', '1',
         '-vf', 'scale=480:854:flags=lanczos', '-q:v', '3', '-f', 'image2', tj])
    tj.replace(entry / 'thumb.jpg')
    return {'preview_bytes': (entry / 'preview.mp4').stat().st_size, 'thumb': str(entry / 'thumb.jpg')}


# ----------------------------------------------------------------------------------- plate prep (fusion)
def vision_exe(work):
    exe = work / 'bin' / 'vision'
    src = SRC / 'vision.swift'
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        exe.parent.mkdir(parents=True, exist_ok=True)
        run(['swiftc', '-O', src, '-o', exe], capture_output=True)
    return exe


def xpc_mb():
    out = subprocess.run(['ps', '-axo', 'rss=,comm='], capture_output=True, text=True).stdout
    return sum(int(l.split()[0]) for l in out.splitlines() if 'VTDecoderXPCService' in l) / 1024


def vision_lines(work, plate, mode, a, b, step=1):
    """faces / hands JSON lines for plate frames [a, b), <= 300 frames per Vision process"""
    exe, base, lines = vision_exe(work), xpc_mb(), []
    for c0 in range(a, b, 300):
        c1 = min(b, c0 + 300)
        r = run([exe, mode, plate, '--start', c0, '--end', c1, '--step', step], capture_output=True, text=True)
        lines += [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
        if xpc_mb() - base > 1500:
            raise SystemExit('decoder XPC services grew past 1.5 GB, stopping')
    return lines


def read_plate(plate, a, n, W, H):
    """RGB frames [a, a+n) of the plate, decoded as BT.709 tv (never re-timed)"""
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '2', '-ss', f'{(a - 0.5) / 30:.6f}', '-i', str(plate), '-frames:v', str(n),
                          '-vf', 'scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24',
                          '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    for _ in range(n):
        buf = p.stdout.read(W * H * 3)
        if len(buf) != W * H * 3:
            raise SystemExit(f'plate read short at frame {a + _}')
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.stdout.close()
    p.wait()


def refine_mattes(raw_dir, frames, W, H):
    """Vision person masks -> full-res soft mattes (uint8): keep the connected person, fill small holes,
    repair drop-out frames from their neighbours, motion-adaptive temporal smoothing. Mattes are held
    as uint8 (about 2 MB a frame) and only three neighbours are ever expanded to float."""
    import cv2

    def load(f):
        m = cv2.imread(str(raw_dir / f'{f:06d}.png'), cv2.IMREAD_GRAYSCALE)
        return cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255

    def clean(m):
        core = (m > 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(core, 8)
        if n > 1:
            big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            keep = np.isin(lab, [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] > 0.02 * st[big, cv2.CC_STAT_AREA]])
            roi = cv2.GaussianBlur(cv2.dilate(keep.astype(np.uint8), np.ones((49, 49), np.uint8)).astype(np.float32), (0, 0), 16)
            m = m * np.clip(roi * 1.6 - 0.3, 0, 1)
        solid = (m > 0.25).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(1 - solid, 4)
        for k in range(1, n):
            x, y, w, h, area = st[k]
            if area <= 6000 and x > 0 and y > 0 and x + w < W and y + h < H:
                solid[lab == k] = 1
        inner = cv2.GaussianBlur(cv2.erode(solid, np.ones((9, 9), np.uint8)).astype(np.float32), (0, 0), 1.2)
        return np.maximum(m, inner)
    q8 = lambda m: np.clip(m * 255 + 0.5, 0, 255).astype(np.uint8)
    f32 = lambda m: m.astype(np.float32) / 255
    ms = [q8(clean(load(f))) for f in frames]
    area = np.array([m.mean() for m in ms])
    out = []
    for k in range(len(ms)):
        lo, hi = max(0, k - 6), min(len(ms), k + 7)
        m = f32(ms[k])
        if area[k] < 0.93 * np.median(area[lo:hi]):          # drop-out: borrow the neighbours' common core
            nb = [f32(ms[j]) for j in (k - 1, k + 1) if 0 <= j < len(ms)]
            m = np.maximum(m, cv2.GaussianBlur(cv2.erode(np.minimum.reduce(nb), np.ones((13, 13), np.uint8)), (0, 0), 1.5))
        prv, nxt = f32(ms[max(0, k - 1)]), f32(ms[min(len(ms) - 1, k + 1)])
        w = np.exp(-(np.abs(nxt - prv) / 0.12) ** 2) * 0.5
        m = m + w * ((prv + nxt) * 0.5 - m)
        out.append(q8(np.clip((m - 0.04) / 0.92, 0, 1)))
    return out


def clean_plate(plate, f0, mattes, W, H):
    """background without the person: weighted mean of uncovered pixels (streamed), holes inpainted"""
    import cv2
    acc = np.zeros((H, W, 3), np.float32)
    ws = np.zeros((H, W), np.float32)
    ker = np.ones((37, 37), np.uint8)
    for img, m8 in zip(read_plate(plate, f0, len(mattes), W, H), mattes):
        w = np.clip(1 - cv2.dilate(m8, ker).astype(np.float32) / 255 * 1.5, 0, 1) ** 2
        acc += img.astype(np.float32) * w[..., None]
        ws += w
    valid = ws > 0.5
    pl = np.where(valid[..., None], acc / np.maximum(ws, 1e-6)[..., None], 0)
    small = cv2.resize(np.clip(pl, 0, 255).astype(np.uint8), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    hole = cv2.dilate(cv2.resize((~valid).astype(np.uint8) * 255, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST), np.ones((5, 5), np.uint8))
    fill = cv2.GaussianBlur(cv2.inpaint(small, hole, 15, cv2.INPAINT_TELEA), (0, 0), 5)
    up = cv2.resize(fill, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    t = np.clip(cv2.distanceTransform(valid.astype(np.uint8), cv2.DIST_L2, 5) / 10, 0, 1)[..., None]
    return np.clip(np.where(valid[..., None], pl * t + up * (1 - t), up) + 0.5, 0, 255).astype(np.uint8), float(valid.mean())


def prep_plate(shot, a):
    """plate frames [start, end) -> work/plate/NNNNNN.png (RGB), work/person/NNNNNN.png (RGBA: plate colour,
    un-mixed from the clean plate at the soft edge; alpha = matte), work/clean.png, work/faces.json,
    work/hands.json, work/voice.wav"""
    import cv2
    from PIL import Image
    P = shot['plate']
    plate = a.plate or os.environ.get('XM_PLATE')
    if not plate or not Path(plate).exists():
        raise SystemExit('fusion prep needs --plate PLATE.mp4 (or $XM_PLATE)')
    work = work_dir(a, shot)
    W, H = shot.get('size', (1080, 1920))
    f0, f1 = P['start'], P['end']
    frames = list(range(f0, f1))
    meta = {'plate': str(Path(plate).name), 'start': f0, 'end': f1, 'kit': KIT_VERSION}
    if P.get('faces', True):
        (work / 'faces.json').write_text(json.dumps(vision_lines(work, plate, 'faces', f0, f1)))
    if P.get('hands'):
        (work / 'hands.json').write_text(json.dumps(vision_lines(work, plate, 'hands', f0, f1)))
    (work / 'plate').mkdir(exist_ok=True)
    for f, img in zip(frames, read_plate(plate, f0, len(frames), W, H)):
        Image.fromarray(img).save(work / 'plate' / f'{f:06d}.png', compress_level=1)
    if P.get('matte'):
        raw = work / 'raw_matte'
        exe, base = vision_exe(work), xpc_mb()
        for c0 in range(f0, f1, 300):
            run([exe, 'matte', plate, raw, '--start', c0, '--end', min(f1, c0 + 300), '--quality', 'accurate'], capture_output=True)
            if xpc_mb() - base > 1500:
                raise SystemExit('decoder XPC services grew past 1.5 GB, stopping')
        mattes = refine_mattes(raw, frames, W, H)
        shutil.rmtree(raw)
        bg, seen = clean_plate(plate, f0, mattes, W, H)
        Image.fromarray(bg).save(work / 'clean.png')
        meta['clean_plate_seen'] = round(seen, 3)
        bgf = bg.astype(np.float32)
        (work / 'person').mkdir(exist_ok=True)
        if P.get('bgfill'):
            (work / 'bg').mkdir(exist_ok=True)
            ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * P['bgfill'] + 1, 2 * P['bgfill'] + 1))
        for f, img, m8 in zip(frames, read_plate(plate, f0, len(frames), W, H), mattes):
            c = img.astype(np.float32)
            al = m8.astype(np.float32)[..., None] / 255
            un = (c - (1 - al) * bgf) / np.maximum(al, 1e-3)     # C = aF + (1-a)B with B known -> F (edge colour un-mixed)
            edge = (al > 0.02) & (al < 0.98)
            fg = np.where(edge, np.clip(un, 0, 255), c)
            rgba = np.dstack([np.clip(fg + 0.5, 0, 255).astype(np.uint8), m8])
            Image.fromarray(rgba, 'RGBA').save(work / 'person' / f'{f:06d}.png', compress_level=1)
            if P.get('bgfill'):                                   # live wall; the person region filled from the clean plate
                md = cv2.GaussianBlur(cv2.dilate(m8, ker).astype(np.float32) / 255, (0, 0), P['bgfill'] / 3)[..., None]
                Image.fromarray(np.clip(c * (1 - md) + bgf * md + 0.5, 0, 255).astype(np.uint8)).save(work / 'bg' / f'{f:06d}.png', compress_level=1)
    if P.get('voice'):
        voice = a.voice or os.environ.get('XM_VOICE')
        if not voice or not Path(voice).exists():
            raise SystemExit('this shot uses the voice stem: pass --voice VOICE.wav (or $XM_VOICE)')
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{f0 / 30:.6f}', '-t', f'{(f1 - f0) / 30:.6f}', '-i', voice,
             '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', work / 'voice.wav'])
    (work / 'prep.json').write_text(json.dumps(meta, indent=1))
    log('prep done:', meta)
    return meta


# ----------------------------------------------------------------------------------- commands
def cmd_stills(shot, a):
    from PIL import Image
    tokens = tokens_for(shot)
    faces = resolve_faces(tokens)
    check_glyphs(shot, faces)
    work = work_dir(a, shot)
    out = Path(a.out or work / 'stills')
    out.mkdir(parents=True, exist_ok=True)
    ims, info = asyncio.run(_stills(shot, engine_cfg(shot, tokens, faces, params=shot.get('still_params')), faces, work, a.times))
    for t, im in zip(a.times, ims):
        Image.fromarray(im[..., :3]).save(out / f'{shot["name"]}_{t:06.3f}.png')
    log('fonts', [(f['family'], f['weight'], f['status']) for f in info['fonts']], 'gl', info['gl'])
    print(json.dumps({'timing': info.get('timing'), 'stills': [str(out / f'{shot["name"]}_{t:06.3f}.png') for t in a.times]}, ensure_ascii=False))


def cmd_render(shot, a):
    tokens = tokens_for(shot)
    faces = resolve_faces(tokens)
    check_glyphs(shot, faces)
    work = work_dir(a, shot)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f'{shot["name"]}.mp4'
    silent = work / f'{shot["name"]}.silent.mp4'
    wav = work / f'{shot["name"]}.sound.wav'
    t0 = time.time()
    res = render_picture(shot, engine_cfg(shot, tokens, faces), faces, work, silent, a.workers)
    shot['T'] = res[0]['timing']                         # beats as the page computed them
    cue_log = render_sound(shot, work, wav)
    part = out_dir / f'{shot["name"]}.partial.mp4'
    mux(silent, wav, part)
    info = verify(part, frames_of(shot), shot.get('fps', 30))
    part.replace(final)
    silent.unlink()
    rep = {'shot': shot['name'], 'final': str(final), 'video': info, 'kit': KIT_VERSION, 'wall_s': round(time.time() - t0, 1),
           'gl': res[0]['gl'], 'fonts': res[0]['fonts'], 'font_probes': res[0]['probes'],
           'subframes_per_frame': round(sum(r['js']['subframes'] for r in res) / max(1, sum(r['js']['frames'] for r in res)), 2),
           'sfx': [{k: c[k] for k in ('id', 'at', 'align', 'gain_db')} for c in cue_log]}
    if not a.no_entry:
        rep.update(preview_and_thumb(shot, final))
    (work / f'{shot["name"]}.render.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    wav.unlink()
    print(json.dumps({k: rep[k] for k in ('final', 'video', 'wall_s', 'subframes_per_frame')}, ensure_ascii=False))


def main(shot):
    ap = argparse.ArgumentParser(description=f'{shot["name"]} (shotkit {KIT_VERSION})')
    sp = ap.add_subparsers(dest='cmd', required=True)
    for name in ('stills', 'render', 'prep'):
        s = sp.add_parser(name)
        s.add_argument('--work')
        s.add_argument('--plate')
        s.add_argument('--voice')
        if name == 'stills':
            s.add_argument('--times', type=float, nargs='+', required=True)
            s.add_argument('--out')
        if name == 'render':
            s.add_argument('--out', required=True)
            s.add_argument('--workers', type=int, default=2)
            s.add_argument('--no-entry', action='store_true', help='do not write preview.mp4 / thumb.jpg into the entry')
    a = ap.parse_args()
    if a.cmd == 'prep':
        prep_plate(shot, a)
    elif a.cmd == 'stills':
        cmd_stills(shot, a)
    else:
        cmd_render(shot, a)
