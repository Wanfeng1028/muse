"""Create load plans and accept bounded module patches; never spawn agents or call models."""
import argparse
import copy
import json
from pathlib import Path
import sys
from contract_core import content_hash, indexed, need, prose

ROOT = Path(__file__).resolve().parents[1]
STAGES = {"script": ["story"], "storyboard": ["shots"], "perform": ["performance"],
          "action": ["performance"], "vfx": ["effects"], "assets": ["assets"],
          "h3-compile": ["model"], "continue": ["continuity"], "audit": ["continuity"],
          "full": ["story", "shots", "performance", "assets", "model", "continuity"]}
INTEGRATION_STATUSES = {"internalized", "selective", "advisory", "guardrail", "maintenance_only", "superseded"}


def registry(root=ROOT):
    root = Path(root)
    modules = indexed(json.loads((root / "data/module-registry.json").read_text(encoding="utf-8"))["modules"], "module registry")
    owners = set()
    for module in modules.values():
        for ref in [module["entry"], *module["reads"]]:
            need((root / ref).is_file(), f"module dependency missing: {ref}")
        for pattern in module["owns"]:
            need(pattern not in owners, f"duplicate final owner: {pattern}")
            owners.add(pattern)
        need(set(module["checks_with"]) <= set(modules), "unknown adjacent checker")
    return modules


def integration_registry(root=ROOT):
    """Load and validate the red-monkey integration catalog without mutating production."""
    root = Path(root)
    payload = json.loads((root / "data/red-monkey-integrations.json").read_text(encoding="utf-8"))
    records = indexed(payload.get("records"), "red-monkey integration registry")
    allowed_stages = set(STAGES)
    for record in records.values():
        for key in ("source_skill", "status", "role", "owner", "conflict_policy"):
            need(isinstance(record.get(key), str) and record[key].strip(), f"integration {record.get('id')}: missing {key}")
        need(record["status"] in INTEGRATION_STATUSES, f"integration {record['id']}: unknown status")
        trigger = record.get("trigger")
        need(isinstance(trigger, dict), f"integration {record['id']}: trigger required")
        need(set(trigger.get("stages", [])) <= allowed_stages, f"integration {record['id']}: unknown trigger stage")
        for key in ("input", "output", "write_paths", "advisory_fields", "required_reads", "self_check"):
            need(isinstance(record.get(key), list), f"integration {record['id']}: {key} list required")
        need(not record["write_paths"], f"integration {record['id']}: integrations cannot own production writes")
        for ref in record["required_reads"]:
            need((root / ref).is_file(), f"integration {record['id']}: missing required read {ref}")
    return records


def select_integrations(request, selected_modules, production=None, root=ROOT):
    """Select only additive, non-superseded integrations for the current dispatch."""
    records = integration_registry(root)
    normalize = lambda value: str(value).strip().lower().replace("_", "-")
    features = {normalize(x) for x in request.get("features", []) if normalize(x)}
    explicit = features | {normalize(x) for x in request.get("integrations", []) if normalize(x)}
    chosen = {}

    def add(identifier, reason):
        record = records.get(identifier)
        if record and record["status"] != "superseded":
            chosen[identifier] = {"record": record, "reason": reason}

    if selected_modules or request.get("stage") in {"audit", "full"}:
        add("lobster-anti-omission-gate", "every substantive delivery needs a single non-writing completeness and claim-honesty gate")
    if "shots" in selected_modules:
        add("camera-moves-whitebox", "storyboard or full production needs semantic Previs movement")
    if "assets" in selected_modules:
        add("im2-clean-image", "asset or keyframe prompt needs the GPT Image clean pass")
    if "effects" in selected_modules:
        add("cinematic-vfx-prompt-engine", "effects module is selected")
    if "model" in selected_modules:
        add("h3-prompt-writing", "H3 syntax and mode contract are mandatory for model compilation")
    if request.get("stage") in {"audit", "full"}:
        add("lobster-self-reflection", "final structure and claim honesty need a receipt")

    feature_map = {
        "scene-concept-art-director": {"scene", "scene-design", "environment", "concept-art", "moodboard"},
        "colossal-scale-visual-director": {"colossal", "megastructure", "giant", "scale"},
        "prompt-library": {"prompt-audit", "reverse-engineer", "prompt-library"},
        "red-monkey-reasoning-kit": {"reasoning-review", "architecture-review", "conflict-review", "red-monkey-reasoning-kit"},
        "lobster-asset-manager": {"asset-archive", "asset-index", "asset-manager"},
        "lobster-security-baseline": {"external-upload", "private-reference", "sensitive-operation", "security-baseline"},
        "lobster-hot-memory-system": {"long-context", "context-trim", "hot-memory-system"},
        "skill-audit": {"skill-audit", "routing-audit"},
        "skill-foundry": {"skill-foundry", "routing-evaluation"},
        "lobster-pre-publish-security": {"package", "release", "pre-publish-security"}
    }
    for identifier, triggers in feature_map.items():
        if explicit & triggers:
            add(identifier, "explicit request feature: " + ", ".join(sorted(explicit & triggers)))
    return [{"id": identifier, "role": item["record"]["role"], "owner": item["record"]["owner"],
             "status": item["record"]["status"], "reason": item["reason"],
             "required_reads": item["record"]["required_reads"], "output": item["record"]["output"],
             "self_check": item["record"]["self_check"], "write_paths": item["record"]["write_paths"]}
            for identifier, item in chosen.items()]


