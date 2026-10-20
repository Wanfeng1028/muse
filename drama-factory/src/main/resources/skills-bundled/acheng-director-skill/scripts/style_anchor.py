"""STYLE_MOTHER preflight and contract helpers.

The style anchor is an asset dependency, not a second production owner.  New
asset runs use ``style_policy=required``; historical fixtures may remain
unlocked only when they explicitly carry a legacy waiver.
"""
import hashlib
from pathlib import Path

from audit_storyboard_quality import require, substantive


STYLE_KINDS = {"character", "costume", "injury", "scene", "prop", "vehicle", "keyframe", "effect"}
STYLE_POLICIES = {"required", "waived", "legacy_unlocked"}


def check_style_lock(payload, base):
    """Validate the STYLE_MOTHER dependency and every dependent asset edge."""
    lock = payload.get("style_lock")
    if lock is None:
        return None
    require(isinstance(lock, dict), "style_lock must be an object")
    for key in ("anchor_asset_id", "anchor_version", "status", "medium"):
        require(isinstance(lock.get(key), str) and lock[key].strip(), f"style_lock.{key} required")
    require(lock["status"] in ("planned", "approved"), "style_lock.status must be planned/approved")
    require(isinstance(lock.get("preserve_scope"), list) and lock["preserve_scope"] and all(substantive(x) for x in lock["preserve_scope"]), "style_lock.preserve_scope required")
    require(isinstance(lock.get("exclude_scope"), list) and lock["exclude_scope"] and all(substantive(x) for x in lock["exclude_scope"]), "style_lock.exclude_scope required")
    apply_to = lock.get("apply_to_kinds")
    require(isinstance(apply_to, list) and apply_to and set(apply_to) <= STYLE_KINDS, "style_lock.apply_to_kinds invalid")
    nodes = {node["id"]: node for node in payload.get("asset_plan", [])}
    cards = {card["id"]: card for card in payload.get("asset_cards", [])}
    anchor_id = lock["anchor_asset_id"]
    require(anchor_id in nodes, "style_lock anchor must be planned in asset_plan")
    anchor = nodes[anchor_id]
    require(anchor.get("kind") == "style" and anchor.get("version") == lock["anchor_version"], "style_lock anchor kind/version mismatch")
    require(anchor.get("status") == lock["status"], "style_lock/anchor approval status mismatch")
    used_kinds = {n.get("kind") for n in nodes.values()} | {c.get("asset_kind") for c in cards.values()}
    require(used_kinds.intersection(STYLE_KINDS) <= set(apply_to), "style_lock.apply_to_kinds omits an asset kind in this production")
    anchor_card = cards.get(anchor_id)
    require(anchor_card is not None and anchor_card.get("recipe") == "style", "STYLE_MOTHER requires a style recipe card")
    if lock["status"] == "approved":
        approved_file = lock.get("approved_file") or anchor.get("file")
        approved_sha = lock.get("approved_sha256") or anchor.get("sha256")
        require(isinstance(approved_file, str) and approved_file.strip(), "approved style_lock requires approved_file")
        file = Path(base) / approved_file
        require(file.is_file(), "approved style_lock file missing")
        require(isinstance(approved_sha, str) and approved_sha == hashlib.sha256(file.read_bytes()).hexdigest(), "approved style_lock hash mismatch")
        require(anchor.get("file") and (Path(base) / anchor["file"]).resolve() == file.resolve(), "style_lock and anchor must approve the same file")
        require(anchor.get("sha256") == approved_sha, "style_lock and anchor must approve the same hash")
        from reference_bindings import inspect_media
        inspect_media(file, "<Picture 1>", approved_sha)
    for node_id, node in nodes.items():
        if node_id == anchor_id or node.get("kind") not in apply_to:
            continue
        need_dependencies = set(node.get("depends_on", []))
        require(anchor_id in need_dependencies, f"{node_id}: style_lock anchor missing from depends_on")
        card = cards.get(node_id)
        if card:
            style_refs = [ref for ref in card.get("references", []) if ref.get("asset_id") == anchor_id and ref.get("role") == "style"]
            require(len(style_refs) == 1 and style_refs[0].get("asset_version") == lock["anchor_version"], f"{node_id}: style reference/version missing")
            require(card.get("references", [])[-1] is style_refs[0], f"{node_id}: STYLE_MOTHER must be the final uploaded reference slot")
    return lock


def style_policy_report(payload, base, strict=True):
    """Return a deterministic preflight result without mutating production data."""
    asset_cards = payload.get("asset_cards") or []
    asset_plan = payload.get("asset_plan") or []
    has_assets = bool(asset_cards or asset_plan)
    if not has_assets:
        return {"status": "NOT_APPLICABLE", "policy": None, "reason": "no asset artifacts requested"}
    # A single isolated image does not need a cross-asset style anchor. Any
    # dependency graph or multi-card asset run does: omitting the policy there
    # is an unresolved contract, not an opt-out.
    requires_cross_asset_lock = (
        len(asset_cards) > 1
        or len(asset_plan) > 1
        or payload.get("style_lock") is not None
        or any(node.get("kind") == "style" for node in asset_plan)
    )
    policy = payload.get("style_policy")
    if policy is None:
        if not requires_cross_asset_lock:
            return {"status": "NOT_APPLICABLE", "policy": None,
                    "reason": "single isolated asset; no cross-asset style lock required"}
        if strict:
            return {"status": "BLOCKED", "policy": "required", "reason": "new asset runs must declare style_policy=required and create STYLE_MOTHER before dependent assets"}
        if payload.get("style_lock") is not None:
            lock = check_style_lock(payload, base)
            return {"status": "READY" if lock["status"] == "approved" else "STYLE_ANCHOR_PENDING_APPROVAL", "policy": "required", "style_lock": lock, "reason": "legacy payload with explicit style_lock"}
        return {"status": "LEGACY_UNCHECKED", "policy": None, "reason": "historical payload omitted the style policy"}
    require(policy in STYLE_POLICIES, "style_policy must be required, waived, or legacy_unlocked")
    if policy in ("waived", "legacy_unlocked"):
        require(substantive(payload.get("style_policy_reason")), "style_policy_reason required for an unlocked style policy")
        return {"status": "STYLE_CONSISTENCY_WAIVED", "policy": policy, "reason": payload["style_policy_reason"]}
    lock = check_style_lock(payload, base)
    if lock is None:
        if strict:
            return {"status": "BLOCKED", "policy": policy, "reason": "style_policy=required but style_lock/STYLE_MOTHER is missing"}
        return {"status": "BLOCKED", "policy": policy, "reason": "style_policy=required but style_lock/STYLE_MOTHER is missing"}
    if lock["status"] == "planned":
        return {"status": "STYLE_ANCHOR_PENDING_APPROVAL", "policy": policy, "style_lock": lock, "reason": "STYLE_MOTHER prompt exists; generate and approve its low-contamination reference image before dependent assets"}
    return {"status": "READY", "policy": policy, "style_lock": lock, "reason": "approved STYLE_MOTHER is hashed and attached to dependent assets"}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Preflight the STYLE_MOTHER dependency before asset image generation.")
    parser.add_argument("production", type=Path)
    parser.add_argument("--base", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.production.read_text(encoding="utf-8"))
        report = style_policy_report(payload, args.base or args.production.parent, strict=True)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] in ("READY", "STYLE_CONSISTENCY_WAIVED", "NOT_APPLICABLE") else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
