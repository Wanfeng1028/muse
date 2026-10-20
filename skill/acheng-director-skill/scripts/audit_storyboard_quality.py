#!/usr/bin/env python3
"""Audit production contracts, not aesthetic quality or ungenerated media."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import re
import sys

from prompt_delivery import expand_prompt, require_standalone
from h3_contract import check_h3_semantics, clip_bounds, speech_map, remap_speech_references, detail_policy
from production_extensions import check_effect, check_performance
from performance_liveliness import check_liveliness, render_liveliness, render_motion_profile
from combat_timing import check_combat_timing, render_combat_timing
from story_contract import check_story
from asset_plan import check_asset_plan
from h3_final_format import finalize_h3_prompt

ROOT = Path(__file__).resolve().parents[1]
GATES = ["timeline_closure", "previs_index", "buzzword_zero", "micro_acting",
         "combat_calculus", "tri_state_vfx", "colossal_proofs", "h3_schema",
         "acoustic_physics", "continuity_ledger", "performance_liveliness"]
TRACKS = ("gaze", "breath", "shoulder", "body_hands", "dialogue")
CALCULUS = ("force_source", "trajectory", "contact", "resistance", "impact_hold", "transfer", "recoil")
BASE_FIELDS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")
REF_FIELDS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")
DETAIL_DIRECTIVE = (
    "This is a self-contained production instruction and must be readable without the production file, an earlier segment, or a hidden character bible. "
    "For every shot, explicitly state: the medium and visible subject appearance, screen position and facing; the current environment, landmarks and light direction; "
    "the exact starting pose, prop ownership, contact points and state; the factual trigger for each change; the chronological action, reaction and physical consequence; "
    "the camera framing, lens, movement type, direction, path, amplitude, speed and target; the source and timing of dialogue, foley, room tone and breath; "
    "the exact held state at the end and what can continue into the next shot. Render objective, social strategy and subtext as observable gaze, breath, posture, hand, facial and voice behavior. "
    "Keep cause and effect physically, spatially, temporally and socially coherent. Do not replace a visible action with a vague adjective, skip the transition between beats, "
    "collapse preparation, accent, follow-through or settle into one verb, or invent dialogue, objects, voices, cuts or state changes that are not written below."
)
SHOT_DETAIL_DIRECTIVE = (
    "Write this shot as a complete independent instruction: restate who is visible and where they are, the environment and light, the start state, "
    "the trigger, the ordered action and reaction, the camera path and speed, synchronized sound, and the resulting held state."
)
DETAIL_MARKERS = ("start state", "trigger", "chronological", "camera", "sound", "held state")
BUZZ = re.compile(r"超清晰|顶级|极度震撼|神作|此处省略|根据需要添加|\bmasterpiece\b|\bultra[- ]?detailed\b|\b8[kK]\b|\b120\s?fps\b", re.I)
LABEL = re.compile(r"<(?:Subject|Picture|Video|Audio) [1-9]\d*>")


class ContractError(ValueError):
    pass


def read_data(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ContractError("YAML input requires PyYAML; JSON uses only the standard library") from exc
        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise ContractError(f"duplicate YAML key: {key}")
                result[key] = loader.construct_object(value_node, deep=deep)
            return result
        class UniqueLoader(yaml.SafeLoader):
            pass
        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        return yaml.load(text, Loader=UniqueLoader)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"invalid number {x}")))


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def integer(value):
    return type(value) is int


def substantive(value):
    return isinstance(value, str) and len(value.strip()) >= 3 and not re.search(
        r"^(?:TBD|TODO|unknown|待填|示例|\.\.\.|…|N/A)$", value.strip(), re.I)


def require(condition, message):
    if not condition:
        raise ContractError(message)


def shape(p):
    require(isinstance(p, dict), "production must be an object")
    require(p.get("version") == "2.0", "version must be 2.0")
    require(p.get("delivery_scope", "prompt_only") in ("prompt_only", "full_production"), "invalid delivery_scope")
    require(substantive(p.get("project_id")), "project_id required")
    for field in ("fps_num", "fps_den"):
        require(integer(p.get(field)) and p[field] > 0, f"{field} must be a positive integer")
    for field in ("production_total_duration", "generation_clip_limit"):
        require(type(p.get(field)) in (int, float, str), f"{field} must be numeric")
        require(Fraction(str(p[field])) > 0, f"{field} must be positive")
    for field in ("scene_registry", "character_registry", "shots", "segments"):
        require(isinstance(p.get(field), list) and len(p[field]) > 0, f"{field} cannot be empty")
        require(all(isinstance(x, dict) for x in p[field]), f"{field} entries must be objects")
    for field in ("scene_registry", "character_registry"):
        for item in p[field]:
            require(substantive(item.get("id")) and isinstance(item.get("name"), str) and bool(item["name"].strip()), f"{field}: id/name required")
    for item in p["character_registry"]:
        require(type(item.get("height_m")) in (int, float) and math.isfinite(item["height_m"]) and item["height_m"] > 0, "character height must be positive finite number")
    for s in p["shots"]:
        require(substantive(s.get("id")), "shot id required")
        require(isinstance(s.get("features"), dict), f"{s['id']}: features required")
        for key in ("core_emotion", "combat", "supernatural_vfx", "colossal"):
            require(type(s["features"].get(key)) is bool, f"{s['id']}: features.{key} must be boolean")
        for key in ("start_frame", "end_frame"):
            require(integer(s.get(key)), f"{s['id']}: {key} must be integer")
        require(s["start_frame"] >= 0 and s["end_frame"] > s["start_frame"], f"{s['id']}: nonpositive time window")
        require(isinstance(s.get("camera"), dict), f"{s['id']}: camera required")
        require(substantive(s.get("visual")), f"{s['id']}: visual description required")
        require(isinstance(s.get("characters"), list), f"{s['id']}: characters must be a list")
        require(isinstance(s.get("dialogues"), list), f"{s['id']}: dialogues must be a list")
        require(isinstance(s.get("audio"), dict), f"{s['id']}: audio required")
        for key in ("state_in", "state_out"):
            require(isinstance(s.get(key), dict), f"{s['id']}: {key} required")
        require(isinstance(s.get("outcome_events"), list), f"{s['id']}: outcome_events required")
    require(isinstance(p.get("ledger"), dict), "ledger required")


def timecode(frame, p):
    milliseconds = round(Fraction(frame * p["fps_den"] * 1000, p["fps_num"]))
    return f"{milliseconds // 60000:02d}:{milliseconds // 1000 % 60:02d}.{milliseconds % 1000:03d}"


def shot_text(shot, production=None, speakers=None, speech_parts=None, referenced_subjects=None):
    """Compile substantive structured fields into visible/audible English prose."""
    c = shot["camera"]
    chunks = [shot["visual"], c["description"],
              f"The camera uses a {c['lens_mm']} mm lens under the {c['sensor_basis']} convention, with a {c['shutter_angle']}-degree shutter-angle convention; movement: {c['movement']}; path: {c['path']}; target: {c['target']}."
              ]
    names = {item['id']: item['name'] for item in (production or {}).get('character_registry', [])}
    for character in shot.get('characters', []):
        x, y = character['position']
        chunks.append(f"At shot entry, {names.get(character['id'], character['id'])} has normalized screen anchor x={x}, y={y} (left-to-right and top-to-bottom); facing {character['facing']}; gaze {character['gaze']}; hand or weapon state: {character['weapon_hand']}; weapon direction or absence: {character['weapon_direction']}.")
    def window(start, end):
        factor = Fraction(production["fps_den"], production["fps_num"]) if production else Fraction(1, 24)
        return f"{float(start * factor):.3f}–{float(end * factor):.3f} seconds within this shot"
    if shot["features"]["core_emotion"]:
        perf = shot["performance"]
        for track in TRACKS:
            if track not in perf.get("tracks", {}):
                continue
            cue = perf["tracks"][track]
            chunks.append(f"During {window(cue['start'], cue['end'])}: " + cue["cue"] + " Visibility: " + cue["visibility"])
        for event in perf.get("events", []):
            chunks.append(f"During {window(event['start'], event['end'])}: " + event["cue"])
        chunks.extend(perf.get("exclusion_controls", []))
        if perf.get('source_beat_id'):
            chunks.extend(("Incoming performance state: " + perf['continuity_in'],
                           "Visible performance evidence: " + perf['visibility_evidence'],
                           "Held performance state: " + perf['continuity_out']))
    if shot.get("performance", {}).get("acting_design"):
        factor = Fraction(production["fps_den"], production["fps_num"]) if production else Fraction(1, 24)
        chunks.extend(render_liveliness(shot, production, factor))
    if shot["features"]["combat"]:
        combat = shot["combat"]
        # Keep the compiled action causal; do not append a second attack after recoil.
        chunks.extend((combat["force_source"], combat["chain"]["attack"], combat["trajectory"],
                       combat["chain"]["response"], combat["contact"], combat["resistance"],
                       combat["impact_hold"], combat["transfer"]))
    if shot["features"]["supernatural_vfx"]:
        vfx = shot["vfx"]
        if vfx.get("family", "energy_fluid") == "energy_fluid":
            chunks.extend((vfx['origin'], vfx["backbone"]))
            for key in ("solid", "gas", "emissive"):
                channel = vfx["particles"][key]
                if channel["present"]:
                    chunks.append(channel["description"])
            chunks.extend((vfx["collision"], vfx["lighting"]))
            factor = Fraction(production["fps_den"], production["fps_num"]) if production else Fraction(1, 24)
            chunks.append("Within this shot, the effect follows " + "; ".join(f"{phase['name']} {float(phase['start'] * factor):.3f}–{float(phase['end'] * factor):.3f}s" for phase in vfx["phases"]) + ".")
        else:
            chunks.extend(vfx[k] for k in ("origin", "scope", "process", "lighting"))
            chunks.extend(f"During {window(e['start'], e['end'])}: {e['cue']}" for e in vfx["events"])
            chunks.extend((vfx["end_state"], vfx["continuity"]))
    if shot["features"]["combat"]:
        chunks.extend((combat["chain"]["result"], combat["recoil"], combat["chain"]["continuation"]))
        factor = Fraction(production["fps_den"], production["fps_num"]) if production else Fraction(1, 24)
        chunks.extend(render_combat_timing(combat.get("timing"), factor))
    if shot["features"]["colossal"]:
        chunks.extend(f"{e['detail']} Visible at {e['frame_location']}; depth relationship: {e['depth_relation']}." for e in shot["scale_proofs"])
    chunks.extend(shot["audio"]["foley"])
    audio = shot['audio']
    if audio.get('low_frequency_hz') is not None:
        chunks.append(f"The designed low-frequency cue is {audio['low_frequency_hz']} Hz, sourced from {audio['source']}.")
    for line in sorted(shot["dialogues"], key=lambda x: x["start"]):
        delivery = "says in an off-screen voiceover" if line.get("voiceover", False) else "says"
        speaker = speakers[line.get("character_id", line["speaker_name"])] if speakers is not None else line["speaker_id"]
        spoken = line["text"]
        if line.get("utterance_id") and speech_parts:
            ids = speech_parts[line["utterance_id"]]
            if shot["id"] != ids[0]:
                spoken = "<scenetrans>" + spoken
            if shot["id"] != ids[-1]:
                spoken += "<scenetrans>"
        if line.get("cutoff"):
            spoken += "<cutoff>"
        subject = (referenced_subjects or {}).get(line.get('character_id')) or (referenced_subjects or {}).get(line['speaker_name'])
        voice_identity = line['speaker_name'] + (' ' + subject if subject else '')
        text = f"During {window(line['start'], line['end'])}, {voice_identity} ({speaker}), {line['delivery']}, {delivery}: <d>[{line['language']}] {spoken}</d>"
        if line.get("voiceover", False):
            text += " while the corresponding on-screen character's lips remain completely closed."
            text += " Keep this utterance intelligible and front-prioritized over room tone and incidental action noise, with the named voice as the only speaker for this line."
        else:
            text += " Keep every word intelligible: synchronize visible mouth shapes to the original words, preserve the written pauses and emphasis, and keep competing action noise below the voice unless the production data explicitly requires overlap."
        if line.get("utterance_id"):
            text += " The speech continues seamlessly across the cut."
        chunks.append(text)
    return " ".join(x.strip() for x in chunks)


def continuity_text(shot, production):
    """Expose only this shot's recorded events and relevant held state, never invent blocking."""
    bindings = production.get('prompt_bindings', {})
    names = {item['id']: bindings.get(item['id'], item['name']) for field in ('character_registry', 'scene_registry') for item in production[field]}
    visible = {item['id'] for item in shot['characters']}
    relevant = visible | {shot['scene_id']}
    chunks = []
    for event in production['ledger']['events']:
        if event['shot_id'] == shot['id']:
            when = timecode(event['frame'] - shot['start_frame'], production)
            chunks.append(f"At local shot time {when}, the recorded state change is: {event['reason']}")
    held = []
    for identifier, state in shot['state_out']['characters'].items():
        if identifier not in visible:
            continue
        prior = shot['state_in']['characters'][identifier]
        if state['ammo'] or state['ammo'] != prior['ammo']:
            held.append(f"{names[identifier]} retains {state['ammo']} recorded ammunition or energy units")
        if state['trauma_phase'] is not None:
            phase = ('acute injury', 'stabilized or treated injury', 'recovery with recorded residual limitations')[state['trauma_phase']]
            held.append(f"{names[identifier]} remains in the {phase} state; preserve the described functional limitations")
    scene = shot['scene_id']
    damage = shot['state_out']['scenes'][scene]
    if damage or damage != shot['state_in']['scenes'][scene]:
        condition = ('established baseline', 'surface damage', 'local heavy damage with main supports usable', 'structural damage affecting routes or loads')[damage]
        held.append(f"{names[scene]} retains {condition}")
    for prop, owner in shot['state_out']['props'].items():
        if owner in relevant or shot['state_in']['props'].get(prop) in relevant:
            held.append('{{' + prop + '}} remains with ' + names[owner])
    if held:
        chunks.append('At the end of this shot, carry forward these recorded constraints: ' + '; '.join(held) + '.')
    return ' '.join(chunks)


