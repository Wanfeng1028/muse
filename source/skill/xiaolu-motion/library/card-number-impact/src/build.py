#!/usr/bin/env python3
"""card-number-impact · 数字冲击 — build entry (see ../README.md).

  python3 build.py stills --times 0.9 1.5 1.62 3.5
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {'value': 90, 'unit': '%', 'label': '剪辑时间省下', 'sub': 'TIME SAVED ON EDITING', 't_count': 0.35, 't_hit': 1.6}

SHOT = {
    'name': 'card-number-impact',
    'component': 'number_impact',
    'dur': 4.0, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'sans': [500, 700, 900]},
    'glyphs': {'sans': '0123456789' + PARAMS['unit'] + PARAMS['label'] + PARAMS['sub']},
    'colors': {'bg': '#050304', 'bg_glow': '#050304'},
    'post': {'vignette': {'opaque': 0.4, 'overlay': 0.0}, 'grain': {'opaque': 1.8, 'overlay': 0.0},
             'bloom': [1.3, 1.2], 'bloom_sigma': [5.0, 14.0], 'shutter': 0.55, 'mb_max': 12},
    'enc_noise': 2,
    'thumb_t': 3.4,
    'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
