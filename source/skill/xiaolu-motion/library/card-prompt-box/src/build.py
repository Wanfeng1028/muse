#!/usr/bin/env python3
"""card-prompt-box · 输入框下指令 — build entry (see ../README.md).

  python3 build.py stills --times 1.0 2.4 2.95 4.5
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {
    'text': '把这段口播剪成竖屏短视频',
    'hint': '描述你想要的视频…',
    'items': [['成片', '00:58'], ['字幕', '83 条'], ['音效', '12 个']],
    't_type': 0.3, 'cps': 10, 'fly': 0.7, 'beat': 0.4, 'close': 0.55,
}

SHOT = {
    'name': 'card-prompt-box',
    'component': 'prompt_box',
    'dur': 5.0, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'sans': [500, 700]},
    'glyphs': {'sans': PARAMS['text'] + PARAMS['hint'] + ''.join(a + b for a, b in PARAMS['items'])},
    'colors': {'bg': '#E6EAF0', 'bg_glow': '#E6EAF0'},
    'post': {'vignette': {'opaque': 0.12, 'overlay': 0.0}, 'grain': {'opaque': 1.4, 'overlay': 0.0},
             'bloom': [0.5, 0.4], 'bloom_sigma': [5.0, 10.0], 'shutter': 0.5, 'mb_max': 12},
    'enc_noise': 1,
    'thumb_t': 4.6,
    'sound_setup': sound.setup, 'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
