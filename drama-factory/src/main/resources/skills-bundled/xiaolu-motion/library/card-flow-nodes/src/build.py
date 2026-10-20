#!/usr/bin/env python3
"""card-flow-nodes · 连线工作流 — build entry (see ../README.md).

  python3 build.py stills --times 0.9 2.2 2.9 4.2
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {
    'nodes': [
        {'id': 'a', 'label': '口播素材', 'icon': 'film', 'x': 0.27, 'y': 0.21},
        {'id': 'b', 'label': '文案', 'icon': 'text', 'x': 0.73, 'y': 0.21},
        {'id': 'c', 'label': '分镜', 'icon': 'grid', 'x': 0.5, 'y': 0.37},
        {'id': 'd', 'label': '动效', 'icon': 'spark', 'x': 0.27, 'y': 0.53},
        {'id': 'e', 'label': '音效', 'icon': 'wave', 'x': 0.73, 'y': 0.53},
        {'id': 'f', 'label': '成片', 'icon': 'play', 'x': 0.5, 'y': 0.69, 'result': True, 'sub': '1080×1920 · 00:58'},
    ],
    'links': [['a', 'c'], ['b', 'c'], ['c', 'd'], ['c', 'e'], ['d', 'f'], ['e', 'f']],
    'title': 'WORKFLOW',
}

SHOT = {
    'name': 'card-flow-nodes',
    'component': 'flow_nodes',
    'dur': 4.6, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'sans': [500, 700]},
    'glyphs': {'sans': ''.join(n['label'] + n.get('sub', '') for n in PARAMS['nodes']) + PARAMS['title'] + '0123456789/ '},
    'colors': {'bg': '#05070C', 'bg_glow': '#0B1222'},
    'post': {'vignette': {'opaque': 0.3, 'overlay': 0.0}, 'grain': {'opaque': 1.2, 'overlay': 0.0},
             'bloom': [1.1, 0.95], 'bloom_sigma': [4.0, 9.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 3,
    'thumb_t': 4.0,
    'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