def animation_term_text(seg):
    """Render authored terminology expansions into model-facing evidence.

    The catalog names are advisory; only the host-authored expansion is
    allowed to affect a shot. This keeps the terminology library connected to
    production facts without inventing timing or action from a label alone.
    """
    term_ids = list(seg.get("animation_term_ids", []))
    evidence = list(seg.get("animation_term_evidence", []))
    if not term_ids and not evidence:
        return ""
    by_id = {item.get("term_id"): item for item in evidence}
    chunks = []
    for term_id in term_ids:
        item = by_id.get(term_id)
        if not item:
            continue
        chunks.append(
            f"Animation craft evidence for {item['term']} ({term_id}): "
            f"time window {item['time_window']}; observable fact {item['observable_fact']}; "
            f"camera or layout {item['camera_or_layout']}; sound or QA evidence {item['sound_or_qa']}."
        )
    return " ".join(chunks)


def compile_segment(p, seg, *, draft=False):
    by_id = {s["id"]: s for s in p["shots"]}
    shots = [by_id[x] for x in seg["shot_ids"]]
    mode = seg["mode"]
    opening = seg["style"]
    body = []
    characters = {c["id"]: c for c in p["character_registry"]}
    scenes = {s["id"]: s for s in p["scene_registry"]}
    speakers = speech_map(p, seg)
    speech_parts = {}
    for shot in shots:
        for line in shot["dialogues"]:
            if line.get("utterance_id"):
                speech_parts.setdefault(line["utterance_id"], []).append(shot["id"])
    for i, s in enumerate(shots, 1):
        prefix = f"[Shot {i}] "
        if i > 1:
            prefix += f"At {timecode(s['start_frame'] - seg['start_frame'], p)}, the camera cuts to the following view. "
        elif mode != "Ref2VA":
            prefix += opening + " "
        panels = [x for x in seg.get("panels", []) if x["shot_id"] == s["id"]]
        panel_text = ""
        if panels:
            numbers = [x["panel"] for x in panels]
            selection = (f"Panels {numbers[0]:02d}–{numbers[-1]:02d}" if numbers == list(range(numbers[0], numbers[-1] + 1))
                         else ", ".join(f"Panel {number:02d}" for number in numbers))
            panel_text = " The shot develops the blocking in <Picture 1> " + selection + "."
        # Repeat the complete visible context in every shot. A later shot in
        # the same segment must remain intelligible when copied on its own.
        context = [SHOT_DETAIL_DIRECTIVE]
        context.extend(characters[ch["id"]]["prompt_description"] for ch in s["characters"])
        context.append(scenes[s["scene_id"]]["prompt_description"])
        context.append("At the start of this shot: " + s["state_description"])
        from reference_bindings import shot_reference_text, applies_to
        reference_text = shot_reference_text(seg, s, p)
        if reference_text:
            context.append(reference_text)
        if s.get("performance", {}).get("acting_design"):
            context.append("The acting design's continuity-out is visible before the shot ends: " + s["performance"]["acting_design"]["continuity_out"])
        referenced_subjects = {}
        for subject in seg.get('subjects', []):
            entity = subject.get('entity_id')
            if entity and s['id'] in applies_to(subject, seg):
                referenced_subjects[entity] = subject['label']
                if entity in characters:
                    referenced_subjects[characters[entity]['name']] = subject['label']
        body.append(prefix + " ".join(context) + " " + shot_text(s, p, speakers, speech_parts, referenced_subjects) + panel_text + ' ' + continuity_text(s, p))
    body.insert(0, DETAIL_DIRECTIVE)
    term_text = animation_term_text(seg)
    if term_text:
        body.insert(0, term_text)
    motion_profile = seg.get("motion_profile")
    if motion_profile:
        body.insert(0, " ".join(render_motion_profile(motion_profile)))
    if mode == "Ref2VA":
        body_text = opening + "\n" + "\n".join(body)
        definitions = [r for r in seg.get("references", []) if not r.get("source_only", False)] + seg.get("subjects", [])
        fields = {"subject_definitions": "\n".join(r.get("definition", "") for r in definitions),
                  "summary": seg.get("summary", ""),
                  "retention_analysis": "\n".join(r.get("retention", "") for r in definitions),
                  "detailed_description": body_text,
                  "overall_soundscape": seg["overall_soundscape"],
                  "non_diegetic_music": seg["non_diegetic_music"]}
        fields = {key: remap_speech_references(value, p, seg) if key != "detailed_description" else value for key, value in fields.items()}
    else:
        fields = {"integrated_multimodal_description": "\n".join(body),
                  "overall_soundscape": seg["overall_soundscape"],
                  "non_diegetic_music": seg["non_diegetic_music"]}
    intro = ""
    duration = f"{float(Fraction((seg['end_frame'] - seg['start_frame']) * p['fps_den'], p['fps_num'])):.2f}"
    if mode == "I2VA":
        intro = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
    elif mode == "FL2VA":
        intro = f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {len(shots)}) aligns with the {duration}-second mark of the target video.\n\n"
    elif mode == "L2VA":
        intro = f"How the reference pictures align with the target video — <Picture 1> (from [Shot {len(shots)}]) aligns with the {duration}-second mark of the target video.\n\n"
    raw = expand_prompt(intro + "\n\n".join(f"{k}:\n{v}" for k, v in fields.items()) + "\n", p.get("prompt_bindings"))
    speech_expectations = []
    for shot in shots:
        for line in shot["dialogues"]:
            identity = line.get("character_id", line["speaker_name"])
            speech_expectations.append((speakers[identity], line["language"], line["text"]))
    policy = detail_policy(p, seg)
    if draft:
        from h3_final_format import normalize_h3_prompt
        return normalize_h3_prompt(raw)
    return finalize_h3_prompt(
        raw,
        mode=mode,
        shot_count=len(shots),
        reference_labels=[ref["label"] for ref in seg.get("references", [])],
        subject_labels=[subject["label"] for subject in seg.get("subjects", [])],
        speech_expectations=speech_expectations,
        minimum_words=policy["minimum_words"] if mode == "Ref2VA" else 0,
    )


