"""Validate and render explicit combat direction and timing contracts.

The timing payload is deliberately more specific than a generic ``fast/slow``
instruction.  A model needs a support point, an intended target, a readable
contact window, and a held tail state in order to preserve the action's spatial
logic when the H3 segment is submitted on its own.
"""
from contract_core import need, prose


PHASES = {"approach", "commit", "contact", "recovery", "reset", "impact", "release", "pursuit", "evade"}
PLAYBACK = {"real_time", "ramped", "slow_motion", "hold", "fast_motion"}
CANONICAL_PHASES = ("approach", "commit", "contact", "recovery", "reset")
DIRECTION_FIELDS = (
    "origin", "target", "screen_direction", "body_orientation", "weapon_direction",
    "support_point", "result_direction",
)
SPEED_FIELDS = ("support", "acceleration", "contact_read", "recovery")
PHASE_TEXT_FIELDS = (
    "positions", "orientation", "action", "dof", "composition", "dynamics", "tail_frame",
)
COMBAT_LOGIC_FIELDS = (
    "attacker", "target", "target_point", "intent", "defender_state",
    "response", "result", "next_authority",
)
CAMERA_FIELDS = ("framing", "movement", "motion_vector", "action_anchor")


def _text(value, label):
    need(prose(value), f"combat timing {label} required")


def _mapping(value, label):
    need(isinstance(value, dict), f"combat timing {label} required")
    return value


def check_combat_timing(timing, duration, shot_id):
    """Require a readable, finite motion plan for every combat shot."""
    need(isinstance(timing, dict), f"{shot_id}: combat.timing required")
    for field in ("axis_lock", "spatial_direction", "speed_curve", "camera_sync"):
        _text(timing.get(field), field)
    direction = _mapping(timing.get("direction_facts"), "direction_facts")
    for field in DIRECTION_FIELDS:
        _text(direction.get(field), f"direction_facts.{field}")
    speed = _mapping(timing.get("speed_profile"), "speed_profile")
    for field in SPEED_FIELDS:
        _text(speed.get(field), f"speed_profile.{field}")
    phases = timing.get("phases")
    need(isinstance(phases, list) and len(phases) >= len(CANONICAL_PHASES), f"{shot_id}: combat timing needs approach/commit/contact/recovery/reset phases")
    cursor = 0
    names = []
    for phase in phases:
        name = phase.get("name")
        need(name in PHASES, f"{shot_id}: unknown combat timing phase")
        names.append(name)
        start, end = phase.get("start"), phase.get("end")
        need(type(start) is int and type(end) is int and start == cursor < end <= duration,
             f"{shot_id}: combat timing phase gap/overflow")
        need(phase.get("playback") in PLAYBACK, f"{shot_id}: combat timing playback invalid")
        for field in ("purpose", "motion"):
            _text(phase.get(field), f"phase.{field}")
        for field in PHASE_TEXT_FIELDS:
            _text(phase.get(field), f"phase.{field}")
        logic = _mapping(phase.get("combat_logic"), "phase.combat_logic")
        for field in COMBAT_LOGIC_FIELDS:
            _text(logic.get(field), f"phase.combat_logic.{field}")
        camera = _mapping(phase.get("camera"), "phase.camera")
        for field in CAMERA_FIELDS:
            _text(camera.get(field), f"phase.camera.{field}")
        cursor = end
    need(cursor == duration, f"{shot_id}: combat timing phases must cover the whole shot")
    positions = [names.index(name) for name in CANONICAL_PHASES if name in names]
    need(tuple(names[i] for i in positions) == CANONICAL_PHASES,
         f"{shot_id}: combat timing phases must include ordered approach/commit/contact/recovery/reset")
    contact_index = names.index("contact")
    contact = phases[contact_index]
    slow = timing.get("slow_motion")
    need(isinstance(slow, dict), f"{shot_id}: slow_motion policy required")
    need(type(slow.get("enabled")) is bool, f"{shot_id}: slow_motion.enabled must be boolean")
    for field in ("trigger", "reason", "exit"):
        _text(slow.get(field), f"slow_motion.{field}")
    if slow["enabled"]:
        need(type(slow.get("start")) is int and type(slow.get("end")) is int and 0 <= slow["start"] < slow["end"] <= duration,
             f"{shot_id}: slow-motion window invalid")
        need(0 < float(slow.get("rate", 0)) < 1, f"{shot_id}: slow-motion rate must be between 0 and 1")
        need(slow["start"] < contact["end"] and slow["end"] > contact["start"],
             f"{shot_id}: slow-motion window must overlap the contact phase")
        need(contact.get("playback") == "slow_motion",
             f"{shot_id}: contact phase must declare slow_motion when the policy is enabled")
    else:
        need(slow.get("start") is None and slow.get("end") is None, f"{shot_id}: disabled slow motion cannot carry a window")
        need(all(phase.get("playback") != "slow_motion" for phase in phases),
             f"{shot_id}: disabled slow motion cannot contain a slow_motion phase")


