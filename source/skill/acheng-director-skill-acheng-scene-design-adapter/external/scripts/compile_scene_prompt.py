#!/usr/bin/env python3
"""Compile a validated scene contract into standalone prompt artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from validate_scene_spec import validate


def _join(values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, list):
        return ", ".join(str(x) for x in values if str(x).strip())
    return str(values)


def compile_prompt(spec: dict[str, Any]) -> str:
    world = spec["world_context"]
    spatial = spec["spatial"]
    design = spec["design"]
    camera = spec["camera"]
    light = spec["lighting"]
    thesis = spec["thesis"]
    purpose = str(spec["purpose"]).replace("_", " ")
    location = world.get("location", "a specific environment")
    paragraphs = [
        f"{purpose.capitalize()} of {location}. {thesis['statement']} The primary visual tension is {thesis['primary_tension']}.",
        f"World context: {world.get('era', 'era unspecified')}, {world.get('season', 'season unspecified')}, {world.get('day_phase', 'time unspecified')}. The place functions as {world.get('function', 'a lived environment')}. {world.get('power_or_maintenance', '')} {world.get('recent_event', '')}",
        f"Composition: {camera.get('framing', 'clear layered framing')} from {camera.get('height', 'a grounded viewpoint')}, {camera.get('lens_feel', 'natural perspective')}, aimed at {camera.get('target', 'the focal subject')}. {spatial.get('foreground', '')} Foreground; {spatial.get('midground', '')} midground; {spatial.get('background', '')} background. Use {spatial.get('dominant_grammar', 'coherent spatial grammar')} with {spatial.get('secondary_grammar', 'no forced secondary grammar')}.",
        f"The space has {spatial.get('boundary', 'legible boundaries')}, entrances { _join(spatial.get('entrances')) }, exits { _join(spatial.get('exits')) }, and landmarks { _join(spatial.get('landmarks')) }. Traversal and scale remain readable through { _join(spatial.get('scale_anchors')) }.",
        f"Materials and design: { _join(design.get('materials')) }. Aging and weathering: { _join(design.get('aging_behavior')) }. Cultural and worldbuilding logic: { _join(design.get('cultural_logic')) }. Use only these motif families: { _join(design.get('motifs')) }. Show practical human use: { _join(design.get('human_use')) }. The iconic object is {design.get('iconic_object', 'none specified')}.",
        f"Lighting comes from { _join(light.get('sources')) }, with key direction {light.get('key_direction', 'physically motivated')}, {light.get('contrast', 'controlled contrast')}, color roles { _join(light.get('color_roles')) }, and {light.get('depth_strategy', 'layered atmospheric depth')}. Weather and atmosphere: {design.get('weather', 'physically plausible weather')} {design.get('atmosphere', '')}.",
        f"Camera intent: {camera.get('intent', 'make the scene purpose immediately legible')}. Camera path or stillness: {camera.get('path', 'static unless the purpose requires movement')}. Render as {spec['generation'].get('model_family', 'model-neutral')} scene concept art with coherent architecture, believable materials, readable silhouettes, and restrained detail."
    ]
    constraints = spec.get("constraints", {})
    if constraints.get("preserve"):
        paragraphs.append("Preserve exactly: " + _join(constraints["preserve"]) + ".")
    if constraints.get("exclude"):
        paragraphs.append("Exclude: " + _join(constraints["exclude"]) + ".")
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


def compile_artifacts(spec: dict[str, Any], out_dir: Path, base_dir: Path | None = None) -> dict[str, Any]:
    errors = validate(spec, base_dir=base_dir)
    if errors:
        raise ValueError("invalid scene spec: " + "; ".join(errors))
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_id = spec["scene_id"]
    prompt = compile_prompt(spec)
    prompt_path = out_dir / f"{scene_id}.image.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    refs = spec["references"]
    missing = [r.get("id") for r in refs if r.get("status") != "approved"]
    prompt_status = "DRAFT_MISSING_REFERENCES" if missing and spec["generation"]["intent"] != "GENERATE" else "READY_TO_SUBMIT"
    upload_lines = [f"# Upload manifest for {scene_id}", "", "Upload in listed order before submitting the prompt."]
    if refs:
        for index, ref in enumerate(refs, 1):
            upload_lines.append(f"{index}. `{ref.get('id')}` — file: `{ref.get('file') or 'MISSING'}`; role: {ref.get('role')}; preserve: {_join(ref.get('preserve'))}; exclude: {_join(ref.get('exclude'))}.")
    else:
        upload_lines.append("No reference image is required; submit the standalone prompt directly.")
    (out_dir / "UPLOAD.md").write_text("\n".join(upload_lines) + "\n", encoding="utf-8")
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    index = {
        "schema_version": "scene-art-index-v1",
        "scene_id": scene_id,
        "revision": spec["revision"],
        "prompt_file": prompt_path.name,
        "prompt_sha256": digest,
        "prompt_status": prompt_status,
        "visual_status": "UNVERIFIED",
        "references": refs,
        "unresolved": list(spec.get("unresolved", [])) + missing,
        "model_family": spec["generation"].get("model_family"),
        "execution_settings": spec["generation"].get("execution_settings", {}),
    }
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    qa = {"scene_id": scene_id, "status": "UNVERIFIED", "checks": ["contract", "prompt completeness", "reference manifest"], "human_review_required": True}
    (out_dir / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_spec", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.scene_spec.read_text(encoding="utf-8"))
    result = compile_artifacts(spec, args.out_dir, base_dir=args.scene_spec.parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