def replay(p):
    ledger = p["ledger"]
    initial = ledger.get("initial")
    require(isinstance(initial, dict), "ledger.initial required")
    chars = {c["id"] for c in p["character_registry"]}
    scenes = {s["id"] for s in p["scene_registry"]}
    require(set(initial.get("characters", {})) == chars, "initial character coverage mismatch")
    require(set(initial.get("scenes", {})) == scenes, "initial scene coverage mismatch")
    require(isinstance(initial.get("props"), dict), "initial props mapping required")
    for char in initial["characters"].values():
        require(integer(char.get("ammo")) and char["ammo"] >= 0, "initial ammo invalid")
        require(char.get("trauma_phase") is None or (integer(char["trauma_phase"]) and char["trauma_phase"] in range(3)), "initial trauma phase invalid")
    require(all(integer(v) and v in range(4) for v in initial["scenes"].values()), "initial damage invalid")
    require(all(v in chars | scenes for v in initial["props"].values()), "initial prop owner invalid")
    events = ledger.get("events")
    require(isinstance(events, list), "ledger.events must be a list")
    state = copy.deepcopy(initial)
    ids = set()
    last_frame = -1
    by_shot = {s["id"]: s for s in p["shots"]}
    for event in events:
        require(isinstance(event, dict), "event must be object")
        eid = event.get("id")
        require(substantive(eid) and eid not in ids, "duplicate/missing event id")
        ids.add(eid)
        frame = event.get("frame")
        require(integer(frame) and frame >= last_frame, f"{eid}: event order invalid")
        last_frame = frame
        s = by_shot.get(event.get("shot_id"))
        require(s is not None and s["start_frame"] <= frame < s["end_frame"], f"{eid}: event outside source shot")
        require(eid in s["outcome_events"], f"{eid}: missing outcome binding")
        require(substantive(event.get("reason")), f"{eid}: reason required")
        domain, target, after = event.get("domain"), event.get("target"), event.get("after")
        if domain in ("ammo", "trauma"):
            require(target in chars, f"{eid}: unknown character")
            key = "ammo" if domain == "ammo" else "trauma_phase"
            container = state["characters"][target]
            if domain == "ammo":
                require(integer(after) and after >= 0, f"{eid}: ammo must remain nonnegative")
                require(integer(event.get("delta")) and container[key] + event["delta"] == after, f"{eid}: ammo conservation failed")
                if event["delta"] > 0:
                    require(event.get("action") in ("reload", "resupply") and substantive(event.get("resource_source")), f"{eid}: ammo increase needs source")
            else:
                require(integer(after) and after in range(3), f"{eid}: trauma phase invalid")
                allowed = {None: {0}, 0: {0, 1}, 1: {0, 1, 2}, 2: {0, 2}}
                require(after in allowed[container[key]], f"{eid}: illegal trauma transition")
                if after > (container[key] if container[key] is not None else -1) and after != 0:
                    require(event.get("action") in ("treat", "recover") and substantive(event.get("story_time_evidence")), f"{eid}: recovery needs treatment/time evidence")
        elif domain == "damage":
            require(target in scenes and integer(after) and after in range(4), f"{eid}: damage invalid")
            container, key = state["scenes"], target
            if after < container[key]:
                require(event.get("action") == "repair", f"{eid}: damage reset without repair")
        elif domain == "prop":
            require(target in state["props"] and after in chars | scenes, f"{eid}: prop/owner invalid")
            container, key = state["props"], target
        else:
            raise ContractError(f"{eid}: unsupported domain")
        require(container[key] == event.get("before"), f"{eid}: stale before state")
        container[key] = after
    require(state == ledger.get("final"), "ledger.final differs from replay")
    state = copy.deepcopy(initial)
    for shot in p["shots"]:
        require(shot["state_in"] == state, f"{shot['id']}: state_in discontinuity")
        current = [e for e in events if e["shot_id"] == shot["id"]]
        require(set(shot["outcome_events"]) == {e["id"] for e in current}, f"{shot['id']}: dangling outcome event")
        for e in current:
            if e["domain"] in ("ammo", "trauma"):
                state["characters"][e["target"]]["ammo" if e["domain"] == "ammo" else "trauma_phase"] = e["after"]
            else:
                state["scenes" if e["domain"] == "damage" else "props"][e["target"]] = e["after"]
        require(shot["state_out"] == state, f"{shot['id']}: state_out differs from events")
    return state


