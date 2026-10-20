"""Pause-tightening cut list on the v2 timeline (user feedback 2026-09-27: 「没有完全把我的口播的一些气口…停顿…剪掉，显得有一点拖沓」).
Deviation from the SOP (no patching of a finished cut) accepted by the coordinator for budget reasons; this list is the
reproducible authority for the v2 candidates.

Rules (coordinator 2026-09-27):
  * a pause = silence between two pause-delimited phrases of the locked voice (words_v2.phrases, 10 ms RMS > -66 dBFS)
    longer than 0.25 s; it is shortened to ~0.15 s inside a sentence and ~0.22 s after a sentence end (。？！):
    keep >= 0.07 s after the last word and >= 0.08 s before the next onset (the extra 0.07 s of a sentence end is split
    between both sides); cut edges snap inwards to frame boundaries (at least one whole frame removed).
  * never cut: inside the three inserts (and 0.1 s around their edges), the hook (shot 1, 0-2.4 s), the IP intro
    (shot 6), or while a transition / animation event is running. Protected spans come from every shot's meta.json
    (keyword_animations / keyword_events / swipes / no_live_footage), every sfx cue (motion cues cover their movement),
    A0's own animation windows and the step-bar changes. A protected span inside a pause shrinks the cut to the
    largest free part (less is cut, the pause is never skipped).
  * risk: how much the two frames that become neighbours differ, relative to the normal frame-to-frame change there
    (jump ratio), plus distance to the nearest protected span.
usage: python3 pause_cuts.py        (one sequential decode of the candidate at 270x480 -> run under with_heavy_lock.py)
Output: 05_visual/build/a0/cuts/pause_cut_list_v2.json, pause_cut_risk_top10.jpg
"""
import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa

OUT = A0 / 'cuts'
VIDEO = Path(sys.argv[1]) if len(sys.argv) > 1 else VP / '07_delivery/视频20_候选_v1_无BGM.mp4'
MIN_GAP, MID_KEEP, END_KEEP, TAIL, HEAD = 0.25, 0.15, 0.22, 0.07, 0.08
SENT_END = '。？！'


def protected_spans():
    spans = [(0.0, 2.40, 'shot 1 hook'), (752 / FPS, 831 / FPS, 'shot 6 ip_intro')]
    for key, (v0, v1, f, df0) in insert_frames().items():
        spans.append((v0 / FPS - 0.10, v1 / FPS + 0.10, f'insert {key}'))
    # A0 animation windows and step-bar changes (a0shots / a0render)
    for a, b, why in [(19.20, 19.50, 'shot 3 stickers out'), (20.25, 20.65, 'shot 4 ticket drop'), (21.80, 22.10, 'shot 4 ticket out'),
                      (22.80, 23.30, 'shot 5 card in'), (24.80, 25.10, 'shot 5 card out'), (64.70, 65.45, 'shot 12 slam + step bar in'),
                      (65.45, 65.76, 'shot 12 out'), (65.85, 66.10, 'step bar -> 1'), (79.28, 79.50, 'step bar -> 2'),
                      (97.97, 98.20, 'step bar -> 3'), (113.25, 113.48, 'step bar -> 4'), (132.18, 132.48, 'step bar out'),
                      (132.95, 133.50, 'shot 17 PiP in'), (133.05, 134.65, 'shot 17 recap cards'), (134.57, 135.12, 'shot 17 PiP out'),
                      (135.40, 135.85, 'shot 17 4步 slam'), (136.90, 137.30, 'shot 17 out'), (146.40, 146.75, 'shot 19 v1.0'),
                      (149.95, 150.35, 'shot 19 v1.0 out'), (154.85, 156.10, 'shot 19 curve'), (156.10, 156.90, 'shot 20 photo card in'),
                      (160.70, 161.00, 'shot 20 wink')]:
        spans.append((a, b, why))
    # every sfx cue (all sessions): motion cues protect their movement, others a short event window
    for c in load_json(A0 / 'work/sfx_merged_cand_v1.json'):
        t = float(c['t'])
        dur = float((c.get('params') or {}).get('dur', c.get('dur', 0)) or 0)
        if c['id'] in ('whoosh_fast', 'whoosh_mid', 'whoosh_slow', 'push'):
            spans.append((t - 0.12, t + max(0.55 if c['id'] != 'whoosh_slow' else 1.0, dur), f"{c.get('source')} {c['id']}"))
        elif c['id'] in ('reverse_whoosh', 'riser') or c.get('align') == 'end':
            spans.append((t - max(0.3, dur), t + 0.2, f"{c.get('source')} {c['id']}"))
        else:
            spans.append((t - 0.10, t + 0.22, f"{c.get('source')} {c['id']}"))
    # every timed event in the shot metas
    for sid, a, b, owner in SHOTS:
        mp = SHOTS_DIR / f's{sid}' / 'meta.json'
        if owner == 'A0' or not mp.exists():
            continue
        m = load_json(mp)

        def walk(x, tag):
            if isinstance(x, dict):
                if 'start_frame' in x and 'frames' in x and isinstance(x['frames'], (int, float)):
                    spans.append((x['start_frame'] / FPS - 0.1, (x['start_frame'] + x['frames']) / FPS + 0.1, f's{sid} {tag}'))
                elif 'frames' in x and isinstance(x['frames'], list) and len(x['frames']) == 2 and all(isinstance(v, (int, float)) for v in x['frames']):
                    spans.append((x['frames'][0] / FPS - 0.1, x['frames'][1] / FPS + 0.1, f's{sid} {tag}'))
                elif isinstance(x.get('f0'), (int, float)) and isinstance(x.get('f1'), (int, float)):      # A3 style
                    spans.append((x['f0'] / FPS - 0.1, x['f1'] / FPS + 0.1, f"s{sid} {x.get('name', tag)}"))
                elif isinstance(x.get('t0'), (int, float)) and isinstance(x.get('t1'), (int, float)):
                    spans.append((x['t0'] - 0.1, x['t1'] + 0.1, f"s{sid} {x.get('name', tag)}"))
                for k, v in x.items():
                    walk(v, f'{tag}.{k}' if tag else k)
            elif isinstance(x, list):
                for v in x:
                    walk(v, tag)
        for key in ('keyword_animations', 'swipes', 'no_live_footage', 'transitions', 'events'):
            if key in m:
                walk(m[key], key)
        for key in ('keyword_events',):
            for k, v in (m.get(key) or {}).items():
                if isinstance(v, (int, float)):
                    spans.append((v - 0.10, v + 0.35, f's{sid} {k}'))
                elif isinstance(v, list) and len(v) == 2:
                    spans.append((v[0] - 0.10, v[1] + 0.10, f's{sid} {k}'))
    return spans


