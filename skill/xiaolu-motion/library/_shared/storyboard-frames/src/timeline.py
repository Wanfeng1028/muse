"""Storyboard v2 timeline: rough cut (cut_plan_v1.json, read-only) + three finished-demo inserts after
"vlog" / "做科普" / "不露脸的视频".

The inserts split kept segment 1 at three source frames that sit in the silence between words
(checked on 01_transcript/source_env10ms_db.npy, see storyboard.md 0.1). The presenter's audio / video are not
shortened; each insert only adds its own length, so every later time = rough time + inserted length.

v2 time t -> ('max', seg, src_frame) or ('insert', key, frame_in_insert)
"""
import json
import os
from pathlib import Path

VP = Path(os.environ.get("XM_VIDEO_PROJECT_ROOT", "."))  # your own video-production project root
PLAN = VP / '02_cut_review/cut_plan_v1.json'
SRC = Path(os.environ.get("XM_RAW_FOOTAGE", "raw_footage.mov"))
WORDS = VP / '01_transcript/source_words_pass1.tsv'
DEMOS = Path(os.environ.get("XM_DEMOS_DIR", "../demos"))
FPS = 30

_plan = json.loads(PLAN.read_text())
SEGMENTS = _plan['segments']

# cut frames in the SOURCE (all inside segment 1, src frames 20..405)
#   C1 5.233 s  between "vlog"(ends ~5.09) and "做"(starts 5.36)      env -84 dB
#   C2 6.133 s  between "普"(ends ~6.04) and "或者"(starts 6.22)       env -87 dB
#   C3 7.800 s  between "视频"(ends ~7.62) and "但是"(starts 7.92)     env -95 dB
# key, source cut frame, frames inserted, demo file, demo in (s), what plays
INSERTS = [
    ('vlog', 157, 90, DEMOS / 'vlog/vlog_demo.mp4', 0.30,
     'vlog_demo.mp4 0.30–3.30 s：「我的一天」剪报标题逐字弹出、红章砸下、翻页进健身房照片、10:58 时间卡'),
    ('kepu', 184, 100, DEMOS / 'kepu/kepu_demo.mp4', 14.10,
     'kepu_demo.mp4 14.10–17.43 s：「所以抬头看，满天都是被散射开的蓝光」，房间变蓝天，「蓝光」大字亮起'),
    ('faceless', 234, 87, DEMOS / 'faceless/faceless_demo.mp4', 0.50,
     'faceless_demo.mp4 0.50–3.40 s：「想快速提升剪辑网感，就练四件事」，「网感」大字弹落、四个方框弹出，翻页开始'),
]
INS = {k: dict(cut=c, n=n, file=f, t0=t0, note=note) for k, c, n, f, t0, note in INSERTS}


def _build():
    """list of pieces: dict(kind, v0, v1 (frames, v2 timeline), plus source info)"""
    pieces, v = [], 0
    for s in SEGMENTS:
        a, b = s['src_in_frame'], s['src_out_frame']
        cuts = [(ins[1], ins) for ins in INSERTS if a < ins[1] < b]
        for c, ins in cuts:
            pieces.append(dict(kind='max', seg=s['seg'], src0=a, src1=c, v0=v, v1=v + (c - a)))
            v += c - a
            pieces.append(dict(kind='insert', key=ins[0], n=ins[2], note=ins[5], v0=v, v1=v + ins[2]))
            v += ins[2]
            a = c
        pieces.append(dict(kind='max', seg=s['seg'], src0=a, src1=b, v0=v, v1=v + (b - a)))
        v += b - a
    return pieces, v


PIECES, TOTAL_FRAMES = _build()
TOTAL_S = TOTAL_FRAMES / FPS


def v2_to_src(t):
    f = round(t * FPS)
    for p in PIECES:
        if p['v0'] <= f < p['v1']:
            if p['kind'] == 'max':
                return 'max', p['seg'], p['src0'] + (f - p['v0'])
            return 'insert', p['key'], f - p['v0']
    raise ValueError(f'v2 time {t} outside the cut')


def src_to_v2(ts):
    """source seconds -> v2 seconds (None if the source time was cut out)"""
    f = ts * FPS
    for p in PIECES:
        if p['kind'] == 'max' and p['src0'] <= f < p['src1']:
            return (p['v0'] + (f - p['src0'])) / FPS
    return None


def rough_to_v2(tr):
    """rough-cut seconds (cut_plan_v1) -> v2 seconds"""
    rf = round(tr * FPS)          # nearest frame, so 7.1333 (= rough frame 214, the C3 cut) counts as after C3
    add = sum(n for key, c, n, *_ in INSERTS if rf >= c - SEGMENTS[0]['src_in_frame'])
    return tr + add / FPS


def insert_range(key):
    p = [p for p in PIECES if p['kind'] == 'insert' and p['key'] == key][0]
    return p['v0'] / FPS, p['v1'] / FPS


def words():
    out = []
    for line in WORDS.read_text().splitlines()[1:]:
        s, e, p, w = line.split('\t')
        vs, ve = src_to_v2(float(s)), src_to_v2(float(e) - 0.001)
        if vs is not None:
            out.append((vs, ve, w))
    return out


def fmt(t):
    m, s = divmod(t, 60)
    return f'{int(m)}:{s:05.2f}'


# keyframes of the presenter's footage, given in ROUGH time (so they survive insert-length changes)
KEY_ROUGH = {
    '1': 2.20,         # 这样的视频 lands on the 6th flash (v1 frame time)
    '4': 12.0667,      # 开源 stamped
    '7': 23.50,        # vlog explanation, 心情 (v1 frame time)
    '9': 33.90,        # 不想露脸 -> PiP closes (v1 frame time)
    '10a': 42.1167,    # 同一套东西: three demo frames flying into the paper box
    '10b': 47.9667,    # 风格包: third tray lit
    '11': 50.1167,     # 丢给
    '13a': 66.3667,    # typing the third message
    '13b': 68.6667,    # 确认没有问题 -> stamp
    '14a': 82.4667,    # 挑一个
    '14b': 85.8667,    # 以这个风格为标准: brush
    '15': 97.7667,     # 怎么转场 / 配什么音效
    '16a': 116.4667,   # 字压到脸上: red box + cross
    '16b': 117.4667,   # slid to the safe band
    '18': 133.4667,    # 可以全部交给
}
# insert keyframes: frame index inside the insert
KEY_INSERT = {'I1': ('vlog', 45), 'I2': ('kepu', 90), 'I3': ('faceless', 81)}

KEYFRAMES = {k: rough_to_v2(t) for k, t in KEY_ROUGH.items()}
for k, (key, fi) in KEY_INSERT.items():
    KEYFRAMES[k] = insert_range(key)[0] + fi / FPS

# v1 frames reused on the board (v1 rough time)
V1_REUSE = {3: 9.80, 12: 56.10, 20: 151.80}

if __name__ == '__main__':
    for key in INS:
        a, b = insert_range(key)
        print(f'INSERT {key:8s} v2 {fmt(a)}–{fmt(b)}  ({b - a:.3f} s)  {INS[key]["note"]}')
    print(f'total {TOTAL_FRAMES} frames = {TOTAL_S:.3f} s = {fmt(TOTAL_S)}')
    for k, t in sorted(KEYFRAMES.items(), key=lambda kv: kv[1]):
        print(k, fmt(t), v2_to_src(t))
