#!/usr/bin/env python3
"""Read a few relevant advisory records; never mutate production or certify art."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ("live_action", "cg_realistic", "anime_2d", "anime_3d", "ink")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_libraries(root=ROOT):
    root = Path(root)
    inquiries = read_json(root / "data/director-inquiries.json")
    visuals = read_json(root / "data/visual-style-materials.json")
    for data in (inquiries, visuals):
        require(data.get("schema_version") == "1.0" and data.get("advisory_only") is True,
                "Unsupported or non-advisory reference library")
    return inquiries, visuals


def render_inquiry_guide(module, data):
    lines = [f"# {module}｜按缺口读取的专业问题", "",
             "此文件由 data/director-inquiries.json 生成。只读被当前决策指南命中的题；不是整份必答表。",
             "有输入、有局部选择、有原字段落点即可结束；不输出内部思维链，不手填机器 PASS。",
             "原稿已确认且输入未变时复用决定；发生跨 owner 冲突时只交具体缺口。", ""]
    for q in data["questions"]:
        if q["owner"] != module:
            continue
        lines += [f"## {q['id']}", "", f"**{q['title']}**（决策位置 {q['case']}）", "",
                  f"触发：{q['trigger']}。先取：{'；'.join(q['inputs'])}。", ""]
        lines += [f"{i}. {text}" for i, text in enumerate(q["questions"], 1)]
        lines += ["", "按条件处理：", ""] + [f"- {text}" for text in q["branches"]]
        lines += ["", f"落点：{'、'.join(q['writes_to'])}。", f"完成即停：{q['stop_when']}",
                  f"不采用的原文硬规则：{q['excluded_rule']}",
                  f"来源：[用户提问原文](../sources/user-director-libraries/15-master-director-inquiries.md)，第{q['source_lines'][0]}–{q['source_lines'][1]}行；原文只作出处。", ""]
    return "\n".join(lines) + "\n"


def validate_libraries(root=ROOT, *, check_views=True):
    root = Path(root)
    inquiries, visuals = load_libraries(root)
    modules = {m["id"]: m for m in read_json(root / "data/module-registry.json")["modules"]}
    for data in (inquiries, visuals):
        source = root / data["source_file"]
        require(source.is_file(), f"Missing library source: {source}")
        require(hashlib.sha256(source.read_bytes()).hexdigest() == data["source_sha256"],
                f"Library source changed: {data['source_file']}")
        n = len(source.read_text(encoding="utf-8").splitlines())
        for record in data.get("questions", data.get("entries", [])):
            span = record.get("source_lines", [])
            require(len(span) == 2 and all(type(x) is int for x in span) and 1 <= span[0] <= span[1] <= n,
                    f"Invalid source range: {record.get('id')}")
    questions = inquiries["questions"]
    require([q.get("id") for q in questions] == [f"Q{i:02d}" for i in range(1, 37)],
            "Inquiry coverage must preserve Q01–Q36 exactly once")
    for q in questions:
        require(q.get("owner") in modules, f"Unknown question owner: {q['id']}")
        require(all(q.get(k) for k in ("title", "case", "trigger", "inputs", "questions", "branches", "stop_when", "excluded_rule")),
                f"Incomplete decision record: {q['id']}")
        require(1 <= len(q["questions"]) <= 3, f"Question card is not bounded: {q['id']}")
        require(q.get("writes_to") and set(q["writes_to"]) <= set(modules[q["owner"]]["owns"]),
                f"Question exceeds original field ownership: {q['id']}")
        guide = (root / f"references/decisions/{q['owner']}.md").read_text(encoding="utf-8")
        require(f"## {q['case']}｜" in guide and f"../inquiries/{q['owner']}.md#{q['id'].lower()}" in guide,
                f"Question not connected to its actual decision position: {q['id']}")
    terms = {t["id"] for c in read_json(root / "data/animation-art-terminology.json")["categories"] for t in c["terms"]}
    seen = set()
    for v in visuals["entries"]:
        require(v.get("id") and v["id"] not in seen, "Missing/duplicate visual ID")
        seen.add(v["id"])
        require(all(v.get(k) for k in ("name", "layer", "media", "use_when", "ask", "description", "avoid")),
                f"Incomplete visual record: {v['id']}")
        require(set(v["media"]) <= set(MEDIA), f"Unknown medium: {v['id']}")
        require(set(v.get("terms", [])) <= terms, f"Unknown existing animation term: {v['id']}")
        if v["layer"] == "surface":
            require(v.get("surface") and v.get("ink") and v.get("cel"), f"Missing surface adapters: {v['id']}")
    require(len(seen) == 31, "Expected 31 curated visual records")
    for owner, paths in visuals["routes"].items():
        require(owner in modules and set(paths) <= set(modules[owner]["owns"]), f"Visual route exceeds owner: {owner}")
    if check_views:
        for module in modules:
            path = root / f"references/inquiries/{module}.md"
            require(path.is_file() and path.read_text(encoding="utf-8") == render_inquiry_guide(module, inquiries),
                    f"Stale or missing inquiry view: {module}")
    return {"status": "PASS", "inquiries": len(questions), "visual_entries": len(seen),
            "surface_entries": sum(v["layer"] == "surface" for v in visuals["entries"]),
            "scope": "catalog structure, source hashes, ownership, routes and generated views only",
            "artistic_quality": "UNVERIFIED", "production_mutated": False}


def bounded_limit(limit):
    require(type(limit) is int and 1 <= limit <= 4, "limit must be between 1 and 4")


def select_questions(*, module=None, case=None, ids=(), limit=2, root=ROOT):
    bounded_limit(limit)
    data, _ = load_libraries(root)
    all_q = data["questions"]
    require(module is None or module in {q["owner"] for q in all_q}, f"Unknown module: {module}")
    require(not case or module, "A case requires --module")
    known = {q["id"] for q in all_q}
    require(set(ids) <= known, f"Unknown question IDs: {sorted(set(ids) - known)}")
    matches = [q for q in all_q if (not module or q["owner"] == module) and
               (not case or q["case"] == case) and (not ids or q["id"] in ids)]
    require(not ids or set(ids) <= {q["id"] for q in matches}, "Requested question conflicts with module/case")
    if not case and not ids:
        return {"status": "INDEX_ONLY", "next": "Choose the current case or exact question ID; do not answer the full list.",
                "index": [{k:q[k] for k in ("id", "owner", "case", "title", "trigger")} for q in matches]}
    return {"status": "CANDIDATES" if matches else "NO_MATCH", "advisory_only": True,
            "cards": matches[:limit], "remaining_ids": [q["id"] for q in matches[limit:]],
            "source_file": data["source_file"], "source_sha256": data["source_sha256"],
            "completion": "Resolve the current gap in existing fields; no private scratchpad or self-certified PASS."}


def select_visuals(*, ids=(), medium=None, surface=None, layer=None, search=None, limit=2, root=ROOT):
    bounded_limit(limit)
    _, data = load_libraries(root)
    entries = data["entries"]
    require(medium is None or medium in MEDIA, f"Unknown medium: {medium}")
    require(surface is None or surface in {v.get("surface") for v in entries}, f"Unknown surface: {surface}")
    require(layer is None or layer in {v["layer"] for v in entries}, f"Unknown layer: {layer}")
    known = {v["id"] for v in entries}
    require(set(ids) <= known, f"Unknown visual IDs: {sorted(set(ids) - known)}")
    matches = [v for v in entries if (not ids or v["id"] in ids) and
               (not medium or medium in v["media"]) and (not surface or v.get("surface") == surface) and
               (not layer or v["layer"] == layer) and
               (not search or search.casefold() in " ".join([v["name"], *v.get("aliases", [])]).casefold())]
    require(not ids or set(ids) <= {v["id"] for v in matches}, "Requested visual is incompatible with the selected medium or filters")
    # A list of candidates is not a combined recipe; conflicting ideas remain visible as alternatives.
    if not medium or not any((ids, surface, layer, search)):
        return {"status": "INDEX_ONLY", "next": "Select medium plus a surface, layer, search term or exact ID.",
                "index": [{k:v[k] for k in ("id", "name", "layer", "media")} for v in matches]}
    cards = []
    for v in matches[:limit]:
        appearance = v["ink"] if v["layer"] == "surface" and medium == "ink" else (
            v["cel"] if v["layer"] == "surface" and medium in ("anime_2d", "anime_3d") else v["description"])
        cards.append({**v, "selected_medium": medium, "appearance": appearance,
                      "adoption": "Name the actual object, existing source, current state and visible scale; reconcile approved style before writing existing fields."})
    return {"status": "CANDIDATES" if matches else "NO_MATCH", "advisory_only": True,
            "cards": cards, "remaining_ids": [v["id"] for v in matches[limit:]],
            "candidate_relationship": "Alternatives, not an automatically stacked preset; reconcile any shared exclusive_group before adoption.",
            "source_file": data["source_file"], "source_sha256": data["source_sha256"],
            "reference_media": [], "production_mutated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("questions")
    q.add_argument("--module")
    q.add_argument("--case")
    q.add_argument("--question", action="append", default=[])
    q.add_argument("--limit", type=int, default=2)
    v = sub.add_parser("visuals")
    v.add_argument("--visual", action="append", default=[])
    v.add_argument("--medium", choices=MEDIA)
    v.add_argument("--surface")
    v.add_argument("--layer")
    v.add_argument("--search")
    v.add_argument("--limit", type=int, default=2)
    sub.add_parser("validate")
    sub.add_parser("render-guides")
    args = parser.parse_args()
    try:
        if args.command == "questions":
            result = select_questions(module=args.module, case=args.case, ids=args.question, limit=args.limit, root=args.root)
        elif args.command == "visuals":
            result = select_visuals(ids=args.visual, medium=args.medium, surface=args.surface, layer=args.layer,
                                    search=args.search, limit=args.limit, root=args.root)
        elif args.command == "validate":
            result = validate_libraries(args.root)
        else:
            data, _ = load_libraries(args.root)
            folder = args.root / "references/inquiries"
            folder.mkdir(parents=True, exist_ok=True)
            for module in {q["owner"] for q in data["questions"]}:
                (folder / f"{module}.md").write_text(render_inquiry_guide(module, data), encoding="utf-8")
            result = {"status": "GENERATED", "directory": str(folder), "production_mutated": False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
