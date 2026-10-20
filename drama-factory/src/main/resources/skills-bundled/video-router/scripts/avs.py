#!/usr/bin/env python3
"""Offline, explainable video-skill routing. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import calendar
import copy
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
REGISTRY = BASE / 'registry' if (BASE / 'registry').is_dir() else BASE / 'references' / 'registry'
GUIDES = BASE / 'docs' if (BASE / 'docs').is_dir() else BASE / 'references'
KINDS = ('models', 'engines', 'agents', 'skills', 'workflows', 'capabilities', 'sources')
REQUEST_KEYS = set('query task model family engine agent host runtime provider require duration fps resolution as_of recent_only limit available_tools reference_images reference_videos reference_audio reference_video_seconds reference_audio_seconds audio_only media_local_only budget_usd input_audio_seconds auto_duration'.split())

def load_catalog(root: Path = REGISTRY) -> dict[str, Any]:
    return {k: json.loads((root / (k + '.json')).read_text(encoding='utf-8')) for k in (*KINDS, 'manifest')}

def normalized(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def tokens(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())

def six_months_before(day: dt.date) -> dt.date:
    month, year = day.month - 6, day.year
    if month <= 0:
        month, year = month + 12, year - 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))

def is_recent(record: dict, as_of: dt.date) -> bool:
    released = record.get('release_date')
    return bool(released and six_months_before(as_of) <= dt.date.fromisoformat(released) <= as_of)

def matches(record: dict, value: str) -> bool:
    return normalized(value) in {normalized(x) for x in [record['id'], *record.get('aliases', [])]}

def infer_task(query: str) -> tuple[str | None, list[str]]:
    q = query.lower()
    rules = [
        (['motion transfer', 'transfer motion'], 'reference', ['motion-transfer']),
        (['retake'], 'retake', []), (['extend', 'continuation'], 'extend', []),
        (['first and last', 'first/last', 'first-last', 'two keyframes'], 'transition', []),
        (['audio driven', 'audio-driven', 'lip sync', 'lip-sync'], 'audio-driven', []),
        (['document to video', 'pdf to video'], 'document-to-video', []),
        (['lora train', 'train a lora'], 'train-lora', []),
        (['multishot', 'multi-shot', 'multiple shots'], 'multishot', []),
        (['math animation', 'manim', 'equation'], 'math', []),
        (['3d product', 'blender'], '3d', []),
        (['motion graphics', 'kinetic', 'audiogram', 'animated chart', 'launch video', 'logo animation', 'canvas', 'remotion', 'hyperframes'], 'motion', []),
        (['quality review', 'quality check'], 'quality-review', []),
        (['subtitle', 'caption', 'encoding'], 'finishing', []),
        (['edit video', 'edit this', 'restyle'], 'edit', []),
        (['animate image', 'animate this image', 'image-to-video'], 'animate-image', []),
        (['reference'], 'reference', []),
        (['footage', 'video', 'cinematic'], 'generate', []),
    ]
    for patterns, task, extra in rules:
        if any(p in q for p in patterns):
            return task, extra
    return None, []

def validate_request(request: dict, catalog: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError('Request must be a JSON object.')
    extra = set(request) - REQUEST_KEYS
    if extra:
        raise ValueError('Unknown request fields: ' + ', '.join(sorted(extra)))
    r = copy.deepcopy(request)
    fields = ('query', 'task', 'model', 'family', 'engine', 'agent', 'host', 'runtime', 'provider', 'resolution', 'as_of')
    for field in fields:
        if field in r and not isinstance(r[field], str):
            raise ValueError(field + ' must be a string.')
    for field in ('require', 'available_tools'):
        if field in r and (not isinstance(r[field], list) or any(not isinstance(x, str) for x in r[field])):
            raise ValueError(field + ' must be an array of strings.')
    for field in ('recent_only', 'audio_only', 'media_local_only', 'auto_duration'):
        if field in r and not isinstance(r[field], bool):
            raise ValueError(field + ' must be boolean.')
    numeric = ('duration', 'fps', 'reference_images', 'reference_videos', 'reference_audio', 'reference_video_seconds', 'reference_audio_seconds', 'budget_usd', 'input_audio_seconds')
    for field in numeric:
        if field not in r:
            continue
        value = r[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(field + ' must be a finite nonnegative number.')
        if field in ('duration', 'fps') and value == 0:
            raise ValueError(field + ' must be positive.')
        if field.startswith('reference_') and not field.endswith('_seconds') and int(value) != value:
            raise ValueError(field + ' must be an integer count.')
    if r.get('runtime', 'either') not in ('either', 'local', 'cloud'):
        raise ValueError('runtime must be either, local or cloud.')
    if r.get('host', 'generic') not in ('generic', 'claude-code', 'codex'):
        raise ValueError('host must be generic, claude-code or codex.')
    limit = r.get('limit', 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer from 1 to 100.')
    r['limit'] = limit
    r.setdefault('as_of', dt.date.today().isoformat())
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['as_of']):
        raise ValueError('as_of must use YYYY-MM-DD.')
    dt.date.fromisoformat(r['as_of'])
    if len(r.get('require', [])) != len(set(r.get('require', []))):
        raise ValueError('require must not contain duplicate capabilities.')
    unknown = set(r.get('require', [])) - {x['id'] for x in catalog['capabilities']}
    if unknown:
        raise ValueError('Unknown capabilities: ' + ', '.join(sorted(unknown)))
    if r.get('media_local_only') and r.get('runtime') == 'cloud':
        raise ValueError('media_local_only conflicts with runtime=cloud.')
    if r.get('audio_only') and (r.get('reference_images', 0) or r.get('reference_videos', 0)):
        raise ValueError('audio_only conflicts with visual references.')
    if r.get('auto_duration') and 'duration' in r:
        raise ValueError('auto_duration and a fixed duration are mutually exclusive.')
    if 'input_audio_seconds' in r and r.get('task') not in (None, 'audio-driven'):
        raise ValueError('input_audio_seconds is for the audio-driven task.')
    return r

def effective_limits(model: dict, request: dict) -> dict:
    # An operation override replaces creation limits; never inherit incompatible profiles.
    return model.get('operation_limits', {}).get(request.get('task'), model.get('limits', {}))

def limit_errors(model: dict, request: dict) -> list[str]:
    errors, limits = [], effective_limits(model, request)
    duration, fps, resolution = (request.get(k) for k in ('duration', 'fps', 'resolution'))
    if limits.get('duration_follows_input_audio'):
        if duration is not None and request.get('input_audio_seconds') is not None and abs(duration - request['input_audio_seconds']) > 0.001:
            errors.append('This operation follows input-audio duration, which differs from the requested duration.')
        duration = None
    if request.get('auto_duration') and request.get('task') in limits.get('auto_duration_forbidden_tasks', []):
        errors.append('Automatic duration cannot be combined with this anchored operation.')
    profiles = limits.get('profiles', [])
    if profiles and any(v is not None for v in (duration, fps, resolution)):
        valid = any((duration is None or duration in p['seconds']) and
                    (fps is None or fps in p['fps']) and
                    (resolution is None or resolution in p['resolutions']) for p in profiles)
        if not valid:
            errors.append('No supported joint duration/resolution/fps profile.')
    else:
        if duration is not None:
            if duration < limits.get('min_seconds', 0) or duration > limits.get('max_seconds', float('inf')):
                errors.append('Duration outside this endpoint’s documented single-segment range.')
        if fps is not None and 'fps' in limits and fps not in limits['fps']:
            errors.append('Frame rate unsupported on this surface.')
        if resolution is not None and 'resolutions' in limits and resolution not in limits['resolutions']:
            errors.append('Resolution unsupported on this surface.')
    counts = [request.get('reference_' + k, 0) for k in ('images', 'videos', 'audio')]
    for field in ('images', 'videos', 'audio'):
        count, maximum = request.get('reference_' + field, 0), limits.get('max_reference_' + field)
        if maximum is not None and count > maximum:
            errors.append('Too many reference ' + field + '.')
    if 'max_reference_files' in limits and sum(counts) > limits['max_reference_files']:
        errors.append('Combined reference count exceeds this surface’s limit.')
    for kind in ('video', 'audio'):
        key = 'reference_' + kind + '_seconds'
        if key in request and request[key] > limits.get('max_' + key, float('inf')):
            errors.append('Reference ' + kind + ' duration exceeds the documented limit.')
    if request.get('audio_only') and limits.get('audio_requires_visual'):
        errors.append('Audio references require at least one visual reference on this surface.')
    return errors

def route(request: dict, catalog: dict | None = None) -> dict:
    c = catalog or load_catalog()
    r = validate_request(request, c)
    as_of = dt.date.fromisoformat(r['as_of'])
    inferred, inferred_caps = infer_task(r.get('query', ''))
    task = r.get('task') or inferred
    result = {'schema_version': '1.0.0', 'request': r, 'snapshot_date': c['manifest']['snapshot_date'],
              'ready_to_execute': False, 'status': 'needs_brief', 'candidates': [], 'excluded': [],
              'warnings': ['Offline routing is not live availability, quality benchmarking or runtime certification.']}
    if as_of.isoformat() > result['snapshot_date']:
        result['warnings'].append('This request is newer than the catalog snapshot. Refresh sources before execution.')
    if not task:
        result['next_action'] = 'Specify a task from the workflows index.'
        return result
    workflows = {w['id']: w for w in c['workflows']}
    if task not in workflows:
        raise ValueError('Unknown task: ' + task)
    workflow = workflows[task]
    required = set(workflow['requires']) | set(r.get('require', []))
    if not r.get('task'):
        required.update(inferred_caps)
        result['warnings'].append('Task inferred by lexical rules; review the structured request before execution.')
    r['task'] = task
    if r.get('auto_duration'):
        required.add('automatic-duration')
    finishing_required = {'exact-text'}
    if task == 'hybrid':
        finishing_required.update(required & {'exact-text', 'editable-code', 'subtitle-timing', 'batch-variants', 'alpha-output'})
        required.difference_update(finishing_required)
    if r.get('audio_only'):
        required.add('audio-only-reference')
    if r.get('reference_audio', 0) and not (r.get('reference_images', 0) or r.get('reference_videos', 0)):
        required.add('audio-only-reference')
    if 'resolution' in r:
        r['resolution'] = {'4k': '2160p', '2k': '1440p'}.get(r['resolution'].lower(), r['resolution'].lower())
    for media, capability in [('images', 'image-reference'), ('videos', 'video-reference'), ('audio', 'audio-reference')]:
        if r.get('reference_' + media, 0):
            required.update(['reference-to-video', capability])
    result.update(task=task, required_capabilities=sorted(required), workflow=workflow)
    agent = next((a for a in c['agents'] if r.get('agent') and matches(a, r['agent'])), None)
    if r.get('agent') and not agent:
        raise ValueError('Unknown controller profile; omit agent for a generic controller.')
    if agent:
        result['controller'] = agent
    if r.get('model') and any(matches(a, r['model']) for a in c['agents']):
        raise ValueError('That is a controller, not a video model. Use --agent instead of --model.')
    procedural = workflow['lane'] == 'procedural'
    pool = c['engines'] if procedural else c['models']
    if procedural and (r.get('model') or r.get('family') or r.get('provider')):
        raise ValueError('Procedural motion uses --engine and --agent; footage models belong to a generative or hybrid task.')
    if not procedural and r.get('engine'):
        raise ValueError('Use a procedural task for an engine selection; hybrid finishing is an explicit second stage.')
    known_families = {m['family'] for m in c['models']}
    if r.get('family') and r['family'] not in known_families:
        raise ValueError('No approved generation surface for family: ' + r['family'] + '; use search for discovery-only skills.')
    if r.get('model') and not any(matches(m, r['model']) or m['family'] == r['model'] for m in pool):
        raise ValueError('Unknown model or alias: ' + r['model'])
    if r.get('engine') and r['engine'] not in {e['id'] for e in c['engines']}:
        raise ValueError('Unknown engine: ' + r['engine'])
    if r.get('provider') and r['provider'] not in {m['provider'] for m in c['models']}:
        raise ValueError('Unknown provider: ' + r['provider'])
    for item in pool:
        if r.get('model') and not (matches(item, r['model']) or item.get('family') == r['model']):
            continue
        if r.get('engine') and item['id'] != r['engine']:
            continue
        if r.get('family') and item.get('family') != r['family']:
            continue
        if r.get('provider') and item.get('provider') != r['provider']:
            continue
        reasons = []
        needed_tools = set(item.get('required_tools', []))
        if 'available_tools' in r and needed_tools - set(r['available_tools']):
            reasons.append('Missing declared adapter prerequisites: ' + ', '.join(sorted(needed_tools - set(r['available_tools']))))
        for capability in sorted(required - set(item['capabilities'])):
            state = 'unsupported' if capability in item.get('unsupported_capabilities', []) else 'not verified'
            reasons.append(capability + ': ' + state + ' on this surface.')
        runtime = 'local' if r.get('media_local_only') else r.get('runtime', 'either')
        if runtime != 'either' and item['runtime'] != runtime:
            reasons.append('Incompatible media runtime: ' + item['runtime'])
        released = item.get('release_date')
        if released and dt.date.fromisoformat(released) > as_of:
            reasons.append('Release is after the requested as-of date.')
        recent = is_recent(item, as_of)
        if r.get('recent_only') and not procedural and not recent:
            reasons.append('Outside six calendar months, or release date unverified.')
        if not procedural:
            reasons.extend(limit_errors(item, r))
        if reasons:
            result['excluded'].append({'id': item['id'], 'reasons': reasons})
            continue
        priority = {'seedance-2-5-byteplus': 10, 'h3-max-fal': 8, 'ltx-2-5-fast-api': 7,
                    'gemini-omni-1-1-flash': 6, 'flux-3-video': 5, 'wan-3-0-prime': 4}
        score = (20 if recent else 0) + priority.get(item['id'], 0)
        if procedural:
            score = {'hyperframes': 8, 'remotion': 7, 'canvas-ffmpeg': 6}.get(item['id'], 5)
            if item['id'] in r.get('query', '').lower():
                score += 10
            if agent and agent['id'] == 'opus-5-5' and item['id'] == 'canvas-ffmpeg' and task == 'motion':
                score += 4
        if needed_tools and needed_tools.issubset(set(r.get('available_tools', []))):
            score += 30
        skills = select_skills(item, r, c)
        pending = ['Current schema, account access, price, media rights and runtime prerequisites.']
        if not procedural:
            limits = effective_limits(item, r)
            for field, evidence in [('duration', 'max_seconds'), ('fps', 'fps'), ('resolution', 'resolutions')]:
                if r.get(field) is not None and evidence not in limits and not limits.get('profiles'):
                    pending.append(field + ' is not verified in this snapshot.')
            if any(r.get('reference_' + t, 0) for t in ('images', 'videos', 'audio')):
                pending.append('Validate every supplied reference type and count in the live operation schema.')
        if effective_limits(item, r).get('duration_follows_input_audio'):
            pending.append('Output length follows input audio; validate source-audio maximum and this operation’s output profile.')
        result['candidates'].append({'id': item['id'], 'name': item['name'], 'routing_score': score,
            'recent_release': recent, 'release_date': released, 'runtime': item['runtime'],
            'guide': str(GUIDES / ('quality.md' if task == 'quality-review' else item['playbook'])), 'native_skill_id': item.get('skill_id', 'video-quality-review' if task == 'quality-review' else 'video-motion'), 'required_tools': sorted(needed_tools), 'skill_ids': [s['id'] for s in skills],
            'skills': skills, 'source_ids': item.get('source_ids', []), 'source_urls': [s['url'] for s in c['sources'] if s['id'] in item.get('source_ids', [])], 'api_model_ids': item.get('api_model_ids', []), 'artifact_ids': item.get('artifact_ids', []), 'preflight_checks': pending,
            'notes': item.get('notes', []), 'reason': 'Meets the verified capability filter; numeric limits checked where documented.'})
    result['candidates'].sort(key=lambda x: (-x['routing_score'], x['id']))
    result['total_compatible'] = len(result['candidates'])
    result['candidates'] = result['candidates'][:r['limit']]
    result['status'] = 'preflight_required' if result['candidates'] else 'no_compatible_route'
    result['next_action'] = 'Read the first candidate guide, resolve the live schema, then complete preflight.' if result['candidates'] else 'Inspect exclusions. Change a constraint only with user approval or add verified evidence.'
    result['warnings'].append('Scores are transparent routing preferences, not measured model quality.')
    if task == 'hybrid' and result['candidates']:
        result['finishing_stage'] = route({'task': 'motion', 'require': sorted(finishing_required), 'as_of': r['as_of'], 'limit': 2}, c)
    if task == 'hybrid' and result.get('finishing_stage', {}).get('status') == 'no_compatible_route':
        result['status'] = 'no_compatible_route'
        result['next_action'] = 'The footage stage has candidates, but the finishing constraints have no compatible route.'
    if 'budget_usd' in r:
        result['warnings'].append('No price quote was fetched. Budget compliance is unresolved until live preflight.')
    return result

def select_skills(item: dict, request: dict, catalog: dict) -> list[dict]:
    available = set(request.get('available_tools', []))
    candidates = []
    for skill in catalog['skills']:
        if skill['curation_tier'] == 'review-required':
            continue
        if skill['portability'] != 'agent-portable' and not set(skill['requires']).issubset(available):
            continue
        if item.get('provider') and 'any' not in skill.get('provider_scope', ['any']) and item['provider'] not in skill['provider_scope']:
            continue
        if item.get('provider') and not skill.get('model_ids'):
            continue
        if skill.get('model_ids') and item['id'] not in skill['model_ids']:
            continue
        match = skill['id'] in item.get('skill_ids', []) or item.get('family') in skill['families']
        if match:
            score = (10 if skill['id'] in item.get('skill_ids', []) else 0) + (3 if skill['curation_tier'] == 'core' else 0)
            candidates.append((score, skill))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    fields = ('id', 'name', 'url', 'portability', 'requires', 'evidence', 'runtime_tested')
    return [{k: s[k] for k in fields} for _, s in candidates[:4]]

def search(query: str, catalog: dict | None = None, kind: str | None = None, family: str | None = None, limit: int = 10) -> list[dict]:
    """BM25 lexical retrieval with exact-ID boost; no external embedding service."""
    c = catalog or load_catalog()
    if not 1 <= limit <= 100:
        raise ValueError('Search limit must be between 1 and 100.')
    if kind and kind not in KINDS:
        raise ValueError('Unknown index: ' + kind)
    docs = [(k, row) for k in ([kind] if kind else KINDS) for row in c[k]
            if not family or row.get('family') == family or family in row.get('families', [])]
    corpus = [tokens(' '.join(str(row.get(f, '')) for f in ('id', 'name', 'title', 'summary', 'family', 'families', 'capabilities', 'aliases', 'novel_abilities'))) for _, row in docs]
    terms, count = set(tokens(query)), len(docs)
    if not terms or not count:
        return []
    average = sum(map(len, corpus)) / count or 1
    frequencies = {t: sum(t in doc for doc in corpus) for t in terms}
    ranked = []
    for (k, row), doc in zip(docs, corpus):
        score = 0.0
        for term in terms:
            tf = doc.count(term)
            idf = math.log(1 + (count - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(doc) / average))
        if normalized(query) == normalized(row['id']):
            score += 100
        if score:
            ranked.append({'kind': k, 'id': row['id'], 'name': row.get('name', row.get('title', row['id'])), 'score': round(score, 4), 'summary': row.get('summary', ''), 'url': row.get('url'), 'guide': row.get('playbook'), 'evidence': row.get('evidence')})
    return sorted(ranked, key=lambda r: (-r['score'], r['id']))[:limit]

def validate_catalog(catalog: dict | None = None) -> list[str]:
    c, errors = catalog or load_catalog(), []
    capabilities = {x['id'] for x in c['capabilities']}
    sources = {s['id'] for s in c['sources']}
    skills = {s['id'] for s in c['skills']}
    for kind in KINDS:
        ids = [row['id'] for row in c[kind]]
        if len(ids) != len(set(ids)):
            errors.append('Duplicate IDs in ' + kind)
    for model in c['models']:
        for capability in model['capabilities'] + model['unsupported_capabilities']:
            if capability not in capabilities:
                errors.append('Unknown model capability: ' + capability)
        if set(model['capabilities']) & set(model['unsupported_capabilities']):
            errors.append('Contradictory capability: ' + model['id'])
        if not model['source_ids'] or set(model['source_ids']) - sources:
            errors.append('Missing model evidence: ' + model['id'])
        if model.get('release_date'):
            try:
                dt.date.fromisoformat(model['release_date'])
            except ValueError:
                errors.append('Invalid release date: ' + model['id'])
    for engine in c['engines']:
        if set(engine['skill_ids']) - skills:
            errors.append('Broken engine skill link: ' + engine['id'])
    for skill in c['skills']:
        if not re.fullmatch(r'[a-f0-9]{40}', skill['revision']) or not re.fullmatch(r'[a-f0-9]{64}', skill['sha256']):
            errors.append('Missing source pin: ' + skill['id'])
        expected = f"https://github.com/{skill['repository']}/blob/{skill['revision']}/{skill['path']}"
        if skill['url'] != expected or '..' in Path(skill['path']).parts:
            errors.append('Invalid pinned path: ' + skill['id'])
    for workflow in c['workflows']:
        steps = {s['id'] for s in workflow['steps']}
        if set(workflow['requires']) - capabilities:
            errors.append('Unknown workflow capability: ' + workflow['id'])
        if len(steps) != len(workflow['steps']):
            errors.append('Duplicate workflow step: ' + workflow['id'])
        for step in workflow['steps']:
            if step['next'] is not None and step['next'] not in steps:
                errors.append('Broken workflow edge: ' + workflow['id'])
    return errors

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    rp = sub.add_parser('route', help='Return a non-executing, evidence-backed routing plan.')
    rp.add_argument('query', nargs='?', default=None)
    rp.add_argument('--request', type=Path, help='JSON request; explicit CLI options override matching fields.')
    for field in ('task', 'model', 'family', 'engine', 'agent', 'host', 'runtime', 'provider', 'resolution', 'as-of'):
        rp.add_argument('--' + field, default=None)
    rp.add_argument('--require', action='append', default=None)
    rp.add_argument('--available-tools', nargs='*', default=None)
    for field in ('duration', 'fps', 'budget-usd', 'reference-video-seconds', 'reference-audio-seconds', 'input-audio-seconds'):
        rp.add_argument('--' + field, type=float, default=None)
    for field in ('limit', 'reference-images', 'reference-videos', 'reference-audio'):
        rp.add_argument('--' + field, type=int, default=None)
    for field in ('recent-only', 'audio-only', 'media-local-only', 'auto-duration'):
        rp.add_argument('--' + field, action='store_true', default=None)
    sp = sub.add_parser('search', help='BM25 lexical retrieval over the local catalog.')
    sp.add_argument('query')
    sp.add_argument('--kind', choices=KINDS)
    sp.add_argument('--family')
    sp.add_argument('--limit', type=int, default=10)
    show = sub.add_parser('show', help='Read one complete record by stable ID.')
    show.add_argument('id')
    listing = sub.add_parser('list')
    listing.add_argument('--kind', choices=KINDS, default='workflows')
    sub.add_parser('stats')
    sub.add_parser('validate')
    args = parser.parse_args(argv)
    try:
        c = load_catalog()
        if args.command == 'route':
            request = json.loads(args.request.read_text()) if args.request else {}
            if not isinstance(request, dict):
                raise ValueError('Request file must contain a JSON object.')
            request.update({k: v for k, v in vars(args).items() if k in REQUEST_KEYS and v is not None})
            output = route(request, c)
        elif args.command == 'search':
            output = search(args.query, c, args.kind, args.family, args.limit)
        elif args.command == 'show':
            output = next((r for k in KINDS for r in c[k] if r['id'] == args.id), None)
            if output is None:
                raise ValueError('Unknown record ID: ' + args.id)
        elif args.command == 'list':
            output = c[args.kind]
        elif args.command == 'validate':
            errors = validate_catalog(c)
            output = {'valid': not errors, 'errors': errors}
            print(json.dumps(output, indent=2))
            return 1 if errors else 0
        else:
            output = c['manifest']
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
