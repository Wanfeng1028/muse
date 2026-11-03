"""Validate and render the causal acting layer used by lively H3 prompts.

The layer is deliberately optional: quiet observation and legacy five-track
cards remain valid. When authors opt into ``acting_design`` every visible
movement must have a trigger, a social purpose, a readable action, and a
continuity result. This is a contract for prompt completeness, not a claim
that a generated actor will look natural without media review.
"""
from __future__ import annotations

import re

from contract_core import need, prose


MODES = {"restrained", "expressive", "action_driven", "comic", "observational"}
MEDIUMS = {"2d_cel", "3d_animation", "live_action", "stop_motion", "hybrid"}
EXPOSURES = {"ones", "twos", "threes", "twos_and_threes", "mixed"}
CUTS = {"hard_cut", "match_cut", "dissolve", "continuous"}
ENGLISH_ONLY = re.compile(r"[\u3400-\u9fff]")


def _model_text(value, label):
    need(prose(value), f"acting {label} required")
    need(not ENGLISH_ONLY.search(value), f"acting {label} must be model-facing English")


def _dialogue_texts(shot):
    return [line["text"] for line in shot.get("dialogues", [])]


def _speech_anchor(anchor, shot):
    need(isinstance(anchor, str) and bool(anchor.strip()), "acting speech_anchor required")
    if anchor.strip().lower() in {"silent", "no dialogue", "none"}:
        return
    need(any(anchor in text for text in _dialogue_texts(shot)), "acting speech_anchor is not an exact dialogue substring")


def _source_literal(anchor, shot):
    for index, line in enumerate(shot.get("dialogues", []), 1):
        start = line["text"].find(anchor)
        if start >= 0:
            return (f"at characters {start + 1} through {start + len(anchor)} of spoken line {index} "
                    "in this shot (a performance cue, not an additional utterance)")
    raise ValueError("acting speech anchor has no approved dialogue source")


def check_liveliness(production):
    """Validate all opted-in shot acting designs and their segment motion language."""
    active = [s for s in production.get("shots", []) if s.get("performance", {}).get("acting_design")]
    if not active:
        return {"status": "N/A", "reason": "no acting_design opt-in"}
    characters = {c["id"] for c in production["character_registry"]}
    shots = {s["id"]: s for s in production["shots"]}
    segments = {sid: seg for seg in production["segments"] for sid in seg["shot_ids"]}
    mapped = 0
    for shot in active:
        design = shot["performance"]["acting_design"]
        need(design.get("version") == "1.0", f"{shot['id']}: acting_design version required")
        need(design.get("mode") in MODES, f"{shot['id']}: unknown acting_design mode")
        cid = design.get("character_id")
        need(cid in characters and any(c["id"] == cid for c in shot["characters"]), f"{shot['id']}: acting character must be visible")
        for field in ("objective", "tactic", "subtext", "trigger", "personality_signature", "continuity_in", "continuity_out"):
            _model_text(design.get(field), field)
        need(isinstance(design.get("action_units"), list) and len(design["action_units"]) >= 2, f"{shot['id']}: at least two acting action_units required")
        duration = shot["end_frame"] - shot["start_frame"]
        previous = -1
        for unit in design["action_units"]:
            start, end = unit.get("start"), unit.get("end")
            need(type(start) is int and type(end) is int and previous <= start < end <= duration, f"{shot['id']}: acting action-unit timing invalid")
            previous = start
            for field in ("cause", "action", "gaze", "face", "follow_through", "delivery"):
                _model_text(unit.get(field), f"action_unit.{field}")
            _speech_anchor(unit.get("speech_anchor"), shot)
            if unit.get("prop") is not None:
                _model_text(unit["prop"], "action_unit.prop")
            if unit.get("camera") is not None:
                _model_text(unit["camera"], "action_unit.camera")
            if unit.get("sound") is not None:
                _model_text(unit["sound"], "action_unit.sound")
        arc = design.get("motion_arc")
        need(isinstance(arc, dict), f"{shot['id']}: motion_arc required")
        for field in ("anticipation", "accent", "follow_through", "settle"):
            _model_text(arc.get(field), f"motion_arc.{field}")
        delivery = design.get("speech_delivery")
        need(isinstance(delivery, dict), f"{shot['id']}: speech_delivery required")
        for field in ("voice_timbre", "pace", "pitch", "volume"):
            _model_text(delivery.get(field), f"speech_delivery.{field}")
        for pause in delivery.get("pauses", []):
            _speech_anchor(pause.get("after_text"), shot)
            need(type(pause.get("duration_ms")) is int and 0 <= pause["duration_ms"] <= 3000, f"{shot['id']}: pause duration invalid")
        for emphasis in delivery.get("emphasis", []):
            _speech_anchor(emphasis.get("text"), shot)
            _model_text(emphasis.get("delivery"), "speech_delivery.emphasis.delivery")
        for cut in design.get("cut_behavior", []):
            at = cut.get("at")
            need(type(at) is int and 0 <= at <= duration, f"{shot['id']}: cut time invalid")
            need(cut.get("type") in CUTS, f"{shot['id']}: unknown cut type")
            need(type(cut.get("audio_carries")) is bool, f"{shot['id']}: audio_carries must be boolean")
            need(type(cut.get("action_carries")) is bool, f"{shot['id']}: action_carries must be boolean")
            for field in ("entry_state", "exit_state"):
                _model_text(cut.get(field), f"cut.{field}")
            if cut["audio_carries"]:
                next_shot = next((s for s in production["shots"] if s["start_frame"] == shot["end_frame"]), None)
                need(next_shot is not None, f"{shot['id']}: carried audio requires a following shot")
                ids = {line.get("utterance_id") for line in shot.get("dialogues", []) if line.get("utterance_id")}
                next_ids = {line.get("utterance_id") for line in next_shot.get("dialogues", []) if line.get("utterance_id")}
                need(ids & next_ids, f"{shot['id']}: carried audio requires one cross-cut utterance_id")
        exclusions = design.get("exclusions", [])
        need(isinstance(exclusions, list) and exclusions and all(prose(x) for x in exclusions), f"{shot['id']}: acting exclusions required")
        seg = segments[shot["id"]]
        profile = seg.get("motion_profile")
        need(isinstance(profile, dict), f"{seg['id']}: motion_profile required for acting_design")
        need(profile.get("version") == "1.0", f"{seg['id']}: motion_profile version required")
        need(profile.get("medium") in MEDIUMS, f"{seg['id']}: motion_profile medium invalid")
        need(type(profile.get("fps")) is int and 1 <= profile["fps"] <= 120, f"{seg['id']}: motion_profile fps invalid")
        need(profile.get("exposure") in EXPOSURES, f"{seg['id']}: motion_profile exposure invalid")
        need(profile.get("cut_style") in CUTS, f"{seg['id']}: motion_profile cut_style invalid")
        for field in ("timing_principle", "camera_principle", "staging_principle", "sound_principle"):
            _model_text(profile.get(field), f"motion_profile.{field}")
        mapped += 1
    return {"status": "PASS", "shots": mapped, "scope": "causal acting completeness; naturalness needs generated-media review"}


