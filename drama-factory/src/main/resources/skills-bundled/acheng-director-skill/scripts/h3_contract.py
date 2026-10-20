"""Additional H3 guide semantics, density policy and segment-local speech identities."""
import re
from math import ceil
from fractions import Fraction
from contract_core import need, prose

TASKS = {"keyframe completion", "reference generation", "video editing", "video continuation", "audio reuse", "audio reference"}
REF2VA_MIN_WORDS = 2000
REF2VA_TARGET_WORDS = 2400
REF2VA_MAX_WORDS = 2900
REF2VA_MIN_WORDS_PER_SECOND = 200
REF2VA_TARGET_WORDS_PER_SECOND = 240


def _duration_seconds(production, segment):
    """Resolve one independent clip duration without inventing a long-form cap."""
    value = segment.get("generation_clip_duration")
    if value is not None:
        try:
            value = float(value)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    start, end = segment.get("start_frame"), segment.get("end_frame")
    fps_num, fps_den = production.get("fps_num", 24), production.get("fps_den", 1)
    if isinstance(start, int) and isinstance(end, int) and end > start and fps_num:
        return float(Fraction((end - start) * fps_den, fps_num))
    # A request without a locked timeline still needs a conservative policy;
    # 10 seconds is the middle of Acheng Director's normal 8–12 second range.
    return 10.0


def _complexity_addition(production, segment):
    """Add coverage budget for facts that cannot be represented safely by a short block."""
    by_id = {shot.get("id"): shot for shot in production.get("shots", [])}
    shots = [by_id[sid] for sid in segment.get("shot_ids", []) if sid in by_id]
    points = 0
    if any(shot.get("features", {}).get("combat") for shot in shots):
        points += 200
    if any(shot.get("features", {}).get("supernatural_vfx") or shot.get("features", {}).get("colossal") for shot in shots):
        points += 100
    dialogue_count = sum(len(shot.get("dialogues", [])) for shot in shots)
    speakers = {line.get("character_id", line.get("speaker_name")) for shot in shots for line in shot.get("dialogues", [])}
    if dialogue_count:
        points += 100
    if len(speakers) >= 2:
        points += 100
    if len(shots) >= 4:
        points += 100
    if len(segment.get("references", [])) + len(segment.get("subjects", [])) >= 4:
        points += 100
    return min(points, 600)


def english_word_count(value):
    """Count English lexical words only; digits and CJK text do not satisfy the detail floor."""
    return len(re.findall(r"\b[A-Za-z]+(?:[-'][A-Za-z]+)*\b", value))


def detail_policy(production, segment):
    """Return the explicit H3 density policy for one independent request.

    New production requests are strict by default. Historical authored fixtures
    can opt into ``legacy_fixture`` so their frozen examples remain byte-stable;
    that exception is never emitted by the user-facing master prompt.
    """
    policy = {}
    root = production.get("prompt_detail_policy", {})
    local = segment.get("prompt_detail_policy", {})
    if isinstance(root, dict):
        policy.update(root)
    if isinstance(local, dict):
        policy.update(local)
    if policy.get("profile") == "legacy_fixture":
        return {"profile": "legacy_fixture", "minimum_words": 0, "target_words": 0}
    seconds = _duration_seconds(production, segment)
    min_rate = int(policy.get("minimum_words_per_second", REF2VA_MIN_WORDS_PER_SECOND))
    target_rate = int(policy.get("target_words_per_second", REF2VA_TARGET_WORDS_PER_SECOND))
    if min_rate < REF2VA_MIN_WORDS_PER_SECOND:
        raise ValueError(f"minimum_words_per_second must be at least {REF2VA_MIN_WORDS_PER_SECOND}")
    if target_rate < min_rate:
        raise ValueError("target_words_per_second must be greater than or equal to minimum_words_per_second")
    addition = _complexity_addition(production, segment)
    maximum = int(policy.get("ref2va_max_words", REF2VA_MAX_WORDS))
    derived_minimum = min(max(REF2VA_MIN_WORDS, ceil(seconds * min_rate)) + addition, maximum)
    derived_target = min(max(REF2VA_TARGET_WORDS, ceil(seconds * target_rate), derived_minimum + 200), maximum)
    explicit_minimum = policy.get("ref2va_min_words")
    explicit_target = policy.get("ref2va_target_words")
    if explicit_minimum is not None and int(explicit_minimum) < derived_minimum:
        raise ValueError(f"Ref2VA minimum detail must be at least the derived {derived_minimum} words for this Segment")
    minimum = int(explicit_minimum) if explicit_minimum is not None else derived_minimum
    if explicit_target is not None and int(explicit_target) < derived_target:
        raise ValueError(f"Ref2VA target detail must be at least the derived {derived_target} words for this Segment")
    target = int(explicit_target) if explicit_target is not None else max(derived_target, min(minimum + 200, maximum))
    if target > maximum:
        target = maximum
    if target < minimum:
        raise ValueError("Ref2VA target detail must be greater than or equal to its minimum")
    return {"profile": policy.get("profile", "strict"), "minimum_words": minimum, "target_words": target,
            "maximum_words": maximum,
            "duration_seconds": seconds, "complexity_addition": addition,
            "derived_minimum_words": derived_minimum, "derived_target_words": derived_target,
            "minimum_words_per_second": min_rate, "target_words_per_second": target_rate}


