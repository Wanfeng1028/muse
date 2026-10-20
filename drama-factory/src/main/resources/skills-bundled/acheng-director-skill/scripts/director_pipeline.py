#!/usr/bin/env python3
"""Deterministic packing, VFX-only patches and immutable continuity archives."""
import argparse
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from audit_storyboard_quality import ContractError, audit, digest, read_data, require
from post_hooks import check_assets
from h3_contract import clip_bounds


def save_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def accepted(p, base):
    report = audit(p, base)
    require(report["status"] == "PASS", json.dumps(report, ensure_ascii=False))
    if p.get("asset_cards"):
        check_assets(p, base, allow_missing=bool(p.get("asset_plan")))
    return report


def verify_archive(directory):
    directory = Path(directory).resolve()
    manifest = read_data(directory / "manifest.json")
    require({"production.json", "ledger.json", "hot.json", "audit.json"} <= set(manifest["hashes"]), "corrupt archive manifest: required files missing")
    import hashlib
    for name, expected in manifest["hashes"].items():
        path = (directory / name).resolve()
        require(directory in path.parents, "archive path escapes revision")
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"corrupt existing archive: {name}")
    p = read_data(directory / "production.json")
    require(digest(p) == manifest["revision"], "corrupt archive revision")
    require(read_data(directory / "ledger.json") == p["ledger"], "archive ledger differs from source")
    require(read_data(directory / "hot.json")["state"] == p["ledger"]["final"], "archive hot state differs from source")
    return p, manifest


def restore(directory, output):
    directory, output = Path(directory).resolve(), Path(output)
    p, manifest = verify_archive(directory)
    require(not output.exists(), "restore output already exists; choose a new directory")
    result = copy.deepcopy(p)
    for seg in result["segments"] + result.get("asset_cards", []):
        for ref in seg.get("references", []):
            if "file" not in ref:
                continue
            mapped = manifest["reference_resolver"].get(ref["file"])
            require(mapped in manifest["hashes"], "archive reference missing from verified manifest")
            ref["file"] = mapped
    for node in result.get("asset_plan", []):
        if node.get("status") == "approved":
            mapped = manifest["reference_resolver"].get(node["file"])
            require(mapped in manifest["hashes"], "approved asset missing from archive")
            node["file"] = mapped
    lock = result.get("style_lock") or {}
    if lock.get("status") == "approved" and lock.get("approved_file"):
        mapped = manifest["reference_resolver"].get(lock["approved_file"])
        require(mapped in manifest["hashes"], "approved STYLE_MOTHER missing from archive")
        lock["approved_file"] = mapped
    # Check the restored relative paths against the archive before any write.
    accepted(result, directory)
    output.mkdir(parents=True)
    for name in set(manifest["reference_resolver"].values()):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(directory / name, path)
    result["base_revision"] = manifest["revision"]
    save_new(output / "production.json", result)
    save_new(output / "restore-receipt.json", {"source_revision": manifest["revision"], "restored_sha256": digest(result), "reference_paths_rebased": True})
    accepted(result, output)
    return output / "production.json"


def pack(p):
    result = copy.deepcopy(p)
    shots = result.get("shots", [])
    require(bool(shots), "cannot pack an empty production")
    minimum, maximum = clip_bounds(p)
    limit = maximum * p["fps_num"] / p["fps_den"]
    floor = minimum * p["fps_num"] / p["fps_den"]
    require(limit.denominator == 1 and limit > 0, "clip limit must align with a positive frame count")
    last = 0
    for shot in shots:
        require(shot["start_frame"] == last, "shots have a gap or overlap")
        length = shot["end_frame"] - shot["start_frame"]
        require(0 < length <= limit, f"{shot['id']}: {length} frames cannot fit {limit}-frame window; split at an approved action boundary")
        last = shot["end_frame"]
    require(Fraction(last * p["fps_den"], p["fps_num"]) == Fraction(str(p["production_total_duration"])), "packing cannot change production duration")
    # Dynamic programming preserves authored shot boundaries and finds a legal
    # partition when greedy maximum-fill would strand a short tail.
    best = {len(shots): []}
    for start in range(len(shots) - 1, -1, -1):
        choices = []
        for end in range(start + 1, len(shots) + 1):
            length = shots[end - 1]["end_frame"] - shots[start]["start_frame"]
            if length > limit:
                break
            if length >= floor and end in best:
                choices.append([shots[start:end], *best[end]])
        if choices:
            best[start] = min(choices, key=lambda groups: (len(groups), -(groups[0][-1]["end_frame"] - groups[0][0]["start_frame"])))
    require(0 in best, "No legal 4–15s partition at authored shot boundaries; revise an action-safe cut or explicitly plan generation handles without changing edit duration")
    buckets = best[0]
    prior = {tuple(s["shot_ids"]): s for s in p.get("segments", [])}
    output = []
    for i, group in enumerate(buckets, 1):
        ids = tuple(s["id"] for s in group)
        if ids in prior:
            seg = copy.deepcopy(prior[ids])
        else:
            # New partitions need a genuine reference/mode and sound decision.
            seg = {"id": f"SEG{i:03d}", "shot_ids": list(ids),
                   "execution_gate": "Rebind mode, references, panels, style and sound for this new partition"}
        seg.update(start_frame=group[0]["start_frame"], end_frame=group[-1]["end_frame"])
        duration = Fraction((seg["end_frame"] - seg["start_frame"]) * p["fps_den"], p["fps_num"])
        seg["generation_clip_duration"] = str(duration) if duration.denominator != 1 else duration.numerator
        output.append(seg)
    result["segments"] = output
    result["base_revision"] = digest(p)
    return result


