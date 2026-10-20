"""Asset coverage, versioned dependencies and honest reference readiness."""
import copy
import hashlib
from pathlib import Path
from contract_core import indexed, need, prose

KINDS = {"character", "costume", "injury", "scene", "prop", "vehicle", "keyframe", "effect", "style"}

DEFAULT_CHARACTER_VIEW_LAYOUT = {
    "type": "four_view_character_turnaround",
    "views": ["front_full_body", "back_full_body", "side_profile_full_body", "front_face_close_up"],
    "order": "left_to_right",
    "same_subject": True,
    "purpose": "identity, proportions, costume, hairstyle and face reference"
}


def prepare_asset_card(card, payload):
    """Apply explicit defaults for character identity boards without changing the source payload."""
    result = copy.deepcopy(card)
    plan_nodes = {node["id"]: node for node in payload.get("asset_plan", [])}
    node = plan_nodes.get(result.get("id"), {})
    need(not result.get("asset_kind") or not node.get("kind") or result["asset_kind"] == node["kind"], "asset card/plan kind conflict: " + str(result.get("id")))
    asset_kind = result.get("asset_kind") or node.get("kind")
    if asset_kind != "character":
        if payload.get("style_lock") and asset_kind:
            result["asset_kind"] = asset_kind
        return result

    result["asset_kind"] = "character"
    registry = {entry.get("id"): entry for entry in payload.get("character_registry", [])}
    character = registry.get(node.get("entity_id"), {})
    result["character_name"] = result.get("character_name") or character.get("name") or result.get("name") or result["id"]
    result["state_label"] = result.get("state_label") or "neutral_identity"
    layout = result.get("view_layout") or copy.deepcopy(DEFAULT_CHARACTER_VIEW_LAYOUT)
    result["view_layout"] = layout
    if layout.get("type") == "four_view_character_turnaround":
        views = layout.get("views")
        if views == DEFAULT_CHARACTER_VIEW_LAYOUT["views"]:
            name = result["character_name"]
            state = result["state_label"]
            directive = (
                f"This is the {name} character identity asset in the approved {state} state. "
                "Create one clean four-view character turnaround board for this single subject, arranged left to right: "
                "1) full-body front view, 2) full-body back view, 3) full-body side profile, "
                "4) front-facing head-and-shoulders face close-up. "
                "Keep the same proportions, costume, hairstyle, facial features, neutral standing pose, lighting and background "
                "across the three full-body views; use the fourth panel only for the straight-on face. "
                "Do not render the character name or state as visible text, and do not add panel letters, labels, logos, extra people or extra limbs."
            )
            if "four-view character turnaround" not in result.get("prompt", "").lower():
                result["prompt"] = directive + " " + result.get("prompt", "")
            if result.get("seven_steps"):
                first = result["seven_steps"][0]
                if "four-view character turnaround" not in first.get("content", "").lower():
                    first["content"] = directive + " " + first.get("content", "")
    return result


