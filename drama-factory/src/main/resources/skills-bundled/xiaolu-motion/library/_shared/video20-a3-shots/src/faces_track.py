"""Face + outer-lip boxes for every source frame of a range (Apple Vision, src/vision_frames.swift).

usage (heavy task, run it under the lock):
  python3 src/with_heavy_lock.py python3 src/faces_track.py <src_first_frame> <count> <out.json>

Frames are decoded frame-exact (-ss (f-0.5)/30, same seek as storyboard_v2/src/extract_frames.py) at 540x960
(BT.709 tv -> full-range RGB, area downscale) and streamed to vision_frames, which reports boxes in 1080x1920
coordinates. Chunks of <= 300 frames per process (memory rule); nothing is written to disk but the JSON
(first as <out>.partial, renamed after the frame count checks).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = os.environ.get("XM_RAW_FOOTAGE", "raw_footage.mov")
BIN = HERE.parent / '_work/bin/vision_frames'
VF = 'scale=540:960:in_color_matrix=bt709:in_range=tv:out_range=pc:flags=area+accurate_rnd,format=rgb24'


def build_tool():
    if not BIN.exists() or BIN.stat().st_mtime < (HERE / 'vision_frames.swift').stat().st_mtime:
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['swiftc', '-O', str(HERE / 'vision_frames.swift'), '-o', str(BIN)], check=True)


def chunk(f0, n):
    dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-filter_threads', '1', '-threads', '2', '-ss', f'{(f0 - 0.5) / 30:.6f}', '-i', SRC,
                            '-frames:v', str(n), '-vf', VF, '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    vis = subprocess.run([str(BIN), '540', '960', 'faces', '2', str(n)], stdin=dec.stdout, capture_output=True,
                         text=True, timeout=600)
    dec.stdout.close()
    dec.wait()
    rows = [json.loads(l) for l in vis.stdout.splitlines() if l.startswith('{')]
    assert len(rows) == n, (f0, n, len(rows), vis.stderr[-500:])
    return {f0 + r['i']: {'face': r['face'], 'lips': r['lips']} for r in rows}


def main():
    f0, n, out = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    build_tool()
    res = {}
    for a in range(f0, f0 + n, 300):
        res.update(chunk(a, min(300, f0 + n - a)))
        print(f'faces {a}..{min(a + 300, f0 + n) - 1} done', flush=True)
    assert sorted(res) == list(range(f0, f0 + n))
    missing = [f for f, v in res.items() if not v['face']]
    part = out.with_name(out.name + '.partial')
    part.write_text(json.dumps({'src_first': f0, 'count': n, 'missing_face': missing,
                                'frames': {str(k): v for k, v in sorted(res.items())}}, indent=0))
    part.rename(out)
    print(f'{n} frames -> {out}; frames without a face: {len(missing)}')


if __name__ == '__main__':
    main()
