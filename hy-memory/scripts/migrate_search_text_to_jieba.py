#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: 把 Qdrant collection 的 payload.search_text 从原始中文（依赖
MULTILINGUAL tokenizer 服务端切词）迁移到 jieba 预切的格式（配 WHITESPACE
tokenizer 服务端零切词）。

背景：
  之前 reconcile/reader_hybrid 的 in-process BM25 query 端用 jieba，candidate
  端用整段中文（_TOKEN_RE 匹配 [一-鿿]+），中文 BM25 全零；hybrid 路径
  query 端 jieba 预切后又被 Qdrant 服务端 MULTILINGUAL 重切，存在切词边界
  分歧。新方案统一两侧用 jieba：
    1. _node_to_payload 写入时把 search_text 过 lemmatize_for_bm25
    2. Qdrant text index tokenizer 改 WHITESPACE
    3. 老数据需要 re-write payload.search_text，本脚本就是干这个的

流程：
  对每个 collection：
    1) 如果 search_text 已有 text index，且 tokenizer != whitespace，先 drop
       （否则 set_payload 期间每条更新都会重建老索引，浪费）
    2) scroll 所有点（with_payload=True, with_vectors=False，不传 vector 节省带宽）
    3) 对每条点：从 payload 拿 content + tags，用 lemmatize_for_bm25 重算 search_text，
       通过 set_payload 只更新这一个字段，其它 payload 字段不动
    4) 全部更新完后 create_payload_index(WHITESPACE)，Qdrant 自动从新 payload 建倒排

幂等：
  - 已经是 whitespace tokenizer 的 collection 会跳过（除非 --force-reindex）
  - 单个 point 的 search_text 是否已经 jieba 切过，无法直接判断（可能恰好原文就有
    空格），脚本一律重算覆盖，结果幂等

用法：
    # 干跑（只统计要改多少条，不真正写）
    python scripts/migrate_search_text_to_jieba.py --dry-run

    # 实跑全部 collection
    python scripts/migrate_search_text_to_jieba.py

    # 只迁移指定 collection
    python scripts/migrate_search_text_to_jieba.py --collection hy_memory_test

    # 调 batch
    python scripts/migrate_search_text_to_jieba.py --batch-size 200

    # Qdrant 连接（不传则读 env: MEMORY_VECTOR_HOST/PORT/PATH）
    python scripts/migrate_search_text_to_jieba.py --qdrant-host localhost --qdrant-port 6333

注意：
  - 只对 Qdrant 后端生效。Chroma/FAISS 后端的 search_text 是 dead field，
    不需要迁移。
  - 跑之前先把 SDK 升级到带新 _node_to_payload 的版本（whitespace tokenizer），
    否则迁移期间新写入的数据还会用老逻辑。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import List, Optional

# 让脚本独立可跑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hy_memory.pipelines._retrieval.lemmatize import lemmatize_for_bm25  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate")


def _build_qdrant_client(args):
    from qdrant_client import QdrantClient

    if args.qdrant_path:
        logger.info(f"using local Qdrant at path={args.qdrant_path}")
        return QdrantClient(path=args.qdrant_path)

    host = args.qdrant_host or os.getenv("MEMORY_VECTOR_HOST") or "localhost"
    port = int(args.qdrant_port or os.getenv("MEMORY_VECTOR_PORT") or 6333)
    api_key = args.qdrant_api_key or os.getenv("MEMORY_VECTOR_API_KEY")
    https = bool(args.https or os.getenv("MEMORY_VECTOR_HTTPS"))

    logger.info(f"using remote Qdrant {host}:{port} https={https}")
    kwargs = {"host": host, "port": port, "https": https}
    if api_key:
        kwargs["api_key"] = api_key
    return QdrantClient(**kwargs)


def _list_collections(client) -> List[str]:
    cols = client.get_collections().collections
    return [c.name for c in cols]


def _detect_search_text_tokenizer(client, collection: str) -> Optional[str]:
    """返回当前 search_text 字段的 tokenizer（小写字符串），没有索引返回 None"""
    try:
        info = client.get_collection(collection)
    except Exception as e:
        logger.warning(f"[{collection}] get_collection failed: {e}")
        return None

    payload_schema = getattr(info, "payload_schema", None) or {}
    if not isinstance(payload_schema, dict):
        return None
    schema_entry = payload_schema.get("search_text")
    if schema_entry is None:
        return None
    params = getattr(schema_entry, "params", None)
    tok = getattr(params, "tokenizer", None) if params else None
    if tok is None:
        return None
    return str(getattr(tok, "value", tok)).lower()


def _drop_search_text_index(client, collection: str) -> bool:
    try:
        client.delete_payload_index(
            collection_name=collection,
            field_name="search_text",
        )
        logger.info(f"[{collection}] dropped existing search_text index")
        return True
    except Exception as e:
        logger.warning(f"[{collection}] drop_payload_index failed (maybe none): {e}")
        return False


def _create_whitespace_index(client, collection: str) -> None:
    from qdrant_client.models import TextIndexParams, TokenizerType

    client.create_payload_index(
        collection_name=collection,
        field_name="search_text",
        field_schema=TextIndexParams(
            type="text",
            tokenizer=TokenizerType.WHITESPACE,
            min_token_len=2,
            max_token_len=20,
        ),
    )
    logger.info(f"[{collection}] created search_text whitespace index")


