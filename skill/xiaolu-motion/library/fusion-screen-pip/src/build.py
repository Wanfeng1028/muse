#!/usr/bin/env python3
"""fusion-screen-pip — build entry (see ../README.md).

  python3 build.py prep --plate PLATE.mp4 --voice VOICE.wav     # plate frames, faces, hands, person mattes
  python3 build.py stills --times 0.8 1.25 1.7 3.8
  python3 build.py render --out DIR
Inputs are the video-20 locked master (plate_v2_video.mp4, 1080x1920 30 fps) and its voice stem
(voice_master_48k.wav, same v2 clock); pass them as --plate/--voice or $XM_PLATE/$XM_VOICE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402

PLATE = {'start': 3477, 'end': 3597, 'matte': False, 'faces': True, 'hands': False, 'voice': True}
PARAMS = {
    'plate_start': PLATE['start'], 'plate_end': PLATE['end'],
    # "完成前三步之后 Agent会进行视频的剪辑": shrink on the first clause, fly in as "Agent…" starts (1.6 s)
    'pip': [300, 400], 't_shrink': [0.45, 1.15], 't_fly': [1.38, 2.02],
    'title': '口播剪辑 · 自动成片', 'tasks': ['识别口播', '生成字幕', '排版动效', '混音配乐'],
}


def cues(shot):
    T = shot['T']
    out = [
        {'id': 'whoosh_mid', 'at': T['shrink'][0], 'align': 'motion', 'gain_db': -12, 'params': {'dur': 0.75, 'pitch': -2, 'travel': 0.0}},
        {'id': 'pop_soft', 'at': T['shrink'][1], 'gain_db': -10, 'params': {'pitch': -3}},
        {'id': 'whoosh_fast', 'at': T['fly'][0], 'align': 'motion', 'gain_db': -9, 'pan': [0.0, 0.6], 'params': {'dur': 0.5, 'travel': 0.5}},
        {'id': 'land', 'at': T['dock'], 'gain_db': -5, 'pan': 0.5},
    ]
    for i, t in enumerate(T['tasks']):
        out.append({'id': 'ui_click', 'at': t, 'gain_db': -10, 'pan': 0.15, 'params': {'pitch': 2 * i}})
    for i, t in enumerate(T['clips']):
        out.append({'id': 'tick', 'at': t, 'gain_db': -12, 'pan': -0.1, 'params': {'pitch': 3 + i}})
    return out

SHOT = {
    'name': 'fusion-screen-pip',
    'component': 'screen_pip',
    'dur': (PLATE['end'] - PLATE['start']) / 30, 'fps': 30, 'size': (1080, 1920),
    'plate': PLATE,
    'params': PARAMS,
    'fonts': {'sans': [500, 700]},
    'glyphs': {'sans': PARAMS['title'] + ''.join(PARAMS['tasks']) + '任务素材字幕动效音效导出会进行视频的剪辑'},
    'post': {'vignette': {'opaque': 0.0, 'overlay': 0.0}, 'grain': {'opaque': 0.0, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 0,
    'sfx': cues,
    'thumb_t': 3.6,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
