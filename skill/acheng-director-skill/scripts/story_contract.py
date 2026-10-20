"""Check narrative references, knowledge timing and screenplay coverage, not artistic merit."""
from contract_core import indexed, need, prose

STATES = {"unknown", "suspects", "believes_false", "knows"}


def check_story(payload):
    story = payload.get("story", {})
    need(story.get("contract_version") == "3.0", "story.contract_version must be 3.0")
    threads = indexed(story.get("threads"), "story threads")
    characters = indexed(payload.get("character_registry"), "characters")
    scenes = indexed(payload.get("scene_registry"), "scenes")
    beats = indexed(story.get("beats"), "story beats")
    facts = indexed(story.get("facts", []), "story facts", True)
    order = {key: i for i, key in enumerate(beats)}
    used_threads = set()
    for thread in threads.values():
        need(thread.get("visibility") in ("overt", "covert", "mixed"), "thread visibility required")
        need(thread.get("function") in ("external", "relationship", "world", "thematic"), "thread function invalid")
        need(prose(thread.get("question")), "thread dramatic question required")
    for fact in facts.values():
        need(prose(fact.get("truth")), "fact truth required")
    knowledge = {}
    holders = set(characters) | {"AUDIENCE"}

    def knowledge_row(row):
        need(row.get("holder") in holders and row.get("fact_id") in facts, "unknown knowledge holder/fact")
        need(row.get("state") in STATES and prose(row.get("evidence")), "knowledge state/evidence required")
        if row["state"] == "believes_false":
            need(prose(row.get("belief")), "false belief must state what is believed")
        return row["holder"], row["fact_id"]

    for row in story.get("initial_knowledge", []):
        key = knowledge_row(row)
        need(key not in knowledge, "duplicate initial knowledge")
        knowledge[key] = row["state"]
    events = indexed(story.get("knowledge_events", []), "knowledge events", True)
    last = -1
    for row in events.values():
        knowledge_row(row)
        need(row.get("after_beat_id") in beats, "knowledge event has unknown beat")
        position = order[row["after_beat_id"]]
        need(position >= last, "knowledge events out of playback order")
        last = position
    for bid, beat in beats.items():
        need(beat.get("scene_id") in scenes, f"{bid}: unregistered story scene")
        need(prose(beat.get("episode")) and prose(beat.get("story_time")), f"{bid}: episode/story time required")
        need(beat.get("primary_thread") in threads, f"{bid}: unknown primary thread")
        secondary = beat.get("secondary_threads", [])
        need(isinstance(secondary, list) and set(secondary) <= set(threads), "unknown secondary thread")
        used_threads.update([beat["primary_thread"], *secondary])
        for field in ("goal", "obstacle", "choice", "cost", "result"):
            need(prose(beat.get(field)), f"{bid}: {field} evidence missing")
        dependencies = beat.get("depends_on", [])
        need(isinstance(dependencies, list) and all(d in order and order[d] < order[bid] for d in dependencies), f"{bid}: forward/cyclic narrative cause")
        need(dependencies or prose(beat.get("entry_cause")), f"{bid}: entry cause required")
        cast = beat.get("characters", [])
        need(isinstance(cast, list) and set(cast) <= set(characters), f"{bid}: unknown participant")
        for prerequisite in beat.get("requires_knowledge", []):
            key = prerequisite.get("holder"), prerequisite.get("fact_id")
            need(key[0] in holders and key[1] in facts, "unknown knowledge prerequisite")
            need(key[0] == "AUDIENCE" or key[0] in cast, "knowledge prerequisite belongs to absent character")
            need(prerequisite.get("state") in STATES, "knowledge prerequisite state invalid")
            need(knowledge.get(key, "unknown") == prerequisite["state"], f"{bid}: premature or contradictory knowledge {key}")
        for event in events.values():
            if event["after_beat_id"] == bid:
                key = event["holder"], event["fact_id"]
                need(event.get("before") == knowledge.get(key, "unknown"), f"{event['id']}: stale knowledge state")
                knowledge[key] = event["state"]
    need(used_threads == set(threads), "unrepresented story thread")
    setups = indexed(story.get("setups", []), "setups", True)
    for setup in setups.values():
        need(setup.get("setup_beat") in beats and prose(setup.get("surface_reading")), "setup source/surface reading required")
        reinforce = setup.get("reinforcement_beats", [])
        need(isinstance(reinforce, list) and all(b in order and order[b] > order[setup["setup_beat"]] for b in reinforce), "reinforcement must follow setup")
        payoff = setup.get("payoff_beat")
        if payoff is None:
            need(prose(setup.get("planned_payoff")), "open setup needs a recovery plan")
        else:
            need(payoff in order and order[payoff] > order[setup["setup_beat"]], "payoff must follow setup")
            need(reinforce and all(order[b] < order[payoff] for b in reinforce), "fulfilled setup needs intervening reinforcement")
            need(prose(setup.get("effect")), "payoff must change a choice, interpretation or situation")
    arcs = indexed(story.get("character_arcs"), "character arcs")
    for arc in arcs.values():
        need(arc.get("character_id") in characters and arc.get("kind") in ("positive", "tragic", "flat", "open"), "arc character/kind invalid")
        for field in ("want", "need", "belief", "voice", "relationship_debt"):
            need(prose(arc.get(field)), f"arc {field} missing")
        points = arc.get("evidence", [])
        need(points and all(x.get("beat_id") in beats and prose(x.get("choice")) for x in points), "arc needs concrete choice evidence")
        positions = [order[x["beat_id"]] for x in points]
        need(positions == sorted(set(positions)), "arc evidence order/duplication")
        for point in points:
            need(arc["character_id"] in beats[point["beat_id"]]["characters"], "arc evidence belongs to absent character")
    relationships = {}
    for relation in indexed(story.get("relationships", []), "relationships", True).values():
        need(len(set(relation.get("characters", []))) >= 2 and set(relation["characters"]) <= set(characters), "relationship participants invalid")
        current, previous = relation.get("initial"), -1
        need(prose(current), "relationship initial state missing")
        for event in relation.get("events", []):
            bid = event.get("beat_id")
            need(bid in beats and order[bid] > previous, "relationship event order invalid")
            need(event.get("before") == current and prose(event.get("after")) and prose(event.get("evidence")), "relationship event lacks prior state or evidence")
            need(set(relation["characters"]) <= set(beats[bid]["characters"]), "relationship participants absent from event")
            current, previous = event["after"], order[bid]
        relationships[relation["id"]] = current
    screenplay = indexed(payload.get("script_scenes"), "script scenes")
    coverage = []
    for scene in screenplay.values():
        need(scene.get("scene_id") in scenes and scene.get("scene_name") == scenes[scene["scene_id"]]["name"], "unregistered scene or screenplay name mismatch")
        need(prose(scene.get("text")), "screenplay text missing")
        ids = scene.get("beat_ids", [])
        need(ids and all(b in beats and beats[b]["scene_id"] == scene["scene_id"] for b in ids), "screenplay beat binding mismatch")
        coverage.extend(ids)
    need(coverage == list(beats), "screenplay coverage/order differs from narrative beats")
    for locked in story.get("locked_dialogue", []):
        need(locked.get("scene_id") in screenplay and prose(locked.get("text")), "locked dialogue source missing")
        need(locked["text"] in screenplay[locked["scene_id"]]["text"], "locked dialogue altered or missing")
    if payload.get("shots") and payload.get("delivery_scope") == "full_production":
        mapping = [bid for shot in payload["shots"] for bid in shot.get("story_beat_ids", [])]
        need(set(mapping) == set(beats), "story-to-shot coverage incomplete")
        need(all(order[a] <= order[b] for a, b in zip(mapping, mapping[1:])), "story-to-shot playback order changed")
        for shot in payload["shots"]:
            need(shot.get("story_beat_ids") and all(beats[b]["scene_id"] == shot["scene_id"] for b in shot["story_beat_ids"]), "shot uses wrong story scene")
    return {"status": "PASS", "scope": "narrative-reference-and-knowledge-contract", "threads": len(threads),
            "beats": len(beats), "setups": len(setups), "open_setups": [s["id"] for s in setups.values() if s.get("payoff_beat") is None],
            "knowledge_final": [{"holder": h, "fact_id": f, "state": s} for (h, f), s in sorted(knowledge.items())],
            "relationship_final": relationships,
            "creative_quality": "REQUIRES_CONTENT_REVIEW"}
