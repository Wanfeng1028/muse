#!/usr/bin/env python3
"""card-frame-tunnel · 画框隧道 — build entry (see ../README.md).

  python3 build.py stills --times 0.3 1.4 2.4 4.2
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {'title': '下一幕', 'sub': 'ACT II', 'frames': 9, 'twist': 5, 't_push': 0.25, 't_arrive': 3.2}

SHOT = {
    'name': 'card-frame-tunnel',
    'component': 'frame_tunnel',
    'dur': 4.5, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'serif': [900], 'sans': [500]},
    'glyphs': {'serif': PARAMS['title'], 'sans': PARAMS['sub']},
    'colors': {'bg': '#120607', 'bg_glow': '#120607'},
    'post': {'vignette': {'opaque': 0.42, 'overlay': 0.0}, 'grain': {'opaque': 1.8, 'overlay': 0.0},
             'bloom': [1.0, 1.0], 'bloom_sigma': [5.0, 12.0], 'shutter': 0.6, 'mb_max': 12},
    'enc_noise': 2,
    'thumb_t': 4.2,
    'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
