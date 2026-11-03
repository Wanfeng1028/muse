#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查看 smoke 跑出来的 coding_memory.db 的全部内容（不截断），经验层 + 事实层。

用法:
    python scripts/dump_coding_db.py /path/to/coding_memory.db
    python scripts/dump_coding_db.py /path/to/coding_memory.db --json
    python scripts/dump_coding_db.py /path/to/coding_memory.db --id <experience_id>
    python scripts/dump_coding_db.py /path/to/coding_memory.db --facts
"""
import argparse
import json
import sqlite3
import sys


def _decode(row, json_fields):
    d = dict(row)
    for fld in json_fields:
        if d.get(fld):
            try:
                d[fld] = json.loads(d[fld])
            except Exception:
                pass
    return d


def fetch(db_path: str, experience_id: str | None = None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if experience_id:
            cur = conn.execute(
                "SELECT * FROM coding_memory_meta WHERE experience_id=?",
                (experience_id,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM coding_memory_meta ORDER BY created_at ASC"
            )
        return [_decode(r, ("search_keys", "files", "source_fact_ids")) for r in cur]
    finally:
        conn.close()


def fetch_facts(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT * FROM working_fact ORDER BY created_at ASC")
        return [_decode(r, ("files", "derived_experience_ids")) for r in cur]
    except sqlite3.OperationalError:
        # 老库还没建事实表
        return []
    finally:
        conn.close()


def render_text(rows):
    for k, r in enumerate(rows, 1):
        print("=" * 80)
        print(f"#{k}  experience_id={r['experience_id']}")
        print(f"    user_id  : {r['user_id']}")
        print(f"    agent_id : {r['agent_id']}")
        print(f"    workspace: {r['workspace_id']}")
        print(f"    branch   : {r['branch']}")
        print(f"    confidence: {r['confidence']}")
        print(f"    created  : {r['created_at']}")
        print(f"    updated  : {r['updated_at']}")
        print(f"\n    TASK:\n      {r['task']}")
        print(f"\n    SEARCH_KEYS:")
        for sk in r["search_keys"] or []:
            print(f"      - {sk}")
        print(f"\n    SOLUTION:")
        for line in (r["solution"] or "").splitlines():
            print(f"      {line}")
        if r.get("boundary_envs"):
            print(f"\n    BOUNDARY_ENVS:")
            for line in r["boundary_envs"].splitlines():
                print(f"      {line}")
        if r.get("files"):
            print(f"\n    FILES:")
            for f in r["files"]:
                print(f"      - {f}")
        if r.get("source_fact_ids"):
            print(f"\n    SOURCE_FACT_IDS:")
            for fid in r["source_fact_ids"]:
                print(f"      - {fid}")
        print()
    print(f"\n[total] {len(rows)} experiences")


def render_facts(rows):
    for k, r in enumerate(rows, 1):
        print("-" * 80)
        status = r["status"]
        if r.get("fact_link"):
            status += f" → {r['fact_link']}"
        print(f"#{k}  fact_id={r['fact_id']}  [{status}]")
        print(f"    user_id  : {r['user_id']}")
        print(f"    workspace: {r['workspace_id']}")
        print(f"    created  : {r['created_at']}")
        print(f"\n    STATEMENT:\n      {r['statement']}")
        if r.get("files"):
            print(f"\n    FILES:")
            for f in r["files"]:
                print(f"      - {f}")
        if r.get("derived_experience_ids"):
            print(f"\n    DERIVED_EXPERIENCE_IDS:")
            for eid in r["derived_experience_ids"]:
                print(f"      - {eid}")
        print()
    active = sum(1 for r in rows if r["status"] == "active")
    print(f"\n[total] {len(rows)} facts ({active} active)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", help="path to coding_memory.db")
    ap.add_argument("--id", help="只看某条经验（experience_id）")
    ap.add_argument("--facts", action="store_true", help="只看事实层")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非可读文本")
    args = ap.parse_args()

    facts = fetch_facts(args.db)
    if args.facts:
        if args.json:
            print(json.dumps(facts, ensure_ascii=False, indent=2, default=str))
        else:
            render_facts(facts)
        return

    rows = fetch(args.db, args.id)
    if args.json:
        print(json.dumps(
            {"experiences": rows, "facts": facts},
            ensure_ascii=False, indent=2, default=str,
        ))
    else:
        render_text(rows)
        if facts:
            print()
            render_facts(facts)


if __name__ == "__main__":
    main()
