#!/usr/bin/env python3
"""card-timeline-cut · 时间线剪口（波纹删除） — build entry (see ../README.md).

  python3 build.py stills --times 0.6 1.05 2.2 3.8
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {'clip': '口播_A01.mov', 'audio': '人声', 'title': '标题', 'total0': 48, 'removed': 7,
          'label': '波纹删除', 'sub': 'RIPPLE DELETE'}

SHOT = {
    'name': 'card-timeline-cut',
    'component': 'timeline_cut',
    'dur': 4.4, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'sans': [500, 700]},
    'glyphs': {'sans': PARAMS['clip'] + PARAMS['audio'] + PARAMS['title'] + PARAMS['label'] + PARAMS['sub']
               + '0123456789:' + '空隙自动合拢，后面的片段整体前移'},
    'colors': {'bg': '#0C0D10', 'bg_glow': '#0C0D10'},
    'post': {'vignette': {'opaque': 0.36, 'overlay': 0.0}, 'grain': {'opaque': 1.6, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 12},
    'enc_noise': 2,
    'thumb_t': 3.9,
    'sound_setup': sound.setup, 'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
