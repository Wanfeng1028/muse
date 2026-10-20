"""Prepare timestamped visual evidence, not cut detection or semantic analysis.

Requires Python standard library and ffmpeg/ffprobe on PATH; no model download.
Each call uses a fresh output directory. Times are relative to the first video PTS.
"""
import argparse
import bisect
import json
import math
import os
from pathlib import Path
import shutil
import subprocess


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def font_path(requested):
    candidates = [requested] if requested else [
        Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts/arial.ttf',
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise ValueError('No label font found; pass --font /path/to/font.ttf. No font is installed automatically.')


def extract(args):
    video = Path(args.video).resolve(strict=True)
    out = Path(args.output_dir).resolve()
    skill = Path(__file__).resolve().parents[1]
    if out == skill or skill in out.parents:
        raise ValueError('Save evidence outside the skill folder.')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty; use a new name for each review pass.')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('ffmpeg and ffprobe must be installed and on PATH.')
    font = font_path(args.font)
    meta = json.loads(run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]).stdout)
    videos = [s for s in meta['streams'] if s['codec_type'] == 'video']
    if not videos:
        raise ValueError('No video stream.')
    stream = videos[0]
    raw = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_frames',
                         '-show_entries', 'frame=best_effort_timestamp_time,duration_time,pkt_duration_time',
                         '-of', 'json', str(video)]).stdout)['frames']
    pts = [number(f.get('best_effort_timestamp_time')) for f in raw]
    if not pts or any(p is None for p in pts) or any(b <= a for a, b in zip(pts, pts[1:])):
        raise ValueError('Missing or non-increasing frame timestamps; inspect the source manually.')
    origin = pts[0]
    times = [p - origin for p in pts]
    last_duration = number(raw[-1].get('duration_time')) or number(raw[-1].get('pkt_duration_time'))
    stream_duration, stream_start = number(stream.get('duration')), number(stream.get('start_time'))
    if last_duration and last_duration > 0:
        duration, basis = times[-1] + last_duration, 'last_frame_pts_plus_duration'
    elif stream_duration is not None and stream_start is not None and stream_start + stream_duration > pts[-1]:
        duration, basis = stream_start + stream_duration - origin, 'stream_end'
    elif len(times) > 1:
        duration, basis = times[-1] + times[-1] - times[-2], 'estimated_last_interval'
    else:
        raise ValueError('Cannot establish the final frame duration.')
    end = duration if args.end is None else args.end
    if not 0 <= args.start < end <= duration + 1e-6:
        raise ValueError(f'Expected 0 <= start < end <= visual duration ({duration:.6f}).')
    lo, hi = bisect.bisect_left(times, args.start - 1e-7), bisect.bisect_left(times, end - 1e-7)
    if lo >= hi:
        raise ValueError('No frame starts in the requested interval.')
    if args.all_frames:
        indexes = list(range(lo, hi))
    else:
        fps = args.fps if args.fps is not None else 1.0
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('--fps must be finite and positive.')
        chosen = {lo, hi - 1}
        # Select original frames crossing the requested sample grid. Never synthesize frames.
        for k in range(math.ceil((end - args.start) * fps)):
            n = bisect.bisect_left(times, args.start + k / fps - 1e-7)
            if lo <= n < hi:
                chosen.add(n)
        indexes = sorted(chosen)
    if args.width < 64:
        raise ValueError('--width must be at least 64.')
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'probe.json', meta)
    # Local font copy makes filter quoting portable, including Windows drive letters.
    shutil.copyfile(font, out / 'label_font.ttf')
    selection = '+'.join(f'eq(n,{n})' for n in indexes)
    graph = (
        f"[0:v:0]select='{selection}',setpts=PTS-({origin:.9f})/TB,"
        f"scale={args.width}:-2,setsar=1,"
        "drawtext=fontfile=label_font.ttf:text='%{pts\\:flt} s':fontsize=16:"
        "fontcolor=white:box=1:boxcolor=black@0.85:x=4:y=4,split=2[frames][tiles];"
        "[tiles]tile=5x4:padding=4:margin=4:color=black[sheets]"
    )
    (out / 'filters.txt').write_text(graph, encoding='utf-8')
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-n', '-copyts', '-i', str(video),
               '-filter_complex_script', 'filters.txt', '-map', '[frames]', '-fps_mode', 'passthrough',
               '-q:v', '3', 'frame_%06d.jpg', '-map', '[sheets]', '-fps_mode', 'passthrough',
               '-q:v', '3', 'sheet_%03d.jpg']
    # A private cwd avoids shell quoting and keeps all generated files in this pass.
    proc = subprocess.run(command, cwd=out, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (out / 'ffmpeg.log').write_text(proc.stderr, encoding='utf-8')
    if proc.returncode:
        raise ValueError(f'Frame extraction failed. Inspect {out / "ffmpeg.log"}')
    if len(list(out.glob('frame_*.jpg'))) != len(indexes):
        raise ValueError('Decoded output count differs from selected source frames; do not use evidence.')
    if len(list(out.glob('sheet_*.jpg'))) != math.ceil(len(indexes) / 20):
        raise ValueError('Contact-sheet count mismatch; inspect ffmpeg output.')
    audios = [s for s in meta['streams'] if s['codec_type'] == 'audio']
    audio = {'stream_present': bool(audios), 'extraction_status': 'not_requested', 'content_status': 'unverified'}
    if args.with_audio:
        if not audios:
            audio['extraction_status'] = 'no_stream'
        else:
            # Whole track, without trimming. Its first PTS maps through offset below.
            proc = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-n', '-i', str(video),
                                   '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', str(out / 'audio.wav')],
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
            audio['extraction_status'] = 'extracted' if proc.returncode == 0 else 'failed'
            audio['path'] = 'audio.wav' if proc.returncode == 0 else None
            audio['error'] = proc.stderr.strip() or None
    if audios:
        a_start = number(audios[0].get('start_time'))
        audio['source_start_pts_s'] = a_start
        audio['offset_from_video_s'] = a_start - origin if a_start is not None else None
        audio['duration_s'] = number(audios[0].get('duration'))
    records = [{'source_frame_index': n, 'source_pts_s': pts[n], 'time_s': round(times[n], 6),
                'path': f'frame_{i+1:06}.jpg', 'sheet': f'sheet_{i//20+1:03}.jpg', 'sheet_cell_0based': i % 20}
               for i, n in enumerate(indexes)]
    manifest = {
        'source': str(video), 'video_origin_pts_s': origin, 'duration_s': round(duration, 6),
        'duration_basis': basis, 'container_duration_s': number(meta['format'].get('duration')),
        'source_frame_count': len(raw), 'requested_interval': {'start': args.start, 'end': end},
        'sampling': 'all_source_frames' if args.all_frames else 'first_source_frame_at_or_after_each_grid_time_plus_endpoints',
        'requested_fps': None if args.all_frames else fps, 'sample_count': len(records),
        'first_sample_s': records[0]['time_s'], 'last_sample_s': records[-1]['time_s'],
        'rotation': stream.get('side_data_list', []), 'display_rotation_applied': 'ffmpeg_default_autorotate',
        'audio': audio, 'frames': records,
        'note': 'Preparation only. Review frames before claiming visual coverage. Frame times are source PTS relative to video_origin_pts_s; sheet cells run left-to-right, top-to-bottom.'
    }
    write_json(out / 'manifest.json', manifest)
    return {'manifest': str(out / 'manifest.json'), 'sample_count': len(records),
            'first_sample_s': records[0]['time_s'], 'last_sample_s': records[-1]['time_s'], 'audio': audio}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--start', type=float, default=0.0)
    parser.add_argument('--end', type=float)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fps', type=float)
    mode.add_argument('--all-frames', action='store_true')
    parser.add_argument('--width', type=int, default=240)
    parser.add_argument('--font')
    parser.add_argument('--with-audio', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(extract(args), ensure_ascii=False))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
