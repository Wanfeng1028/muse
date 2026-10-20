#!/usr/bin/env python3
"""Validate early screenplay/image artifacts without fabricating downstream fields."""
import argparse
import json
from pathlib import Path
import sys

from audit_storyboard_quality import ContractError, audit, digest, read_data, require, substantive
from prompt_delivery import render_asset_prompt
from asset_plan import check_asset_plan, resolve_card
from story_contract import check_story
from style_anchor import check_style_lock, style_policy_report


def check_script(payload):
    require(isinstance(payload, dict), "script payload must be object")
    if payload.get("story", {}).get("contract_version") == "3.0":
        try:
            return {**check_story(payload), "input_sha256": digest(payload), "stage": "script"}
        except ValueError as exc:
            raise ContractError(str(exc)) from exc
    registry = payload.get("scene_registry")
    scenes = payload.get("script_scenes")
    require(isinstance(registry, list) and registry and isinstance(scenes, list) and scenes, "registry and screenplay scenes are both required")
    by_id = {s["id"]: s for s in registry}
    require(len(by_id) == len(registry), "duplicate scene registry id")
    require(len({s["id"] for s in scenes}) == len(scenes), "duplicate screenplay scene id")
    for scene in scenes:
        require(scene.get("scene_id") in by_id, f"{scene.get('id')}: unregistered scene")
        require(scene.get("scene_name") == by_id[scene["scene_id"]]["name"], f"{scene['id']}: scene header/name mismatch")
        require(substantive(scene.get("text")), f"{scene['id']}: screenplay body missing")
        require(scene.get("thread") in ("A", "B", "C"), f"{scene['id']}: primary story thread required")
    return {"status": "PASS", "stage": "script", "script_scenes": len(scenes), "input_sha256": digest(payload),
            "scope": "Registered structured scene headers; unstructured prose still needs content review"}


def check_assets(payload, base, allow_missing=False):
    # New multi-asset work must declare STYLE_MOTHER explicitly. Historical
    # single-image fixtures remain valid without a cross-asset style lock.
    style_policy = style_policy_report(payload, base, strict=True)
    style_blocked = (style_policy.get("policy") == "required"
                     and style_policy.get("status") not in ("READY", "STYLE_ANCHOR_PENDING_APPROVAL"))
    style_lock = check_style_lock(payload, base)
    plan = check_asset_plan(payload, base) if payload.get("asset_plan") else None
    cards = payload.get("asset_cards")
    require(isinstance(cards, list) and cards, "asset_cards cannot be empty")
    require(len({c["id"] for c in cards}) == len(cards), "duplicate asset id")
    missing = []
    for original in cards:
        card, unresolved = resolve_card(original, payload, base, allow_missing)
        missing.extend({"asset_id": card["id"], **item} for item in unresolved)
        require(card.get("target_skill") == "im2-clean-image" and card.get("source_repository") == "im2-image-skills", "IM2 alias routing missing")
        require(card.get("recipe") in ("portrait", "dark", "fantasy", "hard_surface", "ink", "monochrome", "product", "clean_slate", "style"), "unknown image recipe")
        require(card.get("mode") in ("GENERATE", "EDIT", "REBUILD", "MIXED"), "image transaction mode missing")
        steps = card.get("seven_steps")
        require(isinstance(steps, list) and [s["step"] for s in steps] == list(range(1, 8)), "image seven-step order incomplete")
        require(all(substantive(s["content"]) for s in steps), "image step contains empty content")
        if card.get("asset_kind") == "character":
            require(isinstance(card.get("character_name"), str) and card["character_name"].strip(), "character asset name required")
            require(substantive(card.get("state_label")), "character asset state label required")
            layout = card.get("view_layout")
            require(isinstance(layout, dict) and substantive(layout.get("type")), "character view layout required")
            if layout["type"] == "four_view_character_turnaround":
                require(layout.get("views") == ["front_full_body", "back_full_body", "side_profile_full_body", "front_face_close_up"], "character four-view order incomplete")
                require("four-view character turnaround" in card.get("prompt", "").lower(), "character prompt missing four-view directive")
                require("front-facing head-and-shoulders face close-up" in card.get("prompt", "").lower(), "character prompt missing face view")
        if card.get("asset_kind") == "style":
            require(card.get("recipe") == "style", "style asset must use the style recipe")
            require(substantive(card.get("style_anchor_purpose")) or card.get("id") == (style_lock or {}).get("anchor_asset_id"), "style asset purpose required")
        for key in ("change", "preserve", "rebuild"):
            require(substantive(card["transaction"].get(key)), f"image transaction {key} required")
        if card.get("heavy_scene", False):
            for key in ("camera", "landmarks_topology", "depth_occlusion", "mass_support"):
                require(substantive(card["structure_lock"].get(key)), f"heavy-scene lock {key} required")
        for reference in card.get("references", []):
            require(allow_missing or (Path(base) / reference["file"]).is_file(), "missing image reference")
            require(reference["role"] in ("identity", "scene", "style", "pose", "composition", "lighting"), "image reference role invalid")
        require(substantive(card.get("prompt")), "final image prompt required")
        render_asset_prompt(card, payload.get("prompt_bindings"), style_lock)
        require(card.get("generation_status") in ("planned", "generated"), "generation status required")
        if card["generation_status"] == "generated":
            require((Path(base) / card["output_file"]).is_file(), "generated image file missing")
            require(isinstance(card.get("actual_settings"), dict) and card["actual_settings"], "actual generation settings missing")
    if style_blocked:
        require(False, style_policy["reason"])
    pending_style = style_policy.get("status") == "STYLE_ANCHOR_PENDING_APPROVAL"
    return {"status": "DRAFT" if missing or pending_style else "PASS", "stage": "assets", "assets": len(cards), "input_sha256": digest(payload), "missing_references": missing, "asset_plan": plan, "style_lock": style_lock, "style_policy": style_policy,
            "visual_status": "UNVERIFIED", "scope": "Image prompt/transaction contract; inspect actual output before visual acceptance"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("script", "assets", "production"))
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        p = read_data(args.input)
        report = check_script(p) if args.stage == "script" else check_assets(p, args.input.parent) if args.stage == "assets" else audit(p, args.input.parent)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        report = {"status": "FAIL", "stage": args.stage, "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