def optimize(p, patch, base):
    accepted(p, base)
    require(set(patch) == {"base_sha256", "mode", "updates"}, "patch has unexpected top-level fields")
    require(patch["base_sha256"] == digest(p), "stale_revision: VFX patch was prepared for different input")
    require(patch["mode"] == "OPTIMIZE", "only OPTIMIZE is a VFX-only transaction")
    require(isinstance(patch["updates"], list) and patch["updates"], "empty VFX patch")
    result = copy.deepcopy(p)
    index = {s["id"]: s for s in result["shots"]}
    seen = set()
    for entry in patch["updates"]:
        require(set(entry) == {"shot_id", "vfx"}, "OPTIMIZE may only replace vfx, never camera/action/timeline")
        sid = entry["shot_id"]
        require(sid in index and sid not in seen, "unknown or repeated VFX shot")
        require(index[sid]["features"]["supernatural_vfx"], "cannot introduce a new energy event through OPTIMIZE")
        require(isinstance(entry["vfx"], dict), "VFX replacement must be object")
        # Existing event endpoints and outcomes stay fixed even inside the slot.
        for key in ("family", "origin", "collision_type", "collision", "phases", "scope", "process", "end_state", "continuity", "events"):
            require(entry["vfx"].get(key) == index[sid]["vfx"].get(key), f"OPTIMIZE freezes vfx.{key}; submit a director revision instead")
        index[sid]["vfx"] = copy.deepcopy(entry["vfx"])
        seen.add(sid)
    accepted(result, base)
    return result


def archive(p, base, output):
    report = accepted(p, base)
    output = Path(output)
    revision = digest(p)
    revisions = output / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    final = revisions / revision
    if final.exists():
        _, manifest = verify_archive(final)
        require(manifest["revision"] == revision, "archive identity mismatch")
        return final
    temp = Path(tempfile.mkdtemp(prefix=".pending-", dir=revisions))
    # Copy external references into the immutable revision; preserve production
    # bytes semantically and supply a resolver map instead of rewriting its paths.
    asset_map = {}
    reference_groups = p["segments"] + p.get("asset_cards", []) + [{"references": [n for n in p.get("asset_plan", []) if n.get("status") == "approved"]}]
    for seg in reference_groups:
        for ref in seg.get("references", []):
            if "file" not in ref:
                continue
            source = (Path(base) / ref["file"]).resolve()
            import hashlib
            content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            name = "assets/" + content_hash + source.suffix.lower()
            destination = temp / name
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                shutil.copyfile(source, destination)
            asset_map[ref["file"]] = name
    lock = p.get("style_lock") or {}
    if lock.get("status") == "approved" and lock.get("approved_file"):
        source = (Path(base) / lock["approved_file"]).resolve()
        import hashlib
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        name = "assets/" + content_hash + source.suffix.lower()
        destination = temp / name
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        asset_map[lock["approved_file"]] = name
    save_new(temp / "production.json", p)
    save_new(temp / "ledger.json", p["ledger"])
    narrative = {}
    if p.get("story", {}).get("contract_version") == "3.0":
        from story_contract import check_story
        checked = check_story(p)
        narrative = {key: checked[key] for key in ("knowledge_final", "relationship_final", "open_setups")}
    save_new(temp / "hot.json", {"project_id": p["project_id"], "revision": revision,
             "cold_production": "production.json", "state": p["ledger"]["final"],
             "narrative": narrative,
             "last_shot": p["shots"][-1]["id"], "unresolved_threads": p.get("unresolved_threads", [])})
    save_new(temp / "audit.json", report)
    import hashlib
    hashes = {str(path.relative_to(temp)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in temp.rglob("*") if path.is_file()}
    save_new(temp / "manifest.json", {"revision": revision, "hashes": hashes, "reference_resolver": asset_map})
    for name, expected in hashes.items():
        require(hashlib.sha256((temp / name).read_bytes()).hexdigest() == expected, f"archive verification failed: {name}")
    try:
        os.rename(temp, final)
    except FileExistsError:
        raise ContractError(f"Concurrent archive already exists at {final}; pending copy retained at {temp}")
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("pack", "optimize", "archive", "restore"))
    parser.add_argument("production", type=Path)
    parser.add_argument("patch", nargs="?", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "restore":
            print(restore(args.production, args.out))
            return 0
        p = read_data(args.production)
        if args.operation == "archive":
            print(archive(p, args.production.parent, args.out))
        else:
            require(args.out.resolve().parent == args.production.resolve().parent,
                    "Keep output beside production so relative references remain valid")
            if args.operation == "pack":
                result = pack(p)
            else:
                require(args.patch is not None, "optimize requires a patch file")
                result = optimize(p, read_data(args.patch), args.production.parent)
            save_new(args.out, result)
            print(f"Wrote {args.out}; source retained")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