def render_combat_timing(timing, factor):
    """Render the timing contract into standalone model-facing prose."""
    if not timing:
        return []
    def sentence(label, value):
        return f"{label}: {value.rstrip('.')} .".replace(" .", ".")
    direction = timing["direction_facts"]
    speed = timing["speed_profile"]
    lines = [
        sentence("Combat direction lock", timing["axis_lock"]),
        sentence("Spatial direction", timing["spatial_direction"]),
        sentence("Speed curve", timing["speed_curve"]),
        sentence("Camera and action synchronization", timing["camera_sync"]),
        "Direction facts: " + "; ".join(
            f"{label.replace('_', ' ')} = {direction[field].rstrip('.') }"
            for field, label in ((field, field) for field in DIRECTION_FIELDS)
        ) + ".",
        "Speed profile: " + "; ".join(
            f"{field.replace('_', ' ')} = {speed[field].rstrip('.') }"
            for field in SPEED_FIELDS
        ) + ".",
    ]
    for phase in timing["phases"]:
        start = float(phase["start"] * factor)
        end = float(phase["end"] * factor)
        lines.append(
            f"From {start:.3f} to {end:.3f} seconds, the {phase['name']} phase uses {phase['playback']} playback "
            f"because {phase['purpose'].rstrip('.')}; motion: {phase['motion'].rstrip('.')}. "
            f"Positions: {phase['positions'].rstrip('.')}. Orientation: {phase['orientation'].rstrip('.')}. "
            f"Action: {phase['action'].rstrip('.')}. "
            f"Combat logic: attacker {phase['combat_logic']['attacker'].rstrip('.')}; "
            f"target {phase['combat_logic']['target'].rstrip('.')}; "
            f"target point {phase['combat_logic']['target_point'].rstrip('.')}; "
            f"intent {phase['combat_logic']['intent'].rstrip('.')}; "
            f"defender starts {phase['combat_logic']['defender_state'].rstrip('.')}; "
            f"response {phase['combat_logic']['response'].rstrip('.')}; "
            f"result {phase['combat_logic']['result'].rstrip('.')}; "
            f"next authority {phase['combat_logic']['next_authority'].rstrip('.')}. "
            f"Camera framing: {phase['camera']['framing'].rstrip('.')}; movement: {phase['camera']['movement'].rstrip('.')}; "
            f"motion vector: {phase['camera']['motion_vector'].rstrip('.')}; action anchor: {phase['camera']['action_anchor'].rstrip('.')}. "
            f"DOF: {phase['dof'].rstrip('.')}. Composition: {phase['composition'].rstrip('.')}. "
            f"Dynamics: {phase['dynamics'].rstrip('.')}. Tail frame: {phase['tail_frame'].rstrip('.')}."
        )
    slow = timing["slow_motion"]
    if slow["enabled"]:
        lines.append(
            f"Use slow motion only from {float(slow['start'] * factor):.3f} to {float(slow['end'] * factor):.3f} seconds at "
            f"{slow['rate']}x: trigger it when {slow['trigger'].rstrip('.')}, because {slow['reason'].rstrip('.')}; exit when {slow['exit'].rstrip('.')}."
        )
    else:
        lines.append("Do not introduce slow motion in this shot: keep every phase at its declared real-time or ramped speed.")
    return lines