def plan_dispatch(production, request, root=ROOT, skills_root=None):
    modules = registry(root)
    integration_registry(root)
    need(prose(request.get("request_id")) and request.get("stage") in STAGES, "request id/stage required")
    completed = request.get("completed_modules", [])
    need(isinstance(completed, list) and set(completed) <= set(modules), "unknown completed module")
    # Claimed completed stages require their actual artifacts in this revision.
    if "story" in completed:
        from post_hooks import check_script
        check_script(production)
    if "shots" in completed:
        need(bool(production.get("shots")) and bool(production.get("segments")), "completed shots lack artifacts")
    if "performance" in completed:
        from production_extensions import check_performance
        from performance_liveliness import check_liveliness
        need(bool(production.get("shots")), "completed performance lacks shots")
        check_performance(production)
        check_liveliness(production)
    if "assets" in completed:
        from post_hooks import check_assets
        check_assets(production, Path(request.get("production_base", Path(root) / "examples")), allow_missing=bool(production.get("asset_plan")))
    if "effects" in completed:
        from production_extensions import check_effect
        need(bool(production.get("shots")), "completed effects lack shots")
        for s in production["shots"]:
            if s["features"]["supernatural_vfx"]:
                check_effect(s["vfx"], s["end_frame"] - s["start_frame"])
    if "model" in completed or "continuity" in completed:
        from audit_storyboard_quality import audit
        need(audit(production, Path(request.get("production_base", Path(root) / "examples")))["status"] == "PASS", "completed production stage has invalid artifacts")
    selected = list(STAGES[request["stage"]])
    detected = set(request.get("features", []))
    for shot in production.get("shots", []):
        if shot.get("features", {}).get("supernatural_vfx"):
            detected.add("vfx")
        if shot.get("features", {}).get("colossal"):
            detected.add("colossal")
    if request["stage"] == "full" and detected & {"vfx", "colossal"}:
        selected.insert(3, "effects")
    selected = [m for m in selected if m not in completed]
    integration_steps = select_integrations(request, selected, production, root)
    shots = {s["id"] for s in production.get("shots", [])}
    scope = request.get("shot_ids", sorted(shots))
    need(isinstance(scope, list) and set(scope) <= shots, "dispatch scope contains unknown shot")
    reads = ["references/90-production-contract.md", "references/91-module-orchestration.md"]
    reads += [ref for step in integration_steps for ref in step["required_reads"]]
    steps = []
    for mid in selected:
        module = modules[mid]
        reads += [module["entry"], *module["reads"]]
        steps.append({"module": mid, "entry": module["entry"], "required_reads": [module["entry"], *module["reads"]], "allowed_write_paths": module["owns"],
                      "neighbor_checks": [{"module": n, "focus": module["check_focus"], "write_paths": [], "entry": modules[n]["entry"]} for n in module["checks_with"]]})
        reads += [modules[n]["entry"] for n in module["checks_with"]]
    external, blockers = [], []
    if "model" in selected:
        candidates = []
        if skills_root:
            p_root = Path(skills_root)
            candidates.append(p_root if p_root.name == "h3-prompt-writing" else p_root / "h3-prompt-writing")
            candidates.append(p_root)
        candidates.append(ROOT.parent / "h3-prompt-writing")
        candidates.append(ROOT / "modules/model/h3-prompt-writing")
        candidates.append(ROOT / "integrations/h3-prompt-writing")
        candidates.append(Path.home() / ".gemini/config/skills/h3-prompt-writing")
        candidates.append(Path.home() / ".codex/skills/h3-prompt-writing")

        found_h3 = None
        for cand in candidates:
            target = cand if cand.name == "h3-prompt-writing" else cand / "h3-prompt-writing"
            if (target / "SKILL.md").is_file():
                found_h3 = target
                break

        if found_h3:
            for name in ("SKILL.md", "references/base-en.txt", "references/ref-en.txt"):
                path = found_h3 / name
                if path.is_file():
                    external.append(str(path))
                else:
                    blockers.append(f"Required installed H3 guide missing: {path}")
        else:
            blockers.append("Required installed H3 guide missing: h3-prompt-writing")
    return {"contract_version": "3.0", "integration_contract_version": "1.0", "request_id": request["request_id"], "input_revision": content_hash(production),
            "status": "BLOCKED" if blockers else "READY", "steps": steps, "integration_steps": integration_steps,
            "required_reads": list(dict.fromkeys(reads)),
            "external_reads": external, "blockers": blockers, "shot_ids": scope,
            "frozen_paths": request.get("frozen_paths", []), "max_corrections": 1,
            "execution": "load-guidelines-and-return-contract; no automatic subagents or generation calls"}