def audit(p, base_dir=ROOT, *, h3_segment_ids=None):
    results = []
    try:
        shape(p)
    except (ContractError, ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        return {"status": "FAIL", "score": 0, "scope": "structural-contract-only",
                "gates": [{"gate": k, "status": "FAIL", "errors": [f"Input shape: {exc}"]} for k in GATES],
                "visual_status": "UNVERIFIED"}
    shots = p["shots"]
    def gate(name, check, applicable=True):
        if not applicable:
            results.append({"gate": name, "status": "N/A", "score": None, "errors": [], "reason": "No applicable shots"})
            return
        try:
            check()
            results.append({"gate": name, "status": "PASS", "score": 10, "errors": []})
        except (ContractError, ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, ZeroDivisionError) as exc:
            results.append({"gate": name, "status": "FAIL", "score": 0, "errors": [str(exc)]})

    def timeline():
        minimum, maximum = clip_bounds(p)
        scene_ids = [s["id"] for s in p["scene_registry"]]
        char_ids = [c["id"] for c in p["character_registry"]]
        require(len(set(scene_ids)) == len(scene_ids), "duplicate scene registry id")
        require(len(set(char_ids)) == len(char_ids), "duplicate character registry id")
        require(len({s["id"] for s in shots}) == len(shots), "duplicate shot id")
        end = 0
        for s in shots:
            require(s["scene_id"] in scene_ids, f"{s['id']}: unregistered scene")
            require(s["start_frame"] == end and s["end_frame"] > end, f"{s['id']}: gap, overlap, or empty shot")
            end = s["end_frame"]
            for ch in s["characters"]:
                require(ch["id"] in char_ids, f"{s['id']}: unregistered character")
                require(len(ch["position"]) == 2 and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in ch["position"]), f"{s['id']}: invalid screen anchor")
                for key in ("facing", "gaze", "weapon_hand", "weapon_direction"):
                    require(substantive(ch.get(key)), f"{s['id']}: character nail {key} missing")
        require(Fraction(end * p["fps_den"], p["fps_num"]) == Fraction(str(p["production_total_duration"])), "production total duration mismatch")
        require(len({s["id"] for s in p["segments"]}) == len(p["segments"]), "duplicate segment id")
        flat, end = [], 0
        index = {s["id"]: s for s in shots}
        for seg in p["segments"]:
            require(integer(seg["start_frame"]) and integer(seg["end_frame"]), "segment frames must be integer")
            require(seg["start_frame"] == end and seg["end_frame"] > end, f"{seg['id']}: discontinuous segment")
            frames = seg["end_frame"] - seg["start_frame"]
            duration = Fraction(frames * p["fps_den"], p["fps_num"])
            require(duration == Fraction(str(seg["generation_clip_duration"])), f"{seg['id']}: clip duration mismatch")
            require(minimum <= duration <= maximum, f"{seg['id']}: clip outside {minimum}–{maximum} second window")
            ids = seg["shot_ids"]
            require(ids and all(x in index for x in ids), "unknown or empty segment shots")
            require(index[ids[0]]["start_frame"] == end and index[ids[-1]]["end_frame"] == seg["end_frame"], "segment/shot boundary mismatch")
            flat.extend(ids)
            end = seg["end_frame"]
        require(flat == [s["id"] for s in shots], "segment shot order, duplication, or coverage mismatch")
    gate(GATES[0], timeline)

    def previs():
        catalog = read_data(ROOT / "data/camera-moves.json")
        ids = {x["id"] for x in catalog}
        require(ids == {f"{i:03d}" for i in range(1, 133)}, "camera catalog incomplete")
        for s in shots:
            c = s["camera"]
            require(c.get("previs_id") in ids, f"{s['id']}: invalid previs id")
            for key in ("movement", "description", "path", "target", "adaptation", "sensor_basis"):
                require(substantive(c.get(key)), f"{s['id']}: camera.{key} missing")
            require(type(c.get("lens_mm")) in (int, float) and c["lens_mm"] > 0, "lens_mm invalid")
            require(type(c.get("shutter_angle")) in (int, float) and 0 < c["shutter_angle"] <= 360, "shutter_angle invalid")
    gate(GATES[1], previs)

    def buzzwords():
        for s in shots:
            text = shot_text(s, p)
            # Authored dialogue is an immutable source, not a quality-tag instruction.
            text = re.sub(r"<d>.*?</d>", "", text, flags=re.S)
            found = BUZZ.search(text)
            require(not found, f"{s['id']}: prohibited production wording: {found.group() if found else ''}")
        for seg in p["segments"]:
            require(not BUZZ.search(seg["style"]), f"{seg['id']}: prohibited style wording")
    gate(GATES[2], buzzwords)

    def acting():
        for s in shots:
            if not s["features"]["core_emotion"]:
                require(not s.get("performance"), f"{s['id']}: performance present but feature disabled")
                continue
            perf = s["performance"]
            require(substantive(perf["beat_id"]), "EX id missing")
            if perf.get("source_beat_id"):
                require(perf["beat_id"] == perf["source_beat_id"], "expression source/beat id mismatch")
                continue
            require(perf["dominant_track"] in TRACKS, "invalid dominant track")
            selective = perf.get("strategy") == "selective"
            require(bool(perf["tracks"]) and set(perf["tracks"]) <= set(TRACKS) if selective else set(perf["tracks"]) == set(TRACKS), "five tracks required unless strategy is selective")
            require(perf["dominant_track"] in perf["tracks"], "dominant track absent")
            previous = -1
            for key in TRACKS:
                if key not in perf["tracks"]:
                    continue
                t = perf["tracks"][key]
                require(integer(t["start"]) and integer(t["end"]) and (0 if selective else previous) <= t["start"] < t["end"] <= s["end_frame"] - s["start_frame"], f"{s['id']}: {key} timing invalid")
                previous = t["start"]
                require(substantive(t["cue"]) and substantive(t["visibility"]), f"{s['id']}: {key} cue/visibility missing")
    gate(GATES[3], acting, any(s["features"]["core_emotion"] or s.get("performance") for s in shots))

    def combat():
        for s in shots:
            if not s["features"]["combat"]:
                require(not s.get("combat"), "combat payload with feature disabled")
                continue
            c = s["combat"]
            for key in CALCULUS:
                require(substantive(c.get(key)), f"{s['id']}: combat.{key} missing")
            for key in ("attack", "response", "result", "continuation"):
                require(substantive(c["chain"].get(key)), f"{s['id']}: chain.{key} missing")
            factor = Fraction(p["fps_den"], p["fps_num"])
            check_combat_timing(c.get("timing"), s["end_frame"] - s["start_frame"], s["id"])
    gate(GATES[4], combat, any(s["features"]["combat"] or s.get("combat") for s in shots))

    def vfx():
        for s in shots:
            if not s["features"]["supernatural_vfx"]:
                require(not s.get("vfx"), "VFX payload with feature disabled")
                continue
            v = s["vfx"]
            if check_effect(v, s["end_frame"] - s["start_frame"]) != "energy_fluid":
                continue
            require(re.search(r"fluid|流体", v["backbone"], re.I), f"{s['id']}: fluid backbone missing")
            require(v["collision_type"] in ("impact", "contact"), "collision type invalid")
            for key in ("origin", "collision", "lighting"):
                require(substantive(v.get(key)), f"vfx.{key} missing")
            require(set(v["particles"]) == {"solid", "gas", "emissive"}, "three particle channels required")
            for channel in v["particles"].values():
                require(type(channel["present"]) is bool, "particle present must be boolean")
                require(substantive(channel.get("description" if channel["present"] else "reason")), "particle description/reason missing")
            require([x["name"] for x in v["phases"]] == ["anticipation", "release", "impact", "decay"], "VFX four phase order invalid")
            end = v["phases"][0]["start"]
            require(integer(end) and end >= 0, "VFX start invalid")
            for phase in v["phases"]:
                require(integer(phase["start"]) and integer(phase["end"]) and phase["start"] == end < phase["end"] <= s["end_frame"] - s["start_frame"], "VFX phase gap/overflow")
                end = phase["end"]
    gate(GATES[5], vfx, any(s["features"]["supernatural_vfx"] or s.get("vfx") for s in shots))

    def scale():
        heights = {c["id"]: c.get("height_m", 0) for c in p["character_registry"]}
        for s in shots:
            applies = s["features"]["colossal"] or any(heights[c["id"]] >= 100 for c in s["characters"])
            if applies:
                require(s["features"]["colossal"], "100m+ character cannot disable scale proofs")
                proofs = s["scale_proofs"]
                kinds = {e["type"] for e in proofs}
                require(len(kinds) >= 2 and kinds <= {"benchmark", "circulation", "environment", "atmosphere", "modularity", "occlusion"}, f"{s['id']}: two independent scale classes required")
                for e in proofs:
                    require(all(substantive(e.get(k)) for k in ("detail", "frame_location", "depth_relation")), "scale proof location/depth missing")
    gate(GATES[6], scale, any(s["features"]["colossal"] or s.get("scale_proofs") for s in shots) or any(c.get("height_m", 0) >= 100 for c in p["character_registry"]))

    def h3():
        characters = {item["id"]: item for item in p["character_registry"]}
        scenes = {item["id"]: item for item in p["scene_registry"]}
        for registry in (p["character_registry"], p["scene_registry"]):
            for item in registry:
                require(substantive(item.get("prompt_description")), f"{item['id']}: standalone prompt_description required")
        for s in shots:
            require(substantive(s.get("state_description")), f"{s['id']}: standalone current state_description required")
        internal_ids = [item["id"] for group in (p["character_registry"], p["scene_registry"], shots, p["segments"]) for item in group]
        internal_ids.extend(p.get("ledger", {}).get("initial", {}).get("props", {}))
        internal_ids.extend(s["performance"]["beat_id"] for s in shots if s.get("performance"))
        speakers = {}
        for s in shots:
            for line in s["dialogues"]:
                require(re.fullmatch(r"S[1-9]\d*", line["speaker_id"]), "speaker id invalid")
                require(line["speaker_id"] not in speakers or speakers[line["speaker_id"]] == line["speaker_name"], "speaker identity drift")
                speakers[line["speaker_id"]] = line["speaker_name"]
                require(substantive(line["text"]) and re.fullmatch(r"[A-Za-z]+", line["language"]), "dialogue text/language missing")
                require(integer(line["start"]) and integer(line["end"]) and 0 <= line["start"] < line["end"] <= s["end_frame"] - s["start_frame"], "dialogue window invalid")
                require("<" not in line["text"] and ">" not in line["text"], "dialogue source contains reserved markup")
        for seg in p["segments"]:
            mode = seg["mode"]
            if h3_segment_ids is not None and seg['id'] not in h3_segment_ids:
                continue
            require(mode in ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"), "unknown H3 mode")
            mode_lock = seg.get("mode_lock", p.get("h3_mode_lock"))
            if mode_lock is not None:
                require(mode_lock == mode, f"{seg['id']}: h3 mode changed from locked {mode_lock} to {mode}")
                require(substantive(seg.get("mode_selection_reason")), f"{seg['id']}: locked H3 mode needs a selection reason")
            policy = detail_policy(p, seg)
            if mode == "Ref2VA" and policy["profile"] != "legacy_fixture":
                require(policy["minimum_words"] >= 2000, f"{seg['id']}: Ref2VA minimum detail must be at least 2000 words")
                require(policy["target_words"] >= policy["minimum_words"], f"{seg['id']}: Ref2VA target detail is below minimum")
                require(policy["target_words"] >= policy["derived_target_words"],
                        f"{seg['id']}: Ref2VA target detail is below the derived density target")
            for key in ("style", "overall_soundscape", "non_diegetic_music"):
                require(isinstance(seg.get(key), str) and seg[key].strip(), f"{seg['id']}: {key} required")
            refs = seg.get("references", [])
            require(isinstance(refs, list), "references must be list")
            labels = [r["label"] for r in refs]
            require(len(labels) == len(set(labels)), "duplicate reference labels")
            for r in refs:
                require(LABEL.fullmatch(r["label"]), "invalid reference label")
                if r.get("asset_id"):
                    node = next((n for n in p.get("asset_plan", []) if n["id"] == r["asset_id"]), {})
                    require(node.get("status") == "approved" and node.get("version") == r.get("asset_version"), "missing approved reference asset/version")
                    file = node.get("file", "")
                else:
                    file = r.get("file", "")
                require((Path(base_dir) / file).is_file(), f"missing reference file: {file}")
                require(substantive(r.get("role")), "reference role missing")
            expected = {"T2VA": [], "I2VA": ["<Picture 1>"], "FL2VA": ["<Picture 1>", "<Picture 2>"], "L2VA": ["<Picture 1>"]}
            if mode in expected:
                require(labels == expected[mode], f"{mode}: reference set/order mismatch")
                require(not seg.get("subjects"), "Subject definitions require Ref2VA")
            else:
                require(refs and seg["summary"].startswith("["), "Ref2VA needs actual references and task prefix")
                subjects = seg.get("subjects", [])
                require(isinstance(subjects, list), "subjects must be list")
                for subject in subjects:
                    require(re.fullmatch(r"<Subject [1-9]\d*>", subject["label"]), "invalid content Subject label")
                    require(bool(set(LABEL.findall(subject["definition"])) & set(labels)), "Subject must cite an uploaded reference source")
                all_labels = labels + [s["label"] for s in subjects]
                require(len(all_labels) == len(set(all_labels)), "duplicate reference/Subject label")
                for r in refs:
                    if r.get("source_only", False):
                        require(r["label"].startswith(("<Picture", "<Video")) and any(r["label"] in s["definition"] for s in subjects), "source-only reference must be consumed by a Subject")
                for r in [r for r in refs if not r.get("source_only", False)] + subjects:
                    require(r["label"] in r["definition"] and r["label"] in r["retention"], "reference definition/retention disconnected")
                    markers = ("fully_copy", "partially_copy", "reference", "weak_reference") if r["label"].startswith("<Audio") else ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
                    require(any(re.search(r"\b" + marker + r"\b", r["retention"]) for marker in markers), "retention marker invalid")
            panels = seg.get("panels", [])
            if panels:
                require(mode == "Ref2VA" and "<Picture 1>" in labels, "contact sheet requires Ref2VA Picture 1")
                require([x["panel"] for x in panels] == list(range(1, 17)), "16 panels must be complete and ordered")
                index = {s["id"]: s for s in shots}
                last = -1
                for panel in panels:
                    require(panel["shot_id"] in seg["shot_ids"], "panel refers to outside shot")
                    s = index[panel["shot_id"]]
                    require(integer(panel["frame"]) and last <= panel["frame"] and s["start_frame"] <= panel["frame"] < s["end_frame"], "panel frame mismatch")
                    require(substantive(panel["description"]), "panel description missing")
                    last = panel["frame"]
            text = compile_segment(p, seg)
            require_standalone(text, internal_ids, english=True)
            require(set(LABEL.findall(text)) <= set(labels) | {s["label"] for s in seg.get("subjects", [])}, "unresolved reference label")
            require(text.count(SHOT_DETAIL_DIRECTIVE) == len(seg["shot_ids"]), f"{seg['id']}: every shot needs the independent-detail directive")
            for shot_id in seg["shot_ids"]:
                shot = next(item for item in shots if item["id"] == shot_id)
                require(shot["state_description"] in text, f"{shot_id}: current state not consumed by H3")
                for character in shot["characters"]:
                    require(characters[character["id"]]["prompt_description"] in text, f"{shot_id}: character context not consumed by H3")
                    require(scenes[shot["scene_id"]]["prompt_description"] in text, f"{shot_id}: scene context not consumed by H3")
            term_ids = list(seg.get("animation_term_ids", []))
            term_evidence = list(seg.get("animation_term_evidence", []))
            if term_ids or term_evidence:
                from animation_term_catalog import index_catalog, load_catalog
                catalog = index_catalog(load_catalog())
                require(len(term_ids) == len(set(term_ids)), f"{seg['id']}: duplicate animation term id")
                require(all(term_id in catalog for term_id in term_ids), f"{seg['id']}: unknown animation term id")
                evidence_by_id = {item.get("term_id"): item for item in term_evidence}
                require(set(evidence_by_id) == set(term_ids), f"{seg['id']}: terminology selection lacks authored expansions")
                for term_id in term_ids:
                    item = evidence_by_id[term_id]
                    for key in ("term", "time_window", "observable_fact", "camera_or_layout", "sound_or_qa"):
                        require(isinstance(item.get(key), str) and item[key].strip(), f"{seg['id']}: animation term {term_id} missing {key}")
                    require(item["term"] == catalog[term_id]["term"], f"{seg['id']}: animation term name mismatch")
                    require(f"{term_id}" in text and item["observable_fact"] in text, f"{seg['id']}: animation term evidence not consumed by H3")
            fields = tuple(re.findall(r"^([a-z_]+):$", text, re.M))
            require(fields == (REF_FIELDS if mode == "Ref2VA" else BASE_FIELDS), "H3 section order mismatch")
            require("Negative constraints:" not in text, "unverified seventh H3 section")
            check_h3_semantics(p, seg, text)
    gate(GATES[7], h3)

    def sound():
        for s in shots:
            a = s["audio"]
            require(isinstance(a["foley"], list) and all(substantive(x) for x in a["foley"]), "foley must contain concrete cues")
            hz = a["low_frequency_hz"]
            if hz is None:
                require(substantive(a.get("no_low_frequency_reason")), "absent low frequency needs applicability reason")
            else:
                require(type(hz) in (int, float) and math.isfinite(hz) and 0 < hz <= 200, "low-frequency Hz invalid")
                require(substantive(a.get("source")), "low-frequency source required")
                require(not (hz >= 20 and a.get("classification") == "infrasound"), "35Hz/audible bass is not infrasound")
        for seg in p["segments"]:
            require("<d>" not in seg["overall_soundscape"] and "<d>" not in seg["non_diegetic_music"], "dialogue leaked to global sound/music")
            if seg["overall_soundscape"] == "N/A":
                require(seg.get("complete_silence") is True, "N/A soundscape needs explicit complete_silence")
    gate(GATES[8], sound)
    gate(GATES[9], lambda: replay(p))
    gate("narrative_contract", lambda: check_story(p), p.get("delivery_scope") == "full_production" or p.get("story", {}).get("contract_version") == "3.0")
    gate("performance_handoff", lambda: check_performance(p), bool(p.get("expression_handoff")) or any(s.get("performance", {}).get("source_beat_id") for s in shots))
    gate("asset_coverage", lambda: check_asset_plan(p, base_dir), p.get("delivery_scope") == "full_production" or bool(p.get("asset_plan")))
    gate("performance_liveliness", lambda: check_liveliness(p), any(s.get("performance", {}).get("acting_design") for s in shots))
    applicable = [r for r in results if r["status"] != "N/A"]
    score = round(sum(r["score"] for r in applicable) / (10 * len(applicable)) * 100, 2)
    return {"project_id": p["project_id"], "status": "PASS" if all(r["status"] != "FAIL" for r in results) else "FAIL",
            "score": score, "applicable_gates": len(applicable), "scope": "structural-contract-only",
            "production_sha256": digest(p), "gates": results, "visual_status": "UNVERIFIED",
            "limitations": ["Semantic truth, natural acting, visual identity and acoustic spectrum require generated-media inspection.",
                            "Feature declarations and descriptive evidence remain author assertions, not automatic visual proof."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = audit(read_data(args.production), args.production.parent)
    except (OSError, ValueError, TypeError) as exc:
        report = {"status": "FAIL", "score": 0, "error": str(exc)}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
