#!/usr/bin/env python3
"""Final package acceptance: integrity, complete catalogs, links and real examples."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from audit_storyboard_quality import ROOT, audit, compile_segment, read_data, require
from post_hooks import check_assets
from prompt_delivery import render_asset_prompt
from asset_plan import resolve_card
from director_dispatch import integration_registry, registry
from director_library import validate_libraries

REQUIRED = ["00-visual-constitution", "10-scriptwriter-engine", "20-storyboard-compiler",
            "25-combat-video-deconstructor", "30-performance-adapter", "40-action-choreography",
            "45-vfx-sakuga-engine", "50-character-morphology", "60-assets-and-keyframes",
            "70-minimax-h3-compiler", "80-continuity-ledger", "90-production-contract",
            "72-standalone-prompt-delivery", "95-quality-gates", "99-source-audit", "11-story-architecture",
            "12-character-dialogue-revision", "21-genre-camera-capacity", "31-performance-handoff",
            "32-liveliness-performance-framework", "46-effect-families", "61-asset-dependency-production", "91-module-orchestration",
            "93-red-monkey-integration", "94-delivery-integrity", "62-style-anchor", "111-h3-final-format-pass-v4",
            "113-animation-art-terminology-library-v4.3", "114-reference-binding-delivery-v4.3.6", "115-directed-decisions",
            "116-visual-reference-library"]

TERMINOLOGY_CATEGORIES = {
    "timing_exposure", "drawing_structure", "acting_motion", "combat_impact",
    "camera_editing", "layout_environment", "line_color_compositing",
    "effects_debris", "qa_evidence",
}
TERMINOLOGY_FIELDS = ("term", "purpose", "use_when", "expansion", "evidence")


def validate(root=ROOT):
    root = Path(root).resolve()
    for name in REQUIRED:
        require((root / f"references/{name}.md").is_file(), f"Missing reference: {name}")
    entry = (root / "SKILL.md").read_text(encoding="utf-8")
    require(entry.startswith("---\nname: acheng-director\n"), "SKILL frontmatter/name invalid")
    require((root / "使用指南.md").is_file(), "User guide missing")
    modules = registry(root)
    reference_libraries = validate_libraries(root)
    require(len(modules) == 7, "Seven production modules required")
    for module_id, module in modules.items():
        guide = f"references/decisions/{module_id}.md"
        require(guide in module["reads"] and (root / guide).is_file(), f"Missing local decision route: {module_id}")
    integrations = integration_registry(root)
    required_integrations = {
        "h3-prompt-writing", "im2-clean-image", "cinematic-vfx-prompt-engine",
        "colossal-scale-visual-director", "camera-moves-whitebox", "prompt-library",
        "red-monkey-reasoning-kit", "lobster-asset-manager", "lobster-security-baseline", "lobster-anti-omission-gate",
        "lobster-self-reflection", "lobster-hot-memory-system", "skill-audit", "skill-foundry"
    }
    require(required_integrations <= set(integrations), "Required red-monkey integration missing")
    require(all(record["write_paths"] == [] for record in integrations.values()), "Integration acquired a production write path")
    require(integrations["red-monkey-reasoning-kit"]["owner"] == "director", "Reasoning kit must remain director advisory")
    require(integrations["prompt-library"]["owner"] == "director", "Prompt library must remain director advisory")
    active_md = [*sorted(root.glob("*.md")), *sorted((root / "references").glob("*.md")), *sorted((root / "references/decisions").glob("*.md")),
                 *sorted((root / "references/inquiries").glob("*.md")),
                 *sorted((root / "examples").rglob("*.md")), *sorted((root / "templates").glob("*.md")),
                 *sorted((root / "modules").rglob("*.md")), root / "reports/v3-capability-trace.md",
                 root / "reports/v3.1-liveliness-review.md", root / "reports/v3.2-conflict-resolution.md"]
    for path in active_md:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "#")):
                continue
            require(not target.startswith("file://"), f"Nonportable link in {path.name}")
            require((path.parent / unquote(target.strip("<>").split("#")[0])).exists(), f"Broken link in {path.name}: {target}")
    for path in (root / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    catalog = read_data(root / "data/camera-moves.json")
    require(len(catalog) == 132, "Camera catalog count")
    ids = [x["id"] for x in catalog]
    require(ids == [f"{i:03d}" for i in range(1, 133)], "Camera catalog ID order")
    source = read_data(root / "references/sources/camera/manifest.json")
    for derived, original in zip(catalog, source["moves"]):
        require(derived["key"] == original["key"] and derived["name_zh"] == original["cn"] and derived["name_en"] == original["en"], "Camera source identity changed")
    storyboard = (root / "references/20-storyboard-compiler.md").read_text(encoding="utf-8")
    require(re.findall(r"^\| (\d{3}) \|", storyboard, re.M) == ids, "Inline 132 table mismatch")
    emotion = (root / "references/30-performance-adapter.md").read_text(encoding="utf-8")
    require(re.findall(r"^\| E(\d{3}) ", emotion, re.M) == [f"{i:03d}" for i in range(1, 101)], "Expanded emotions must contain exactly E001-E100")
    original = (root / "references/sources/emotions-original.md").read_text(encoding="utf-8")
    require(len(re.findall(r"^\d+\. \*\*", original, re.M)) == 100, "Original 100 emotions lost")
    for record in read_data(root / "data/source-hashes.json"):
        path = root / record["file"]
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], f"Source integrity mismatch: {record['file']}")
    terminology = read_data(root / "data/animation-art-terminology.json")
    require(terminology.get("schema_version") == "4.3", "Animation terminology catalog schema version mismatch")
    require(terminology.get("catalog_id") == "acheng-animation-art-terminology", "Animation terminology catalog id mismatch")
    policy = terminology.get("selection_policy")
    require(isinstance(policy, dict) and policy.get("require_expansion") is True and policy.get("term_is_not_a_fact") is True,
            "Animation terminology selection policy is incomplete")
    require(set(policy.get("required_evidence_keys", [])) == {"time_window", "observable_fact", "camera_or_layout", "sound_or_qa"},
            "Animation terminology evidence contract mismatch")
    categories = terminology.get("categories")
    require(isinstance(categories, list) and {item.get("id") for item in categories} == TERMINOLOGY_CATEGORIES,
            "Animation terminology category coverage mismatch")
    term_ids = []
    for category in categories:
        require(isinstance(category.get("name_zh"), str) and category["name_zh"].strip(),
                f"Animation terminology category name missing: {category.get('id')}")
        terms = category.get("terms")
        require(isinstance(terms, list) and terms, f"Animation terminology category empty: {category.get('id')}")
        for term in terms:
            require(all(isinstance(term.get(field), (str, list)) and term.get(field) for field in TERMINOLOGY_FIELDS),
                    f"Animation terminology term incomplete: {term.get('id')}")
            require(term.get("id") not in term_ids, f"Duplicate animation terminology id: {term.get('id')}")
            term_ids.append(term["id"])
    term_id_set = set(term_ids)
    groups = policy.get("mutual_exclusion_groups")
    require(isinstance(groups, list) and all(isinstance(group, list) and len(group) >= 2 for group in groups),
            "Animation terminology mutual exclusion policy is malformed")
    require(all(set(group) <= term_id_set and len(set(group)) == len(group) for group in groups),
            "Animation terminology mutual exclusion group references an unknown or duplicate term")
    reports = []
    video_count, image_count, draft_count, character_asset_count, draft_video_count = 0, 0, 0, 0, 0
    modes, scopes = set(), set()
    liveliness_examples = 0
    def check_export(directory, entries):
        require((directory / "UPLOAD.md").is_file(), f"Upload instructions missing: {directory}")
        if directory.parent.name == "images":
            require((directory / "ASSET_NAMES.txt").is_file(), f"Asset names index missing: {directory}")
            names = (directory / "ASSET_NAMES.txt").read_text(encoding="utf-8").splitlines()
            require(names == [entry["display_name"] for entry in entries], f"Asset names index differs: {directory}")
            require(all("提示词" not in name and "状态" not in name and "参考图" not in name for name in names), "Asset names index contains presentation noise")
        for entry in entries:
            for ref in entry.get("references", []):
                if ref.get('binding_status') in {'PLANNED', 'PLANNED_OR_CONFLICTED', 'NEEDS_REFERENCE_DECISION'}:
                    continue
                copied = directory / ref["file"]
                require(copied.is_file() and hashlib.sha256(copied.read_bytes()).hexdigest() == ref["sha256"], "Exported reference missing or corrupt")
    for path in sorted((root / "examples").glob("*.production.json")):
        production = read_data(path)
        report = audit(production, path.parent)
        expected_draft = production.get('example_delivery_expectation') == 'DRAFT_MISSING_REFERENCES'
        failed = [g for g in report['gates'] if g['status'] == 'FAIL']
        require(report['status'] == 'PASS' or (expected_draft and failed and all(g['gate'] == 'h3_schema' and all('missing reference file:' in error for error in g['errors']) for g in failed)),
                f"Example failed: {path.name}: {json.dumps(report, ensure_ascii=False)}")
        asset_report = check_assets(production, path.parent, allow_missing=bool(production.get("asset_plan")))
        scopes.add(production.get("delivery_scope", "prompt_only"))
        liveliness_examples += any(s.get("performance", {}).get("acting_design") for s in production["shots"])
        folder = path.name.split("-", 1)[1].split(".", 1)[0]
        video_dir = root / "examples/compiled" / folder
        image_dir = root / "examples/compiled/images" / folder
        video_index = read_data(video_dir / "index.json")
        image_index = read_data(image_dir / "index.json")
        require(video_index["production_sha256"] == report["production_sha256"], "Stale H3 export")
        require(image_index["input_sha256"] == report["production_sha256"], "Stale image export")
        check_export(video_dir, video_index["segments"])
        if video_index.get('version') == '4.3.6':
            from h3_delivery import validate_package
            joint = validate_package(video_dir, production, path.parent)
            require(joint['status'] == ('DRAFT_NOT_SUBMITTABLE' if expected_draft else 'PASS'), 'Example joint delivery failed')
        else:
            raise ValueError('Example lacks 4.3.6 joint delivery bundle')
        check_export(image_dir, image_index["assets"])
        from asset_delivery import validate_asset_entries
        require(video_index.get('asset_reference_contract') == '1.0' and image_index.get('asset_reference_contract') == '1.0', 'Example asset reference contract missing')
        validate_asset_entries(image_dir, image_index['assets'], production=production, source_base=path.parent)
        for seg in production["segments"]:
            from reference_bindings import resolve_bindings
            import copy
            exported = next(e for e in video_index['segments'] if e['segment_id'] == seg['id'])
            snapshot = resolve_bindings(production, seg, path.parent)
            resolved = copy.deepcopy(seg)
            resolved['references'] = [r for r in snapshot['references'] if r['label'].startswith('<')]
            resolved['subjects'] = snapshot['subjects']
            is_draft = not exported['accepted']
            require(is_draft == expected_draft, 'Example readiness differs from declared acceptance scenario')
            if is_draft:
                require(snapshot['issues'] and exported['status'] == 'DRAFT_MISSING_REFERENCES', 'Missing-media example must actually be blocked')
            prefix = 'DRAFT — planned references/contract unresolved; do not submit. Creative content retained below.\n\n' if is_draft else ''
            require((video_dir / exported['file']).read_text(encoding='utf-8') == prefix + compile_segment(production, resolved, draft=is_draft), 'H3 export differs from source')
            draft_video_count += is_draft
            video_count += 1
            modes.add(seg["mode"])
        entries = {item["asset_id"]: item for item in image_index["assets"]}
        for card in production["asset_cards"]:
            resolved, missing = resolve_card(card, production, path.parent, True)
            if resolved.get("asset_kind") == "character":
                character_asset_count += 1
                require(resolved.get("character_name") and resolved.get("state_label"), f"Character asset labels missing: {card['id']}")
                require(resolved.get("view_layout", {}).get("type") == "four_view_character_turnaround", f"Character four-view layout missing: {card['id']}")
                require(resolved["view_layout"].get("views") == ["front_full_body", "back_full_body", "side_profile_full_body", "front_face_close_up"], f"Character four-view order invalid: {card['id']}")
            entry = entries[card["id"]]
            prefix = "DRAFT — required reference images are not yet supplied. Do not submit until the upload manifest is resolved.\n\n" if missing else ""
            require((image_dir / entry["prompt_file"]).read_text(encoding="utf-8") == prefix + render_asset_prompt(resolved, production.get("prompt_bindings"), production.get("style_lock")), "Image export differs from source")
            require(entry["status"] == ("draft-missing-references" if missing else "ready-to-submit-not-generated"), "Asset readiness misreported")
            require(entry["missing_references"] == missing, "Missing-reference manifest differs from source")
            image_count += 1
            draft_count += bool(missing)
        require(image_index["status"] == ("draft-dependencies-pending" if asset_report["missing_references"] else "ready-to-submit-not-generated"), "Asset package readiness mismatch")
        reports.append({"file": path.relative_to(root).as_posix(), "scope": production.get("delivery_scope", "prompt_only"), "score": report["score"], "applicable_gates": report["applicable_gates"], "sha256": report["production_sha256"]})
    require(len(reports) >= 8, "At least eight authored production examples required")
    require(modes == {"T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"}, "Examples do not cover all H3 modes")
    require("full_production" in scopes, "Full narrative/asset production example missing")
    require(liveliness_examples >= 1, "At least one authored example must exercise acting_design")
    return {"status": "PASS", "camera_entries": 132, "original_emotions": 100, "expanded_emotions": 100,
            "required_references": len(REQUIRED), "examples": reports, "reference_libraries": reference_libraries,
            "modules": len(modules), "local_decision_guides": len(modules), "asset_reference_contract": "1.0", "integrations": len(integrations), "terminology_categories": len(categories),
            "terminology_terms": len(term_ids), "character_four_view_assets": character_asset_count, "h3_modes": sorted(modes),
            "standalone_video_prompts": video_count, "image_prompt_designs": image_count,
            "ready_video_prompts": video_count - draft_video_count, "draft_video_prompts": draft_video_count,
            "ready_image_prompts": image_count - draft_count, "draft_image_prompts": draft_count,
            "visual_verification": "Authored blocking and ink reference images only; generated film and audio remain UNVERIFIED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (ValueError, OSError, KeyError, TypeError, SyntaxError) as exc:
        report = {"status": "FAIL", "error": str(exc)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
