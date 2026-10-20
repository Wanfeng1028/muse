#!/usr/bin/env python3
"""Compile audio source anchors onto a composition timeline; no listening/asset claim."""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import tempfile
from fractions import Fraction
from pathlib import Path, PurePosixPath

STATES = {'measured_candidate', 'listening_confirmed', 'user_confirmed', 'designed'}


def number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite number')
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ValueError(f'{label} must be a finite number') from None
    if not math.isfinite(float(result)):
        raise ValueError(f'{label} must be finite')
    return result


def quantize(value):
    """Nonnegative round-half-up, matching Math.round for supported values."""
    if value < 0:
        raise ValueError('Cannot quantize negative timeline positions')
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def compile_sheet(sheet, include_candidates=False):
    if not isinstance(sheet, dict):
        raise ValueError('Input must be a JSON object')
    fps = number(sheet.get('fps'), 'fps')
    duration = number(sheet.get('duration_s'), 'duration_s')
    if fps <= 0 or duration <= 0:
        raise ValueError('fps and duration_s must be positive')
    composition_frames = quantize(duration * fps)
    if composition_frames < 1:
        raise ValueError('Composition is shorter than one frame')
    raw = sheet.get('cues')
    if not isinstance(raw, list):
        raise ValueError('cues must be an array')
    result, ids = [], set()
    for index, cue in enumerate(raw):
        if not isinstance(cue, dict):
            raise ValueError(f'cue {index} must be an object')
        cue_id = cue.get('id')
        if not isinstance(cue_id, str) or not cue_id.strip() or cue_id in ids:
            raise ValueError(f'cue {index}: id must be nonempty and unique')
        ids.add(cue_id)
        status = cue.get('verification')
        if status not in STATES:
            raise ValueError(f'{cue_id}: verification must be one of {sorted(STATES)}')
        if status == 'measured_candidate' and not include_candidates:
            raise ValueError(f'{cue_id}: measured_candidate remains unverified. '
                             'Use --include-candidates to compile a labeled draft, '
                             'or supply actual listening/user evidence. Do not relabel it just to pass.')
        asset = cue.get('asset')
        if not isinstance(asset, str) or not asset.strip() or '\\' in asset:
            raise ValueError(f'{cue_id}: asset must be a nonempty project-relative POSIX path')
        if PurePosixPath(asset).is_absolute() or '..' in PurePosixPath(asset).parts or ':' in asset:
            raise ValueError(f'{cue_id}: asset must be project-relative without .. or URL scheme')
        asset_status = cue.get('asset_status', sheet.get('asset_status', 'not_checked'))
        if asset_status not in {'planned', 'provided', 'not_checked'}:
            raise ValueError(f'{cue_id}: asset_status must be planned, provided or not_checked')
        target = number(cue.get('target_s'), f'{cue_id}.target_s')
        source_in = number(cue.get('source_in_s'), f'{cue_id}.source_in_s')
        anchor = number(cue.get('source_anchor_s'), f'{cue_id}.source_anchor_s')
        source_out = number(cue.get('source_out_s'), f'{cue_id}.source_out_s')
        rate = number(cue.get('playback_rate', 1), f'{cue_id}.playback_rate')
        if rate <= 0 or source_in < 0 or source_out <= source_in:
            raise ValueError(f'{cue_id}: require rate > 0 and 0 <= source_in < source_out')
        if not source_in <= anchor < source_out:
            raise ValueError(f'{cue_id}: source anchor must be inside retained source interval')
        if not 0 <= target < duration:
            raise ValueError(f'{cue_id}: target must be inside the composition')
        start = target - (anchor - source_in) / rate
        end = start + (source_out - source_in) / rate
        if start < 0 or end > duration:
            raise ValueError(f'{cue_id}: clip span {float(start):.6f}..{float(end):.6f}s '
                             'extends outside the composition; adjust timing/trim explicitly')
        start_frame = quantize(start * fps)
        trim_frame = quantize(source_in * fps)
        source_end_frame = quantize(source_out * fps)
        source_frames = source_end_frame - trim_frame
        if source_frames < 1:
            raise ValueError(f'{cue_id}: retained source is shorter than one quantized frame')
        # Source anchor remains continuous; trim is quantized to composition frame units.
        effective_in = Fraction(trim_frame, 1) / fps
        effective_out = Fraction(source_end_frame, 1) / fps
        if not effective_in <= anchor < effective_out:
            raise ValueError(f'{cue_id}: frame quantization cuts off the source anchor; widen trim or raise fps')
        output_frames = math.ceil(Fraction(source_frames, 1) / rate)
        if start_frame + output_frames > composition_frames:
            raise ValueError(f'{cue_id}: frame quantization extends the clip past the composition; adjust trim')
        actual_anchor = Fraction(start_frame, 1) / fps + (anchor - effective_in) / rate
        result.append({
            'id': cue_id, 'asset': asset, 'asset_status': asset_status,
            'verification': status, 'note': cue.get('note', ''),
            'target_s': float(target), 'target_frame': quantize(target * fps),
            'source_in_s': float(source_in), 'source_anchor_s': float(anchor),
            'source_out_s': float(source_out), 'playback_rate': float(rate),
            'continuous_clip_start_s': float(start), 'continuous_clip_end_s': float(end),
            'clip_start_frame': start_frame, 'source_trim_before_frame': trim_frame,
            'source_duration_frames': source_frames, 'output_duration_frames': output_frames,
            'quantized_anchor_time_s': float(actual_anchor),
            'anchor_quantization_error_ms': float((actual_anchor - target) * 1000),
        })
    return {
        'schema_version': 1, 'fps': float(fps), 'fps_fraction': str(fps),
        'composition_duration_frames': composition_frames,
        'status': 'candidate_draft' if any(c['verification'] == 'measured_candidate' for c in result)
                  else 'designed_or_confirmed_timings',
        'checks': 'Timing/schema only. No asset existence, duration, listening, rights or mix verification.',
        'asset_files_checked': False,
        'mapping': 'Sequence from=clip_start_frame, duration=output_duration_frames; '
                   'Audio source trim/duration are composition-fps source units; playbackRate applies once.',
        'cues': result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--include-candidates', action='store_true', help='Preserve candidates in a labeled draft')
    parser.add_argument('--overwrite', action='store_true', help='Replace an existing derived output')
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.out.resolve():
            raise ValueError('Output cannot replace the input cue sheet')
        if args.out.exists() and not args.overwrite:
            raise ValueError('Output already exists; choose a new file or use --overwrite')
        data = compile_sheet(json.loads(args.input.read_text(encoding='utf-8')), args.include_candidates)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.cue-', dir=args.out.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
                out.write('\n')
            if args.overwrite:
                os.replace(temporary, args.out)
            else:
                # Atomically fail if another process creates the output after our check.
                os.link(temporary, args.out)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        print(json.dumps({'output': str(args.out.resolve()), 'cue_count': len(data['cues']), 'status': data['status']}))
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
