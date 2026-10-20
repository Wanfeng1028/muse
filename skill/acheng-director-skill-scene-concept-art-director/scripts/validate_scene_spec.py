#!/usr/bin/env python3
"""Validate the portable scene-art direction contract without calling a model."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

STATUSES = {"DRAFT", "DIRECTION_LOCKED", "PROMPT_READY", "BLOCKED", "SUPERSEDED"}
PURPOSES = {"concept_keyart", "establishing_shot", "background_plate", "set_design", "matte_painting", "game_environment", "layout", "style_probe", "repair", "multi_view"}
INTENTS = {"GENERATE", "EDIT", "REBUILD", "MIXED"}
PROMPT_STATUSES = {"DRAFT", "DRAFT_MISSING_REFERENCES", "READY_TO_SUBMIT", "BLOCKED"}


def _obj(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _list(value: Any, path: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    return value


def validate(payload: Any, base_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    root = _obj(payload, "$", errors)
    required = ("schema_version", "scene_id", "revision", "status", "purpose", "source", "thesis", "world_context", "spatial", "design", "camera", "lighting", "references", "constraints", "generation", "handoff", "prompt_status", "visual_status", "evidence", "unresolved")
    for key in required:
        if key not in root:
            errors.append(f"missing required field: {key}")
    if root.get("schema_version") != "scene-art-v1":
        errors.append("schema_version must be scene-art-v1")
    if not isinstance(root.get("scene_id"), str) or not root.get("scene_id", "").strip():
        errors.append("scene_id must be a non-empty string")
    if type(root.get("revision")) is not int or root.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    if root.get("status") not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if root.get("purpose") not in PURPOSES:
        errors.append(f"purpose must be one of {sorted(PURPOSES)}")
    if root.get("prompt_status") not in PROMPT_STATUSES:
        errors.append(f"prompt_status must be one of {sorted(PROMPT_STATUSES)}")
    if root.get("visual_status") != "UNVERIFIED":
        errors.append("visual_status must remain UNVERIFIED until human review of a real image")
    for key in ("source", "thesis", "world_context", "spatial", "design", "camera", "lighting", "constraints", "generation", "handoff"):
        _obj(root.get(key), key, errors)
    for key in ("references", "evidence", "unresolved"):
        _list(root.get(key), key, errors)

    thesis = _obj(root.get("thesis"), "thesis", errors)
    for key in ("statement", "primary_tension"):
        if not isinstance(thesis.get(key), str) or not thesis.get(key, "").strip():
            errors.append(f"thesis.{key} must be a non-empty string")

    generation = _obj(root.get("generation"), "generation", errors)
    intent = generation.get("intent")
    if intent not in INTENTS:
        errors.append(f"generation.intent must be one of {sorted(INTENTS)}")
    if not isinstance(generation.get("model_family"), str) or not generation.get("model_family", "").strip():
        errors.append("generation.model_family must be a non-empty string")
    if not isinstance(generation.get("execution_settings"), dict):
        errors.append("generation.execution_settings must be an object")

    refs = _list(root.get("references"), "references", errors)
    ref_ids: set[str] = set()
    usable_refs = 0
    for i, ref in enumerate(refs):
        item = _obj(ref, f"references[{i}]", errors)
        rid = item.get("id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"references[{i}].id must be a non-empty string")
        elif rid in ref_ids:
            errors.append(f"duplicate reference id: {rid}")
        else:
            ref_ids.add(rid)
        for key in ("file", "role", "preserve", "exclude", "status"):
            if key not in item:
                errors.append(f"references[{i}] missing {key}")
        if not isinstance(item.get("preserve"), list):
            errors.append(f"references[{i}].preserve must be an array")
        if not isinstance(item.get("exclude"), list):
            errors.append(f"references[{i}].exclude must be an array")
        if item.get("status") == "approved":
            if not isinstance(item.get("file"), str) or not item.get("file", "").strip():
                errors.append(f"approved reference {rid} needs a real file")
            if not isinstance(item.get("sha256"), str) or len(item.get("sha256", "")) != 64:
                errors.append(f"approved reference {rid} needs a SHA-256")
            else:
                usable_refs += 1
                if base_dir is not None and isinstance(item.get("file"), str):
                    ref_path = Path(item["file"])
                    if not ref_path.is_absolute():
                        ref_path = base_dir / ref_path
                    if not ref_path.is_file():
                        errors.append(f"approved reference {rid} file does not exist: {item['file']}")
                    else:
                        digest = hashlib.sha256(ref_path.read_bytes()).hexdigest()
                        if digest.lower() != item["sha256"].lower():
                            errors.append(f"approved reference {rid} SHA-256 does not match file")

    if intent in {"EDIT", "REBUILD", "MIXED"} and not refs:
        errors.append(f"generation.intent={intent} requires at least one reference")
    handoff = _obj(root.get("handoff"), "handoff", errors)
    if handoff.get("write_paths") != []:
        errors.append("handoff.write_paths must be an empty array; the scene specialist is advisory")
    if root.get("prompt_status") == "READY_TO_SUBMIT" and root.get("unresolved"):
        errors.append("READY_TO_SUBMIT cannot contain unresolved items")
    if intent in {"EDIT", "REBUILD", "MIXED"} and root.get("prompt_status") == "READY_TO_SUBMIT" and usable_refs == 0:
        errors.append("READY_TO_SUBMIT edit/rebuild contract needs an approved reference")
    return errors


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_spec", type=Path)
    args = parser.parse_args()
    errors = validate(load(args.scene_spec), base_dir=args.scene_spec.parent)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("SCENE_SPEC_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
