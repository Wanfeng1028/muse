"""v2 candidates (pause-cut, and pause-cut at 1.1x) from the v2 cut list. Heavy steps go through with_heavy_lock.py.
usage: python3 deliver_v2.py render | audio | package | qa | all
07_delivery/: 视频20_候选_v2_删停顿_{含BGM,无BGM,手机预览}.mp4, 视频20_候选_v2_删停顿1.1倍速_{含BGM,无BGM,手机预览}.mp4,
              matching .srt/.ass and 每秒1帧 contact sheets; evidence in a0/qa/v2_*.json"""
import json
import os
import random
import subprocess
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
LOCK = [sys.executable, str(HERE / 'with_heavy_lock.py')]
DEL = VP / '07_delivery'
V = {'v2p': dict(name='视频20_候选_v2_删停顿', frames=A0 / 'cuts/frames_v2p.json'),
     'v2p110': dict(name='视频20_候选_v2_删停顿1.1倍速', frames=A0 / 'cuts/frames_v2p110.json')}


def run(cmd, heavy=False):
    cmd = [str(c) for c in cmd]
    print('>>', ' '.join(cmd)[:150], flush=True)
    subprocess.run((LOCK + cmd) if heavy else cmd, check=True)


def nframes(p):
    return int(subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries',
                               'stream=nb_read_packets', '-of', 'csv=p=0', str(p)], capture_output=True, text=True).stdout)


def mux(video, audio, out, n):
    part = str(out) + '.partial'
    run(['ffmpeg', '-v', 'error', '-y', '-threads', '4', '-i', video, '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-ac', '2', '-shortest', '-movflags', '+faststart', '-f', 'mp4', part], heavy=True)
    assert nframes(part) == n, (out, nframes(part), n)
    os.replace(part, out)


def phone(src, wav, out, dur):
    """720p preview: picture from the delivered file, sound encoded once from the master WAV (re-encoding the delivered AAC
    lifted the true peak to -0.9 dBTP)"""
    for vb in (int((26.3e6 * 8 / dur - 128e3) / 1000), int((24.5e6 * 8 / dur - 128e3) / 1000)):
        part = str(out) + '.partial'
        run(['ffmpeg', '-v', 'error', '-y', '-threads', '4', '-i', src, '-i', wav, '-map', '0:v:0', '-map', '1:a:0', '-shortest',
             '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264',
             '-preset', 'medium', '-b:v', f'{vb}k', '-maxrate', f'{int(vb * 1.2)}k', '-bufsize', f'{int(vb * 2)}k', '-profile:v', 'high',
             '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
             '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', '-f', 'mp4', part], heavy=True)
        if Path(part).stat().st_size < 28e6:
            os.replace(part, out)
            return vb
    raise SystemExit(f'phone version still >= 28 MB: {out}')


def make_phone(tag, d):
    n = load_json(d['frames'])['n']
    out = DEL / f"{d['name']}_手机预览.mp4"
    vb = phone(DEL / f"{d['name']}_含BGM.mp4", AUDIO / f'mix_{tag}_bgm1.wav', out, n / FPS)
    assert nframes(out) == n, (out, nframes(out), n)
    print(tag, 'phone video kb/s', vb, round(out.stat().st_size / 1e6, 2), 'MB', flush=True)
    run([sys.executable, HERE / 'qa_draft.py', out, '-', A0 / f'qa/{tag}_手机预览_tech.json', '--expect', str(n)], heavy=True)


