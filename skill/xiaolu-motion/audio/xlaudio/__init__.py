"""xlaudio -- 小鹿动效系统的声音库 (code-synthesised SFX, sonic identity,
music beds, voice/BGM mixing, beat grid).

Public API
----------
render_sfx(id, seed=0, **params) -> (2, n)      one effect / ident, 48 kHz stereo
list_sfx(family=None)                            ids ('sfx' | 'ident')
render_cues(cues, duration, sr=48000)            storyboard sfx field -> effects track
render_score(preset, duration, ...)              parametric music bed (ScoreResult)
mix_with_voice(voice, bgm, sfx, ...)             ducking + loudness master + report
BeatGrid / BeatMap / load_jianying_beat          卡点 helpers
read_audio / write_wav                           I/O (any ffmpeg-readable input)
"""
from .dsp import SR
from .sfx import render_sfx, list_sfx, get_spec, REGISTRY
from . import ident, motion  # noqa: F401  register the ident + motion families
from .cues import render_cues, load_cues
from .grid import BeatGrid, BeatMap, load_jianying_beat, frame_locked_bpms
from .wavio import read_audio, write_wav

__all__ = ['SR', 'render_sfx', 'list_sfx', 'get_spec', 'REGISTRY', 'render_cues', 'load_cues', 'BeatGrid',
           'BeatMap', 'load_jianying_beat', 'frame_locked_bpms', 'read_audio', 'write_wav',
           'render_score', 'mix_with_voice']


def __getattr__(name):          # lazy: score / mix pull in heavier setup
    if name == 'render_score':
        from .score import render_score
        return render_score
    if name == 'mix_with_voice':
        from .mix import mix_with_voice
        return mix_with_voice
    raise AttributeError(name)