def _compute_new_search_text(payload: dict) -> str:
    """跟 _node_to_payload 中的逻辑保持一致"""
    content = payload.get("content") or ""
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        # payload 里 tags 也可能存成字符串
        tags = [t for t in tags.split(",") if t]
    tags_text = " ".join(tags) if tags else ""
    raw = f"{content} {tags_text}".strip() if tags_text else content
    return lemmatize_for_bm25(raw) if raw else ""


def _migrate_collection(
    client,
    collection: str,
    *,
    dry_run: bool,
    batch_size: int,
    force_reindex: bool,
) -> dict:
    stats = {
        "collection": collection,
        "scanned": 0,
        "updated": 0,
        "skipped_unchanged": 0,
        "errors": 0,
        "tokenizer_before": None,
        "tokenizer_after": None,
        "elapsed_s": 0.0,
    }

    t0 = time.time()
    tok_before = _detect_search_text_tokenizer(client, collection)
    stats["tokenizer_before"] = tok_before
    logger.info(f"[{collection}] current tokenizer={tok_before!r}")

    if (
        tok_before is not None
        and tok_before.endswith("whitespace")
        and not force_reindex
    ):
        logger.info(f"[{collection}] already on whitespace tokenizer, skipping (use --force-reindex to override)")
        stats["tokenizer_after"] = tok_before
        stats["elapsed_s"] = round(time.time() - t0, 2)
        return stats

    # Step 1: drop old index (only if not dry-run)
    if not dry_run and tok_before is not None:
        _drop_search_text_index(client, collection)

    # Step 2: scroll + set_payload
    offset = None
    while True:
        scroll_result = client.scroll(
            collection_name=collection,
            scroll_filter=None,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if isinstance(scroll_result, tuple):
            points, next_offset = scroll_result
        else:
            points = scroll_result.points
            next_offset = scroll_result.next_page_offset

        if not points:
            break

        for p in points:
            stats["scanned"] += 1
            try:
                payload = p.payload or {}
                old = payload.get("search_text") or ""
                new = _compute_new_search_text(payload)
                if new == old:
                    stats["skipped_unchanged"] += 1
                    continue
                if dry_run:
                    stats["updated"] += 1
                    if stats["updated"] <= 3:
                        # 给前几条样例日志
                        logger.info(
                            f"[{collection}] sample update: id={p.id} "
                            f"old={old[:80]!r}... new={new[:80]!r}..."
                        )
                else:
                    client.set_payload(
                        collection_name=collection,
                        payload={"search_text": new},
                        points=[p.id],
                        wait=False,
                    )
                    stats["updated"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"[{collection}] update failed for id={p.id}: {e}")

        if stats["scanned"] % 1000 == 0 or next_offset is None:
            logger.info(
                f"[{collection}] progress: scanned={stats['scanned']} "
                f"updated={stats['updated']} skipped={stats['skipped_unchanged']} "
                f"errors={stats['errors']}"
            )

        if next_offset is None:
            break
        offset = next_offset

    # Step 3: create new whitespace index
    if not dry_run:
        try:
            _create_whitespace_index(client, collection)
        except Exception as e:
            logger.error(f"[{collection}] create whitespace index failed: {e}")
            stats["errors"] += 1

        stats["tokenizer_after"] = _detect_search_text_tokenizer(client, collection)

    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", help="只迁移指定 collection；不传则全量")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写")
    ap.add_argument("--batch-size", type=int, default=256, help="scroll 单批大小")
    ap.add_argument("--force-reindex", action="store_true",
                    help="即使 tokenizer 已经是 whitespace 也强制 re-write search_text + 重建索引")
    ap.add_argument("--qdrant-host")
    ap.add_argument("--qdrant-port", type=int)
    ap.add_argument("--qdrant-path", help="本地 PersistentClient 路径")
    ap.add_argument("--qdrant-api-key")
    ap.add_argument("--https", action="store_true")
    args = ap.parse_args()

    client = _build_qdrant_client(args)

    if args.collection:
        targets = [args.collection]
    else:
        targets = _list_collections(client)
        logger.info(f"discovered {len(targets)} collections: {targets}")

    all_stats = []
    for col in targets:
        logger.info(f"=== migrating collection: {col} ===")
        try:
            s = _migrate_collection(
                client,
                col,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                force_reindex=args.force_reindex,
            )
        except Exception as e:
            logger.exception(f"[{col}] failed: {e}")
            s = {"collection": col, "error": str(e)}
        all_stats.append(s)

    # 汇总
    print()
    print("=" * 60)
    print("Migration summary")
    print("=" * 60)
    total_scanned = sum(s.get("scanned", 0) for s in all_stats)
    total_updated = sum(s.get("updated", 0) for s in all_stats)
    total_errors = sum(s.get("errors", 0) for s in all_stats)
    for s in all_stats:
        print(f"  - {s.get('collection')}: "
              f"scanned={s.get('scanned', 0)} "
              f"updated={s.get('updated', 0)} "
              f"skipped={s.get('skipped_unchanged', 0)} "
              f"errors={s.get('errors', 0)} "
              f"tok={s.get('tokenizer_before')!r}→{s.get('tokenizer_after')!r} "
              f"({s.get('elapsed_s', 0)}s)")
    print(f"TOTAL: scanned={total_scanned} updated={total_updated} errors={total_errors}")
    print(f"DRY-RUN: {args.dry_run}")

    if total_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
