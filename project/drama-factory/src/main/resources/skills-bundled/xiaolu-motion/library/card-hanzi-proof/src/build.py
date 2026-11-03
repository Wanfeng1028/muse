#!/usr/bin/env python3
"""card-hanzi-proof · 汉字雨纠错 — build entry (see ../README.md).

  python3 build.py stills --times 0.5 1.9 2.9 4.2
  python3 build.py render --out DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PARAMS = {'text': '再接再励', 'wrong': 3, 'right': '厉', 'seal': '校', 't_settle': 1.35}


def gb2312_level1():
    """the rain draws from the 3755 level-1 GB2312 characters (same set as the page builds)"""
    out = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            if hi == 0xD7 and lo > 0xF9:
                continue
            out.append(bytes([hi, lo]).decode('gb2312'))
    return ''.join(out)


SHOT = {
    'name': 'card-hanzi-proof',
    'component': 'hanzi_proof',
    'dur': 4.5, 'fps': 30, 'size': (1080, 1920),
    'params': PARAMS,
    'fonts': {'serif': [700, 900], 'kai': [500]},
    'glyphs': {'serif': gb2312_level1() + PARAMS['text'] + PARAMS['right'], 'kai': PARAMS['right'] + PARAMS['seal']},
    'colors': {'bg': '#EDE4D3', 'bg_glow': '#EDE4D3'},
    'post': {'vignette': {'opaque': 0.22, 'overlay': 0.0}, 'grain': {'opaque': 2.2, 'overlay': 0.0},
             'bloom': [0.25, 0.2], 'bloom_sigma': [4.0, 8.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 2,
    'thumb_t': 3.9,
    'sound_setup': sound.setup, 'sfx': sound.cues, 'bed': sound.bed,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
