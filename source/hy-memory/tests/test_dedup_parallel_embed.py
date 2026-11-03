# -*- coding: utf-8 -*-
"""extractor DEDUP 路径：多条 memory embed 必须并行，并记录 embed 耗时 / meta。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from hy_memory.pipelines.base import WriteRequest
from hy_memory.pipelines.writer import MemoryWriter


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeCache:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []

    async def store_pipeline_log(self, **kwargs):
        self.logs.append(kwargs)


class TestDedupExtractedParallelEmbed:
    def test_dedup_extracted_uses_write_batch_queue(self):
        """N 条文本并发进入 write batch queue，并把向量交给后续阶段。"""

        async def _test():
            delay = 0.08
            in_flight = 0
            max_in_flight = 0
            call_order: List[str] = []

            class _FakeEmbed:
                async def embed_queued_with_meta(self, text: str):
                    nonlocal in_flight, max_in_flight
                    call_order.append(text)
                    in_flight += 1
                    max_in_flight = max(max_in_flight, in_flight)
                    await asyncio.sleep(delay)
                    in_flight -= 1
                    idx = int(text.split("-")[1])
                    vec = [0.0] * 8
                    vec[idx % 8] = 1.0
                    return vec, {
                        "http_status": 200,
                        "model": "fake-embed",
                        "usage": {"prompt_tokens": 3, "total_tokens": 3},
                        "response_headers": {"x-request-id": f"req-{idx}"},
                        "cache_hit": False,
                    }

            cache = _FakeCache()
            writer = MemoryWriter.__new__(MemoryWriter)
            writer._embed_service = _FakeEmbed()  # type: ignore[assignment]
            writer._cache = cache

            texts = [f"memory-{i}-content-about-topic-{i}" for i in range(6)]
            metas: List[Dict[str, Any]] = [
                {"content": t, "layer": "L2_FACT", "tags": []} for t in texts
            ]
            req = WriteRequest(
                content="irrelevant",
                user_id="u1",
                agent_id="a1",
            )

            t0 = asyncio.get_event_loop().time()
            out_texts, out_metas, out_embeddings = await writer._dedup_extracted(
                texts, metas, req, req_id="rq-parallel",
            )
            wall = asyncio.get_event_loop().time() - t0

            assert out_texts == texts
            assert len(out_metas) == 6
            assert set(out_embeddings) == set(texts)
            assert set(call_order) == set(texts)
            assert max_in_flight >= 2
            assert wall < 0.30, f"expected parallel wall <0.30s, got {wall:.3f}s"

            assert len(cache.logs) == 1
            parsed = json.loads(cache.logs[0]["parsed"])
            assert parsed["trigger"] == "extractor"
            assert parsed["embedding_source"] == "embed_service"
            assert parsed["embed_count"] == 6
            assert parsed["embed_ok_count"] == 6
            assert isinstance(parsed["embed_elapsed_ms"], (int, float))
            assert parsed["embed_elapsed_ms"] < 300
            assert len(parsed["embed_metas"]) == 6
            for m in parsed["embed_metas"]:
                assert "embedding" not in m
                assert m.get("model") == "fake-embed"
                assert "elapsed_ms" in m
                assert "response_headers" in m

        run(_test())
