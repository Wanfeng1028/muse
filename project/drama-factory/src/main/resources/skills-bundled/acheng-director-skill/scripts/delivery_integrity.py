#!/usr/bin/env python3
"""Run the single-pass, non-invasive delivery integrity gate."""
import argparse
import json
import re
from pathlib import Path

from asset_plan import resolve_card
from audit_storyboard_quality import audit, read_data


STAGES = {
    "script", "storyboard", "perform", "action", "vfx", "assets",
    "h3-compile", "continue", "audit", "full",
}
OMISSION_PATTERNS = (
    r"\bsame as above\b",
    r"\bas above\b",
    r"\bcontinue (?:from|the) previous\b",
    r"\badjust as needed\b",
    r"\bsee (?:the )?(?:character )?setup\b",
    r"\betc\.?\b",
    r"同上",
    r"如上",
    r"沿用前段",
    r"根据需要调整",
    r"若干动作",
    r"等等",
    r"见角色设定",
)
OMISSION_RE = re.compile("|".join(OMISSION_PATTERNS), re.IGNORECASE)


def _add_unique(items, value):
    if value and value not in items:
        items.append(value)


def _model_texts(payload):
    """Yield only model-facing text; dialogue source is intentionally excluded."""
    for segment in payload.get("segments", []):
        for key in ("style", "summary", "overall_soundscape", "non_diegetic_music"):
            value = segment.get(key)
            if isinstance(value, str):
                yield f"segments[{segment.get('id', '?')}].{key}", value
    for card in payload.get("asset_cards", []):
        value = card.get("prompt")
        if isinstance(value, str):
            yield f"asset_cards[{card.get('id', '?')}].prompt", value


def _scope(payload, stage):
    declared = payload.get("delivery_scope", "prompt_only")
    if declared not in {"prompt_only", "full_production"}:
        return declared, "delivery_scope must be prompt_only or full_production"
    if stage == "full" and declared != "full_production":
        return declared, "full stage requires delivery_scope=full_production"
    return declared, None


def check_delivery_integrity(payload, stage, base=None, require_ready=False):
    """Return a receipt without mutating *payload* or any referenced file."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if not isinstance(payload, dict):
        raise ValueError("production payload must be an object")
    base = Path(base or ".").resolve()
    scope, scope_error = _scope(payload, stage)
    blocked, unresolved, evidence = [], [], []
    if scope_error:
        blocked.append(scope_error)

    for location, text in _model_texts(payload):
        match = OMISSION_RE.search(text)
        if match:
            blocked.append(f"{location} contains unresolved omission shorthand: {match.group(0)}")

    if stage in {"storyboard", "perform", "action", "vfx", "h3-compile", "full"}:
        if not payload.get("shots"):
            blocked.append("shots is required for this stage")
        else:
            evidence.append(f"shots:{len(payload['shots'])}")
    if stage in {"h3-compile", "full"}:
        if not payload.get("segments"):
            blocked.append("segments is required for H3 delivery")
        else:
            evidence.append(f"segments:{len(payload['segments'])}")
            from reference_bindings import resolve_bindings
            for segment in payload['segments']:
                try:
                    snapshot = resolve_bindings(payload, segment, base)
                    for issue in snapshot['issues']:
                        _add_unique(unresolved, segment['id'] + ': ' + issue)
                        _add_unique(blocked, segment['id'] + ': ' + issue)
                except (ValueError, KeyError, TypeError) as exc:
                    blocked.append(segment.get('id', '?') + ': reference binding cannot resolve: ' + str(exc))
    if stage in {"assets", "full"}:
        if not payload.get("asset_cards"):
            blocked.append("asset_cards is required for asset delivery")
        else:
            evidence.append(f"asset_cards:{len(payload['asset_cards'])}")

    for item in payload.get("unresolved", []):
        _add_unique(unresolved, str(item))
    for item in payload.get("execution_gate", []):
        _add_unique(unresolved, str(item))
    for card in payload.get("asset_cards", []):
        if payload.get("asset_plan"):
            try:
                _, missing = resolve_card(card, payload, base, True)
            except (ValueError, KeyError, TypeError) as exc:
                blocked.append(f"asset_cards[{card.get('id', '?')}] cannot resolve: {exc}")
                missing = []
            for item in missing:
                if isinstance(item, dict):
                    detail = item.get("file") or item.get("asset_id") or str(item)
                    _add_unique(unresolved, f"missing reference: {card.get('id', '?')} -> {detail}")
        for ref in card.get("references", []):
            if isinstance(ref, dict) and ref.get("file") and not (base / ref["file"]).is_file():
                _add_unique(unresolved, f"missing reference: {card.get('id', '?')} -> {ref['file']}")
    if payload.get("visual_status") == "UNVERIFIED" or payload.get("generated_media_status") == "UNVERIFIED":
        _add_unique(unresolved, "generated image/video/audio remains UNVERIFIED")

    if require_ready and unresolved:
        blocked.append("delivery has unresolved items and require_ready=true")
    if blocked:
        status = "EXECUTION_BLOCKED" if stage in {"h3-compile", "full"} else "NEEDS_DIRECTOR_REVISION"
        next_action = "Resolve the listed blockers, then rerun this gate."
    else:
        status = "PASS"
        next_action = "None; preserve unresolved disclosures in the handoff."
    return {
        "status": status,
        "scope": scope,
        "delivered": stage,
        "blocked": blocked,
        "evidence": evidence,
        "unresolved": unresolved,
        "next_action": next_action,
    }


def check_production(path, stage, require_ready=False):
    path = Path(path).resolve()
    payload = read_data(path)
    receipt = check_delivery_integrity(payload, stage, path.parent, require_ready=require_ready)
    if stage in {"script", "assets", "full"} and not receipt["blocked"]:
        from post_hooks import check_assets, check_script
        try:
            checks = []
            if stage in {"script", "full"}:
                checks.append(check_script(payload))
            if stage in {"assets", "full"}:
                checks.append(check_assets(payload, path.parent, allow_missing=not require_ready))
            for result in checks:
                receipt["evidence"].append(result["stage"] + "_contract:" + result["status"])
                if result["status"] != "PASS":
                    receipt["unresolved"].append(result["stage"] + " contract remains draft")
                    if require_ready:
                        raise ValueError("stage contract not ready: " + result["stage"])
        except (ValueError, KeyError, TypeError) as exc:
            receipt["blocked"].append(str(exc))
            receipt["status"] = "EXECUTION_BLOCKED" if stage == "full" else "NEEDS_DIRECTOR_REVISION"
            receipt["next_action"] = "Repair the stage contract, then rerun this gate."
    if stage in {"storyboard", "perform", "action", "vfx", "h3-compile", "full", "audit"} and not receipt["blocked"]:
        report = audit(payload, path.parent)
        receipt["evidence"].append(f"machine_audit:{report['status']}")
        if report["status"] != "PASS":
            receipt["blocked"].append("machine production audit failed")
            receipt["status"] = "EXECUTION_BLOCKED" if stage in {"h3-compile", "full"} else "NEEDS_DIRECTOR_REVISION"
            receipt["next_action"] = "Repair the failed production gates, then rerun this gate."
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument("input", type=Path)
    parser.add_argument("--require-ready", action="store_true", help="Treat unresolved items as blockers.")
    args = parser.parse_args()
    try:
        receipt = check_production(args.input, args.stage, args.require_ready)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        receipt = {"status": "EXECUTION_BLOCKED", "scope": "unknown", "delivered": args.stage,
                   "blocked": [str(exc)], "evidence": [], "unresolved": [],
                   "next_action": "Fix the input and rerun this gate."}
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
