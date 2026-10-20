#!/usr/bin/env python3
"""fusion-word-behind — build entry (see ../README.md).

  python3 build.py prep --plate PLATE.mp4 --voice VOICE.wav     # plate frames, faces, hands, person mattes
  python3 build.py stills --times 0.2 0.9 1.4 4.5
  python3 build.py render --out DIR
Inputs are the video-20 locked master (plate_v2_video.mp4, 1080x1920 30 fps) and its voice stem
(voice_master_48k.wav, same v2 clock); pass them as --plate/--voice or $XM_PLATE/$XM_VOICE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402

PLATE = {'start': 1586, 'end': 1726, 'matte': True, 'faces': True, 'hands': False, 'voice': True, 'bgfill': 24}
PARAMS = {
    'plate_start': PLATE['start'], 'plate_end': PLATE['end'],
    # "它其实就是一个开源的 动效库加音效库加风格包"; 开源 is said at 53.947 s on the v2 clock = 1.08 s into the shot
    'text': '开源', 'at': 1.08, 'color': '#2448C9', 'size': 400, 'y': 360, 'gap': 150,
}


def cues(shot):
    T = shot['T']
    return [
        {'id': 'reverse_whoosh', 'at': T['at'], 'align': 'end', 'gain_db': -12, 'params': {'dur': 0.45, 'bright': 0.4}},
        {'id': 'impact_soft', 'at': T['at'], 'gain_db': -11, 'params': {'pitch': -4, 'bright': 0.35, 'dur': 0.6}},
        {'id': 'pluck', 'at': T['at'] + 0.02, 'gain_db': -16, 'params': {'note': 'D5', 'space': 0.4, 'bright': 0.4}},
    ]

SHOT = {
    'name': 'fusion-word-behind',
    'component': 'word_behind',
    'dur': (PLATE['end'] - PLATE['start']) / 30, 'fps': 30, 'size': (1080, 1920),
    'plate': PLATE,
    'params': PARAMS,
    'fonts': {'serif': [900]},
    'glyphs': {'serif': PARAMS['text']},
    'post': {'vignette': {'opaque': 0.0, 'overlay': 0.0}, 'grain': {'opaque': 0.0, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 0,
    'sfx': cues,
    'thumb_t': 3.6,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
