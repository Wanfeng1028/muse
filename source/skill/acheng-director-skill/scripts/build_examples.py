#!/usr/bin/env python3
"""Rebuild the three authored production cards and deterministic blocking sheets."""
import copy
import json
from pathlib import Path

from audit_storyboard_quality import compile_segment, TRACKS
from prompt_delivery import render_asset_prompt

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def write_json(path, value):
    if isinstance(value, dict) and value.get('version') == '2.0' and value.get('ledger'):
        prepare_fixture_bindings(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_fixture_bindings(production):
    """Authored example labels only; never infer labels for arbitrary production IDs."""
    props = {'SHIELD': 'the steel shield', 'BRASS_KEY': 'the brass key',
             'STONE_SHIELD': 'the stone shield', 'PHONE': 'the phone',
             'PROP_LEDGER': 'the archive ledger', 'PROP_TIDE': 'the tide board',
             'PROP_NOTICE': 'the posted notice', 'PROP_SANDBAG': 'the sandbags',
             'PROP_STATIONERY': 'the stationery', 'UMBRELLA': 'the red umbrella',
             'FLASHLIGHT': 'the flashlight'}
    scenes = {'EXAMPLE_MECHA': 'the repair hangar', 'EXAMPLE_DRAMA': 'the maintenance room',
              'EXAMPLE_COLOSSAL': 'the harbor', 'EXAMPLE_ANIMATED_PHONE': 'the office',
              'EXAMPLE_COMEDY_MISUNDERSTANDING': 'the prop workshop',
              'EXAMPLE_SUSPENSE_WHISPER': 'the archive'}
    labels = production.setdefault('prompt_bindings', {})
    for key in production['ledger']['initial']['props']:
        if key in props:
            labels.setdefault(key, props[key])
    for scene in production['scene_registry']:
        location = {'SC_ARCHIVE': 'the archive room', 'SC_DOCK': 'the dock', 'SC_BRIDGE': 'the wooden bridge'}.get(scene['id'])
        labels.setdefault(scene['id'], scenes.get(production['project_id']) or location or scene['prompt_description'])
    names = {c['id']: c['name'] for c in production['character_registry']}
    for shot in production['shots']:
        for character in shot['characters']:
            others = [names[c['id']] for c in shot['characters'] if c['id'] != character['id']]
            if character['gaze'] == 'toward the other registered character' and len(others) == 1:
                character['gaze'] = 'toward ' + others[0]
            anchors = {'CHAR_WARD': 'left-arm steel shield', 'CHAR_FORGE': 'right-forearm emitter',
                       'CHAR_AER': 'forearm blade channel', 'CHAR_GUARDIAN': 'ribbed shield forearm'}
            if character['id'] in anchors:
                character['weapon_hand'] = anchors[character['id']]
    return production


def nail(cid, x, direction):
    return {"id": cid, "position": [x, 0.55], "facing": direction,
            "gaze": "toward the other registered character", "weapon_hand": "right hand or mounted right forearm",
            "weapon_direction": "toward the established contact line"}


def camera(previs, lens, description, path):
    movement = "slow controlled lateral translation" if previs in ("039", "106") else "slow controlled pull" if previs == "084" else "slow controlled push"
    return {"previs_id": previs, "lens_mm": lens, "sensor_basis": "full-frame equivalent",
            "shutter_angle": 180, "movement": movement,
            "path": path, "target": "the visible action and contact plane",
            "adaptation": "project-specific amplitude and speed; source ID is a motion-family reference",
            "description": description}


def shot(sid, start, end, visual, cam, characters, **features):
    return {"id": sid, "scene_id": "S01", "start_frame": start, "end_frame": end,
            "visual": visual, "camera": cam, "characters": characters,
            "features": {key: features.get(key, False) for key in ("core_emotion", "combat", "supernatural_vfx", "colossal")},
            "dialogues": [], "audio": {"foley": ["A short metal resonance follows the visible movement."],
                "low_frequency_hz": 35, "classification": "audible_sub_bass", "source": "the established mechanical drive"},
            "outcome_events": [], "state_in": {}, "state_out": {}}


def state(initial, shots, events):
    current = copy.deepcopy(initial)
    for s in shots:
        s["state_in"] = copy.deepcopy(current)
        for e in events:
            if e["shot_id"] != s["id"]:
                continue
            s["outcome_events"].append(e["id"])
            if e["domain"] in ("ammo", "trauma"):
                current["characters"][e["target"]]["ammo" if e["domain"] == "ammo" else "trauma_phase"] = e["after"]
            else:
                current["scenes" if e["domain"] == "damage" else "props"][e["target"]] = e["after"]
        s["state_out"] = copy.deepcopy(current)
    return {"initial": initial, "events": events, "final": current}


def panels(shots, captions):
    records = []
    for i, s in enumerate(shots):
        for j in range(8):
            records.append({"panel": i * 8 + j + 1, "shot_id": s["id"],
                            "frame": s["start_frame"] + [0, 16, 30, 48, 60, 72, 120, 167][j],
                            "phase": (["establish", "grounding", "shield", "light", "align", "observe", "hold", "ready"] if i == 0 else ["compress", "drive", "release", "deflect", "contact", "chips", "brake", "recover"])[j],
                            "description": captions[i][j]})
    return records


def segment(sid, shots, style, sound, mode="T2VA", sheet=None, captions=None):
    seg = {"id": sid, "start_frame": shots[0]["start_frame"], "end_frame": shots[-1]["end_frame"],
           "shot_ids": [s["id"] for s in shots], "generation_clip_duration": (shots[-1]["end_frame"] - shots[0]["start_frame"]) // 24,
           "mode": mode, "style": style, "overall_soundscape": sound, "non_diegetic_music": "N/A", "references": []}
    if sheet:
        seg["references"] = [{"label": "<Picture 1>", "file": sheet, "role": "storyboard blocking and ordering only",
            "definition": "<Picture 1> is the sixteen-panel gray blocking diagram for [Shot 1] and [Shot 2], providing left-right placement and event order; its schematic figures and flat shading are not appearance or material references.",
            "retention": "<Picture 1> (planning reference for [Shot 1] and [Shot 2]): weak_reference - preserve the two figures' relative sides and the ordered action beats, while replacing schematic blocks with the described original character designs in a single full-screen view."}]
        seg["summary"] = "[reference generation] The target video follows the blocking and order in <Picture 1>, first establishing the confrontation and then showing the attack, defense, material response and continuing recovery."
        seg["panels"] = panels(shots, captions)
    return seg


def fluid(origin, backbone, collision, solids, gas, sparks, lighting):
    return {"origin": origin, "backbone": backbone, "collision_type": "impact", "collision": collision,
            "particles": {"solid": {"present": True, "description": solids},
                          "gas": {"present": True, "description": gas},
                          "emissive": {"present": True, "description": sparks}}, "lighting": lighting,
            "phases": [{"name": name, "start": start, "end": end} for name, start, end in
                       [("anticipation", 0, 24), ("release", 24, 60), ("impact", 60, 62), ("decay", 62, 168)]]}


def combat_timing(direction):
    def phase(name, start, end, playback, purpose, motion, stage):
        return {
            "name": name, "start": start, "end": end, "playback": playback,
            "purpose": purpose, "motion": motion,
            "positions": f"The attacker remains on screen left and the defender on screen right during the {stage} beat, with the established landmark visible.",
            "orientation": f"The attacker faces the defender and the defender faces the attacker throughout {stage}; both gazes stay on the active line.",
            "action": f"The {stage} action follows the declared support, target and result direction without a teleport or axis flip.",
            "combat_logic": {
                "attacker": "The registered attacker or its active weapon owns this beat.",
                "target": "The registered defender or stated environmental target receives the action.",
                "target_point": "The declared contact surface or target point remains specific and visible.",
                "intent": f"The tactical purpose is to complete the {stage} beat of the exchange.",
                "defender_state": "The defender begins from the inherited balance, guard and support state.",
                "response": "The defender responds along the declared line with a visible physical cause.",
                "result": f"The immediate {stage} result is visible before the next phase begins.",
                "next_authority": "The next phase starts from this held pose and its stated active side."
            },
            "camera": {
                "framing": f"The camera framing keeps both bodies, the active line and the {stage} anchor readable.",
                "movement": f"The camera uses a controlled {stage} movement with amplitude and speed matched to the action.",
                "motion_vector": "The camera vector supports the declared attack, defense and result vectors without crossing the axis.",
                "action_anchor": f"The camera follows the visible {stage} anchor: support, weapon path, contact, recoil or settled guard."
            },
            "dof": f"Focus stays on the {stage} anchor and transfers only when the next physical result becomes readable.",
            "composition": "The left-right axis, depth landmark and protected movement exit remain visible.",
            "dynamics": f"Environmental response remains subordinate during {stage} and follows the same force direction.",
            "tail_frame": f"The {stage} phase ends with an explicit inherited distance, facing, weapon state and gaze."
        }

    return {
        "axis_lock": "Keep the established left-right axis: the attacker remains on screen left and the defender on screen right; do not cross the 180-degree line during the exchange.",
        "spatial_direction": direction,
        "speed_curve": "Use fast readable approach, a brief compressed commitment, a precisely readable contact beat, then a longer real-time recovery; never insert a decorative slow-motion pause between unrelated actions.",
        "camera_sync": "The camera tracks parallel to the action line, keeps the feet, weapon path and contact plane visible, and eases only after the defender's result is readable.",
        "direction_facts": {
            "origin": "The attack begins at the declared planted foot, hand or mounted weapon.",
            "target": "The declared defender or environmental target receives the action.",
            "screen_direction": direction,
            "body_orientation": "The attacker faces the target and the defender faces the attacker without an unexplained turn.",
            "weapon_direction": "The active limb, weapon or emitted object follows the declared contact line.",
            "support_point": "The declared planted foot, hand, ground or structural brace carries the force.",
            "result_direction": "The result travels along the declared deflection, recoil or displacement line."
        },
        "speed_profile": {
            "support": "Establish the planted support and readable distance before acceleration.",
            "acceleration": "Accelerate from the support through the body into the weapon or action path.",
            "contact_read": "Compress only the single contact and first material response so the force direction is readable.",
            "recovery": "Return to real time for recoil, displacement, braking and the inherited tail state."
        },
        "phases": [
            phase("approach", 0, 24, "real_time", "the planted support and target line must be established before acceleration", "the attacker compresses the support leg and the defender raises the readable defense without changing sides", "approach"),
            phase("commit", 24, 60, "ramped", "the attack must gain speed from a visible body-driven initiation", "the hip and shoulder drive the weapon or energy from screen left toward the defender's stated target point", "commitment"),
            phase("contact", 60, 62, "slow_motion", "the contact surface, direction of deflection and first material response must be legible", "the leading edge meets the defense, holds its silhouette for two frames, and begins to turn along the deflection plane", "contact"),
            phase("recovery", 62, 120, "real_time", "the result must propagate through both bodies and the environment", "the defender yields along the declared line while the attacker absorbs recoil instead of teleporting to a new stance", "recovery"),
            phase("reset", 120, 168, "real_time", "the next beat needs a stable inherited distance and active side", "both bodies settle into the declared tail state with weapons, feet and gaze still aligned", "reset")
        ],
        "slow_motion": {"enabled": True, "start": 60, "end": 62, "rate": 0.5, "trigger": "the weapon or energy visibly reaches the defense surface", "reason": "the audience must read the single contact and deflection rather than a generic flash", "exit": "restore real-time motion immediately after the contact silhouette and first material response are clear"}
    }


def create_mecha():
    a, b = "CHAR_FORGE", "CHAR_WARD"
    shots = [shot("FILM-S01-SH001", 0, 168,
        "Forge stands left of the service trench; Ward stands right. The east lamp illuminates upper armor edges through localized oil haze; matte steel flats retain their shape.",
        camera("052", 35, "From the south platform, the camera slowly pushes forward half a meter, keeping both machines and the trench visible.", "straight 0.5m push from the south-side platform"), [nail(a, 0.3, "toward screen right"), nail(b, 0.72, "toward screen left")]),
        shot("FILM-S01-SH002", 168, 336,
        "From the same safe side of the action axis, Forge brings its right forearm emitter toward Ward's raised left shield. The service doors and east-wall light retain their established positions; the trench remains between the machines.",
        camera("039", 50, "The camera tracks laterally one meter with the shield edge, then decelerates as the machines recover; the contact line remains unobstructed.", "one-meter eastward track, easing to a hold"), [nail(a, 0.38, "toward screen right"), nail(b, 0.66, "toward screen left")], combat=True, supernatural_vfx=True)]
    shots[0]["audio"]["foley"] = ["Hydraulic pumps cycle under a steady 35 Hz motor rumble; loose floor grit clicks under the planted soles."]
    shots[1]["combat"] = {
        "force_source": "Forge loads its left sole, rotates its hip frame and drives the right shoulder forward.",
        "trajectory": "The forearm follows a short forward arc toward the shield's upper outside edge.",
        "contact": "The emitted stream meets the shield's beveled metal edge.",
        "resistance": "Overlapping shield plates resist the impact and guide its direction downward.",
        "impact_hold": "At the contact beat, the shield silhouette stays readable for two planned frames while dust continues moving.",
        "transfer": "The shield retracts into Ward's shoulder damper; its rear sole slides along the floor.",
        "recoil": "Forge's elbow folds back as its planted left foot absorbs the emitter's recoil.",
        "chain": {"attack": "Forge releases one charge toward the raised shield.", "response": "Ward turns its hip and angles the shield to deflect the stream.",
                  "result": "The charge scrapes the concrete surface, leaving grit and a shallow scar without breaking the supporting slab.",
                  "continuation": "Ward keeps its shield forward; Forge resets its forearm with one fewer charge available."},
        "timing": combat_timing("Forge's emitter travels from screen left toward Ward's shield on screen right; Ward's deflection turns the result down toward the trench, never back through Forge.")}
    shots[1]["vfx"] = fluid("Forge's registered right forearm emitter", "A narrow plasma fluid stream remains continuously attached to the forearm nozzle, folding along the shield bevel before reaching the floor.",
        "The stream grazes the concrete top layer; only its surface chips detach.",
        "Small concrete chips travel outward from the grazing line and fall into the trench.",
        "A thin dust sheet expands close to the floor and thins behind the machines.",
        "Brief orange sparks peel from the shield's contact edge and fade before reaching the doors.",
        "The bright contact core occupies a narrow strip; soft amber spill stays local while the east-wall lamp continues to define the armor planes.")
    initial = {"characters": {a: {"ammo": 4, "trauma_phase": None}, b: {"ammo": 0, "trauma_phase": None}}, "scenes": {"S01": 0}, "props": {"SHIELD": b}}
    events = [{"id": "EV_FIRE", "frame": 205, "shot_id": shots[1]["id"], "domain": "ammo", "target": a, "before": 4, "after": 3, "delta": -1, "reason": "One registered emitter charge is released."},
              {"id": "EV_SCRAPE", "frame": 228, "shot_id": shots[1]["id"], "domain": "damage", "target": "S01", "before": 0, "after": 1, "reason": "The deflected charge chips only the floor surface."}]
    captions = [["Both units and the trench are established.", "Forge keeps its left sole planted.", "Ward presents the left shield.", "The east lamp separates the armor planes.", "Forge aligns its forearm with the shield edge.", "Ward watches the aligned nozzle.", "Both positions remain on the established sides.", "The nozzle and shield line are ready."],
                ["Forge compresses the left leg suspension.", "The right shoulder starts the forward drive.", "The emitter stream extends from the nozzle.", "Ward rotates the shield bevel downward.", "The stream reaches the readable contact edge.", "Deflected energy chips the floor surface.", "Ward brakes through the rear sole.", "Forge recovers the arm with a spent charge."]]
    p = base("EXAMPLE_MECHA", 14, 14, [(a, "Forge", 8.0), (b, "Ward", 8.0)], "维修机库", "Service trench, two human-sized doors and east-wall maintenance lamp", shots)
    p["segments"] = [segment("MECHA_SEG01", shots, "The video uses grounded live-action mechanical rendering with distinct painted steel and matte ceramic surfaces.", "A steady 35 Hz mechanical rumble underlies hydraulic hisses, shield scraping and concrete chips landing inside the trench. The hangar gives each impact a short metallic tail.", "Ref2VA", "media/mecha-contact.png", captions)]
    p["ledger"] = state(initial, shots, events)
    p["asset_prompt"] = "Create one original mechanical confrontation frame inside the registered repair hangar: Forge at left with broad ochre shoulder plates and square visor, Ward at right with overlapping dark plates and silver visor, its left shield facing Forge's right forearm emitter. Preserve both eight-meter body proportions, the service trench between them, the two human-sized doors and the world-east maintenance lamp. Use a 35 mm equivalent view from the south platform with both soles and the shield contact plane visible. Painted steel stays matte across broad panels, worn shield edges show narrow metal highlights, and ceramic joints remain darker with visible thickness. The east lamp passes through localized oil haze onto the upper armor edges, with weak concrete bounce preserving the shadow-side structure. Concentrate detail at the shield bevel and actuator joints; combine distant trusses into broad quiet forms. Avoid disconnected joints, tiled micro-panels and uniform plastic gloss."
    p["story"] = {"synopsis": "Forge试图穿过维修沟，Ward用盾面导走能量。护盾守住通路，Forge损失一发能量，浅层地面损伤成为下一轮站位限制。", "A": "一次射流攻击是否突破防线", "B": "防守者用退让角度取代硬顶", "C": "盾缘导流机制在结果中被证明", "arc_scope": "战斗段落局部选择；不是完整人物成长五阶段"}
    return prepare_fixture_bindings(p)


def base(pid, duration, limit, cast, scene_name, scene_space, shots):
    descriptions = {
        "CHAR_FORGE": "Forge is an eight-meter bipedal machine with broad ochre shoulders, a square visor and a right-forearm emitter.",
        "CHAR_WARD": "Ward is an eight-meter machine with overlapping dark armor, a silver visor and a left-arm steel shield.",
        "CHAR_LU": "Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt.",
        "CHAR_CEN": "Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers.",
        "CHAR_AER": "Aer is a 180-meter bronze guardian with broad wings and a forearm blade channel.",
        "CHAR_GUARDIAN": "The Stone Sentinel is a 160-meter dark stone guardian with a ribbed shield forearm."}
    stage = {
        "EXAMPLE_MECHA": "The repair hangar contains a central trench, two human-sized doors and an east-wall maintenance lamp.",
        "EXAMPLE_DRAMA": "The maintenance room contains one wooden desk, an east-facing window, a west doorway and a brass-key hook on the rear dark wall. Soft east-window light crosses the desk and falls off toward the west wall.",
        "EXAMPLE_COLOSSAL": "A harbor shelf faces a sea wall, with a train causeway and warehouses behind it."}
    for s in shots:
        s["state_description"] = {
            "EXAMPLE_MECHA": "Ward's shield and the supporting concrete slab are intact.",
            "EXAMPLE_DRAMA": "Lu's bandaged right wrist is supported on the desk. The brass key is in his left hand; Cen's receiving palm is empty.",
            "EXAMPLE_COLOSSAL": "The train route is clear and the shield rib intact."}[pid]
    return {"version": "2.0", "project_id": pid, "fps_num": 24, "fps_den": 1,
            # These generated cards are deterministic legacy fixtures used by
            # the v3 contract suite.  Keep their authored prompt bytes stable
            # while new productions use the strict Ref2VA detail gate.
            "prompt_detail_policy": {"profile": "legacy_fixture"},
            "production_total_duration": duration, "generation_clip_limit": limit,
            "scene_registry": [{"id": "S01", "name": scene_name, "space": scene_space,
                 "version": "v1", "entrances": ["west service route"], "exits": ["east service route"],
                 "landmarks": [scene_space], "key_light": "fixed world-east source", "prompt_description": stage[pid]}],
            "character_registry": [{"id": cid, "name": name, "height_m": height,
                 "identity": "Original design; appearance defined by the production prose, not by a franchise reference",
                 "prompt_description": descriptions[cid]} for cid, name, height in cast],
            "shots": shots, "segments": [], "unresolved_threads": [],
            "dispatch_log": [{"contract": "B", "target": "h3-prompt-writing", "implementation": "bundled-guideline compiler"},
                             {"contract": "C", "target": "im2-clean-image", "source_repository": "im2-image-skills", "status": "prompt-planned; no paid image generation"}]}


def create_drama():
    a, b = "CHAR_LU", "CHAR_CEN"
    poses = [nail(a, 0.35, "toward screen right"), nail(b, 0.7, "toward screen left")]
    for pose in poses:
        pose.update(weapon_hand="both hands visible and unarmed", weapon_direction="no weapon present in this scene")
    shots = [shot("FILM-S01-SH001", 0, 240,
        "Lu Chuan, an adult operator with a short scar over the right eyebrow and a gray work jacket, sits on the left side of the maintenance desk. Cen He, an adult technician with tied dark hair and an olive coat, holds her empty palm near the brass key in his hand. The single east window lights their cheek planes and the key; the dark wall behind them stays quiet. His previously bandaged right wrist rests on the desk, so his left hand carries the key.",
        camera("103", 65, "The camera advances twenty centimeters in a medium close two-shot, keeping Lu's eyes, both shoulder lines and his left hand visible without a cut.", "twenty-centimeter slow push toward the shared desk plane"), copy.deepcopy(poses), core_emotion=True),
        shot("FILM-S01-SH002", 240, 480,
        "A medium-close view favors Cen on the right of the wooden desk, with Lu on the left. Cen leaves her open palm between them, with enough distance for Lu to decline. East-window light produces a narrow highlight on the key and a broad shadow across her olive coat.",
        camera("106", 85, "The camera drifts ten centimeters toward Cen while retaining Lu's hand at the lower edge; the desk and window preserve the same spatial axis.", "ten-centimeter drift on the south side of the desk"), copy.deepcopy(poses), core_emotion=True)]
    cues = [["Lu's gaze moves from the key to Cen's open hand and then settles on her eyes.", "He interrupts one inhale, swallows once, and releases a longer breath.", "His left shoulder slowly drops while the injured right wrist stays supported.", "His left thumb releases pressure on the key ring without yet handing it over.", "His lips stay closed until the agreed line, then close again after the final word."],
            ["Cen holds eye contact without widening her eyes or looking at the key.", "Her breath remains quiet, with a small inhale before replying.", "Her shoulders relax while her neck remains upright and still.", "She keeps the palm open; Lu places the key into it, and she closes her fingers only after contact.", "Her voice stays low and clear; both mouths remain closed after her short answer."]]
    for i, s in enumerate(shots):
        s["performance"] = {"beat_id": f"EX-S01-B0{i + 1}", "dominant_track": "gaze" if i == 0 else "body_hands",
            "tracks": {key: {"start": start, "end": end, "cue": cue, "visibility": "medium-close framing includes the face, shoulder line and hands"}
                       for key, start, end, cue in zip(TRACKS, (0, 36, 72, 108, 144), (66, 100, 132, 220, 236), cues[i])}}
        s["audio"] = {"foley": ["Fabric shifts softly at the elbow and the brass key makes one small ring."], "low_frequency_hz": None,
                      "no_low_frequency_reason": "A quiet desk conversation has no designed bass event."}
    shots[0]["performance"]["acting_design"] = {
        "version": "1.0", "mode": "restrained", "character_id": a,
        "objective": "decide whether to transfer responsibility without losing dignity",
        "tactic": "admit the previous refusal, then offer the key as a concrete concession",
        "subtext": "he wants cooperation but tests whether Cen will accept it without taking control by force",
        "trigger": "Cen leaves an empty palm between them instead of reaching for the key",
        "personality_signature": "he lets a practical hand movement speak before he allows his voice to soften",
        "action_units": [
            {"start": 0, "end": 66, "cause": "the empty palm stays available without pressure", "action": "moves his gaze from the key to Cen's palm and then to her eyes", "gaze": "key, palm, then her eyes", "face": "alert at first, then less guarded", "follow_through": "keeps the key in the left hand while the injured right wrist remains supported", "speech_anchor": "silent", "delivery": "hold the first breath for one beat", "prop": "the brass key remains in the left hand", "camera": "keep the eyes, shoulder line and key in one readable plane", "sound": "a small fabric shift follows the gaze change"},
            {"start": 108, "end": 220, "cause": "the admission reaches its final clause", "action": "loosens the left thumb on the key ring and lets the shoulder drop before speaking", "gaze": "steady on Cen's eyes", "face": "mouth controlled, jaw no longer clenched", "follow_through": "the key stays offered rather than snatched back after the line", "speech_anchor": "现在你来", "delivery": "low rough voice, slow pace, a short pause before the final clause", "prop": "the right wrist remains supported on the desk", "camera": "advance twenty centimeters without cutting away from the hand", "sound": "the ring gives one small metal click"}
        ],
        "motion_arc": {"anticipation": "the gaze and thumb prepare the transfer before the voice changes", "accent": "the shoulder drops on the offer of responsibility", "follow_through": "the key remains visible after the line instead of returning to the fist", "settle": "the left hand rests open enough for Cen to receive the key"},
        "speech_delivery": {"voice_timbre": "a low, slightly rough adult male voice", "pace": "slow and deliberate", "pitch": "slightly lower on the admission", "volume": "quiet indoor conversational volume", "pauses": [{"after_text": "没听。", "duration_ms": 220}], "emphasis": [{"text": "你来", "delivery": "give the pronoun and verb a restrained release"}]},
        "cut_behavior": [], "continuity_in": "the key remains in Lu's left hand and the bandaged right wrist stays supported", "continuity_out": "the key is still offered and the left thumb has released pressure", "exclusions": ["added dialogue", "a forceful grab with the injured right wrist", "a smile that turns the admission into a joke"]
    }
    shots[1]["performance"]["acting_design"] = {
        "version": "1.0", "mode": "observational", "character_id": b,
        "objective": "accept the offered responsibility while protecting the shared task",
        "tactic": "keep the palm open until contact, then close it only after the key arrives",
        "subtext": "she accepts the apology without rewarding it with a dramatic reaction",
        "trigger": "Lu's thumb releases the key ring",
        "personality_signature": "she holds eye contact, lets the receiving hand do the emotional work, and answers with a practical invitation",
        "action_units": [
            {"start": 0, "end": 72, "cause": "the key is offered but has not touched her hand", "action": "keeps the receiving palm open and her shoulders level", "gaze": "on Lu's eyes rather than the key", "face": "steady eyes with a small release around the mouth", "follow_through": "does not close the fingers before contact", "speech_anchor": "silent", "delivery": "take one quiet inhale before replying", "prop": "the open palm stays between the two people", "camera": "retain Lu's hand at the lower edge of frame", "sound": "cloth settles at the elbow"},
            {"start": 72, "end": 224, "cause": "the brass key reaches the center of the open palm", "action": "allows the fingers to close around the key and turns the answer toward cooperation", "gaze": "briefly checks the key, then returns to Lu's eyes", "face": "calm acceptance without a triumphant smile", "follow_through": "keeps the closed hand between them instead of hiding it", "speech_anchor": "一起", "delivery": "soft clear consonants at an even pace", "prop": "the key changes hands only after visible contact", "camera": "drift ten centimeters toward her while preserving the desk axis", "sound": "one small key ring after the fingers close"}
        ],
        "motion_arc": {"anticipation": "the empty palm establishes a boundary without reaching", "accent": "the fingers close on physical contact with the key", "follow_through": "the closed hand stays visible as proof of shared action", "settle": "the shoulders relax while the neck remains upright"},
        "speech_delivery": {"voice_timbre": "a clear adult female voice with an even center", "pace": "soft and measured", "pitch": "level, with a slight lift on the invitation", "volume": "quiet indoor conversational volume", "pauses": [{"after_text": "就", "duration_ms": 120}], "emphasis": [{"text": "一起", "delivery": "make the shared-action word warm but practical"}]},
        "cut_behavior": [], "continuity_in": "the empty palm remains open and the brass key is still held by Lu", "continuity_out": "the key rests in Cen's hand and both mouths close after the line", "exclusions": ["a second phone voice", "closing the hand before contact", "a triumphant pose that breaks the quiet negotiation"]
    }
    shots[0]["dialogues"] = [{"speaker_id": "S1", "speaker_name": "Lu Chuan", "language": "Chinese", "text": "上次是我没听。现在你来。", "delivery": "speaking slowly in a low, slightly rough voice", "start": 144, "end": 222, "voiceover": False}]
    shots[1]["dialogues"] = [{"speaker_id": "S2", "speaker_name": "Cen He", "language": "Chinese", "text": "那就一起把门打开。", "delivery": "speaking softly with clear consonants and an even pace", "start": 160, "end": 224, "voiceover": False}]
    p = base("EXAMPLE_DRAMA", 20, 10, [(a, "Lu Chuan", 1.8), (b, "Cen He", 1.7)], "维修室", "One desk, east window, west doorway and a fixed brass-key hook", shots)
    p["segments"] = [segment(f"DRAMA_SEG0{i + 1}", [s], "Live-action cinematic staging uses restrained facial movement and natural cloth response.", "Quiet ventilation and distant rain remain under breathing, a sleeve brushing the desk and the small ring of a brass key.") for i, s in enumerate(shots)]
    for seg in p["segments"]:
        seg["motion_profile"] = {"version": "1.0", "medium": "live_action", "fps": 24, "exposure": "ones", "timing_principle": "let a small preparatory change precede the decisive hand action and hold the resulting state", "camera_principle": "keep the eye-line, receiving hand and prop contact readable before drifting closer", "staging_principle": "preserve the desk axis, left-right positions and the injured wrist limitation", "sound_principle": "keep room tone continuous and make each key contact a local foley event", "cut_style": "continuous"}
    initial = {"characters": {a: {"ammo": 0, "trauma_phase": 1}, b: {"ammo": 0, "trauma_phase": None}}, "scenes": {"S01": 0}, "props": {"BRASS_KEY": a}}
    events = [{"id": "EV_KEY", "frame": 430, "shot_id": shots[1]["id"], "domain": "prop", "target": "BRASS_KEY", "before": a, "after": b, "reason": "Lu visibly places the brass key in Cen's open palm."}]
    p["ledger"] = state(initial, shots, events)
    p["asset_prompt"] = "Create one live-action medium-close two-person keyframe in the registered maintenance room. Lu Chuan, an adult man with a short scar above his right eyebrow and a gray woven work jacket, sits on the left; his bandaged right wrist rests on the desk, and his left hand holds one brass key. Cen He, an adult woman with tied dark hair and an olive coat, sits on the right with an empty palm held between them. Capture the single moment before Lu releases the key. Use a 65 mm equivalent lens from the south side, showing eyes, shoulders and both hands together. One east window casts soft directional light across their cheek planes; a weak wall reflection leaves the shadow side readable. Skin has broad soft highlights, cloth folds retain fibrous edges only near the hands, and the brass key catches a narrow highlight. The rear wall and key hook remain quiet low-frequency shapes. Preserve identity, hand ownership, the bandage and the room geometry. Avoid waxy faces, extra hands and ghost texture."
    p["story"] = {"synopsis": "受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手。陆川承认之前拒绝协作，并把钥匙交给她。岑禾以共同行动回应，右腕伤势没有因为情绪转变消失。", "A": "钥匙是否交出", "B": "独断保护转向共同承担", "C": "前次事故仅由明确台词提出，本段不擅自补回忆", "five_stage_arc": ["开场攥钥匙保留控制", "看见包扎手腕承受旧选择代价", "松开拇指先试探", "交钥匙承担失去控制", "停手不夺回，接受一起行动"]}
    return prepare_fixture_bindings(p)


def create_colossal():
    a, b = "CHAR_AER", "CHAR_GUARDIAN"
    shots = [shot("FILM-S01-SH001", 0, 168,
        "Aer stands left, facing the sentinel across the water. Its left wing extends beyond frame. Low east sunlight defines broad shadow masses.",
        camera("084", 50, "The camera slowly pulls back along the causeway, retaining the train, ankle platform and harbor horizon.", "slow backward travel along the causeway observation platform"), [nail(a, 0.32, "toward screen right"), nail(b, 0.74, "toward screen left")], colossal=True),
        shot("FILM-S01-SH002", 168, 336,
        "Aer braces on the harbor shelf. The sentinel keeps its base against the sea wall, with the maintenance train outside the contact zone.",
        camera("039", 70, "The camera tracks parallel to the harbor wall, holding the shield contact and the ground reference in the same medium-wide view.", "lateral tracking along the original safe side of the harbor wall"), [nail(a, 0.38, "toward screen right"), nail(b, 0.68, "toward screen left")], combat=True, supernatural_vfx=True, colossal=True)]
    for s in shots:
        s["scale_proofs"] = [{"type": "benchmark", "detail": "Ankle and train share depth; one armor joint spans several carriage doors.", "frame_location": "lower-left causeway", "depth_relation": "train and ankle share the same ground plane"},
                             {"type": "environment", "detail": "Wing pressure pushes waves; its shadow spans warehouses.", "frame_location": "harbor midground and opposite shore", "depth_relation": "wave and shadow connect the guardian to the distant port"},
                             {"type": "atmosphere", "detail": "Clouds cross the torso, lowering head contrast while leaving the legs clear.", "frame_location": "upper torso", "depth_relation": "cloud layer sits between camera and upper body"}]
        s["audio"] = {"foley": ["A delayed stone resonance follows the visible contact, with wind and harbor water continuing underneath."], "low_frequency_hz": 35,
                      "classification": "audible_sub_bass", "source": "designed ground-coupled resonance at the harbor wall"}
    shots[0]["audio"]["foley"] = ["Train wheels click along the causeway under wind and harbor water."]
    shots[1]["scale_proofs"] = shots[1]["scale_proofs"][:2]
    shots[1]["combat"] = {"force_source": "Aer's planted foot drives torso rotation into the shoulder.",
        "trajectory": "The stream arcs downward toward the raised forearm.",
        "contact": "Its narrow leading edge meets the shield's outer stone rib.", "resistance": "Layered stone resists compression before its outer rib flakes away.",
        "impact_hold": "The contact outline holds for two planned frames; clouds continue drifting.",
        "transfer": "The retreating forearm transmits load through the torso into the sea-wall brace.",
        "recoil": "Aer lowers its wing and bends the planted knee to brake rotation.",
        "chain": {"attack": "Aer sends one blade-shaped pulse toward the shield.", "response": "The sentinel turns the shield to guide the pulse away from the train.",
                  "result": "The shield rib sheds stone flakes and the sea-wall surface cracks without collapsing the causeway.",
                  "continuation": "Both giants remain supported; the sentinel's damaged shield stays raised for the next exchange."},
        "timing": combat_timing("Aer attacks from screen left toward the sentinel on screen right; the shield turns the pulse down and away from the train, preserving the harbor support line.")}
    shots[1]["vfx"] = fluid("Aer's registered forearm blade channel", "A thin blade-shaped luminous fluid remains attached to Aer's forearm channel before its leading section strikes the shield rib.",
        "The outer stone rib flakes at the contact line; the sea-wall surface cracks but its load-bearing base remains intact.",
        "Broad stone flakes separate only from the damaged rib and drop toward the harbor edge.",
        "A low dust plume follows the shield surface and thins across the water.",
        "Sparse amber light points detach from the fluid edge and extinguish within the contact region.",
        "A narrow white contact line fades to soft amber edges against blue-gray shadow; the east sun remains the dominant world source.")
    initial = {"characters": {a: {"ammo": 2, "trauma_phase": None}, b: {"ammo": 0, "trauma_phase": None}}, "scenes": {"S01": 0}, "props": {"STONE_SHIELD": b}}
    events = [{"id": "EV_PULSE", "frame": 205, "shot_id": shots[1]["id"], "domain": "ammo", "target": a, "before": 2, "after": 1, "delta": -1, "reason": "One stored pulse leaves the registered blade channel."},
              {"id": "EV_WALL", "frame": 228, "shot_id": shots[1]["id"], "domain": "damage", "target": "S01", "before": 0, "after": 2, "reason": "A localized wall facing cracks, but the causeway bearing structure remains usable."},
              {"id": "EV_SHIELD", "frame": 230, "shot_id": shots[1]["id"], "domain": "trauma", "target": b, "before": None, "after": 0, "reason": "The sentinel's shield-arm outer rib breaks and remains functionally weakened."}]
    captions = [["Train and guardian ankle share a depth plane.", "The wing extends beyond the left frame edge.", "The cloud shelf crosses the upper torso.", "A broad shadow crosses warehouses.", "The sentinel holds the opposing shore.", "The water between both bodies remains visible.", "Aer lowers its foot onto the shelf.", "The forearm channel aligns with the shield."],
                ["Aer compresses its planted leg.", "The torso transfers load to the shoulder.", "A blade-shaped fluid pulse extends.", "The sentinel rotates its stone forearm.", "The shield rib receives the readable contact.", "Stone flakes leave the shield rib.", "The wall facing cracks above its support.", "Both giants recover while the cloud layer moves."]]
    p = base("EXAMPLE_COLOSSAL", 14, 14, [(a, "Aer", 180), (b, "Stone Sentinel", 160)], "港湾堤道", "Harbor shelf, train platform, sea-wall and warehouse skyline", shots)
    p["segments"] = [segment("COLOSSAL_SEG01", shots, "The sequence uses large cel-shaded forms, selective painted atmosphere and restrained luminous edges.", "Wind and harbor waves continue beneath a designed 35 Hz ground resonance. Stone impact reaches the observing causeway after the visible contact, with a rolling echo across the water.", "Ref2VA", "media/colossal-contact.png", captions)]
    p["ledger"] = state(initial, shots, events)
    p["asset_prompt"] = "Create one cel-shaded harbor confrontation keyframe with a 180-meter winged bronze guardian at left and a 160-meter stone sentinel at right. The maintenance train touches the guardian's ankle platform at the same depth, while a cloud shelf crosses the upper torso and the wing shadow spans multiple warehouse roofs. Keep one clear vertical silhouette and let the left wing leave the frame. Use a distant causeway observer and a 50 mm equivalent lens; retain the harbor horizon and usable railway route. Low east sunlight defines three large value masses. Bronze panels receive narrow directional highlights, stone shield ribs show broad matte planes and chipped thickness only at the chosen contact area. The train doors remain legible scale modules; distant roof details merge into lower-contrast atmosphere. Restrict luminous energy to a thin forearm-attached blade-shaped fluid edge. Avoid miniature tilt-shift blur, repeated ornamental texture and disconnected load-bearing structure."
    p["story"] = {"synopsis": "港湾中的两座巨体以列车和云带确立尺度。Aer释放一道刃形能量，石哨兵用盾臂把冲击导离列车。盾肋与海墙表层受损，交通承重结构保持，双方带着真实代价进入下一轮。", "A": "能量是否越过防线", "B": "防守者优先保护列车而非自身盾臂", "C": "地形承托和导流机制共同限制巨体行动", "arc_scope": "战斗节选，不虚构完整长片弧光"}
    return prepare_fixture_bindings(p)


def contact_sheet(p, path):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1600, 1000), "#e8e5de")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18) if Path("C:/Windows/Fonts/arial.ttf").exists() else ImageFont.load_default()
    shot_index = {s["id"]: s for s in p["shots"]}
    for panel in p["segments"][0]["panels"]:
        i = panel["panel"] - 1
        x, y = i % 4 * 400, i // 4 * 250
        draw.rectangle((x + 3, y + 3, x + 397, y + 247), fill="#d9d8d2", outline="#373b3d", width=2)
        draw.line((x + 5, y + 170, x + 395, y + 170), fill="#858884", width=2)
        for floor_x in range(35, 400, 60):
            draw.line((x + 200, y + 170, x + floor_x, y + 246), fill="#bbbdb7")
        for floor_y in (185, 210, 240):
            draw.line((x + 5, y + floor_y, x + 395, y + floor_y), fill="#bbbdb7")
        shot_data = shot_index[panel["shot_id"]]
        centers = [c["position"][0] * 400 for c in shot_data["characters"]]
        for k, center in enumerate(centers):
            cx = x + center
            fill = "#696d70" if k == 0 else "#959998"
            draw.rectangle((cx - 17, y + 69, cx + 17, y + 100), fill=fill)
            draw.rectangle((cx - 28, y + 105, cx + 28, y + 160), fill=fill)
            draw.line((cx - 12, y + 160, cx - 22, y + 205), fill=fill, width=12)
            draw.line((cx + 12, y + 160, cx + 25, y + 205), fill=fill, width=12)
            hand = cx + (46 if k == 0 else -46)
            draw.line((cx, y + 121, hand, y + 126), fill=fill, width=11)
            draw.text((cx - 5, y + 78), "A" if k == 0 else "B", fill="white", font=font)
        shield_x = x + centers[1] - 45
        draw.line((shield_x - 5, y + 105, shield_x + 10, y + 161), fill="#3f474a", width=7)
        if p["project_id"] == "EXAMPLE_COLOSSAL":
            wing_x = x + centers[0]
            draw.polygon([(wing_x - 18, y + 111), (x + 4, y + 53), (x + 8, y + 91), (wing_x - 22, y + 139)], fill="#818984")
            draw.line((x + 9, y + 91, x + 385, y + 91), fill="#edf0e9", width=8)
            for tx in (22, 44, 66):
                draw.rectangle((x + tx, y + 203, x + tx + 18, y + 213), fill="#535b61")
                draw.rectangle((x + tx + 4, y + 204, x + tx + 8, y + 208), fill="#dbe3df")
            draw.text((x + 9, y + 181), "train", fill="#353e42", font=font)
        else:
            for door_x in (25, 355):
                draw.rectangle((x + door_x, y + 142, x + door_x + 15, y + 170), outline="#878c8b", width=2)
            draw.polygon([(x + 181, y + 174), (x + 204, y + 174), (x + 226, y + 218), (x + 197, y + 218)], fill="#969b98")
        phase = i % 8
        if i >= 8 and 2 <= phase <= 5:
            launch = x + centers[0] + 44
            reach = shield_x - 3 if phase >= 3 else launch + (shield_x - launch) * 0.65
            draw.line((launch, y + 126, reach, y + 127), fill="#3f5145", width=3)
            if phase >= 4:
                draw.line((shield_x, y + 127, shield_x - 22, y + 204), fill="#3f5145", width=2)
                for dx, dy in ((-12, -4), (3, -14), (16, -2), (-22, -12)):
                    draw.rectangle((shield_x - 22 + dx, y + 204 + dy, shield_x - 18 + dx, y + 208 + dy), fill="#5c6460")
        draw.text((x + 12, y + 11), f"Panel {i+1:02d} | frame {panel['frame']:03d}", fill="#252b30", font=font)
        draw.text((x + 12, y + 224), "BLOCKING ONLY / " + panel["phase"], fill="#252b30", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def image_card(p, name):
    prompt = p["asset_prompt"].replace("registered repair hangar", "repair hangar").replace("registered maintenance room", "maintenance room")
    if name == "01-mecha":
        prompt = prompt.replace("one original mechanical confrontation frame", "one live-action mechanical confrontation frame")
    if name == "03-colossal":
        prompt = prompt.replace("stone shield ribs show broad matte planes and chipped thickness only at the chosen contact area", "the intact stone shield ribs show broad matte planes and clear edge thickness")
        prompt = prompt.replace("Restrict luminous energy to a thin forearm-attached blade-shaped fluid edge", "Capture the grounded opening stance before the attack; the forearm channel is unlit and no energy has been emitted")
    if name == "02-drama":
        prompt = " ".join(c["prompt_description"] for c in p["character_registry"]) + " " + prompt
    # The input diagram supplies blocking only, never a face or costume identity.
    refs = []
    if p["segments"][0].get("panels"):
        first, second = [c["name"] for c in p["character_registry"]]
        refs = [{"image": 1, "file": p["segments"][0]["references"][0]["file"], "role": "composition",
                 "subject": f"the confrontation between {first} and {second}",
                 "preserve": f"only Panel 01's left-right placement and ground line; the left block marked A denotes {first}, and the right block marked B denotes {second}",
                 "exclude": "the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image"}]
    return {"id": "ASSET_" + name.upper().replace("-", "_"), "name": p["story"]["synopsis"].split("。")[0],
            "target_skill": "im2-clean-image", "source_repository": "im2-image-skills",
            "recipe": "portrait" if name == "02-drama" else "hard_surface" if name == "01-mecha" else "fantasy",
            "mode": "GENERATE", "reference_policy": "required" if refs else "none", "references": refs,
            "heavy_scene": name != "02-drama",
            "structure_lock": {"camera": p["shots"][0]["camera"]["description"], "landmarks_topology": p["scene_registry"][0]["prompt_description"],
                               "depth_occlusion": "Keep the stated foreground, subject and background planes separate.",
                               "mass_support": "Feet and load-bearing structures remain in physical contact with the stated ground plane."},
            "transaction": {"change": "Create one opening keyframe before the exchange.",
                            "preserve": "The written identities, left-right placement, costume, material and opening prop ownership.",
                            "rebuild": "Render coherent anatomy, surfaces and shared world lighting from the written design."},
            "seven_steps": [{"step": i + 1, "content": text} for i, text in enumerate([
                " ".join(c["prompt_description"] for c in p["character_registry"]) + " " + p["shots"][0]["state_description"],
                p["segments"][0]["style"], p["shots"][0]["camera"]["description"],
                "Use the described world-east source and separate skin, cloth, metal or stone by their material response.",
                "Concentrate visible detail on the subjects and current narrative object; keep the distant background quiet.",
                "Restrict wear, texture and small surface marks to the explicitly described near surfaces.",
                "Avoid extra limbs, disconnected supports, ghost texture and unrequested text."])],
            "prompt": prompt, "generation_status": "planned", "actual_settings": None}


def render_card(p, filename, title, datafile):
    lines = [f"# {title}", "", "状态：完整生产卡及提示词已编译；图像仅有随包灰模构图示意，未调用影视生成模型。", "",
             f"- 总时长：{p['production_total_duration']} 秒；最大生成窗：{p['generation_clip_limit']} 秒；24 fps。",
             f"- 数据真值源：[{datafile}]({datafile})。", "- 声音：现场音；非叙事配乐 N/A。", "", "## 剧情与人物选择", "", p["story"]["synopsis"], ""]
    for key in ("A", "B", "C"):
        lines.append(f"{key}：{p['story'][key]}。")
    if "five_stage_arc" in p["story"]:
        lines.extend(["", "五阶段可见弧光：" + " → ".join(p["story"]["five_stage_arc"]) + "。"])
    lines.extend(["", "## 登记场景与人物", "", "```json", json.dumps({"scenes": p["scene_registry"], "characters": p["character_registry"]}, ensure_ascii=False, indent=2), "```", "", "## 逐镜生产卡", ""])
    for s in p["shots"]:
        lines.extend([f"### {s['id']}｜{s['start_frame']/24:.3f}–{s['end_frame']/24:.3f} 秒", "", s["visual"], "", "```json", json.dumps(s, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## GPT Image 2 / 2.5 可直接复制提示词", "", "按主体、媒介、构图、光材、密度、受控细节、当前风险顺序编译。执行尺寸和采样设置留给实际出图入口。", ""])
    for card in p["asset_cards"]:
        lines.append("参考图：不需要，可纯文字生成。" if not card["references"] else "参考图：必须上传下列文件；只继承明确列出的用途。")
        lines.append("")
        for ref in card["references"]:
            lines.extend([f"- Reference image {ref['image']}：[上传该图]({ref['file']})；用途：{ref['role']}；保留：{ref['preserve']}；不继承：{ref['exclude']}。", ""])
        lines.extend(["```text", render_asset_prompt(card).rstrip(), "```", ""])
    for seg in p["segments"]:
        if seg.get("panels"):
            lines.extend([f"## {seg['id']}｜16格逐项映射", "", f"![灰模构图示意]({seg['references'][0]['file']})", "", "灰模不代表最终外貌、材质或准确摄影轨迹。", "", "| Panel | Shot | 全局帧 | 单相位 |", "|---|---|---:|---|"])
            lines.extend(f"| {x['panel']:02d} | {x['shot_id']} | {x['frame']} | {x['description']} |" for x in seg["panels"])
        lines.extend(["", f"## {seg['id']}｜H3 {seg['mode']} 完整提示词", "", "```text", compile_segment(p, seg).rstrip(), "```", ""])
    lines.extend(["## 场记末尾回写", "", "```json", json.dumps(p["ledger"], ensure_ascii=False, indent=2), "```", "", "## 结果验收", "", "运行 audit_storyboard_quality.py 检查当前数据。实际生成后逐帧看身份、接触、主光、伤势和道具；音轨核对对白与频谱。未生成时视觉及声学实测保持 UNVERIFIED。", ""])
    (EXAMPLES / filename).write_text("\n".join(lines), encoding="utf-8")


def build():
    for factory, name, card, title in [
        (create_mecha, "01-mecha", "01-hollywood-mecha-combat-h3.md", "重工业机甲｜盾缘导流"),
        (create_drama, "02-drama", "02-dramatic-micro-acting-h3.md", "文戏对峙｜把钥匙交出来"),
        (create_colossal, "03-colossal", "03-colossal-scale-combat-h3.md", "超巨构神魔对决｜港湾守线")]:
        p = factory()
        # Final prose must not imply access to an internal registration document.
        for s in p["shots"]:
            s["visual"] = s["visual"].replace("registered repair hangar", "repair hangar")
        p["asset_cards"] = [image_card(p, name)]
        p["asset_prompt"] = p["asset_cards"][0]["prompt"]
        datafile = name + ".production.json"
        write_json(EXAMPLES / datafile, p)
        if name == "01-mecha":
            write_json(ROOT / "templates/shot-spec.yaml", p["shots"][1])
        if p["segments"][0].get("panels"):
            contact_sheet(p, EXAMPLES / p["segments"][0]["references"][0]["file"])
        render_card(p, card, title, datafile)
        if name == "02-drama":
            script = {"production_total_duration": 20, "scene_registry": p["scene_registry"],
                      "script_scenes": [{"id": "SC01", "scene_id": "S01", "scene_name": "维修室", "thread": "B",
                          "text": "夜，维修室内。陆川右腕缠着绷带，搁在桌面，左手攥着黄铜钥匙。岑禾把空掌停在两人之间。陆川看她的手，吸气中止，肩线落下，拇指逐渐松开。他低声说：上次是我没听。现在你来。岑禾仍保持空掌，直到钥匙落入掌心才收拢手指。她说：那就一起把门打开。陆川没有伸手夺回，右腕始终由桌面支撑。"}]}
            write_json(ROOT / "templates/script-stage.json", script)
            write_json(ROOT / "templates/asset-stage.json", {"asset_cards": copy.deepcopy(p["asset_cards"])})
    print("Built three complete production datasets, three cards and two blocking sheets")


if __name__ == "__main__":
    build()
