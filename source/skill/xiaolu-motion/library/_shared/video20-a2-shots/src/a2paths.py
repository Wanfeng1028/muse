"""Paths shared by the A2 shot renderers (shots 13, 14, 18 of video 20). Inputs are read-only."""
import os
import sys
from pathlib import Path

VP = Path(os.environ.get("XM_VIDEO_PROJECT_ROOT", "."))  # your own project's working dir
SRC_VIDEO = Path(os.environ.get("XM_RAW_FOOTAGE", "raw_footage.mov"))  # your own camera source
DEMOS = Path(os.environ.get("XM_DEMOS_DIR", "../demos"))
SB2_SRC = VP / '05_visual/storyboard_v2/src'          # timeline.py (time truth) + sb_lib.py (drawing kit), read-only
SHOTS = VP / '05_visual/build/shots'
XM_FONTS = Path(os.environ.get("XM_FONT_DIR", str(Path(__file__).resolve().parents[4] / 'fonts')))
XM_AUDIO = Path(os.environ.get("XM_AUDIO_DIR", str(Path(__file__).resolve().parents[4] / 'audio')))
# scratch (transient mattes, plates, compiled Vision tools); everything here can be rebuilt by prep_vision.py
SCRATCH = Path(os.environ.get("XM_SCRATCH_DIR", "/tmp/xm_scratch")) / 'a2'
WORK = SCRATCH / 'work'
BIN = SCRATCH / 'bin'
W, H, FPS = 1080, 1920, 30

if str(SB2_SRC) not in sys.path:
    sys.path.insert(0, str(SB2_SRC))
