"""guidechar.py - does a key-coloured guide character keep moving while the rest of the frame is still? (T11)

Frames at --fps (default 10), scaled to width 320, compared with the previous frame
(grey diff > 20 = changed pixel, the density.py definition). The key layer is every pixel
within --tol (RGB Euclidean) of --key, dilated by 3 px. Per frame pair:
  present      key layer >= --min-px pixels
  key_moving   changed pixels inside the key layer >= --min-px
  rest_still   changed pixels outside the key layer < 0.2 % of the frame
Outputs: present_share, key_moving_share, rest_still_share, and
fill_share = frames where rest is still AND the key layer moves / frames where rest is still.

Limits: the key layer is a colour, not an identity - any element of that colour counts
(labels, chapter bars); confirm on a contact sheet. A character with no distinctive colour
(C15's white-and-line mascot) cannot be measured this way.

--selftest: synthetic clips with known answers (positive: still page + moving key square;
negative: no key colour; control: a key square that never moves).
"""
import argparse, json, subprocess, sys
import numpy as np

W = 320


def frames(video, fps):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                            'stream=width,height', '-of', 'csv=p=0', video], capture_output=True, text=True).stdout
    w, h = [int(v) for v in probe.strip().split(',')[:2]]
    H = int(round(h * W / w / 2)) * 2
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vf', f'fps={fps},scale={W}:{H}',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)


def dilate(m, r=3):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def analyse(fr, key, tol, min_px, fps):
    key = np.array(key, float)
    n = len(fr) - 1
    area = fr.shape[1] * fr.shape[2]
    pres = mov = still = fill = 0
    for i in range(1, len(fr)):
        a, b = fr[i - 1].astype(float), fr[i].astype(float)
        m = np.linalg.norm(b - key, axis=2) < tol
        m = dilate(m | (np.linalg.norm(a - key, axis=2) < tol))
        ch = np.abs(b.mean(2) - a.mean(2)) > 20
        p = m.sum() >= min_px
        km = p and (ch & m).sum() >= min_px
        rs = (ch & ~m).sum() < 0.002 * area
        pres += p; mov += km; still += rs; fill += (rs and km)
    return {'frames': n, 'fps': fps, 'present_share': round(pres / n, 3), 'key_moving_share': round(mov / n, 3),
            'rest_still_share': round(still / n, 3), 'fill_share': round(fill / still, 3) if still else None}


def synth(kind, n=60, H=180):
    fr = np.full((n, H, W, 3), 235, np.uint8)
    fr[:, 20:40, 20:200] = 60  # static text block
    for i in range(n):
        if kind == 'moving':
            x = 100 + int(30 * np.sin(i / 3))
            fr[i, 120:150, x:x + 30] = (212, 117, 84)
        elif kind == 'static':
            fr[i, 120:150, 100:130] = (212, 117, 84)
    return fr


def selftest():
    ok = True
    key, tol, mp = (212, 117, 84), 40, 20
    pos = analyse(synth('moving'), key, tol, mp, 10)
    neg = analyse(synth('none'), key, tol, mp, 10)
    sta = analyse(synth('static'), key, tol, mp, 10)
    checks = [('positive fill_share >= 0.9', pos['fill_share'] is not None and pos['fill_share'] >= 0.9),
              ('positive present_share == 1', pos['present_share'] == 1.0),
              ('negative present_share == 0', neg['present_share'] == 0.0),
              ('negative fill_share == 0', neg['fill_share'] == 0.0),
              ('static key fill_share == 0', sta['fill_share'] == 0.0),
              ('static key present_share == 1', sta['present_share'] == 1.0)]
    for name, c in checks:
        print(name, '->', 'ok' if c else 'FAIL'); ok &= c
    # the positive check must fail when the key colour is wrong
    wrong = analyse(synth('moving'), (40, 90, 200), tol, mp, 10)
    c = not (wrong['fill_share'] and wrong['fill_share'] >= 0.9)
    print('wrong key does not pass positive ->', 'ok' if c else 'FAIL'); ok &= c
    print('SELFTEST PASS' if ok else 'SELFTEST FAIL')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video', nargs='?')
    ap.add_argument('--key', default='212,117,84', help='R,G,B of the character')
    ap.add_argument('--tol', type=float, default=40)
    ap.add_argument('--min-px', type=int, default=20)
    ap.add_argument('--fps', type=float, default=10)
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    key = [int(v) for v in a.key.split(',')]
    res = analyse(frames(a.video, a.fps), key, a.tol, a.min_px, a.fps)
    res.update({'video': a.video, 'key': key, 'tol': a.tol, 'min_px': a.min_px})
    print(json.dumps(res, ensure_ascii=False))
    if a.out:
        open(a.out, 'w', encoding='utf8').write(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
