#!/usr/bin/env python3
"""fusion-type-scan — build entry (see ../README.md).

  python3 build.py prep --plate PLATE.mp4 --voice VOICE.wav     # plate frames, faces, hands, person mattes
  python3 build.py stills --times 0.6 2.6 3.3 4.4
  python3 build.py render --out DIR
Inputs are the video-20 locked master (plate_v2_video.mp4, 1080x1920 30 fps) and its voice stem
(voice_master_48k.wav, same v2 clock); pass them as --plate/--voice or $XM_PLATE/$XM_VOICE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402

PLATE = {'start': 3600, 'end': 3738, 'matte': True, 'faces': True, 'hands': False, 'voice': True}
# the forme is set from the video's own script (Chinese characters only); the flip reveals the next passage
TEXT_A = ('不会剪辑也能做出这样的视频如果你想做做科普或者做不露脸的视频但是你又不想剪辑或者说你也不会剪辑'
          '那你可以看看我这个免费的开源工具本期视频的所有工具都已经放入了文档里面我是小鹿一个很会玩的文科生'
          '这是转场多一点字幕做成贴纸时间天气心情这些小卡片它会自己点缀上去而这是科普你讲到的原理会变成图和动画')
TEXT_B = ('第一步确认选题第二步画面风格第三步分镜脚本第四步剪辑成片完成前三步之后会进行视频的剪辑动效音效等包装'
          '完成后它会自己检查一遍如果出现字压到脸上或者说挡住字幕等影响观感的情况就会自己去重新做一遍')
PARAMS = {
    'plate_start': PLATE['start'], 'plate_end': PLATE['end'],
    # "动效音效等包装 完成后它会自己检查一遍": the wall turns to type first, the check-scan runs on the second clause
    'text': TEXT_A, 'text2': TEXT_B, 'phrase': '自己检查一遍', 'phrase_row': 2,
    'reveal': [0.12, 1.0], 'scan': [2.2, 3.9], 'pitch': 128,
}


def cues(shot):
    T = shot['T']
    out = [
        {'id': 'whoosh_slow', 'at': T['reveal'][0], 'gain_db': -16, 'params': {'dur': 1.0, 'pitch': 3, 'travel': 0.0}},
        {'id': 'whoosh_slow', 'at': T['scan'][0], 'gain_db': -13, 'params': {'dur': 1.8, 'pitch': 5, 'travel': 0.0, 'bright': 0.7}},
        {'id': 'shimmer', 'at': T['phraseAt'], 'gain_db': -11, 'params': {'dur': 1.0, 'density': 0.5, 'root': 'D'}},
        {'id': 'pluck', 'at': T['phraseAt'] + 0.05, 'gain_db': -13, 'params': {'note': 'A5', 'space': 0.4}},
    ]
    for i, t in enumerate(T['rowsRevealed']):            # rows of type settling, a dry metal tick each
        out.append({'id': 'tick', 'at': t, 'gain_db': -15, 'pan': 0.3 * ((i % 3) - 1), 'params': {'pitch': -6 + (i % 4), 'bright': 0.4}})
    for i, t in enumerate(T['rowsFlipped']):             # rows turning over under the check-scan
        out.append({'id': 'clack', 'at': t + 0.08, 'gain_db': -16, 'pan': 0.3 * ((i % 3) - 1), 'params': {'pitch': -4 + (i % 5)}})
    return out

SHOT = {
    'name': 'fusion-type-scan',
    'component': 'type_scan',
    'dur': (PLATE['end'] - PLATE['start']) / 30, 'fps': 30, 'size': (1080, 1920),
    'plate': PLATE,
    'params': PARAMS,
    'fonts': {'serif': [900]},
    'glyphs': {'serif': TEXT_A + TEXT_B + PARAMS['phrase']},
    'post': {'vignette': {'opaque': 0.0, 'overlay': 0.0}, 'grain': {'opaque': 0.0, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 0,
    'sfx': cues,
    'thumb_t': 4.3,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
