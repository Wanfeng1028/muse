"""Build three v3.2 examples that exercise different acting and reference conditions."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from build_examples import create_drama, image_card, write_json

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def replace_nested(value, replacements):
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [replace_nested(item, replacements) for item in value]
    if isinstance(value, dict):
        return {replace_nested(key, replacements): replace_nested(item, replacements) for key, item in value.items()}
    return value


def base_variant(project_id, replacements):
    production = replace_nested(copy.deepcopy(create_drama()), replacements)
    production["project_id"] = project_id
    for shot in production["shots"]:
        shot["visual"] = shot["visual"].replace("registered ", "")
    return production


def update_asset(production, asset_id, name, prompt, reference=None, state_version=None, asset_version="v1.0"):
    card = copy.deepcopy(production["asset_cards"][0]) if production.get("asset_cards") else image_card(production, "02-drama")
    card.update({"id": asset_id, "name": name, "asset_version": asset_version, "prompt": prompt,
                 "reference_policy": "required" if reference else "none", "references": [reference] if reference else []})
    if state_version:
        card["state_version"] = state_version
    else:
        card.pop("state_version", None)
    production["asset_cards"] = [card]
    production["asset_prompt"] = prompt


def shrink_two_shot_sequence(production):
    """Convert the 20-second drama fixture into a legal 10-second two-shot clip."""
    for shot in production["shots"]:
        shot["start_frame"] //= 2
        shot["end_frame"] //= 2
        for line in shot.get("dialogues", []):
            line["start"] //= 2
            line["end"] //= 2
        performance = shot.get("performance", {})
        for track in performance.get("tracks", {}).values():
            track["start"] //= 2
            track["end"] //= 2
        design = performance.get("acting_design", {})
        for unit in design.get("action_units", []):
            unit["start"] //= 2
            unit["end"] //= 2
        for cut in design.get("cut_behavior", []):
            cut["at"] //= 2
    for event in production.get("ledger", {}).get("events", []):
        event["frame"] //= 2
    for segment in production["segments"]:
        segment["start_frame"] //= 2
        segment["end_frame"] //= 2
        segment["generation_clip_duration"] = 10
    production["production_total_duration"] = 10
    production["generation_clip_limit"] = 10


def animated_phone():
    p = base_variant("EXAMPLE_ANIMATED_PHONE", {"CHAR_LU": "CHAR_QIAN", "CHAR_CEN": "CHAR_HANDLER",
        "Lu Chuan": "Chen Qianyu", "Cen He": "the unseen handler", "maintenance room": "a futuristic office",
        "east window": "wide glass window", "brass key": "phone", "key": "phone"})
    p["character_registry"][0]["prompt_description"] = (
        "Chen Qianyu is an adult woman with a compact athletic build, pale skin, long black hair with one teal streak, "
        "dark horn ornaments, red eyes, a white and sky-blue outfit, blue gloves, black knee boots and a long tail. "
        "She holds a phone to her left ear with her left hand."
    )
    p["character_registry"][1]["prompt_description"] = "The unseen handler is never visible; only a silent phone connection is present."
    p["scene_registry"][0]["prompt_description"] = (
        "The futuristic office has a wide glass window overlooking a bright green cliff with hanging vines, a desk with two screens, "
        "a dark office chair, a glossy dark floor marked by white and yellow guide lines, a rear corridor doorway and stacked crates on the right."
    )
    p["shots"][0]["visual"] = (
        "Chen Qianyu stands beside the dark office chair near the glass window, facing the window with a phone at her left ear. "
        "The bright green cliff remains behind her while the room falls softly out of focus."
    )
    p["shots"][1]["visual"] = (
        "A direct hard cut shows Chen Qianyu from behind beside the chair. Her shoulder blades, long hair, tail and the phone hand fill the frame; "
        "the green cliff beyond her softens into bokeh."
    )
    p["shots"][0]["state_description"] = "The phone is pressed to Chen Qianyu's left ear; her eyes are closed in a short laugh and her right hand hangs free."
    p["shots"][1]["state_description"] = "The phone remains at her left ear after the hard cut; her right hand is free and her tail hangs behind her legs."
    for shot in p["shots"]:
        shot["characters"] = shot["characters"][:1]
    p["shots"][0]["camera"].update({"description": "The camera advances twenty centimeters in a close view of Chen Qianyu's head, shoulders and phone hand without a cut.", "path": "twenty-centimeter slow push toward Chen Qianyu beside the window", "target": "her face, phone hand and the window edge"})
    p["shots"][1]["camera"].update({"description": "The camera holds a close back view of Chen Qianyu and drifts ten centimeters toward her shoulder blades while the window stays in the background.", "path": "ten-centimeter drift toward the back view beside the window", "target": "her shoulder blades, tail, phone hand and window bokeh"})
    p["shots"][0]["performance"]["tracks"] = {
        "gaze": {"start": 0, "end": 66, "cue": "Chen Qianyu's gaze stays toward the window with her eyes closed in the opening laugh, then opens toward the bright cliff.", "visibility": "close framing keeps her eyes and phone hand readable"},
        "breath": {"start": 0, "end": 100, "cue": "Her laugh releases one short breath before the speaking breath begins.", "visibility": "the shoulders and mouth remain visible in close view"},
        "shoulder": {"start": 72, "end": 132, "cue": "Her chin lifts and the shoulder line rises slightly before the right-hand slice.", "visibility": "the close frame includes the shoulder line"},
        "body_hands": {"start": 108, "end": 220, "cue": "Her left hand keeps the phone at the ear while the free right hand begins a controlled downward slice.", "visibility": "both hands and the phone remain inside the frame"},
        "dialogue": {"start": 144, "end": 236, "cue": "The voice shifts from an easy laugh to a hard, cocky delivery without changing the phone position.", "visibility": "mouth, jaw and phone hand stay readable"}}
    p["shots"][1]["performance"]["tracks"] = {
        "gaze": {"start": 0, "end": 66, "cue": "Her face remains toward the window; only the corner of the smirk turns slightly toward the shoulder.", "visibility": "the back close-up retains the head angle and hair edge"},
        "breath": {"start": 0, "end": 100, "cue": "Her voice carries across the cut with steady breath and no second phone voice.", "visibility": "the shoulder blades reveal the breath rhythm"},
        "shoulder": {"start": 72, "end": 132, "cue": "The shoulder line follows the right-hand slice, then settles as the arm opens outward.", "visibility": "the back close-up keeps both shoulder blades visible"},
        "body_hands": {"start": 108, "end": 220, "cue": "The right hand sweeps outward, cocks the hip and finally returns to the hip while the left hand keeps the phone fixed.", "visibility": "the close view includes the phone, free hand and tail"},
        "dialogue": {"start": 144, "end": 236, "cue": "The delivery stays confident through the title and reward promise, then stops into a held smug pose.", "visibility": "the head angle and shoulder rhythm remain visible"}}
    phone_source = "没错，干掉她之后我就是监督。到时候调动物资，少不了给你大笔分红！"
    p["shots"][0]["dialogues"] = [{"speaker_id": "S1", "speaker_name": "Chen Qianyu", "language": "Chinese", "text": "没错，",
        "source_text": phone_source, "delivery": "laughing first, then speaking in a hard, cocky voice", "start": 48, "end": 240, "voiceover": False, "utterance_id": "U_PHONE"}]
    p["shots"][1]["dialogues"] = [{"speaker_id": "S1", "speaker_name": "Chen Qianyu", "language": "Chinese",
        "text": "干掉她之后我就是监督。到时候调动物资，少不了给你大笔分红！", "source_text": phone_source, "delivery": "continuing in the same smug, forceful voice", "start": 0, "end": 240,
        "voiceover": False, "utterance_id": "U_PHONE"}]
    first = p["shots"][0]["performance"]["acting_design"]
    first.update({"character_id": "CHAR_QIAN", "objective": "secure an accomplice while claiming future authority", "tactic": "laugh, then turn the request into a confident promise of reward",
                  "subtext": "she treats a dangerous order as if the outcome already belongs to her", "trigger": "the handler accepts the premise without interrupting",
                  "personality_signature": "she uses a laugh, a lifted chin and broad hand shapes to make control look effortless",
                  "continuity_out": "the sentence is still in progress as the camera cuts to her back"})
    first["action_units"][0] = {"start": 0, "end": 66, "cause": "the phone connection is quiet and she chooses to make the order sound effortless", "action": "laughs with her eyes closed, then opens them toward the bright cliff", "gaze": "window, then phone", "face": "broad laugh softens into a smug half-smile", "follow_through": "the laugh leaves a visible breath before the first hard word", "speech_anchor": "silent", "delivery": "one short laugh before the line", "prop": "the phone stays at the left ear", "camera": "keep the face, phone hand and window edge in one close plane", "sound": "a short easy laugh and a small jacket rustle"}
    first["action_units"][1].update({"cause": "the short laugh ends and she commits to the order", "action": "opens her eyes, lifts her chin and slices the free right hand down once",
                                     "gaze": "toward the window, then briefly toward the phone", "face": "eyes open into a smug half-smile",
                                     "follow_through": "the hand remains low as the voice continues into the cut", "speech_anchor": "没错", "delivery": "hard consonants with a compact laugh before the phrase", "prop": "the phone stays pressed to the left ear", "camera": "advance twenty centimeters without cutting away from the face, phone and window", "sound": "the jacket rustles as the free hand slices"})
    first["motion_arc"] = {"anticipation": "the laugh ends and the chin rises before the first hard word", "accent": "the right-hand slice lands on the order's opening certainty", "follow_through": "the phone hand stays fixed while the free hand completes its downward path", "settle": "the sentence remains in progress as the camera cuts to the back view"}
    first["speech_delivery"] = {"voice_timbre": "a bright adult female voice with a confident center", "pace": "quick laugh followed by deliberate speech", "pitch": "slightly higher on the laugh, then level and firm", "volume": "clear indoor phone-call volume", "pauses": [{"after_text": "没错", "duration_ms": 90}], "emphasis": [{"text": "没错", "delivery": "make the certainty land before the cut"}]}
    first["continuity_in"] = "the phone is already pressed to the left ear and the right hand is free"
    first["exclusions"] = ["added dialogue", "switching the phone to the right hand", "a second phone voice", "random tail motion"]
    for shot in p["shots"]:
        shot["audio"]["no_low_frequency_reason"] = "A quiet phone conversation has no designed bass event."
    first["speech_delivery"].update({"pauses": [{"after_text": "没错", "duration_ms": 90}], "emphasis": [{"text": "没错", "delivery": "make the certainty land before the cut"}]})
    first["cut_behavior"] = [{"at": 240, "type": "hard_cut", "audio_carries": True, "action_carries": True,
        "entry_state": "the order is in progress and the right hand is completing its downward slice", "exit_state": "the same voice continues over the back view while the tail begins to flick"}]
    second = p["shots"][1]["performance"]["acting_design"]
    second.update({"character_id": "CHAR_QIAN", "mode": "expressive", "objective": "turn a private order into a public claim of control", "tactic": "alternate cutting gestures with a generous promise and finish in a self-satisfied pose",
                   "subtext": "she is selling certainty to the person on the phone and to herself", "trigger": "the voice carries across the cut into the back view",
                   "personality_signature": "the tail, hip and shoulders echo each verbal promise without becoming random motion",
                   "continuity_in": "the first phrase continues from the previous close view", "continuity_out": "the phone stays at the left ear and the right hand settles on the hip"})
    second["action_units"] = [
        {"start": 0, "end": 64, "cause": "the carried sentence reaches its decisive order", "action": "swings the free right hand up and slices it down flat while the tail flicks once", "gaze": "face remains toward the window", "face": "smug mouth hidden except for the cheek line", "follow_through": "the shoulder finishes the slice before relaxing", "speech_anchor": "干掉她", "delivery": "forceful attack on the first verb", "prop": "phone remains fixed at the left ear", "camera": "hold the close back view so the shoulder blades and tail stay readable", "sound": "jacket fabric snaps softly with the hand slice"},
        {"start": 64, "end": 156, "cause": "the promise of authority begins", "action": "sweeps the right arm outward in a generous arc and cocks her hip", "gaze": "still toward the bright window", "face": "chin lifted, neck relaxed", "follow_through": "the arm reaches its widest point before returning toward the waist", "speech_anchor": "监督", "delivery": "slightly slower, as if savoring the title", "prop": "the tail counterbalances the hip shift", "camera": "remain close and static while the body supplies the scale change", "sound": "a boot scuffs once on the glossy floor"},
        {"start": 156, "end": 232, "cause": "the promised reward reaches its final amount", "action": "plants the right hand on the hip, tips her head back over the shoulder and rolls both shoulders back", "gaze": "toward the window with a sidelong glance over the shoulder", "face": "the corner of a smirk becomes visible", "follow_through": "lowers the hand slightly and holds the pose", "speech_anchor": "分红", "delivery": "bright, confident finish without shouting", "prop": "phone remains at the left ear and never produces a second voice", "camera": "hold the back close-up until the final frame", "sound": "shoulder cloth rustles and then stops"}
    ]
    second["speech_delivery"].update({"pauses": [{"after_text": "监督", "duration_ms": 160}], "emphasis": [{"text": "分红", "delivery": "stretch the final reward word with satisfied certainty"}]})
    second["motion_arc"] = {"anticipation": "the carried voice reaches the order before the free hand rises", "accent": "the slice, hip cock and shoulder roll land on successive speech promises", "follow_through": "the tail and shoulders echo the gesture while the phone remains fixed", "settle": "the right hand lowers to the hip and the smug pose holds through the final frame"}
    second["exclusions"] = ["a second phone voice", "moving the phone away from the left ear", "random tail motion", "an extra visible handler"]
    shrink_two_shot_sequence(p)
    p["segments"] = [{"id": "ANIME_PHONE_SEG01", "start_frame": 0, "end_frame": 240, "shot_ids": [s["id"] for s in p["shots"]], "generation_clip_duration": 10,
        "mode": "Ref2VA", "style": "Japanese TV anime aesthetics: clean 2D cel animation on twos and threes at 24 fps with painted backgrounds and direct hard cuts.",
        "overall_soundscape": "Quiet indoor room tone and a low ventilation hum continue under a short laugh, chair creak, jacket rustle and one soft boot scuff.", "non_diegetic_music": "N/A",
        "references": [{"label": "<Picture 1>", "file": "media/PENDING-anime-phone-approved.png", "role": "first-frame composition and pose anchor",
            "shot_ids": [s['id'] for s in p['shots']], "anchor_shot_ids": [p['shots'][0]['id']], "asset_version": "planned-v1", "entity_ids": ["CHAR_QIAN", "S01"],
            "preserve": "approved character identity and office layout across both shots; opening pose only in Shot 1", "exclude": "source pose after the opening, future gestures, captions and unrelated characters",
            "definition": "<Picture 1> is the first-frame pose and close composition for Chen Qianyu beside the office chair; it supplies the laughing expression, phone-at-left-ear placement and opening framing only.",
            "retention": "<Picture 1> (appears in [Shot 1]): fully_preserved - retain the opening expression, phone hand and close framing while using the written office and character design."}],
        "summary": "[keyframe completion + reference generation] The target video starts from <Picture 1> and follows Chen Qianyu's smug phone performance through a hard cut to her back view.",
        "subjects": [{"label": "<Subject 1>", "entity_id": "CHAR_QIAN", "definition": "<Subject 1> is Chen Qianyu in <Picture 1>, with dark horn ornaments, long black hair with a teal streak, red eyes, a white and sky-blue outfit, blue gloves, black knee boots and a long tail.",
            "retention": "<Subject 1> (appears in [Shot 1] and [Shot 2]): fully_preserved - preserve identity, costume, hair, horns and tail across the cut."},
            {"label": "<Subject 2>", "entity_id": "S01", "definition": "<Subject 2> is the futuristic office established by the written scene and the composition of <Picture 1>: glass window, green cliff, desk, chair, guide-lined floor, doorway and crates.",
            "retention": "<Subject 2> (appears in [Shot 1] and [Shot 2]): fully_preserved - retain the landmark layout while allowing the background to soften in the close back view."}],
        "motion_profile": {"version": "1.0", "medium": "2d_cel", "fps": 24, "exposure": "twos_and_threes", "timing_principle": "hold the laugh for one beat, then let each hand accent land on a precise speech beat", "camera_principle": "use a close view and one direct hard cut without changing the action axis", "staging_principle": "keep the phone hand, tail and window landmarks readable through the cut", "sound_principle": "carry the same voice and room tone across the hard cut while foley stays local", "cut_style": "hard_cut"}}]
    p["asset_cards"] = []
    update_asset(p, "ASSET_ANIME_PHONE", "陈千语·办公室电话戏", "Create a clean 2D cel-animation character-and-environment keyframe of Chen Qianyu beside a dark office chair near a wide glass window. She has dark horn ornaments, long black hair with one teal streak, red eyes, a white and sky-blue outfit, blue gloves, black knee boots and a long tail. Her left hand holds a phone to her left ear; her eyes are closed in a broad laugh and her free right hand hangs loose. The futuristic office contains two screens, a glossy dark floor with white and yellow guide lines, a rear corridor doorway and stacked crates. The bright green cliff and hanging vines outside the window provide the only saturated background color. Use painted backgrounds, clean linework, flat cel shading and a readable close composition. Keep one complete character, one phone and one tail; avoid extra text, captions, duplicate limbs or a second phone voice.",
        None, "laughing-open", "v1.1")
    p['example_delivery_expectation'] = 'DRAFT_MISSING_REFERENCES'
    p['reference_review'] = 'Correct character/office media pending. The unrelated ink bridge diagram is not a valid source.'
    p = replace_nested(p, {"Lu": "Chen Qianyu", "Cen": "the handler", "injured right wrist": "right hand", "right wrist": "right hand", "the handler's palm": "the phone", "empty palm": "quiet phone connection", "palm": "phone", "admission": "dangerous order"})
    p["scene_registry"][0]["space"] = "Wide glass window, desk with two screens, dark office chair, guide-lined floor, rear corridor doorway and stacked crates"
    p["scene_registry"][0]["landmarks"] = [p["scene_registry"][0]["space"]]
    initial = {"characters": {"CHAR_QIAN": {"ammo": 0, "trauma_phase": None}, "CHAR_HANDLER": {"ammo": 0, "trauma_phase": None}}, "scenes": {"S01": 0}, "props": {"PHONE": "CHAR_QIAN"}}
    p["ledger"] = {"initial": initial, "events": [], "final": copy.deepcopy(initial)}
    for shot in p["shots"]:
        shot["outcome_events"] = []
        shot["state_in"] = copy.deepcopy(initial)
        shot["state_out"] = copy.deepcopy(initial)
    return p


def comedy_misunderstanding():
    p = base_variant("EXAMPLE_COMEDY_MISUNDERSTANDING", {"CHAR_LU": "CHAR_PEI", "CHAR_CEN": "CHAR_TAO", "Lu Chuan": "Pei Jun", "Cen He": "Tao Lin", "maintenance room": "a cramped prop workshop", "brass key": "a red umbrella"})
    p["character_registry"][0]["prompt_description"] = "Pei Jun is a slim adult stage manager with a round face, cropped black hair, a mustard vest over a white shirt and oversized work gloves."
    p["character_registry"][1]["prompt_description"] = "Tao Lin is an adult performer with a compact build, a short bob haircut, a cobalt rehearsal jacket and a red scarf tied loosely at the neck."
    p["scene_registry"][0]["prompt_description"] = "The cramped prop workshop has a tilted worktable, hanging costume racks, a rolling ladder, a red umbrella hook and one warm ceiling lamp."
    p["shots"][0]["visual"] = "Pei Jun stands left of the tilted worktable, holding an empty umbrella hook and looking at Tao Lin. Tao Lin stands right with both gloved hands raised, trying to appear innocent."
    p["shots"][1]["visual"] = "The camera cuts wider as the red umbrella rolls out from behind the ladder by itself. Pei Jun freezes in disbelief while Tao Lin slowly points at the umbrella and then at the ceiling."
    p["shots"][0]["state_description"] = "The umbrella hook is empty; Pei Jun's left hand points at it and Tao Lin's raised hands are empty."
    p["shots"][1]["state_description"] = "The umbrella is on the floor behind the ladder; both performers remain upright and the hook is still empty."
    p["shots"][0]["dialogues"] = [{"speaker_id": "S1", "speaker_name": "Pei Jun", "language": "Chinese", "text": "你说你没拿？", "delivery": "accusing, then suddenly uncertain", "start": 128, "end": 220, "voiceover": False}]
    p["shots"][1]["dialogues"] = [{"speaker_id": "S2", "speaker_name": "Tao Lin", "language": "Chinese", "text": "它自己跑了！", "delivery": "dead serious while pointing at the moving umbrella", "start": 72, "end": 150, "voiceover": False}]
    for shot in p["shots"]:
        design = shot["performance"]["acting_design"]
        design["mode"] = "comic"
        design["character_id"] = "CHAR_PEI" if shot is p["shots"][0] else "CHAR_TAO"
        design["objective"] = "win the accusation without being caught by the visible prop movement"
        design["tactic"] = "overcommit to a pose, wait for the prop to contradict it, then redirect blame"
        design["subtext"] = "both performers know the denial is weak but try to preserve a straight face"
        design["trigger"] = "the empty hook becomes visible and the umbrella makes a delayed rolling sound"
        design["personality_signature"] = "a precise freeze is followed by one oversized gesture and a delayed reaction"
        design["motion_arc"].update({"anticipation": "hold the accusation or denial one beat too long", "accent": "hit the prop reveal with a sudden head turn", "follow_through": "let the pointing hand overshoot the target", "settle": "return to an almost normal pose while the eyes remain fixed on the umbrella"})
        design["speech_delivery"].update({"voice_timbre": "clear theatrical adult voice", "pace": "quick setup with a deliberate pause before the excuse", "pitch": "rises on the question or exclamation", "volume": "medium indoor rehearsal volume", "pauses": [], "emphasis": []})
        for unit in design.get("action_units", []):
            unit["speech_anchor"] = "silent"
    p["segments"] = []
    for i, shot in enumerate(p["shots"], 1):
        p["segments"].append({"id": f"COMEDY_SEG0{i}", "start_frame": shot["start_frame"], "end_frame": shot["end_frame"], "shot_ids": [shot["id"]],
            "generation_clip_duration": 10, "mode": "T2VA", "style": "Live-action physical comedy with readable pauses, crisp prop timing and restrained handheld camera response.",
            "overall_soundscape": "Workshop room tone continues under glove squeaks, a delayed umbrella roll and a small ladder rattle.", "non_diegetic_music": "Short pizzicato strings at a brisk tempo punctuate the prop reveal.", "references": [],
            "motion_profile": {"version": "1.0", "medium": "live_action", "fps": 24, "exposure": "ones", "timing_principle": "hold the false certainty one beat before the prop supplies the contradiction", "camera_principle": "keep the face and prop entrance in the same readable axis", "staging_principle": "preserve the empty hook, ladder and red umbrella path", "sound_principle": "delay the rolling prop sound until after the accusation lands", "cut_style": "continuous"}})
    update_asset(p, "ASSET_COMEDY_UMBRELLA", "红伞误会·工作坊", "Create a live-action wide keyframe in a cramped prop workshop. Pei Jun, a slim adult stage manager in a mustard vest, points at an empty red umbrella hook beside a tilted worktable while Tao Lin, an adult performer in a cobalt rehearsal jacket and loose red scarf, raises both empty gloved hands in exaggerated innocence. A rolling ladder, costume racks and one warm ceiling lamp establish the space. Keep the empty hook visibly readable, leave a clear floor path behind the ladder for the later red umbrella reveal, and preserve grounded feet and contact shadows. Avoid captions, extra umbrellas, duplicated hands and frozen theatrical smiles.")
    return p


def suspense_whisper():
    p = base_variant("EXAMPLE_SUSPENSE_WHISPER", {"CHAR_LU": "CHAR_NING", "CHAR_CEN": "CHAR_ECHO", "Lu Chuan": "Ning Yue", "Cen He": "the reflected figure", "maintenance room": "an abandoned archive", "brass key": "a metal drawer"})
    p["character_registry"][0]["prompt_description"] = "Ning Yue is an adult archivist with a narrow face, tied black hair, a dark raincoat and a small flashlight held low in her right hand."
    p["character_registry"][1]["prompt_description"] = "The reflected figure is a pale human silhouette visible only as a delayed reflection in the archive glass; it never speaks or touches Ning Yue."
    p["scene_registry"][0]["prompt_description"] = "The abandoned archive has tall metal shelves, a glass records room, a dusty tile floor, a dead emergency light and one narrow flashlight beam cutting from the doorway."
    p["shots"][0]["visual"] = "Ning Yue begins in the stance and framing established by <Picture 1> at the left of the glass records room, listening with the flashlight held low. The reflection behind the glass is delayed by one breath and does not match her shoulders."
    p["shots"][1]["visual"] = "The camera cuts to a closer angle on the glass. Ning Yue stops breathing and slowly turns her eyes without turning her head; the reflected figure raises one hand a beat later."
    p["shots"][0]["state_description"] = "Ning Yue's flashlight is on and held low; her shoulders are still and the reflected figure's hand is down."
    p["shots"][1]["state_description"] = "Ning Yue remains frozen beside the glass; the delayed reflection has begun to raise one hand while the flashlight beam stays on the floor."
    for shot in p["shots"]:
        shot["dialogues"] = []
        shot["audio"] = {"foley": ["A low ventilation tick repeats irregularly.", "Ning Yue's breath stops before the delayed reflection moves."], "low_frequency_hz": None, "no_low_frequency_reason": "The scene is driven by near-silent room tone, breath and a delayed glass movement rather than bass."}
        design = shot["performance"]["acting_design"]
        design["mode"] = "observational"
        design["character_id"] = "CHAR_NING"
        design["objective"] = "confirm whether the reflection is following her or acting independently"
        design["tactic"] = "reduce movement until the mismatch becomes measurable"
        design["subtext"] = "she refuses to give the reflected figure a visible reaction to copy"
        design["trigger"] = "the reflection moves after her breath stops"
        design["personality_signature"] = "fear is externalized as held breath, fixed shoulders and a tiny eye movement"
        design["speech_delivery"] = {"voice_timbre": "nearly inaudible adult whisper", "pace": "no speech; breath controls the timing", "pitch": "flat", "volume": "silent", "pauses": [], "emphasis": []}
        for unit in design.get("action_units", []):
            unit["speech_anchor"] = "silent"
        design["exclusions"] = ["spoken exposition", "a sudden turn toward the reflection", "a flashlight beam leaving the floor", "a reflection that moves in perfect sync"]
    shrink_two_shot_sequence(p)
    p["segments"] = [{"id": "SUSPENSE_SEG01", "start_frame": 0, "end_frame": 240, "shot_ids": [s["id"] for s in p["shots"]], "generation_clip_duration": 10,
        "mode": "I2VA", "style": "Low-key live-action suspense with restrained handheld drift, practical flashlight illumination and shallow depth of field.",
        "overall_soundscape": "Sparse archive room tone, irregular ventilation ticks, cloth tension and a breath that stops before the delayed glass movement.", "non_diegetic_music": "N/A",
        "references": [{"label": "<Picture 1>", "file": "media/PENDING-suspense-archive-approved.png", "role": "opening composition anchor",
            "asset_version": "planned-v1", "entity_id": "S01", "shot_ids": [p['shots'][0]['id']],
            "preserve": "approved opening stance, archive geometry and low flashlight placement", "exclude": "later reflected-hand motion and any unrelated figure or environment",
            "definition": "<Picture 1> is the opening still for Ning Yue beside the glass records room with the flashlight held low.",
            "retention": "<Picture 1> (appears at the 0.00-second mark): fully_preserved - preserve the opening stance and flashlight placement while extending the delayed reflection action."}],
        "motion_profile": {"version": "1.0", "medium": "live_action", "fps": 24, "exposure": "ones", "timing_principle": "let the breath stop before the reflection begins its delayed movement", "camera_principle": "drift closer only after the mismatch is visible, keeping the glass plane square to frame", "staging_principle": "preserve the flashlight floor pool and the reflection's depth behind the glass", "sound_principle": "make silence, breath and one delayed glass movement carry the beat", "cut_style": "hard_cut"}}]
    update_asset(p, "ASSET_SUSPENSE_ARCHIVE", "废档案室·延迟倒影", "Create a low-key live-action suspense keyframe in an abandoned archive. Ning Yue, an adult archivist in a dark raincoat with tied black hair, stands beside a glass records room holding a small flashlight low in her right hand. Tall metal shelves, dusty tile, a dead emergency light and a narrow doorway beam create clear depth. Her shoulders are held still while the glass reflection is subtly delayed and its hand remains down. Use one practical flashlight beam with readable falloff and quiet shadow planes. Keep the reflection behind the glass, never as a second physical person in the room. Avoid captions, horror typography, duplicate bodies and a bright fantasy glow.",
        None, "listening-still", "v1.0")
    p['example_delivery_expectation'] = 'DRAFT_MISSING_REFERENCES'
    p['reference_review'] = 'Correct archive opening frame pending. The unrelated ink bridge diagram is not a valid source.'
    return p


def repair_variant_facts(p):
    """Replace copied drama facts with the authored variant's actual staging."""
    kind = p['project_id']
    if kind == 'EXAMPLE_ANIMATED_PHONE':
        for i, shot in enumerate(p['shots']):
            shot['characters'][0].update(gaze='eyes initially closed toward the window' if i == 0 else 'toward the window, seen from behind',
                                         facing='toward the window', weapon_hand='left hand holds the phone at the left ear; right hand is free')
        p['story'] = {'synopsis': '陈千语在电话中从轻笑转为确信，以手势和尾部余势承接跨切镜的同一句台词；电话始终留在左耳。'}
        return p
    if kind not in {'EXAMPLE_COMEDY_MISUNDERSTANDING', 'EXAMPLE_SUSPENSE_WHISPER'}:
        return p
    comic = kind == 'EXAMPLE_COMEDY_MISUNDERSTANDING'
    p.setdefault('prompt_bindings', {})['S01'] = 'the workshop' if comic else 'the glass corridor'
    p['prompt_bindings'].pop('BRASS_KEY', None)
    prop, owner = ('UMBRELLA', 'S01') if comic else ('FLASHLIGHT', 'CHAR_NING')
    initial = {'characters': {c['id']: {'ammo': 0, 'trauma_phase': None} for c in p['character_registry']},
               'scenes': {'S01': 0}, 'props': {prop: owner}}
    p['ledger'] = {'initial': initial, 'events': [], 'final': copy.deepcopy(initial)}
    p['story'] = {'synopsis': '裴峻指着空伞钩质问陶林，红伞从梯后滚出；陶林指向伞再指天花板，试图保住无辜姿态。' if comic else '宁月停止呼吸和转头，只用眼睛核对玻璃倒影；倒影延迟抬手，手电光始终留在地面。'}
    p['scene_registry'][0].update(space=p['scene_registry'][0]['prompt_description'],
        landmarks=[p['scene_registry'][0]['prompt_description']],
        key_light='one warm ceiling lamp' if comic else 'the low flashlight beam and its reflected spill')
    actions = ([
        ('the empty umbrella hook is visible', 'Pei Jun points at the fixed empty hook, then looks at Tao Lin without stepping closer', 'from the empty hook to Tao Lin', 'lips purse before the accusation', 'the pointing hand stays extended through the question', 'the umbrella stays behind the ladder; neither person holds it', 'one glove squeak follows the point'),
        ('the umbrella begins to roll into view', 'Tao Lin turns toward the umbrella, points after it, then redirects the same finger toward the ceiling', 'umbrella, then ceiling, then Pei Jun', 'an over-serious expression held through the excuse', 'the hand overshoots the ceiling target and settles; nobody catches the umbrella', 'the umbrella rolls along the workshop floor and remains there', 'a delayed umbrella roll and one ladder rattle')
    ] if comic else [
        ('the reflection lags behind one breath', 'Ning Yue holds her shoulders still and stops breathing while keeping the flashlight low', 'toward the delayed reflection through the glass', 'lips stay closed and the jaw firms', 'the beam remains on the floor after the breath stops', 'the flashlight stays in her right hand', 'one ventilation tick followed by held breath'),
        ('the reflected hand rises after Ning Yue has stopped moving', 'Ning Yue turns only her eyes toward the rising reflected hand; her head and flashlight hand stay fixed', 'from the reflected shoulders to the raised hand', 'a small tightening under the eyes; no spoken reaction', 'the reflection holds its raised hand while Ning Yue remains still', 'the flashlight floor pool remains unchanged', 'cloth tension settles into near-silence')
    ])
    for i, shot in enumerate(p['shots']):
        shot['state_in'] = copy.deepcopy(initial); shot['state_out'] = copy.deepcopy(initial); shot['outcome_events'] = []
        cause, action, gaze, face, follow, prop_text, sound = actions[i]
        span = shot['end_frame'] - shot['start_frame']
        camera = shot['camera']
        camera.update(movement='static', path='stationary on the established side of the action axis',
            target='the empty hook, both faces and the floor beside the ladder' if comic else 'Ning Yue, the glass reflection and the low flashlight pool',
            description=('The camera holds a medium-wide view of both performers, the fixed hook and the ladder; the second shot is wider to expose the umbrella path.' if comic else 'The camera holds the glass plane and flashlight pool; the second shot is closer to reveal the eye movement and delayed reflected hand.'))
        shot['audio']['foley'] = [sound]
        perf = shot['performance']; design = perf['acting_design']
        perf.update(strategy='selective', dominant_track='body_hands' if comic else 'gaze',
            tracks={('body_hands' if comic else 'gaze'): {'start': 0, 'end': span-1, 'cue': action, 'visibility': camera['description']}})
        design.update(trigger=cause, continuity_in=shot['state_description'], continuity_out=follow,
            action_units=[{'start': 0, 'end': span-1, 'cause': cause, 'action': action, 'gaze': gaze, 'face': face,
                           'follow_through': follow, 'speech_anchor': 'silent',
                           'delivery': 'use the existing written line only' if comic else 'no speech; lips remain closed',
                           'prop': prop_text, 'camera': camera['description'], 'sound': sound}],
            motion_arc={'anticipation': cause, 'accent': action, 'follow_through': follow, 'settle': prop_text},
            exclusions=['added dialogue', 'new injuries', 'a prop changing hands', 'unwritten extra characters'])
        first_unit = design['action_units'][0]
        first_unit['end'] = span // 2
        settled = copy.deepcopy(first_unit)
        settled.update(start=span // 2, end=span-1, cause='the preceding visible action has reached its accent',
                       action=follow, follow_through=prop_text)
        design['action_units'].append(settled)
        for character in shot['characters']:
            if comic:
                character['weapon_hand'] = 'empty gloved hands; pointing gestures only'
            else:
                character['weapon_hand'] = 'right hand holds the flashlight low' if character['id'] == 'CHAR_NING' else 'a reflected hand visible behind glass; no physical prop contact'
                character['gaze'] = 'toward the glass reflection' if character['id'] == 'CHAR_NING' else 'a delayed reflection of Ning Yue; no independent physical presence'
    if comic:
        p['shots'][0]['visual'] = p['shots'][0]['visual'].replace('holding an empty umbrella hook', 'pointing at the fixed empty umbrella hook')
    for card in p.get('asset_cards', []):
        card['structure_lock']['camera'] = p['shots'][0]['camera']['description']
        card['seven_steps'][0]['content'] = ' '.join(c['prompt_description'] for c in p['character_registry']) + ' ' + p['shots'][0]['state_description']
        card['seven_steps'][2]['content'] = p['shots'][0]['camera']['description']
        card['seven_steps'][3]['content'] = p['scene_registry'][0]['key_light'] + '; separate the described materials by their visible response.'
    return p