def check_asset_plan(payload, base):
    nodes = indexed(payload.get("asset_plan"), "asset plan")
    cards = indexed(payload.get("asset_cards", []), "asset cards", True)
    order, visiting, visited = [], set(), set()

    def visit(aid):
        need(aid in nodes, f"unknown asset dependency: {aid}")
        need(aid not in visiting, "cyclic asset dependency")
        if aid in visited:
            return
        visiting.add(aid)
        node = nodes[aid]
        need(node.get("kind") in KINDS and isinstance(node.get("version"), str) and node["version"].strip() and prose(node.get("purpose")), f"{aid}: asset kind/version/purpose required")
        dependencies = node.get("depends_on", [])
        need(isinstance(dependencies, list) and len(dependencies) == len(set(dependencies)), "invalid asset dependencies")
        for dep in dependencies:
            visit(dep)
        need(node.get("status") in ("planned", "approved"), "asset status must be planned/approved")
        if node["status"] == "approved":
            file = Path(base) / node.get("file", "")
            need(file.is_file(), f"{aid}: approved asset file missing")
            need(hashlib.sha256(file.read_bytes()).hexdigest() == node.get("sha256"), f"{aid}: approved asset hash changed")
        else:
            need(aid in cards, f"{aid}: planned asset lacks a prompt card")
        if aid in cards:
            prepare_asset_card(cards[aid], payload)
            need(cards[aid].get("asset_version") == node["version"], f"{aid}: prompt/asset version mismatch")
            refs = {r["asset_id"] for r in cards[aid].get("references", []) if "asset_id" in r}
            need(refs == set(dependencies), f"{aid}: dependencies must match numbered asset references")
        visiting.remove(aid)
        visited.add(aid)
        order.append(aid)

    for aid in nodes:
        visit(aid)
    need(set(cards) <= set(nodes), "unplanned asset card")
    consumers = {aid: [] for aid in nodes}
    for shot in payload.get("shots", []):
        required = shot.get("required_assets", [])
        need(required and isinstance(required, list) and set(required) <= set(nodes), f"{shot['id']}: asset requirements incomplete")
        for aid in required:
            consumers[aid].append(shot["id"])
        visible_chars = {c["id"] for c in shot["characters"]}
        supplied_chars = {nodes[a].get("entity_id") for a in required if nodes[a]["kind"] == "character"}
        need(visible_chars <= supplied_chars, f"{shot['id']}: visible character asset missing")
        need(any(nodes[a]["kind"] == "scene" and nodes[a].get("entity_id") == shot["scene_id"] for a in required), f"{shot['id']}: scene asset missing")
        for prop in shot.get("required_prop_ids", []):
            need(any(nodes[a]["kind"] in ("prop", "vehicle") and nodes[a].get("entity_id") == prop for a in required), f"{shot['id']}: prop asset missing")
    impact = {}
    shots = {s["id"]: s for s in payload.get("shots", [])}
    keyframe_coverage = {}
    for aid, node in nodes.items():
        if node["kind"] != "keyframe" or not shots:
            continue
        targets = node.get("shot_ids") or consumers[aid] or ([node["entity_id"]] if node.get("entity_id") in shots else [])
        need(isinstance(targets, list) and targets and set(targets) <= set(shots), f"{aid}: keyframe target shots missing or unknown")
        need(set(consumers[aid]) <= set(targets), f"{aid}: keyframe target scope omits a consuming shot")
        required = {a for sid in targets for a in shots[sid]["required_assets"] if nodes[a]["kind"] not in {"keyframe", "style"}}
        need(required <= set(node.get("depends_on", [])), f"{aid}: keyframe missing target-shot references: {sorted(required - set(node.get('depends_on', [])))}")
        keyframe_coverage[aid] = {"shot_ids": targets, "required_asset_ids": sorted(required)}
    for aid in nodes:
        dependents = {aid}
        for candidate in order:
            if set(nodes[candidate].get("depends_on", [])) & dependents:
                dependents.add(candidate)
        affected_shots = {s for dep in dependents for s in consumers[dep]}
        impact[aid] = {"assets": sorted(dependents), "shots": sorted(affected_shots),
                       "segments": [s["id"] for s in payload.get("segments", []) if set(s["shot_ids"]) & affected_shots]}
    return {"status": "PASS", "scope": "declared requirements, versions and reference dependencies",
            "production_order": order, "planned": [a for a in order if nodes[a]["status"] == "planned"], "impact": impact,
            "keyframe_coverage": keyframe_coverage, "visual_acceptance": "NOT_INFERRED_FROM_FILE_EXISTENCE"}


def resolve_card(card, payload, base, allow_missing=False):
    from reference_bindings import inspect_media
    result = prepare_asset_card(card, payload)
    nodes = {x["id"]: x for x in payload.get("asset_plan", [])}
    missing = []
    for ref in result.get("references", []):
        expected = ref.get("sha256")
        if "asset_id" in ref:
            aid = ref["asset_id"]
            need(aid in nodes, f"reference asset {aid} not planned")
            node = nodes[aid]
            need(ref.get("asset_version") == node["version"], f"reference version mismatch: {aid}")
            for field in ("entity_id", "state_label", "state_version"):
                need(not ref.get(field) or not node.get(field) or ref[field] == node[field], f"reference {field} conflict: {aid}")
            if node["status"] == "approved":
                need(not ref.get("file") or (Path(base) / ref["file"]).resolve() == (Path(base) / node["file"]).resolve(), f"reference file conflicts with approved asset: {aid}")
                need(not expected or expected == node.get("sha256"), f"reference SHA-256 conflicts with approved asset: {aid}")
                expected = node.get("sha256")
                need(expected, f"approved reference hash missing: {aid}")
                ref["file"] = node["file"]
            else:
                ref["file"] = "PENDING_APPROVED_ASSET"
                missing.append({"image": ref["image"], "asset_id": aid, "version": node["version"], "role": ref["role"]})
        if not any(x["image"] == ref["image"] for x in missing):
            try:
                ref['sha256'] = inspect_media(Path(base) / ref.get("file", ""), f"<Picture {ref['image']}>", expected)
            except (ValueError, OSError) as exc:
                missing.append({"image": ref["image"], "file": ref.get("file"), "role": ref["role"], "reason": str(exc)})
    need(allow_missing or not missing, f"missing approved image references: {missing}")
    return result, missing
