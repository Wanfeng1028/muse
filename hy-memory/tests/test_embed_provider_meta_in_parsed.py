# -*- coding: utf-8 -*-
"""Embed pipeline log：provider_meta（非 vector payload）应写入 parsed。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from hy_memory.pipelines._retrieval.trace import ReadTraceLogger


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestEmbedProviderMetaInParsed:
    def test_log_embed_query_includes_provider_meta(self):
        async def _test():
            captured: List[Dict[str, Any]] = []

            class _Cache:
                async def store_pipeline_log(self, **kwargs):
                    captured.append(kwargs)

            tracer = ReadTraceLogger(
                cache=_Cache(),
                request_id="rq1",
                user_id="u1",
                agent_id="a1",
            )
            meta = {
                "http_status": 200,
                "model": "fake",
                "usage": {"prompt_tokens": 2},
                "response_headers": {"x-request-id": "abc"},
                "cache_hit": False,
            }
            await tracer.log_embed_query(
                query="hello",
                dims=8,
                cache_hit=False,
                elapsed_ms=12.5,
                provider_meta=meta,
            )
            assert len(captured) == 1
            parsed = captured[0]["parsed"]
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            assert parsed["provider_meta"]["model"] == "fake"
            assert "embedding" not in parsed["provider_meta"]
            assert parsed["provider_meta"]["response_headers"]["x-request-id"] == "abc"

        run(_test())

    def test_log_coding_embed_includes_provider_meta(self):
        async def _test():
            captured: List[Dict[str, Any]] = []

            class _Cache:
                async def store_pipeline_log(self, **kwargs):
                    captured.append(kwargs)

            tracer = ReadTraceLogger(
                cache=_Cache(),
                request_id="rq2",
                user_id="u1",
                agent_id="a1",
            )
            await tracer.log_coding_embed(
                query="q",
                dims=4,
                elapsed_ms=3.0,
                provider_meta={"http_status": 200, "model": "m"},
            )
            parsed = captured[0]["parsed"]
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            assert parsed["provider_meta"]["model"] == "m"

        run(_test())

    def test_log_keyword_embed_includes_provider_metas(self):
        async def _test():
            captured: List[Dict[str, Any]] = []

            class _Cache:
                async def store_pipeline_log(self, **kwargs):
                    captured.append(kwargs)

            tracer = ReadTraceLogger(
                cache=_Cache(),
                request_id="rq3",
                user_id="u1",
                agent_id="a1",
            )
            await tracer.log_keyword_embed(
                keywords=["a", "b"],
                vec_count=2,
                elapsed_ms=5.0,
                provider_metas=[
                    {"cache_hit": False, "model": "m"},
                    {"cache_hit": True},
                ],
            )
            parsed = captured[0]["parsed"]
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            assert len(parsed["provider_metas"]) == 2
            assert parsed["provider_metas"][0]["model"] == "m"

        run(_test())