def sync_qa():
    """5 random cuts: picture (delivered v2p frame vs the uncut render at the mapped v2 frame) and sound (voice at the
    join vs the v2 voice at the mapped time: normalised correlation at lag 0 and best lag); 5 random 1.1x frames"""
    import v2_timeline as TL
    import mix as M
    cuts = TL.cut_list()['cuts']
    keep = TL.kept_frames()
    pos = {f: i for i, f in enumerate(keep)}
    ref = A0 / 'work/cand_v1b_video.mp4'

    def gray(path, f):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-ss', f'{(f - 0.5) / FPS:.6f}', '-i', str(path), '-frames:v', '1',
                              '-vf', 'scale=270:480:flags=area,format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(480, 270).astype(float)

    def psnr(a, b):
        m = ((a - b) ** 2).mean()
        return 99.0 if m == 0 else round(float(10 * np.log10(255 ** 2 / m)), 1)
    v, ins, _ = M.voice_and_inserts()
    vc = TL.cut_audio(v, cuts)
    random.seed(20)
    out = dict(cuts=[], speed=[])
    cand = DEL / f"{V['v2p']['name']}_无BGM.mp4"
    for c in random.sample(cuts, 5):
        f0, f1 = c['frames']
        j = pos[f1]
        pic = dict(after=psnr(gray(cand, j), gray(ref, f1)), before=psnr(gray(cand, j - 1), gray(ref, f0 - 1)))
        a = vc[0, (j * SPF) - 9600:(j * SPF) + 9600]
        b = v[0, (f1 * SPF) - 9600 - (f1 - f0) * SPF * 0:(f1 * SPF) + 9600]
        # compare the 0.2 s after the join (identical samples expected) and search +-40 ms for the best lag
        A_ = vc[0, j * SPF + 600:j * SPF + 600 + 9600]
        best = max(range(-1920, 1921, 16), key=lambda L: float(np.dot(A_, v[0, f1 * SPF + 600 + L:f1 * SPF + 600 + L + 9600])))
        B0 = v[0, f1 * SPF + 600:f1 * SPF + 600 + 9600]
        corr0 = float(np.dot(A_, B0) / (np.linalg.norm(A_) * np.linalg.norm(B0) + 1e-12))
        out['cuts'].append(dict(cut_v2=[f0, f1], shot=c['shot'], words=c['prev_word'] + '|' + c['next_word'], v2p_frame=j, picture_psnr=pic,
                                audio_corr_lag0=round(corr0, 4), audio_best_lag_ms=round(best / 48, 2)))
    sel = load_json(V['v2p110']['frames'])['v2_frames']
    c110 = DEL / f"{V['v2p110']['name']}_无BGM.mp4"
    for k in sorted(random.sample(range(len(sel)), 5)):
        out['speed'].append(dict(frame=k, v2_frame=sel[k], psnr=psnr(gray(c110, k), gray(ref, sel[k]))))
    ins = {key: (v0, v1) for key, (v0, v1, _, _) in insert_frames().items()}
    out['cuts_inside_inserts'] = [c['frames'] for c in cuts if any(c['frames'][0] < b and c['frames'][1] > a for a, b in ins.values())]
    save_json(A0 / 'qa/v2_sync.json', out)
    print(json.dumps(out, ensure_ascii=False)[:900])


def decode_mono(p):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-i', str(p), '-vn', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def env_db(x, starts, win):
    """RMS level (dB) of x in windows [s, s + win) for every start s"""
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    s = np.clip(np.asarray(starts, int), 0, len(x) - win)
    return 10 * np.log10((c[s + win] - c[s]) / win + 1e-12)


def best_lag(a, b, max_lag):
    """lag L (in hops) maximising corr(a[i], b[i - L]); positive L = a (delivered) is late"""
    a = np.clip(a, a.max() - 50, None)
    b = np.clip(b, b.max() - 50, None)
    a, b = a - a.mean(), b - b.mean()
    score = {}
    for L in range(-max_lag, max_lag + 1):
        x, y = (a[L:], b[:len(b) - L]) if L >= 0 else (a[:L], b[-L:])
        n = min(len(x), len(y))
        score[L] = float(np.dot(x[:n], y[:n]) / (np.linalg.norm(x[:n]) * np.linalg.norm(y[:n]) + 1e-12))
    L = max(score, key=score.get)
    frac = 0.0
    if -max_lag < L < max_lag:                                  # parabolic refinement
        y0, y1, y2 = score[L - 1], score[L], score[L + 1]
        den = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / den if den else 0.0
    return L + frac, score[L]


