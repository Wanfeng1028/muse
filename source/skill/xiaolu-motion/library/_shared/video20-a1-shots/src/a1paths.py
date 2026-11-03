"""A1 (shots 07-11) shared paths.  Timeline authority: storyboard_v2/src/timeline.py (imported read-only)."""
import os
import sys
from pathlib import Path

VP = Path(os.environ.get("XM_VIDEO_PROJECT_ROOT", "."))  # your own project's working dir
SB2 = VP / '05_visual/storyboard_v2'
sys.path.insert(0, str(SB2 / 'src'))
import timeline as T  # noqa: E402  (single source of truth: v2_to_src, PIECES, INS ...)

SHOTS_DIR = VP / '05_visual/build/shots'
SRC = T.SRC
DEMOS = T.DEMOS
VLOG = DEMOS / 'vlog/vlog_demo.mp4'
KEPU = DEMOS / 'kepu/kepu_demo.mp4'
FACELESS = DEMOS / 'faceless/faceless_demo.mp4'
XM = Path(os.environ.get("XM_REPO_ROOT", str(Path(__file__).resolve().parents[4])))  # this repo's own root
FONTS = XM / 'fonts'
SP = Path(os.environ.get("XM_SCRATCH_DIR", "/tmp/xm_scratch"))
WORK = Path(os.environ.get('A1_WORK', str(SP / 'a1_work')))      # temp files (deleted when done)
BIN = WORK / 'bin'
FPS = 30
W, H = 1080, 1920

# shot table (v2 frames, [f0, f1)) -- identical to storyboard v2 boundaries / A0's SHOTS
SHOTS = {'07': (831, 1065), '08': (1065, 1259), '09': (1259, 1490), '10': (1490, 1730), '11': (1730, 1850)}


def src_frame(f):
    """v2 frame index -> source frame index (presenter footage only), via timeline.v2_to_src on the frame grid"""
    kind, seg, sf = T.v2_to_src(f / FPS)
    assert kind == 'max', (f, kind)
    return sf


def seg_of(f):
    return T.v2_to_src(f / FPS)[1]
