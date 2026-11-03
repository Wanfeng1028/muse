#!/usr/bin/env python3
"""card-movable-type · 活字印刷标题 — build entry (see ../README.md).

  python3 build.py stills --times 0.6 1.4 2.4 3.6
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402  (also puts the repo and audio/ on sys.path)
import sound  # noqa: E402

PARAMS = {
    'text': '开源镜头库',
    'sub': 'OPEN SOURCE · MOTION LIBRARY',
    'label': 'LETTERPRESS',
    't0': 0.15, 'stagger': 0.12, 'rise': 0.62, 'fall': 0.27, 'lock_gap': 0.34,
}

SHOT = {
    'name': 'card-movable-type',
    'component': 'movable_type',
    'dur': 4.4, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'serif': [900], 'sans': [500]},
    'glyphs': {'serif': PARAMS['text'], 'sans': PARAMS['sub'] + PARAMS['label']},
    'colors': {'bg': '#0C0A08', 'bg_glow': '#0C0A08'},
    'post': {'vignette': {'opaque': 0.34, 'overlay': 0.0}, 'grain': {'opaque': 1.5, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 12},
    'enc_noise': 2,
    'thumb_t': 3.7,
    'sound_setup': sound.setup, 'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