def clip_bounds(p):
    minimum = Fraction(str(p.get("generation_clip_min", 4)))
    maximum = Fraction(str(p.get("generation_clip_limit", 15)))
    need(4 <= minimum <= maximum <= 15, "generation window must stay within 4–15 seconds")
    return minimum, maximum


def speech_map(p, seg):
    shots = {s["id"]: s for s in p["shots"]}
    mapping = {}
    for sid in seg["shot_ids"]:
        for line in sorted(shots[sid]["dialogues"], key=lambda x: x["start"]):
            identity = line.get("character_id", line["speaker_name"])
            if identity not in mapping:
                mapping[identity] = f"S{len(mapping) + 1}"
    return mapping


def remap_speech_references(value, p, seg):
    local = speech_map(p, seg)
    old = {line["speaker_id"]: local[line.get("character_id", line["speaker_name"])]
           for shot in p["shots"] for line in shot["dialogues"]
           if line.get("character_id", line["speaker_name"]) in local}
    return re.sub(r"\((S[1-9]\d*)\)", lambda m: "(" + old.get(m[1], m[1]) + ")", value)


def check_h3_semantics(p, seg, text):
    policy = detail_policy(p, seg)
    refs = seg.get("references", [])
    if seg["mode"] == "Ref2VA":
        match = re.match(r"^\[([^\]]+)\]\s+\S", seg.get("summary", ""))
        need(match is not None, "Ref2VA task prefix missing")
        tasks = match[1].split(" + ")
        need(len(tasks) == len(set(tasks)) and set(tasks) <= TASKS, "unsupported/duplicate H3 task prefix")
        if "video editing" in tasks or "video continuation" in tasks:
            need(any(r["label"].startswith("<Video") for r in refs), "video editing/continuation lacks video source")
        if "video editing" in tasks:
            need(re.match(r"^\[[^\]]+\] The target video is an edited version of <Video [1-9]\d*>\.", seg["summary"]), "video editing opening differs from guide")
        if "audio reuse" in tasks or "audio reference" in tasks:
            need(any(r["label"].startswith("<Audio") for r in refs), "audio task lacks Audio source")
        if "keyframe completion" in tasks:
            need(any(r["label"].startswith("<Picture") for r in refs), "keyframe task lacks Picture source")
        for ref in refs:
            need(not ref["label"].startswith("<Subject"), "Subject is content, not an uploaded file; use subjects[]")
        body = text.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
        if policy["profile"] != "legacy_fixture":
            word_count = english_word_count(body)
            need(word_count >= policy["minimum_words"],
                 f"Ref2VA detailed_description is {word_count} words; minimum is {policy['minimum_words']} (target {policy['target_words']})")
            need(word_count <= policy.get("maximum_words", REF2VA_MAX_WORDS),
                 f"Ref2VA detailed_description is {word_count} words; exceeds maximum ceiling of {policy.get('maximum_words', REF2VA_MAX_WORDS)} words (2900 words limit)")
        for subject in seg.get("subjects", []):
            need(subject["label"] in body, "defined Subject never used in detailed_description")
        defined_speakers = set(re.findall(r"\((S[1-9]\d*)\)", text.split("detailed_description:", 1)[0]))
        need(defined_speakers <= set(speech_map(p, seg).values()), "reference audio invents a speaker absent from this request")
    else:
        body = text.split("integrated_multimodal_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
        expected = {"T2VA": [], "I2VA": [1], "FL2VA": [1, 2], "L2VA": [1]}[seg["mode"]]
        for number in expected:
            need(re.search(r"\bPicture " + str(number) + r"\b", body), "keyframe anchor is declared but not consumed in the motion description")
    shots = {s["id"]: s for s in p["shots"]}
    utterances = {}
    for local_index, sid in enumerate(seg["shot_ids"]):
        for line in sorted(shots[sid]["dialogues"], key=lambda x: x["start"]):
            if line.get("utterance_id"):
                utterances.setdefault(line["utterance_id"], []).append((local_index, line))
            if line.get("cutoff"):
                need(seg.get("allow_speech_cutoff") is True and sid == seg["shot_ids"][-1], "speech cutoff requires explicit approval at final shot")
    for uid, pieces in utterances.items():
        need(len(pieces) > 1, f"{uid}: cross-cut speech needs both parts inside this request")
        need([i for i, _ in pieces] == list(range(pieces[0][0], pieces[0][0] + len(pieces))), "cross-cut speech must occupy consecutive shots")
        first = pieces[0][1]
        need(prose(first.get("source_text")), "cross-cut speech requires verbatim source_text")
        need("".join(line["text"] for _, line in pieces) == first["source_text"], "cross-cut speech source altered")
        need(all(line.get("source_text") == first["source_text"] and line["speaker_name"] == first["speaker_name"] and line["language"] == first["language"] for _, line in pieces), "cross-cut speech identity/source mismatch")
        for position, (index, line) in enumerate(pieces):
            shot = shots[seg["shot_ids"][index]]
            if position:
                need(line["start"] == 0, "continuous speech must start at the incoming cut")
            if position < len(pieces) - 1:
                need(line["end"] == shot["end_frame"] - shot["start_frame"], "continuous speech must reach the outgoing cut")