def write_example(p, filename, title):
    repair_variant_facts(p)
    data_path = EXAMPLES / filename
    write_json(data_path, p)
    lines = [f"# {title}", "", "This authored v3.2 example is a prompt-production template; no image or video model was called.", "", f"Data: [{filename}]({filename})", ""]
    for seg in p["segments"]:
        folder = filename.split('-', 1)[1].split('.')[0]
        suffix = '.h3.draft.txt' if p.get('example_delivery_expectation') else '.h3.txt'
        lines.extend([f"## {seg['id']} / {seg['mode']}", "", p.get('reference_review', ''), "",
                      f"[Complete prompt/draft](compiled/{folder}/{seg['id']}{suffix}) · [Upload card](compiled/{folder}/{seg['id']}.upload.md)", ""])
    (EXAMPLES / title).with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main():
    examples = [(animated_phone(), "06-animated-phone.production.json", "06-animated-phone"),
                (comedy_misunderstanding(), "07-comedy-misunderstanding.production.json", "07-comedy-misunderstanding"),
                (suspense_whisper(), "08-suspense-whisper.production.json", "08-suspense-whisper")]
    for production, filename, title in examples:
        write_example(production, filename, title)
    print(f"Built {len(examples)} v3.2 examples")


if __name__ == "__main__":
    main()
