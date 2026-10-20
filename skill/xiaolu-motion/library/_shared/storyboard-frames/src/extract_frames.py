"""Step 1 (v2): pull the source frames behind the v2 keyframes (frame-exact), the finished-demo frames used in
the inserts / shots 1, 7, 10a, 18, the card frames, then run Apple Vision (matte_still) for person mattes + face /
lip boxes.

Frame-exact seek: the MOV is 30 fps CFR with start_time 0, so `-ss (f-0.5)/30` before -i returns frame f
(checked against v1's select=eq(n,f) extraction of frame 314: identical pixels).
The faceless demo mp4 is being re-mixed by another session and is NOT read: its stills come from
demos/faceless/filmstrip/frames/ (0.2 s steps) directly in render_v2.py.
All inputs are read-only; outputs go to ../_work/.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeline import KEYFRAMES, SRC, v2_to_src, INS

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / '_work'
SP = Path(os.environ.get("XM_SCRATCH_DIR", "/tmp/xm_scratch"))
CARDS = SP / 'cards-v1/out'
EXTRA_SRC = [314]          # v1 shot-3 frame, used for the seek check
# demo frames (30 fps frame numbers) -> what they are used for
VLOG_FRAMES = [54, 102, 216, 288, 345, 534, 565, 720]        # I1 key, shots 18 / 1 thumbs, shot 7 key, 10a
KEPU_FRAMES = [36, 423, 513, 522, 600]                        # 10a (title), insert in / key / out, shots 1 / 18


def grab(video, f, out, fps=30):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{(f - 0.5) / fps:.4f}', '-i', str(video), '-frames:v', '1',
                    str(out)], check=True)


def main():
    frames_dir, assets, matte = WORK / 'src_frames', WORK / 'assets', WORK / 'matte'
    for d in (frames_dir, assets, matte, WORK / 'bin'):
        d.mkdir(parents=True, exist_ok=True)
    frames = sorted({v2_to_src(t)[2] for t in KEYFRAMES.values() if v2_to_src(t)[0] == 'max'} | set(EXTRA_SRC))
    for f in frames:
        grab(SRC, f, frames_dir / f'{f:06d}.png')
    for kf in VLOG_FRAMES:
        grab(INS['vlog']['file'], kf, assets / f'vlog_{kf:04d}.png')
    for kf in KEPU_FRAMES:
        grab(INS['kepu']['file'], kf, assets / f'kepu_{kf:04d}.png')
    for name, t, out in [('03_输入框下指令.mp4', 3.55, 'card03_3.55.png'), ('01_活字印刷标题.mp4', 2.9, 'card01_2.9.png'),
                         ('02_汉字雨纠错.mp4', 2.6, 'card02_2.6.png'), ('06_数字冲击.mp4', 2.0, 'card06_2.0.png')]:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', str(CARDS / name), '-frames:v', '1',
                        str(assets / out)], check=True)
    exe = WORK / 'bin/matte_still'
    if not exe.exists():
        subprocess.run(['swiftc', '-O', str(HERE / 'matte_still.swift'), '-o', str(exe)], check=True, capture_output=True)
    r = subprocess.run([str(exe), str(matte)] + [str(frames_dir / f'{f:06d}.png') for f in frames],
                       check=True, capture_output=True, text=True)
    (WORK / 'faces.jsonl').write_text(r.stdout)
    print(f'{len(frames)} source frames {frames}, faces.jsonl written')


if __name__ == '__main__':
    main()
