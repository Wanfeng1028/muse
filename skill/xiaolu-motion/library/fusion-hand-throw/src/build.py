#!/usr/bin/env python3
"""fusion-hand-throw — build entry (see ../README.md).

  python3 build.py prep --plate PLATE.mp4 --voice VOICE.wav     # plate frames, faces, hands, person mattes
  python3 build.py stills --times 0.45 2.45 2.75 4.3
  python3 build.py render --out DIR
Inputs are the video-20 locked master (plate_v2_video.mp4, 1080x1920 30 fps) and its voice stem
(voice_master_48k.wav, same v2 clock); pass them as --plate/--voice or $XM_PLATE/$XM_VOICE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shotkit  # noqa: E402
import sound  # noqa: E402

PLATE = {'start': 2550, 'end': 2685, 'matte': False, 'faces': True, 'hands': True, 'voice': True}
PARAMS = {
    'plate_start': PLATE['start'], 'plate_end': PLATE['end'],
    # "比如拼接的、胶片的、杂志的、发布会的等等" — each style name is thrown on the flick nearest to when it is said
    'words': [{'text': '拼接', 'at': 0.54, 'style': 'collage'}, {'text': '胶片', 'at': 1.49, 'style': 'film'},
              {'text': '杂志', 'at': 2.50, 'style': 'mag'}, {'text': '发布会', 'at': 3.33, 'style': 'keynote'}],
    'slots': [[985, 285, -4], [978, 400, 3], [988, 515, -3], [980, 630, 4]],   # right of the face box, below the top band
    'flight': 0.5,
}

SHOT = {
    'name': 'fusion-hand-throw',
    'component': 'hand_throw',
    'dur': (PLATE['end'] - PLATE['start']) / 30, 'fps': 30, 'size': (1080, 1920),
    'plate': PLATE,
    'params': PARAMS,
    'fonts': {'sans': [700, 900], 'serif': [700, 900]},
    'glyphs': {'sans': '拼接发布会', 'serif': '胶片杂志'},
    'post': {'vignette': {'opaque': 0.0, 'overlay': 0.0}, 'grain': {'opaque': 0.0, 'overlay': 0.0},
             'bloom': [1.0, 0.9], 'bloom_sigma': [4.0, 10.0], 'shutter': 0.5, 'mb_max': 10},
    'enc_noise': 0,
    'sound_setup': sound.setup, 'sfx': sound.cues,
    'thumb_t': 4.2,
}

if __name__ == '__main__':
    shotkit.main(SHOT)