def allowed(path, pattern):
    parts, rule = path.strip("/").split("/"), pattern.strip("/").split("/")
    return len(parts) >= len(rule) and all(a == b or b == "*" for a, b in zip(parts, rule))


def accept_response(production, dispatch, response, root=ROOT):
    modules = registry(root)
    need(dispatch.get("status") == "READY", "dispatch dependencies blocked")
    need(dispatch.get("input_revision") == content_hash(production), "stale dispatch revision")
    need(response.get("request_id") == dispatch["request_id"] and response.get("input_revision") == dispatch["input_revision"], "response identity/revision mismatch")
    module = response.get("module")
    need(module in {x["module"] for x in dispatch["steps"]}, "unrequested module")
    need(response.get("status") == "READY" and not response.get("unresolved"), "module must return unresolved issues to director before merge")
    need(type(response.get("attempt")) is int and response["attempt"] in (1, 2), "one correction maximum; return conflict to director")
    need(isinstance(response.get("evidence"), list) and response["evidence"] and all(prose(x) for x in response["evidence"]), "module evidence required")
    patch = response.get("patch")
    need(isinstance(patch, list) and patch, "empty module patch")
    result, seen = copy.deepcopy(production), set()
    for change in patch:
        need(set(change) == {"path", "value"}, "patch supports explicit replacement only")
        path = change["path"]
        need(isinstance(path, str) and path.startswith("/") and not any(t in ("", ".", "..") for t in path[1:].split("/")), "invalid patch path")
        need(path not in seen and not any(path.startswith(x + "/") or x.startswith(path + "/") for x in seen), "overlapping patch writes")
        seen.add(path)
        need(any(allowed(path, rule) for rule in modules[module]["owns"]), f"unauthorized field: {path}")
        need(not any(allowed(path, frozen) or allowed(frozen, path) for frozen in dispatch.get("frozen_paths", [])), f"frozen field: {path}")
        parts = path[1:].split("/")
        if parts[0] == "shots":
            need(parts[1].isdigit() and int(parts[1]) < len(result["shots"]) and result["shots"][int(parts[1])]["id"] in dispatch["shot_ids"], "patch leaves shot scope")
        target = result
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        key = int(parts[-1]) if isinstance(target, list) else parts[-1]
        target[key] = copy.deepcopy(change["value"])
    if module == "story":
        from story_contract import check_story
        check_story(result)
    if module == "performance":
        from production_extensions import check_performance
        from performance_liveliness import check_liveliness
        check_performance(result)
        check_liveliness(result)
    if module == "assets":
        from post_hooks import check_assets
        check_assets(result, Path(response.get("production_base", root)), allow_missing=bool(result.get("asset_plan")))
    phase_gates = {
        "story": {"narrative_contract"}, "assets": {"asset_coverage"},
        "shots": {"timeline_closure", "previs_index", "asset_coverage"},
        "performance": {"micro_acting", "combat_calculus", "performance_handoff", "performance_liveliness"},
        "effects": {"tri_state_vfx", "colossal_proofs"},
    }
    checked_gates, deferred_gates = [], []
    if result.get("shots") and result.get("segments") and result.get("ledger"):
        from audit_storyboard_quality import audit
        report = audit(result, Path(response.get("production_base", Path(root) / "examples")))
        relevant = [g for g in report["gates"] if module not in phase_gates or g["gate"] in phase_gates[module]]
        checked_gates = [g['gate'] for g in relevant if g['status'] != 'N/A']
        deferred_gates = [g['gate'] for g in report['gates'] if g not in relevant]
        failures = [g for g in relevant if g['status'] == 'FAIL']
        need(not failures, "merged production fails phase contracts: " + json.dumps(failures, ensure_ascii=False))
    else:
        need(module in {"story", "assets", "performance"}, "phase requires populated shots, segments and ledger")
        checked_gates = {"story": ["narrative_contract"], "assets": ["asset_prompt_contract"], "performance": ["performance_handoff", "performance_liveliness"]}[module]
        deferred_gates = ["full_production_audit"]
    receipt = {"request_id": dispatch["request_id"], "module": module, "input_revision": dispatch["input_revision"],
               "result_revision": content_hash(result), "changed_paths": sorted(seen), "evidence": response["evidence"],
               "attempt": response["attempt"], "status": "MERGED_CONTRACT_CHECKED",
               "validation_scope": "phase_contract_only" if deferred_gates else "populated_production_contracts",
               "checked_gates": checked_gates, "deferred_gates": deferred_gates,
               "final_delivery_accepted": False}
    result.setdefault("dispatch_log", []).append(receipt)
    return result, receipt


def main():
    from audit_storyboard_quality import read_data
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "accept"))
    parser.add_argument("production", type=Path)
    parser.add_argument("request", type=Path)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        p, req = read_data(args.production), read_data(args.request)
        if args.operation == "plan":
            req["production_base"] = str(args.production.parent)
            result = plan_dispatch(p, req, skills_root=args.skills_root)
        else:
            need(args.response is not None, "accept requires --response")
            response = read_data(args.response)
            response["production_base"] = str(args.production.parent)
            result, _ = accept_response(p, req, response)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(f"Wrote {args.out}; no model calls made")
        return 0
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