def av_sync_delivered():
    """sound-vs-picture timing measured on the delivered 无BGM files. Reference = the dialogue (voice + inserts) placed where the
    picture needs it: v2p sample s <-> cut dialogue sample s; v2p110 output time t <-> v2p time 1.1 t (picture frame k shows v2p
    frame round(1.1 k)). Level envelopes (10 ms windows, 2.5 ms hop) are cross-correlated over +-150 ms, globally and in 3 s
    windows around the 5 sampled cuts / frames of v2_sync.json. Positive lag = delivered sound late."""
    import v2_timeline as TL
    import mix as M
    cuts = TL.cut_list()['cuts']
    v, ins, _ = M.voice_and_inserts()
    ref = (TL.cut_audio(v, cuts) + TL.cut_audio(ins, cuts)).mean(0)
    del v, ins
    rep = load_json(A0 / 'qa/v2_sync.json')
    hop, win = int(0.0025 * SR), int(0.010 * SR)
    res = {}
    for tag, speed, marks in (('v2p', 1.0, [c['v2p_frame'] for c in rep['cuts']]),
                              ('v2p110', TL.SPEED, [s['frame'] for s in rep['speed']])):
        d = decode_mono(DEL / f"{V[tag]['name']}_无BGM.mp4")
        n = len(d) // hop - 8
        a = env_db(d, np.arange(n) * hop, win)
        b = env_db(ref, np.round(np.arange(n) * hop * speed).astype(int), int(round(win * speed)))
        g, c = best_lag(a, b, 60)
        loc = []
        for f in marks:
            i = int(f / FPS * SR / hop)
            s0, s1 = max(0, i - 600), min(n, i + 600)
            L, cc = best_lag(a[s0:s1], b[s0:s1], 60)
            loc.append(dict(frame=int(f), lag_ms=round(L * hop / SR * 1000, 1), corr=round(cc, 3)))
        res[tag] = dict(global_lag_ms=round(g * hop / SR * 1000, 1), global_corr=round(c, 3), local=loc,
                        delivered_s=round(len(d) / SR, 3))
        print(tag, json.dumps(res[tag], ensure_ascii=False), flush=True)
    rep['av_sync_delivered'] = dict(method=av_sync_delivered.__doc__.split('. ')[0], results=res)
    save_json(A0 / 'qa/v2_sync.json', rep)


def main():
    step = sys.argv[1]
    if step == 'syncqa':
        return sync_qa()
    if step == 'avsync':
        return av_sync_delivered()
    if step == 'phone':
        for tag, d in V.items():
            make_phone(tag, d)
        return
    for s in (['render', 'audio', 'package', 'qa'] if step == 'all' else [step]):
        if s == 'render':
            run([sys.executable, HERE / 'v2_timeline.py', 'frames'])
            run([sys.executable, HERE / 'v2_timeline.py', 'captions'])
            for tag in V:
                run([sys.executable, HERE / 'a0render.py', 'video', A0 / f'work/cand_{tag}_video.mp4', '--workers', '2', '--crf', '16',
                     '--frames-file', V[tag]['frames']], heavy=True)
        elif s == 'audio':
            run([sys.executable, HERE / 'v2_timeline.py', 'audio'], heavy=True)
        elif s == 'package':
            for tag, d in V.items():
                n = load_json(d['frames'])['n']
                vid = A0 / f'work/cand_{tag}_video.mp4'
                mux(vid, AUDIO / f'mix_{tag}_bgm1.wav', DEL / f"{d['name']}_含BGM.mp4", n)
                mux(vid, AUDIO / f'mix_{tag}_nobgm.wav', DEL / f"{d['name']}_无BGM.mp4", n)
                for ext in ('srt', 'ass'):
                    (DEL / f"{d['name']}.{ext}").write_bytes((CAPS / f'captions_{tag}_burn.{ext}').read_bytes())
                make_phone(tag, d)
                run([sys.executable, HERE / 'contact_sheet.py', DEL / f"{d['name']}_含BGM.mp4", DEL / f"{d['name']}_联系表_每秒1帧.jpg"], heavy=True)
        elif s == 'qa':
            for tag, d in V.items():
                n = load_json(d['frames'])['n']
                for kind in ('含BGM', '无BGM'):
                    run([sys.executable, HERE / 'qa_draft.py', DEL / f"{d['name']}_{kind}.mp4", '-', A0 / f'qa/{tag}_{kind}_tech.json',
                         '--expect', str(n)], heavy=True)
            run([sys.executable, Path(__file__).resolve(), 'syncqa'], heavy=True)     # loads the voice arrays: under the lock
            run([sys.executable, Path(__file__).resolve(), 'avsync'], heavy=True)


if __name__ == '__main__':
    main()
