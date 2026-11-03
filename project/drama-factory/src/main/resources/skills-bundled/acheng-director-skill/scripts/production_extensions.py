"""Performance handoffs and conditional effect families."""
from contract_core import indexed, need, prose

PERFORMANCE_FIELDS = ("state_in", "displayed_state", "leakage", "control_action", "residual", "continuity_out")
FAMILIES = {"energy_fluid", "destruction", "weather", "transformation", "spatial", "optical"}


def check_performance(p):
    handoff = p.get("expression_handoff")
    compiled = [s for s in p["shots"] if s.get("performance", {}).get("source_beat_id")]
    if not handoff:
        need(not compiled, "performance references missing expression_handoff")
        return {"status": "N/A", "reason": "screenplay-only performance; no external handoff claimed"}
    need(handoff.get("version") == "1.0" and handoff.get("source_locked") is True, "unlocked/unrecognized expression handoff")
    beats = indexed(handoff.get("beats"), "expression beats")
    used = set()
    for beat in beats.values():
        for field in PERFORMANCE_FIELDS + ("source_anchor", "character", "trigger", "prompt_ready_zh"):
            need(prose(beat.get(field)), f"expression {field} required")
        need(beat["character"] in {c["id"] for c in p["character_registry"]}, "expression character unknown")
        need(beat.get("intensity") is None or type(beat["intensity"]) is int and 0 <= beat["intensity"] <= 5, "expression intensity invalid")
        need(type(beat.get("confidence")) in (int, float) and 0 <= beat["confidence"] <= 1, "expression confidence invalid")
        need(isinstance(beat.get("visible_cues"), list) and beat["visible_cues"] and isinstance(beat.get("exclusions"), list), "expression cues/exclusions required")
        need(prose(beat.get("visibility")) and prose(beat.get("timing")), "expression timing/visibility required")
    for shot in compiled:
        perf = shot["performance"]
        bid = perf["source_beat_id"]
        need(bid in beats, "unknown expression source")
        beat = beats[bid]
        used.add(bid)
        need(beat["character"] in {c["id"] for c in shot["characters"]}, "expression character not visible in shot")
        need(perf.get("source_anchor") == beat["source_anchor"], "expression provenance mismatch")
        need(perf.get("selected_phase") in PERFORMANCE_FIELDS and perf.get("visibility_result") == "visible", "expression phase/visibility unresolved")
        need(prose(perf.get("visibility_evidence")), "expression visibility evidence required")
        need(prose(perf.get("continuity_in")) and prose(perf.get("continuity_out")), "expression continuity required")
        events = perf.get("events", [])
        need(events and all(e.get("phase") in (*PERFORMANCE_FIELDS, "trigger") and prose(e.get("cue")) for e in events), "performance events missing")
        previous = -1
        for event in events:
            need(type(event.get("start")) is int and type(event.get("end")) is int and max(0, previous) <= event["start"] < event["end"] <= shot["end_frame"] - shot["start_frame"], "performance event time invalid")
            previous = event["start"]
        need(len(perf.get("exclusion_controls", [])) == len(beat["exclusions"]) and all(prose(x) for x in perf["exclusion_controls"]), "performance exclusions not compiled")
    unresolved = handoff.get("unresolved", [])
    need(isinstance(unresolved, list) and all(x.get("id") in beats and prose(x.get("reason")) for x in unresolved), "invalid unresolved expression list")
    need(used | {x["id"] for x in unresolved} == set(beats), "expression beat silently dropped")
    need(not unresolved, "expression conflicts remain unresolved before video export")
    return {"status": "PASS", "mapped_beats": len(used), "scope": "source-and-timing; semantic visibility needs content review"}


def check_effect(vfx, shot_frames):
    family = vfx.get("family", "energy_fluid")
    need(family in FAMILIES, "unknown VFX family")
    if family == "energy_fluid":
        return family
    for field in ("origin", "scope", "process", "end_state", "lighting", "continuity"):
        need(prose(vfx.get(field)), f"{family}: {field} required")
    need(not any(key in vfx for key in ("backbone", "particles", "collision_type", "phases")), "non-fluid effect must not mix energy-only fields")
    phases = vfx.get("events", [])
    need(phases, "effect visible events required")
    end = 0
    for event in phases:
        need(type(event.get("start")) is int and type(event.get("end")) is int and end <= event["start"] < event["end"] <= shot_frames, "effect event order/window invalid")
        need(prose(event.get("cue")), "effect visible cue required")
        end = event["end"]
    return family
