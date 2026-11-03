"""Check timeline consistency and optionally render the table from the same JSON.

This validates structure, not visual interpretation or transcript accuracy.
"""
import argparse
import json
import math
from pathlib import Path

EPS = 0.00001


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(data):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    duration = data.get('video', {}).get('duration_s')
    if not numeric(duration) or duration <= 0:
        return ['video.duration_s must be a positive finite number']

    def interval(obj, name, lower=0, upper=duration, nullable=False):
        a, b = obj.get('start'), obj.get('end')
        if nullable and a is None and b is None:
            return False
        ok = numeric(a) and numeric(b) and lower-EPS <= a < b <= upper+EPS
        require(ok, f'{name}: invalid interval')
        return ok

    def timing(obj, name):
        require(obj.get('basis') in ('measured', 'estimated', 'unknown'), f'{name}: invalid timing basis')
        value = obj.get('uncertainty_s')
        require(value is None or (numeric(value) and value >= 0), f'{name}: invalid timing uncertainty')

    rows = data.get('timeline', [])
    dialogue = data.get('dialogue', [])
    require(bool(rows), 'timeline is empty')
    for label, items in [('timeline', rows), ('dialogue', dialogue)]:
        ids = [x.get('id') for x in items]
        require(all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids), f'{label}: missing/duplicate IDs')
    dmap = {d['id']: d for d in dialogue if d.get('id')}
    for d in dialogue:
        interval(d, d.get('id', 'dialogue'), nullable=True)
        timing(d.get('timing', {}), d.get('id', 'dialogue'))
        require(d.get('delivery') in ('on_camera', 'voiceover', 'offscreen', 'unknown'), 'invalid dialogue delivery')
    valid_rows = []
    seen_shots = set()
    previous = None
    for s in rows:
        name = s.get('id', 'row')
        valid = interval(s, name)
        timing(s.get('timing', {}), name)
        for boundary in s.get('boundary_timing', {}).values():
            timing(boundary, name)
        if valid:
            valid_rows.append(s)
        shot = s.get('shot_id')
        require(isinstance(shot, str) and bool(shot), f'{name}: missing shot_id')
        transition = s.get('editing', {}).get('transition_in')
        if previous:
            if numeric(previous.get('end')) and numeric(s.get('start')):
                require(s['start'] >= previous['end']-EPS, f'{name}: overlapping/out-of-order timeline')
            same = shot == previous.get('shot_id')
            require((transition == 'continuous') == same, f'{name}: shot_id/transition mismatch')
            require(same or shot not in seen_shots, f'{name}: noncontiguous shot ID reuse')
        else:
            require(transition == 'start', f'{name}: first transition must be start')
        seen_shots.add(shot)
        previous = s
        refs = s.get('dialogue_ids', [])
        require(len(refs) == len(set(refs)), f'{name}: duplicate dialogue references')
        for ref in refs:
            require(ref in dmap, f'{name}: missing dialogue ID {ref}')
        if valid:
            for d in dialogue:
                if numeric(d.get('start')) and numeric(d.get('end')):
                    overlaps = d['start'] < s['end'] and d['end'] > s['start']
                    require((d.get('id') in refs) == overlaps, f'{name}: dialogue overlap/reference mismatch {d.get("id")}')
            for a in s.get('action_beats', []):
                interval(a, f'{name}.action_beats', s['start'], s['end'])
                timing(a.get('timing', {}), f'{name}.action_beats')
            window = s.get('editing', {}).get('transition_window')
            if window:
                interval(window, f'{name}.transition_window', s['start'], s['end'])
                require(abs(window.get('start', -1)-s['start']) < EPS, f'{name}: transition must start at row boundary')
        for post in s.get('postproduction', []):
            if isinstance(post, dict) and ('start' in post or 'end' in post):
                interval(post, f'{name}.postproduction', nullable=True)
    observation = data.get('observation', {})
    coverage = observation.get('coverage', [])
    require(bool(coverage), 'observation.coverage is empty')
    for c in coverage:
        interval(c, 'coverage')
    for c in observation.get('audio_coverage', []):
        interval(c, 'audio_coverage', upper=max(duration, data.get('video', {}).get('audio_duration_s') or duration))
    for log in observation.get('review_log', []):
        interval(log, 'review_log')

    def merged(items):
        spans = []
        for obj in sorted(items, key=lambda x: x['start']):
            a, b = obj['start'], obj['end']
            if spans and a <= spans[-1][1] + EPS:
                spans[-1][1] = max(spans[-1][1], b)
            else:
                spans.append([a, b])
        return spans
    valid_coverage = [c for c in coverage if numeric(c.get('start')) and numeric(c.get('end'))]
    a, b = merged(valid_rows), merged(valid_coverage)
    require(len(a) == len(b) and all(abs(x-y) < EPS for aa, bb in zip(a, b) for x, y in zip(aa, bb)),
            'timeline union differs from declared visual coverage (gap or uncovered interval)')
    video = data.get('video', {})
    require(video.get('audio_status') in ('verified_present', 'verified_absent', 'unverified'), 'invalid audio_status')
    if video.get('audio_stream_present') is False:
        require(video.get('audio_status') != 'verified_present' and not dialogue, 'dialogue/audio contradicts absent stream')
    if data.get('schema_version') == '1.1':
        require('audio_stream_present' in video, '1.1 requires audio_stream_present')
        require(video.get('duration_scope') == 'video_stream', '1.1 duration_scope must be video_stream')
        require(observation.get('coverage_modality') in ('visual_sampled', 'visual_all_frames', 'visual_playback'), 'invalid coverage_modality')
        require('audio_coverage' in observation, '1.1 requires audio_coverage')
    return errors


def table(data):
    def esc(x):
        return str(x).replace('|', '\\|').replace('\n', '<br>')
    dmap = {d['id']: d for d in data.get('dialogue', [])}
    lines = ['| 시간·숏 | 카메라 | 행동 | 대사·발화 시간 | 연출·편집 |', '|---|---|---|---|---|']
    for s in data['timeline']:
        speech = []
        for ref in s['dialogue_ids']:
            d = dmap[ref]
            when = f"{d['start']:.3f}–{d['end']:.3f}" if d.get('start') is not None else '시간 미확인'
            speech.append(f"{ref}: {d['text']} ({when})")
        if not speech:
            speech = ['미확인' if data['video']['audio_status'] == 'unverified' else '확인된 발화 ID 없음']
        values = [f"{s['start']:.3f}–{s['end']:.3f} / {s['shot_id']}·{s['id']} ({s['timing']['basis']})",
                  ' / '.join(str(x) for x in s['camera'].values()), s['action'], '; '.join(speech),
                  f"{s['editing']['transition_in']}. {s['direction_observed']}"]
        lines.append('| ' + ' | '.join(esc(x) for x in values) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis')
    parser.add_argument('--table')
    args = parser.parse_args()
    data = json.loads(Path(args.analysis).read_text(encoding='utf-8-sig'))
    errors = validate(data)
    print(json.dumps({'status': 'failed' if errors else 'passed', 'errors': errors,
                      'rows': len(data.get('timeline', [])), 'scope': 'structural_consistency_only'}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)
    if args.table:
        Path(args.table).write_text(table(data), encoding='utf-8')


if __name__ == '__main__':
    main()
