#!/usr/bin/env python3
"""Select and expand animation-art vocabulary without creating production facts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "animation-art-terminology.json"


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != "4.3":
        raise ValueError("unsupported animation terminology catalog version")
    seen = set()
    for category in data.get("categories", []):
        if not category.get("id") or not category.get("terms"):
            raise ValueError("each terminology category needs an id and terms")
        for term in category["terms"]:
            if term.get("id") in seen:
                raise ValueError(f"duplicate terminology id: {term.get('id')}")
            seen.add(term.get("id"))
            for key in ("term", "purpose", "use_when", "expansion", "evidence"):
                if not term.get(key):
                    raise ValueError(f"{term.get('id')}: missing {key}")
    return data


def index_catalog(data: dict) -> dict[str, dict]:
    return {term["id"]: {**term, "category": category["id"], "category_name_zh": category["name_zh"]}
            for category in data["categories"] for term in category["terms"]}


def select_terms(*, requested=(), categories=(), limit=12, catalog=None) -> list[dict]:
    data = catalog or load_catalog()
    index = index_catalog(data)
    selected = []
    groups = [set(group) for group in data.get("selection_policy", {}).get("mutual_exclusion_groups", [])]

    def add(item: dict, *, explicit: bool) -> None:
        if item["id"] in [entry["id"] for entry in selected]:
            return
        selected_ids = {entry["id"] for entry in selected}
        conflicting_ids = set().union(
            *(group & selected_ids for group in groups if item["id"] in group),
        )
        if conflicting_ids:
            if explicit:
                conflict = sorted(conflicting_ids)[0]
                raise ValueError(f"mutually exclusive terminology selected: {item['id']} conflicts with {conflict}")
            return
        selected.append(item)

    for term_id in requested:
        if term_id not in index:
            raise KeyError(f"unknown animation terminology id: {term_id}")
        add(index[term_id], explicit=True)
    for category in categories:
        matches = [item for item in index.values() if item["category"] == category]
        if not matches:
            raise KeyError(f"unknown animation terminology category: {category}")
        for item in matches:
            add(item, explicit=False)
            if len(selected) >= limit:
                return selected[:limit]
    return selected[:limit]


def expansion_contract(term: dict, *, time_window: str, observable_fact: str,
                       camera_or_layout: str, sound_or_qa: str) -> dict:
    """Return a host-facing expansion record; it is advisory and has no write path."""
    return {
        "term_id": term["id"],
        "term": term["term"],
        "category": term["category"],
        "time_window": time_window,
        "observable_fact": observable_fact,
        "camera_or_layout": camera_or_layout,
        "sound_or_qa": sound_or_qa,
        "required_evidence": term["evidence"],
        "expansion_instruction": term["expansion"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--list", action="store_true", dest="list_all")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 12:
        parser.error("--limit must be between 1 and 12")
    data = load_catalog()
    if args.list_all:
        print(json.dumps(index_catalog(data), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(select_terms(requested=args.term, categories=args.category,
                                      limit=args.limit, catalog=data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