def subtract(a, b, spans):
    """free parts of [a, b) after removing the spans -> list of (x0, x1, touched_spans)"""
    free = [(a, b)]
    hit = []
    for s0, s1, why in spans:
        if s1 <= a or s0 >= b:
            continue
        hit.append(why)
        nxt = []
        for x0, x1 in free:
            if s1 <= x0 or s0 >= x1:
                nxt.append((x0, x1))
                continue
            if s0 > x0:
                nxt.append((x0, s0))
            if s1 < x1:
                nxt.append((s1, x1))
        free = nxt
    return free, hit


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    W2 = load_json(CAPS / 'words_v2.json')
    PH = W2['phrases']
    U = W2['units']
    last_in_clause = {}
    for s in W2['sentences']:
        last_in_clause[s['units'][-1]] = s['punct']
    spans = protected_spans()
    cuts = []
    for i in range(len(PH) - 1):
        e0, s1 = PH[i]['e'], PH[i + 1]['s']
        gap = s1 - e0
        if gap <= MIN_GAP:
            continue
        us = [u for u in U if u['phrase'] == i]
        un = [u for u in U if u['phrase'] == i + 1]
        if not us or not un:
            continue                                            # breath / noise phrase without words: leave it
        prev_u, next_u = us[-1], un[0]
        kind = 'sentence_end' if last_in_clause.get(prev_u['i'], '') in SENT_END else 'mid'
        keep = END_KEEP if kind == 'sentence_end' else MID_KEEP
        extra = (keep - (TAIL + HEAD)) / 2
        a, b = e0 + TAIL + extra, s1 - HEAD - extra
        if b - a <= 0:
            continue
        free, hit = subtract(a, b, spans)
        if not free:
            cuts.append(dict(skipped=True, reason='fully protected', gap_s=round(gap, 3), at=round(e0, 3), protected_by=hit[:4]))
            continue
        x0, x1 = max(free, key=lambda p: p[1] - p[0])
        f0, f1 = math.ceil(x0 * FPS - 1e-6), math.floor(x1 * FPS + 1e-6)
        if f1 - f0 < 1:
            cuts.append(dict(skipped=True, reason='less than one frame after protection', gap_s=round(gap, 3), at=round(e0, 3),
                             protected_by=hit[:4]))
            continue
        near = min([min(abs(f0 / FPS - s1_), abs(f1 / FPS - s0_)) for s0_, s1_, _ in spans] + [9.9])
        cuts.append(dict(frames=[f0, f1], v2_from=round(f0 / FPS, 3), v2_to=round(f1 / FPS, 3), removed_s=round((f1 - f0) / FPS, 3),
                         shot=shot_at(f0)[0], owner=shot_at(f0)[3], kind=kind, gap_orig_s=round(gap, 3),
                         gap_new_s=round(gap - (f1 - f0) / FPS, 3), prev_word=prev_u['w'], next_word=next_u['w'],
                         reduced_by=hit[:4] if hit else [], nearest_protected_s=round(near, 3)))
    real = [c for c in cuts if not c.get('skipped')]
    # no word may be cut: the raw voice inside every removed span (+ the 7.5 ms each crossfade borrows) stays below
    # the phrase threshold; a span that touches speech is shrunk frame by frame from the side that is loud
    x = read_audio(LOCKED / 'voice_bound_raw_44k.wav', SR_SRC, ch=1)[:, 0]

    def peak_db(f0, f1):
        a, b = int((f0 / FPS - 0.0075) * SR_SRC), int((f1 / FPS + 0.0075) * SR_SRC)
        seg = x[a:b]
        n = len(seg) // 441
        if n == 0:
            return -120.0
        return float(20 * np.log10(np.sqrt((seg[:n * 441].reshape(n, 441) ** 2).mean(1)).max() + 1e-12))
    for c in real:
        f0, f1 = c['frames']
        while f1 - f0 >= 1 and peak_db(f0, f1) >= -66.0:
            if peak_db(f0, f0 + 1) >= peak_db(f1 - 1, f1):
                f0 += 1
            else:
                f1 -= 1
        c['frames'] = [f0, f1]
        c['max_voice_db'] = round(peak_db(f0, f1), 1) if f1 > f0 else None
    real = [c for c in real if c['frames'][1] > c['frames'][0]]
    for c in real:
        f0, f1 = c['frames']
        c.update(v2_from=round(f0 / FPS, 3), v2_to=round(f1 / FPS, 3), removed_s=round((f1 - f0) / FPS, 3),
                 gap_new_s=round(c['gap_orig_s'] - (f1 - f0) / FPS, 3))
    # visual jump at every cut: frames f0-1 (last kept) vs f1 (next kept), against the normal change f0-2 -> f0-1
    need = set()
    for c in real:
        f0, f1 = c['frames']
        need |= {f0 - 2, f0 - 1, f1, f1 + 1}
    small = {}
    r = RawReader(VIDEO, pix='gray', w=270, h=480, vf_extra='scale=270:480:flags=area')
    for f in range(TOTAL):
        im = r.read()
        if im is None:
            break
        if f in need:
            small[f] = im.astype(np.float32)
    r.close()
    for c in real:
        f0, f1 = c['frames']
        jump = float(np.abs(small[f0 - 1] - small[f1]).mean())
        base = max(0.5, float(np.abs(small[f0 - 2] - small[f0 - 1]).mean()), float(np.abs(small[f1] - small[f1 + 1]).mean()))
        c['jump'] = round(jump, 2)
        c['jump_ratio'] = round(jump / base, 2)
        score = c['jump_ratio'] + (2.0 if c['nearest_protected_s'] < 0.15 else 0) + (1.0 if c['owner'] != 'A0' else 0)
        c['risk_score'] = round(score, 2)
        c['risk'] = 'high' if (c['jump_ratio'] > 4 or score > 6) else ('medium' if (c['jump_ratio'] > 2 or score > 3.5) else 'low')
    removed = sum(c['removed_s'] for c in real)
    nf = TOTAL - sum(c['frames'][1] - c['frames'][0] for c in real)
    res = dict(version='v2-pause-1', clock='v2 (4857 frames) -> v2p', rules=__doc__.strip(), source_video=str(VIDEO),
               n_cuts=len(real), removed_s=round(removed, 3), new_frames=nf, new_duration_s=round(nf / FPS, 3),
               skipped=[c for c in cuts if c.get('skipped')], cuts=real,
               risk_counts={k: sum(c['risk'] == k for c in real) for k in ('high', 'medium', 'low')},
               removed_by_shot={s: round(sum(c['removed_s'] for c in real if c['shot'] == s), 3) for s in sorted({c['shot'] for c in real})})
    save_json(OUT / 'pause_cut_list_v2.json', res)
    # top-10 risk sheet: last kept frame | next kept frame
    top = sorted(real, key=lambda c: -c['risk_score'])[:10]
    F = ImageFont.truetype(str(FONTS / 'SourceHanSansSC-Medium.otf'), 15)
    tw, th = 180, 320
    sheet = Image.new('RGB', (5 * (2 * tw + 14) + 6, 2 * (th + 44) + 6), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    r = RawReader(VIDEO, pix='rgb24', w=tw, h=th, vf_extra=f'scale={tw}:{th}:flags=area')
    want = {}
    for c in top:
        want[c['frames'][0] - 1] = None
        want[c['frames'][1]] = None
    for f in range(TOTAL):
        im = r.read()
        if im is None:
            break
        if f in want:
            want[f] = Image.fromarray(im)
    r.close()
    for n, c in enumerate(top):
        x, y = 6 + (n % 5) * (2 * tw + 14), 6 + (n // 5) * (th + 44)
        sheet.paste(want[c['frames'][0] - 1], (x, y + 40))
        sheet.paste(want[c['frames'][1]], (x + tw + 4, y + 40))
        d.text((x, y), f"#{n + 1} 镜{c['shot']} {fmt(c['v2_from'])}-{fmt(c['v2_to'])} 删{c['removed_s']:.2f}s", font=F, fill=(255, 214, 10))
        d.text((x, y + 19), f"{c['prev_word']}|{c['next_word']} 跳变×{c['jump_ratio']} {c['risk']}", font=F, fill=(230, 230, 230))
    sheet.save(OUT / 'pause_cut_risk_top10.jpg', quality=85)
    print(json.dumps({k: res[k] for k in ('n_cuts', 'removed_s', 'new_frames', 'new_duration_s', 'risk_counts')}, ensure_ascii=False))
    print('skipped', len(res['skipped']))


if __name__ == '__main__':
    main()
