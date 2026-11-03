#!/usr/bin/env python3
"""清理图里 `RELATED_TO` 的重复边（同一对节点 + 同一 relation_type 保留权重最大的一条）。

## 为什么会有重复

旧版本的 `add_edge` 使用 `CREATE` 而不是 `MERGE`，同一对节点之间可能会
**反复**建同类型边：

- `UPDATE` 是原地更新（`node_id` 不变），一条记忆被合并多次就会多次参与图投影。
  两条老节点若再次同批出现，`co_occurs` 就会重复建。
- System 2（ultra）的 agent 循环可能对同一对节点反复调用 `add_edge`。

大型长期运行数据库中可能累积大量平行边，尤其是 System 2 写入的无类型 `related`。

## 影响

重复边**不会放大打分** —— 读侧 `build_adjacency` 会把同一对节点之间的平行边折叠成
最强的那条。真实代价是吃掉 `get_related_edges` 的 `max_edges` 预算：Cypher 的 `LIMIT`
先截断、去重在 Python 侧做，于是重复边挤掉了本该返回的真实边。

当前 `add_edge` 使用 `MERGE`（`ON MATCH` 取较大权重），新数据不会再重复。
这个脚本用来清历史数据。

## 用法

    # 先看有多少重复（不改数据）
    python scripts/dedupe_graph_edges.py --dry-run

    # 实际清理，每批 5000 对
    python scripts/dedupe_graph_edges.py --batch 5000

    # 只清某个 relation_type
    python scripts/dedupe_graph_edges.py --relation-type related

连接参数从 env 读：`NEO4J_URL` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE`。
仅支持 Neo4j —— Kuzu 是嵌入式单机库，重建成本远低于原地去重。
"""

import argparse
import asyncio
import os
import sys


def _args():
    p = argparse.ArgumentParser(description="清理 RELATED_TO 重复边")
    p.add_argument("--dry-run", action="store_true", help="只统计，不修改")
    p.add_argument("--batch", type=int, default=5000, help="每批处理多少对（默认 5000）")
    p.add_argument("--relation-type", default=None, help="只处理指定 relation_type")
    p.add_argument("--max-batches", type=int, default=1000, help="安全上限")
    return p.parse_args()


async def main() -> int:
    a = _args()
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        print("需要 neo4j driver: pip install neo4j", file=sys.stderr)
        return 2

    url = os.getenv("NEO4J_URL") or "bolt://localhost:7687"
    user = os.getenv("NEO4J_USERNAME") or "neo4j"
    pwd = os.getenv("NEO4J_PASSWORD") or ""
    db = os.getenv("NEO4J_DATABASE") or "neo4j"

    rt_filter = "AND r.relation_type = $rt" if a.relation_type else ""
    params = {"rt": a.relation_type} if a.relation_type else {}

    driver = AsyncGraphDatabase.driver(url, auth=(user, pwd))
    try:
        async with driver.session(database=db) as s:
            # ── 统计 ──
            res = await s.run(
                f"""
                MATCH (x:Memory)-[r:RELATED_TO]->(y:Memory)
                WHERE true {rt_filter}
                WITH x.node_id AS s1, y.node_id AS t1,
                     r.relation_type AS rt, count(*) AS dup
                WHERE dup > 1
                RETURN count(*) AS dup_pairs, sum(dup - 1) AS removable, max(dup) AS worst
                """,
                params,
            )
            row = await res.single()
            dup_pairs = int((row or {}).get("dup_pairs") or 0)
            removable = int((row or {}).get("removable") or 0)
            worst = int((row or {}).get("worst") or 0)
            print(f"重复对: {dup_pairs}   可删边: {removable}   最严重一对: {worst} 份")

            if a.dry_run or not dup_pairs:
                if a.dry_run:
                    print("--dry-run：未修改任何数据")
                return 0

            # ── 分批删除：每对只留权重最大的一条 ──
            total = 0
            for i in range(a.max_batches):
                res = await s.run(
                    f"""
                    MATCH (x:Memory)-[r:RELATED_TO]->(y:Memory)
                    WHERE true {rt_filter}
                    WITH x.node_id AS s1, y.node_id AS t1,
                         r.relation_type AS rt, collect(r) AS rels
                    WHERE size(rels) > 1
                    WITH rels LIMIT $batch
                    // 权重降序，保留第一条
                    WITH [e IN rels | e] AS es
                    UNWIND es AS e
                    WITH es, e ORDER BY coalesce(e.weight, 0) DESC
                    WITH es, collect(e) AS sorted
                    WITH sorted[1..] AS extras
                    UNWIND extras AS victim
                    DELETE victim
                    RETURN count(*) AS removed
                    """,
                    {**params, "batch": a.batch},
                )
                row = await res.single()
                removed = int((row or {}).get("removed") or 0)
                total += removed
                print(f"  批 {i + 1}: 删除 {removed} 条（累计 {total}）")
                if removed == 0:
                    break

            print(f"完成：共删除 {total} 条重复边")
    finally:
        await driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