def render_liveliness(shot, production, factor):
    """Render an acting_design into independent model-facing prose."""
    design = shot.get("performance", {}).get("acting_design")
    if not design:
        return []
    def window(start, end):
        return f"{float(start * factor):.3f}–{float(end * factor):.3f} seconds within this shot"
    chunks = [
        f"The performance uses {design['mode']} acting. Immediate objective: {design['objective']}. Tactic: {design['tactic']}. Social subtext: {design['subtext']}. Trigger: {design['trigger']}. Visible personality signature: {design['personality_signature']}."
    ]
    for unit in design["action_units"]:
        line = f"During {window(unit['start'], unit['end'])}, because {unit['cause']}, the character {unit['action']}. Gaze: {unit['gaze']}. Face: {unit['face']}. Follow-through: {unit['follow_through']}. Delivery: {unit['delivery']}."
        anchor = unit.get("speech_anchor", "silent")
        if anchor.strip().lower() not in {"silent", "no dialogue", "none"}:
            line += f" The movement punctuates the source phrase {_source_literal(anchor, shot)}."
        for field, label in (("prop", "Prop continuity:"), ("camera", "Camera:"), ("sound", "Coupled sound:")):
            if unit.get(field):
                line += f" {label} {unit[field]}."
        chunks.append(line)
    arc = design["motion_arc"]
    chunks.append(f"The motion phrase has this arc: anticipation—{arc['anticipation']}; accent—{arc['accent']}; follow-through—{arc['follow_through']}; settle—{arc['settle']}.")
    speech = design["speech_delivery"]
    chunks.append(f"Voice delivery uses {speech['voice_timbre']}, {speech['pace']}, {speech['pitch']} and {speech['volume']}.")
    for pause in speech.get("pauses", []):
        chunks.append(f"Pause after the source phrase {_source_literal(pause['after_text'], shot)} for {pause['duration_ms']} milliseconds.")
    for emphasis in speech.get("emphasis", []):
        chunks.append(f"Emphasize the source phrase {_source_literal(emphasis['text'], shot)} with {emphasis['delivery']}.")
    for cut in design.get("cut_behavior", []):
        carry = "Audio carries across the cut." if cut["audio_carries"] else "Audio stops or resets at the cut."
        action = "The action carries across the cut." if cut["action_carries"] else "The action resolves before the cut."
        chunks.append(f"At {float(cut['at'] * factor):.3f} seconds within this shot, use a {cut['type']}; {carry} {action} Entry state: {cut['entry_state']}. Exit state: {cut['exit_state']}.")
    chunks.append(f"Continuity in: {design['continuity_in']}. Continuity out: {design['continuity_out']}.")
    chunks.extend(f"Avoid {item}." for item in design["exclusions"])
    return chunks


def render_motion_profile(profile):
    """Render the medium/timing language once per independent H3 segment."""
    if not profile:
        return []
    return [
        f"Motion language: {profile['medium']} at {profile['fps']} fps, exposed on {profile['exposure']}.",
        f"Timing principle: {profile['timing_principle']}.",
        f"Camera principle: {profile['camera_principle']}.",
        f"Staging principle: {profile['staging_principle']}.",
        f"Sound principle: {profile['sound_principle']}.",
        f"Cut language: {profile['cut_style']}."
    ]
