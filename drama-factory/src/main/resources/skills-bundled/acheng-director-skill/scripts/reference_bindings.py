"""Derive one per-request reference snapshot from production; never generate media.

Planned inputs, verified local bytes and platform upload receipts are different
facts. This module does not infer approval from a file or from a prompt card.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

from contract_core import content_hash

MEDIA = r"<(Picture|Video|Audio) ([1-9]\d*)>"
LABEL = r"<(?:Subject|Picture|Video|Audio) [1-9]\d*>"
EXTENSIONS = {
    "Picture": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"},
    "Video": {".mp4", ".mov", ".mkv", ".webm", ".avi"},
    "Audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".mp4", ".mov"},
}


def inspect_media(path, label, expected=None):
    match = re.fullmatch(MEDIA, label)
    if not match:
        raise ValueError("invalid media label: " + str(label))
    path = Path(path)
    kind = match[1]
    if path.suffix.lower() not in EXTENSIONS[kind]:
        raise ValueError("reference must be media, not an asset prompt or JSON: " + path.name)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("missing or empty reference media: " + path.name)
    data = path.read_bytes()
    if kind == "Picture":
        valid = data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM")) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    elif kind == "Video":
        valid = data[4:8] == b"ftyp" or data[:4] == b"\x1aE\xdf\xa3" or (data[:4] == b"RIFF" and data[8:12] == b"AVI ")
    else:
        valid = data[:4] in {b"fLaC", b"OggS"} or (data[:4] == b"RIFF" and data[8:12] == b"WAVE") or data[:3] == b"ID3" or data[4:8] == b"ftyp" or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)
    if not valid:
        raise ValueError("reference media signature invalid: " + label)
    sha = hashlib.sha256(data).hexdigest()
    if expected and expected != sha:
        raise ValueError("reference SHA-256 stale: " + label)
    return sha


def applies_to(item, segment):
    """Explicit Shot scope, then authored retention scope; never global ID guessing."""
    if "shot_ids" in item:
        return list(item["shot_ids"])
    numbers = [int(n) for n in re.findall(r"\[Shot (\d+)\]", item.get("retention", "") + " " + item.get("definition", ""))]
    return list(dict.fromkeys(segment["shot_ids"][n - 1] for n in numbers if 0 < n <= len(segment["shot_ids"]))) or list(segment["shot_ids"])


def state_at(production, shot, frame):
    """Replay existing events up to a reference window; do not invent states."""
    state = copy.deepcopy(shot.get('state_in', {}))
    for event in production.get('ledger', {}).get('events', []):
        if event.get('shot_id') != shot['id'] or event.get('frame', frame + 1) > frame:
            continue
        domain = event.get('domain')
        if domain in {'ammo', 'trauma'}:
            field = 'ammo' if domain == 'ammo' else 'trauma_phase'
            state['characters'][event['target']][field] = event['after']
        elif domain in {'damage', 'prop'}:
            state['scenes' if domain == 'damage' else 'props'][event['target']] = event['after']
    return state


def resolve_bindings(production, segment, base):
    """Read-only resolution. Missing requirements survive as explicit blocked rows."""
    base = Path(base)
    refs = copy.deepcopy(segment.get("references", []))
    subjects = copy.deepcopy(segment.get("subjects", []))
    nodes = {x["id"]: x for x in production.get("asset_plan", [])}
    shots = {x["id"]: x for x in production.get("shots", [])}
    legacy = segment.get("prompt_detail_policy", production.get("prompt_detail_policy", {})).get("profile") == "legacy_fixture"
    issues, labels, rows = [], [], []
    if not legacy and (segment.get("mode_lock") != segment["mode"] or not segment.get("mode_selection_reason")):
        issues.append("explicit mode_lock and mode_selection_reason required; no silent mode fallback")
    requirements = []
    for sid in segment["shot_ids"]:
        if not legacy and segment['mode'] != 'T2VA' and 'reference_requirements' not in shots[sid]:
            issues.append('Shot reference strategy not declared: ' + sid)
        for requirement in shots[sid].get("reference_requirements", []):
            requirements.append({**requirement, "shot_id": sid})
    for order, ref in enumerate(refs, 1):
        label = ref.get("label", "")
        errors = []
        if not re.fullmatch(MEDIA, label) or label in labels:
            errors.append("invalid or duplicate media label")
        labels.append(label)
        aid = ref.get("asset_id")
        node = nodes.get(aid, {})
        if aid and not node:
            errors.append("unknown asset_id: " + aid)
        if node and ref.get("asset_version") != node.get("version"):
            errors.append("asset version conflict")
        if node.get("entity_id") and ref.get("entity_id") and node["entity_id"] != ref["entity_id"]:
            errors.append("reference/approved asset entity conflict")
        if node and ref.get("entity_ids"):
            owned = node.get("entity_ids") or ([node["entity_id"]] if node.get("entity_id") else [])
            if not set(ref["entity_ids"]) <= set(owned):
                errors.append("reference composite entities not declared by approved asset")
        file = ref.get("file")
        if node.get("status") == "approved":
            if file and (base / file).resolve() != (base / node["file"]).resolve():
                errors.append("file conflicts with approved asset version")
            file = node["file"]
        elif node:
            errors.append("asset planned; real approved media pending")
        expected = node.get("sha256") if node.get("status") == "approved" else ref.get("sha256")
        if node.get("status") == "approved" and ref.get("sha256") and ref["sha256"] != expected:
            errors.append("reference SHA-256 conflicts with approved asset")
        if ref.get('approval', {}).get('status') in {'rejected', 'revoked'}:
            errors.append('reference content approval rejected or revoked')
        if node.get("status") == "approved" and not expected:
            errors.append("approved asset SHA-256 missing")
        sha = None
        if file:
            try:
                sha = inspect_media(base / file, label, expected)
            except ValueError as exc:
                errors.append(str(exc))
        else:
            errors.append("real media not bound")
        if not legacy and not node:
            approval = ref.get("approval", {})
            if not (ref.get("asset_version") and expected and approval.get("sha256") == sha and approval.get("status") == "approved" and approval.get("evidence")):
                errors.append("external media version/content approval evidence missing")
        scope = applies_to(ref, segment)
        if not scope or not set(scope) <= set(segment["shot_ids"]):
            errors.append("reference Shot scope outside Segment")
        if 'anchor_shot_ids' in ref and (not ref['anchor_shot_ids'] or not set(ref['anchor_shot_ids']) <= set(scope)):
            errors.append('frame anchor Shot scope outside media availability')
        preserve = ref.get("preserve") or ref.get("retention")
        if ref.get("source_only"):
            source_subjects = [s for s in subjects if label in s.get("definition", "")]
            preserve = preserve or " / ".join(s.get("retention", "") for s in source_subjects)
            if not ref.get("shot_ids"):
                scope = list(dict.fromkeys(sid for s in source_subjects for sid in applies_to(s, segment)))
        if not legacy:
            for key, value in (("role", ref.get("role")), ("preserve", preserve), ("exclude", ref.get("exclude"))):
                if not value:
                    errors.append(key + " required")
            if not ref.get("shot_ids"):
                errors.append("explicit shot_ids required for production reference scope")
            if not ref.get("entity_id") and not ref.get("source_only"):
                errors.append("stable entity_id required for standalone referenced content")
        active_ranges = []
        if ref.get("start_frame", segment["start_frame"]) < segment["start_frame"] or ref.get("end_frame", segment["end_frame"]) > segment["end_frame"]:
            errors.append("reference frame scope outside Segment")
        for sid in scope:
            if sid not in shots:
                continue
            shot = shots[sid]
            start = max(shot["start_frame"], ref.get("start_frame", shot["start_frame"]))
            end = min(shot["end_frame"], ref.get("end_frame", shot["end_frame"]))
            if start >= end or start < segment["start_frame"] or end > segment["end_frame"]:
                errors.append("invalid reference frame scope")
            active_ranges.append({"shot_id": sid, "start_frame": start, "end_frame": end})
            for check in ref.get("state_guards", []):
                domain, target = check.get("domain"), check.get("target")
                sample_frames = [start] + [e['frame'] for e in production.get('ledger', {}).get('events', []) if e.get('shot_id') == sid and start < e.get('frame', end) < end]
                for frame in sample_frames:
                    actual = state_at(production, shot, frame).get(domain, {}).get(target)
                    if check.get("field") and isinstance(actual, dict):
                        actual = actual.get(check["field"])
                    if actual != check.get("equals"):
                        errors.append("reference state conflicts with active frame window: " + sid)
                        break
        if ref.get("state_label") and node.get("state_label") and ref["state_label"] != node["state_label"]:
            errors.append("reference state version conflict")
        if ref.get("state_version") and node.get("state_version") and ref["state_version"] != node["state_version"]:
            errors.append("reference state version conflict")
        row = {**ref, "label": label, "upload_order": order, "file": file, "sha256": sha,
               "asset_version": ref.get("asset_version") or ("sha256:" + sha if sha else None),
               "entity_id": ref.get("entity_id") or node.get("entity_id"),
               "shot_ids": scope, "active_ranges": active_ranges,
               "preserve": preserve or "See the authored retention relationship.",
               "exclude": ref.get("exclude"),
               "binding_status": "BOUND_LOCAL" if sha and not errors else "PLANNED_OR_CONFLICTED",
               "content_status": "LEGACY_FIXTURE_NOT_REVIEWED" if legacy else ("APPROVAL_RECORDED" if not errors else "UNVERIFIED"),
               "platform_status": "NOT_UPLOADED", "issues": errors}
        rows.append(row)
        issues.extend(label + ": " + e for e in errors)
    for requirement in requirements:
        if not (requirement.get('asset_id') or requirement.get('entity_id')) or not requirement.get('asset_version') or not requirement.get('purpose'):
            issues.append('Shot reference requirement lacks identity/version/purpose: ' + requirement['shot_id'])
        matched = [r for r in rows if requirement["shot_id"] in r["shot_ids"] and
                   ((requirement.get('asset_id') and r.get('asset_id') == requirement['asset_id']) or
                    (not requirement.get('asset_id') and requirement.get('entity_id') and
                     requirement['entity_id'] in (r.get('entity_ids') or [r.get('entity_id')])))]
        if not matched:
            rows.append({"label": "未分配", "binding_status": "PLANNED", "platform_status": "NOT_UPLOADED",
                         "asset_id": requirement.get("asset_id"), "asset_version": requirement.get("asset_version"),
                         "role": requirement.get("purpose"), "shot_ids": [requirement["shot_id"]], "file": None,
                         "issues": ["required reference has no Segment binding"]})
            issues.append("unbound Shot reference requirement: " + str(requirement.get("asset_id")))
        elif requirement.get("asset_version") and not any(r.get("asset_version") == requirement["asset_version"] for r in matched):
            issues.append("Shot requirement asset version conflict: " + str(requirement.get("asset_id")))
        if matched and requirement.get("entity_id") and not any(r.get("entity_id") == requirement["entity_id"] or requirement["entity_id"] in r.get("entity_ids", []) for r in matched):
            issues.append("Shot requirement entity conflict: " + requirement["entity_id"])
    if not legacy:
        for row in rows:
            if not row.get('label', '').startswith('<'):
                continue
            for sid in row.get('shot_ids', []):
                if not any(q['shot_id'] == sid and ((q.get('asset_id') and q['asset_id'] == row.get('asset_id')) or
                           (not q.get('asset_id') and q.get('entity_id') and q['entity_id'] in (row.get('entity_ids') or [row.get('entity_id')]))) for q in requirements):
                    issues.append('reference has no matching Shot requirement: ' + row['label'] + ' / ' + sid)
    if segment["mode"] != "T2VA" and not refs:
        issues.append("reference mode has no media bindings; plan references from ShotSpec, do not switch mode")
        if not requirements:
            for sid in segment["shot_ids"]:
                shot = shots[sid]
                for aid in shot.get("required_assets", []):
                    node = nodes.get(aid, {})
                    if node.get("kind") == "style":
                        continue
                    rows.append({"label": "未分配", "asset_id": aid, "asset_version": node.get("version"),
                                 "role": node.get("purpose"), "shot_ids": [sid], "file": None,
                                 "binding_status": "NEEDS_REFERENCE_DECISION", "platform_status": "NOT_UPLOADED",
                                 "issues": ["decide relevant source/role from ShotSpec before binding"]})
                if not shot.get("required_assets"):
                    candidates = [(c["id"], "identity/current state") for c in shot.get("characters", [])]
                    candidates += [(shot["scene_id"], "scene layout")]
                    candidates += [(prop, "prop/current state") for prop in shot.get("required_prop_ids", [])]
                    for entity, role in candidates:
                        rows.append({"label": "未分配", "entity_id": entity, "role": role,
                                     "shot_ids": [sid], "file": None, "binding_status": "NEEDS_REFERENCE_DECISION",
                                     "platform_status": "NOT_UPLOADED", "issues": ["confirm relevant asset and version; not an automatic upload requirement"]})
    if segment["mode"] == "T2VA" and (refs or requirements):
        issues.append("T2VA cannot discard declared reference requirements")
    subject_labels = []
    from h3_contract import speech_map
    speakers = speech_map(production, segment)
    character_names = {c['id']: c['name'] for c in production.get('character_registry', [])}
    for subject in subjects:
        label = subject.get("label", "")
        if not re.fullmatch(r"<Subject [1-9]\d*>", label) or label in subject_labels:
            issues.append("invalid or duplicate Subject identity: " + label)
        subject_labels.append(label)
        sources = re.findall(MEDIA, subject.get("definition", ""))
        source_labels = [f"<{kind} {number}>" for kind, number in sources]
        if not source_labels or not set(source_labels) <= set(labels):
            issues.append("Subject has unbound sources: " + label)
        if any(kind == "Audio" for kind, _ in sources):
            issues.append("visual Subject must use Picture/Video sources, not Audio: " + label)
        scope = applies_to(subject, segment)
        if not scope or not set(scope) <= set(segment["shot_ids"]):
            issues.append("Subject Shot scope outside Segment: " + label)
        if not legacy and not subject.get("entity_id"):
            issues.append("Subject stable entity_id required: " + label)
        if not legacy and not subject.get('shot_ids'):
            issues.append('explicit Subject shot_ids required: ' + label)
        subject["shot_ids"] = scope
        subject["source_labels"] = source_labels
        identity = subject.get('entity_id')
        subject['speaker_id'] = speakers.get(identity) or speakers.get(character_names.get(identity))
        retained_numbers = [int(n) for n in re.findall(r"\[Shot (\d+)\]", subject.get('retention', ''))]
        retained_scope = {segment['shot_ids'][n - 1] for n in retained_numbers if 0 < n <= len(segment['shot_ids'])}
        if retained_scope != set(scope):
            issues.append('Subject retention and Shot scope disagree: ' + label)
        for source in rows:
            if source["label"] in source_labels:
                if not set(scope) <= set(source["shot_ids"]):
                    issues.append("Subject outside media scope: " + label)
                for sid in scope:
                    if sid not in shots:
                        continue
                    start = max(shots[sid]['start_frame'], subject.get('start_frame', shots[sid]['start_frame']))
                    end = min(shots[sid]['end_frame'], subject.get('end_frame', shots[sid]['end_frame']))
                    if start >= end or not any(r['shot_id'] == sid and r['start_frame'] <= start and r['end_frame'] >= end for r in source.get('active_ranges', [])):
                        issues.append('Subject outside media frame window: ' + label)
                entities = source.get("entity_ids") or ([source["entity_id"]] if source.get("source_only") and source.get("entity_id") else [])
                if entities and subject.get("entity_id") not in entities:
                    issues.append("Subject/source entity conflict: " + label)
    snapshot = {"schema_version": "4.3.6", "segment_id": segment["id"], "mode": segment["mode"],
                "input_revision": content_hash(production), "references": rows, "subjects": subjects,
                "requirements": requirements, "issues": list(dict.fromkeys(issues)), "legacy_fixture": legacy}
    snapshot["binding_sha256"] = content_hash(snapshot)
    return snapshot


def shot_reference_text(segment, shot, production):
    """A scoped additive instruction; all authored creative prose remains intact."""
    parts = []
    for item in segment.get("references", []) + segment.get("subjects", []):
        if shot["id"] not in applies_to(item, segment):
            continue
        if item.get('anchor_shot_ids') and shot['id'] not in item['anchor_shot_ids']:
            # Media can supply identity in later shots without reapplying an
            # opening-pose/keyframe constraint there; Subjects carry that role.
            continue
        start = max(shot["start_frame"], item.get("start_frame", shot["start_frame"])) - segment["start_frame"]
        end = min(shot["end_frame"], item.get("end_frame", shot["end_frame"])) - segment["start_frame"]
        factor = production["fps_den"] / production["fps_num"]
        window = f"From {start * factor:.3f} to {end * factor:.3f} seconds of this request, "
        if item.get("source_only"):
            consumers = [s for s in segment.get('subjects', []) if item['label'] in s.get('definition', '') and shot['id'] in applies_to(s, segment)]
            if consumers:
                preserve = item.get('preserve') or ' / '.join(s.get('retention', '') for s in consumers)
                rule = '; do not inherit ' + item['exclude'] if item.get('exclude') else ''
                parts.append(window + 'for ' + ', '.join(s['label'] for s in consumers) + ' sourced from ' + item['label'] + ', preserve only ' + preserve + rule + '.')
            continue
        detail = item.get("definition", item.get("role", ""))
        # Legacy fixtures without explicit retain/exclude metadata keep their
        # original creative text; missing production metadata is not invented.
        preserve = item.get('preserve') or item.get('retention') or 'See the authored retention relationship.'
        rule = f" Preserve only: {preserve}."
        rule += f" Do not inherit: {item['exclude']}." if item.get('exclude') else ''
        parts.append(window + detail + rule)
    return " ".join(parts)
