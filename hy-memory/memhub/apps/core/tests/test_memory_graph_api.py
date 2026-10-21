import asyncio
import time

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory import api as api_module
from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.candidates import RootCandidateKind
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)


def _confirm(app, client, content: str, evidence_id: str, index: int):
    async def run() -> None:
        created = await client.post(
            "/api/v1/memories",
            json={
                "request_id": f"create-{index}",
                "draft": {
                    "user_id": "local",
                    "kind": "chat",
                    "content": content,
                    "scopes": ["all-apps"],
                    "evidence_ids": [evidence_id],
                },
            },
        )
        assert created.status_code == 200

    return run()


def test_graph_labels_where_every_edge_came_from(tmp_path) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for index, (message_id, content) in enumerate(
                (
                    ("message-1", "用户要求看板只用真实数据。"),
                    ("message-2", "用户希望问答给出引用。"),
                )
            ):
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id="conversation-a",
                        message_id=message_id,
                        correlation_id=message_id,
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=content,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(app, client, content, evidence.evidence_id, index)

            other = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation-b",
                    message_id="message-3",
                    correlation_id="message-3",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="用户在另一次对话里提到偏好。",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            await _confirm(app, client, "用户在另一次对话里提到偏好。", other.evidence_id, 2)

            graph = await client.get("/api/v1/memories/graph")

            assert graph.status_code == 200
            body = graph.json()
            assert body["projected_memories"] == 3
            origins = {edge["origin"] for edge in body["edges"]}
            assert origins == {"provenance", "same_conversation"}
            # Only the two memories from one conversation are linked to each
            # other; the memory from another conversation is not.
            same = [edge for edge in body["edges"] if edge["origin"] == "same_conversation"]
            assert len(same) == 1
            # HY was never reachable in this test, and the response says so
            # instead of letting the map imply the relations are all there is.
            assert body["hy_graph_available"] is False

    asyncio.run(scenario())


def test_a_created_memory_is_on_the_map_with_its_source_links(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data", source_home=tmp_path, api_token=SecretStr("local-token")
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer local-token"},
            ) as client,
        ):
            evidence = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="candidate",
                    message_id="c1",
                    role="assistant",
                    written_by=WrittenBy.AGENT,
                    verbatim="Agent建议蓝色按钮。",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            created = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "candidate-create",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "Agent建议蓝色按钮。",
                        "origin": "agent",
                        "scopes": ["all-apps"],
                        "evidence_ids": [evidence.evidence_id],
                    },
                },
            )
            assert created.status_code == 200
            identifier = created.json()["memory_id"]
            graph = (await client.get("/api/v1/memories/graph")).json()
            assert graph["projected_memories"] == 1
            assert any(
                node["memory_id"] == identifier and node["status"] == "confirmed"
                for node in graph["nodes"]
            )
            assert any(edge["origin"] == "provenance" for edge in graph["edges"])

    asyncio.run(scenario())


def test_drawing_the_map_does_not_stop_the_app_answering(tmp_path) -> None:
    """The map is what the memory view opens with, and it used to block the
    process while it was read.

    Every store call in the read is synchronous and the evidence is fetched an
    id at a time, so a full map is hundreds of blocking calls. Made on the
    loop, they were made instead of answering anyone: the watchdog caught this
    endpoint holding the loop for 2.1s, and /health — which does no work at
    all — was measured at 17.9s on the real library while a map was drawn.
    """

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for index in range(4):
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id="conversation-a",
                        message_id=f"message-{index}",
                        correlation_id=f"message-{index}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"用户说了第 {index} 件事。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                said = f"用户说了第 {index} 件事。"
                await _confirm(app, client, said, evidence.evidence_id, index)

            # Each evidence read takes a moment, the way a contended one does.
            inner = app.state.evidence_store
            delay = 0.1

            class _Sluggish:
                def __getattr__(self, name: str):
                    attribute = getattr(inner, name)
                    if not callable(attribute):
                        return attribute

                    def slowly(*args, **kwargs):
                        time.sleep(delay)
                        return attribute(*args, **kwargs)

                    return slowly

            app.state.evidence_store = _Sluggish()

            longest = 0.0
            answered = 0

            async def keep_asking() -> None:
                # The gap between turns, not the duration of one request: a
                # task cannot time a stall it was not running for, and timing
                # its own request measures nothing while the loop is blocked.
                nonlocal longest, answered
                last = time.perf_counter()
                while True:
                    reply = await client.get("/api/v1/health")
                    assert reply.status_code == 200
                    now = time.perf_counter()
                    longest = max(longest, now - last)
                    last = now
                    answered += 1
                    await asyncio.sleep(0.005)

            asking = asyncio.create_task(keep_asking())
            graph = await client.get("/api/v1/memories/graph")
            asking.cancel()

            assert graph.status_code == 200
            # The map really was read, so this cannot pass by drawing nothing.
            assert graph.json()["projected_memories"] == 4
            # Read on the loop, not one of these got an answer until the map
            # was finished, which is the whole defect.
            assert answered > 1, "画图期间没有任何请求被应答：循环被堵住了"
            # Several tenth-of-a-second reads happen while the map is drawn;
            # on the loop none of these could have been answered until it
            # finished.
            assert longest < delay * 3, f"画图期间循环被堵住 {longest:.3f}s"

    asyncio.run(scenario())


def _confirm_tagged(app, client, content: str, evidence_id: str, index: int, tags):
    async def run() -> None:
        created = await client.post(
            "/api/v1/memories",
            json={
                "request_id": f"create-tagged-{index}",
                "draft": {
                    "user_id": "local",
                    "kind": "chat",
                    "content": content,
                    "scopes": ["all-apps"],
                    "evidence_ids": [evidence_id],
                    "tags": list(tags),
                },
            },
        )
        assert created.status_code == 200, created.text

    return run()


def test_a_shared_tag_becomes_a_topic_on_the_map(tmp_path) -> None:
    """标签要在图上长成一个点，并把带它的记忆连起来。

    图上原先只有三种点：记忆、来源 App、以及 HY 自己 TOPIC 层的归纳。我们从 HY
    接回来的 tags 只在左栏当文字展示，没有进图 —— 于是一张记忆还很少的库打开来
    满屏都是来源 App，看起来像是按 App 聚类，而不是按事项聚类。

    只连「被两条以上记忆共用」的标签：只出现一次的标签连出去的是一根挂着单个
    记忆的线，那不是聚类，只是把同一条记忆画了两遍。
    """

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            plans = (
                ("m-1", "用户要求前端统一走 axios 封装。", ("axios", "frontend")),
                ("m-2", "用户要求测试先行。", ("axios", "testing")),
                ("m-3", "用户在做记忆产品。", ("memory-product",)),
            )
            for index, (message_id, content, tags) in enumerate(plans):
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id=f"conversation-{index}",
                        message_id=message_id,
                        correlation_id=message_id,
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=content,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm_tagged(app, client, content, evidence.evidence_id, index, tags)

            body = (await client.get("/api/v1/memories/graph")).json()

            topics = {
                node["label"]: node["node_id"]
                for node in body["nodes"]
                if node["node_type"] == "topic"
            }
            # axios 被两条记忆共用，所以它是一个主题。
            assert "axios" in topics
            # frontend / testing / memory-product 各只出现一次 —— 不成聚类。
            assert set(topics) == {"axios"}

            tagged = [edge for edge in body["edges"] if edge["origin"] == "shared_tag"]
            assert len(tagged) == 2
            assert {edge["source_node_id"] for edge in tagged} == {topics["axios"]}

    asyncio.run(scenario())


def test_a_tag_used_once_does_not_become_a_topic(tmp_path) -> None:
    """正向对照：全库只有一条带标签的记忆时，图上不许出现主题点。

    没有这条，上一条可以被「每个标签都建一个点」骗过 —— 那样 axios 照样在，
    只是同时多出三个各挂一条记忆的孤点。
    """

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            evidence = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation-solo",
                    message_id="m-solo",
                    correlation_id="m-solo",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="用户要求前端统一走 axios 封装。",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            await _confirm_tagged(
                app, client, "用户要求前端统一走 axios 封装。", evidence.evidence_id, 9, ("axios",)
            )

            body = (await client.get("/api/v1/memories/graph")).json()

            assert [node for node in body["nodes"] if node["node_type"] == "topic"] == []
            assert [edge for edge in body["edges"] if edge["origin"] == "shared_tag"] == []

    asyncio.run(scenario())


def test_the_map_only_verifies_the_memories_it_draws(tmp_path) -> None:
    """A full library must not be verified row by row just to count it.

    The map reads 500 memories but draws at most `limit`. Verifying all 500
    meant one freshness check plus one citation check per memory, and on a
    1,226-memory library it passed the 5 s interrupt, so /memories/graph
    answered 503 every time while /memories, which verifies one page, stayed
    at 0.1 s.
    """
    calls: list[int] = []

    def counting(memories):
        calls.append(len(memories))
        return list(memories)

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for index in range(12):
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id=f"conversation-{index}",
                        message_id=f"m-{index}",
                        correlation_id=f"m-{index}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"第 {index} 条真实对话内容。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(
                    app, client, f"第 {index} 条真实对话内容。", evidence.evidence_id, index
                )

            app.state.source_read_access.memories = counting
            body = (await client.get("/api/v1/memories/graph?limit=5")).json()

            assert body["total_memories"] == 12
            assert body["projected_memories"] == 5
            # The count is not row-verified, and neither is the tail: only the
            # five memories the map draws are checked.
            assert calls == [5]

    asyncio.run(scenario())


def test_the_map_resolves_the_source_catalog_once(tmp_path) -> None:
    """The catalog is resolved once per request, not once per drawn source.

    `_source_catalog` re-reads and re-resolves every registered source. The
    map called it inside the per-memory loop, once per distinct source: on a
    160-memory library that is over a thousand resolutions, and it is where
    the map's five seconds went.
    """
    from one_memory.imports.candidates import SourceCandidateStore

    calls: list[int] = []
    original = SourceCandidateStore.resolve_catalog

    def counting(self, catalog, *, user_id="local"):
        calls.append(1)
        return original(self, catalog, user_id=user_id)

    SourceCandidateStore.resolve_catalog = counting
    try:

        async def scenario() -> None:
            app = create_app(
                Settings(
                    data_dir=tmp_path / "data",
                    source_home=tmp_path,
                    api_token=SecretStr("local-token"),
                )
            )
            async with (
                app.router.lifespan_context(app),
                AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={
                        "Authorization": "Bearer local-token",
                        "Origin": "http://127.0.0.1:5173",
                    },
                ) as client,
            ):
                for index in range(6):
                    evidence = app.state.evidence_store.put(
                        EvidenceInput(
                            source_id="cursor",
                            conversation_id=f"conversation-{index}",
                            message_id=f"m-{index}",
                            correlation_id=f"m-{index}",
                            role="user",
                            written_by=WrittenBy.PERSON,
                            verbatim=f"第 {index} 条真实对话内容。",
                            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                        )
                    ).record
                    await _confirm(
                        app, client, f"第 {index} 条真实对话内容。", evidence.evidence_id, index
                    )

                calls.clear()
                body = (await client.get("/api/v1/memories/graph")).json()

                assert body["projected_memories"] == 6
                # Six memories share one source. One resolution, not six.
                assert len(calls) == 1

        asyncio.run(scenario())
    finally:
        SourceCandidateStore.resolve_catalog = original


def test_the_map_count_leaves_a_revoked_source_out(tmp_path) -> None:
    """The count is the cheap one, but not so cheap it counts revoked work.

    D22 settled that a total skips the per-row freshness check. It still has
    to leave out memories a revoked source supplied, or the number the map
    reports includes memories it refuses to draw.
    """

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for index, source_id in enumerate(("cursor", "claude-code")):
                folder = tmp_path / source_id
                folder.mkdir(exist_ok=True)
                app.state.source_grant_store.grant(
                    user_id="local",
                    source_id=source_id,
                    root=folder,
                    candidate_kind=RootCandidateKind.DEFAULT,
                )
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id=source_id,
                        conversation_id=f"conversation-{source_id}",
                        message_id=f"m-{source_id}",
                        correlation_id=f"m-{source_id}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"{source_id} 的真实对话内容。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(
                    app, client, f"{source_id} 的真实对话内容。", evidence.evidence_id, index
                )

            before = (await client.get("/api/v1/memories/graph")).json()
            assert before["total_memories"] == 2

            app.state.source_grant_store.revoke(user_id="local", source_id="claude-code")

            after = (await client.get("/api/v1/memories/graph")).json()
            assert after["total_memories"] == 1
            assert after["projected_memories"] == 1

    asyncio.run(scenario())


def test_the_map_reads_its_evidence_in_one_pass(tmp_path) -> None:
    """D89: one query for the map's evidence, not one per citation.

    Each drawn memory looked up every one of its citations separately: 1,274
    round trips for a 160-memory map, each taking a turn through the pool.
    That is what put the map over its five second budget on a library being
    written to at the same time — the acceptance run saw 4.2-14.8 s and a 503
    on three calls out of ten.
    """
    from one_memory.imports.storage import EvidenceStore

    calls: list[int] = []
    original = EvidenceStore.get

    def counting(self, evidence_id):
        calls.append(1)
        return original(self, evidence_id)

    EvidenceStore.get = counting
    try:

        async def scenario() -> None:
            app = create_app(
                Settings(
                    data_dir=tmp_path / "data",
                    source_home=tmp_path,
                    api_token=SecretStr("local-token"),
                )
            )
            async with (
                app.router.lifespan_context(app),
                AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={
                        "Authorization": "Bearer local-token",
                        "Origin": "http://127.0.0.1:5173",
                    },
                ) as client,
            ):
                for index in range(6):
                    evidence = app.state.evidence_store.put(
                        EvidenceInput(
                            source_id="cursor",
                            conversation_id=f"conversation-{index % 2}",
                            message_id=f"m-{index}",
                            correlation_id=f"m-{index}",
                            role="user",
                            written_by=WrittenBy.PERSON,
                            verbatim=f"第 {index} 条真实对话内容。",
                            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                        )
                    ).record
                    await _confirm(
                        app, client, f"第 {index} 条真实对话内容。", evidence.evidence_id, index
                    )

                calls.clear()
                body = (await client.get("/api/v1/memories/graph")).json()

                assert body["projected_memories"] == 6
                # Six memories with one citation each, read together.
                assert len(calls) <= 1

        asyncio.run(scenario())
    finally:
        EvidenceStore.get = original


def test_a_timed_out_map_falls_back_to_the_last_good_one(tmp_path) -> None:
    """D91: a slow map must not answer 503 while a good one is known.

    While a library is being written to, the map read can cross its five
    second interrupt. The memory view then has nothing to show, even though
    the very same map was drawn successfully a moment ago and the library has
    not changed since.
    """
    import sqlite3

    calls: list[int] = []
    real = api_module._governed_graph_part

    def counting(app, limit):
        calls.append(limit)
        if len(calls) > 1:
            raise sqlite3.OperationalError("interrupted")
        return real(app, limit)

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for index in range(3):
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id=f"conversation-{index}",
                        message_id=f"m-{index}",
                        correlation_id=f"m-{index}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"第 {index} 条真实对话内容。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(
                    app, client, f"第 {index} 条真实对话内容。", evidence.evidence_id, index
                )

            api_module._governed_graph_part = counting
            try:
                first = await client.get("/api/v1/memories/graph")
                assert first.status_code == 200
                assert first.json()["projected_memories"] == 3

                # The next read crosses the interrupt. Nothing has changed
                # since the one that succeeded, so the known map is the better
                # answer than a 503.
                second = await client.get("/api/v1/memories/graph")
            finally:
                api_module._governed_graph_part = real

            assert second.status_code == 200
            assert second.json()["projected_memories"] == 3

    asyncio.run(scenario())


def test_a_changed_library_is_drawn_again(tmp_path) -> None:
    """The cache is keyed on the library, so a new memory redraws the map."""

    calls: list[int] = []
    real = api_module._governed_graph_part

    def counting(app, limit):
        calls.append(limit)
        return real(app, limit)

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            evidence = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation-0",
                    message_id="m-0",
                    correlation_id="m-0",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="第 0 条真实对话内容。",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            await _confirm(app, client, "第 0 条真实对话内容。", evidence.evidence_id, 0)

            api_module._governed_graph_part = counting
            try:
                assert (await client.get("/api/v1/memories/graph")).status_code == 200
                # Same library: served from the last good map.
                assert (await client.get("/api/v1/memories/graph")).status_code == 200
                assert len(calls) == 1

                second = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id="cursor",
                        conversation_id="conversation-1",
                        message_id="m-1",
                        correlation_id="m-1",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim="第 1 条真实对话内容。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(app, client, "第 1 条真实对话内容。", second.evidence_id, 1)

                body = await client.get("/api/v1/memories/graph")
            finally:
                api_module._governed_graph_part = real

            assert body.status_code == 200
            assert body.json()["projected_memories"] == 2
            assert len(calls) == 2

    asyncio.run(scenario())


def test_withdrawing_a_second_source_redraws_the_map(tmp_path) -> None:
    """D95: the cache must notice a second revocation, not just the first.

    Keying on whether *any* source is revoked keeps serving the map drawn
    before the second withdrawal, so that source's memories stay on a map the
    reader is no longer allowed to see them on.
    """
    from one_memory.imports.candidates import RootCandidateKind

    calls: list[int] = []
    real = api_module._governed_graph_part

    def counting(app, limit):
        calls.append(limit)
        return real(app, limit)

    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            for source_id in ("cursor", "claude-code"):
                folder = tmp_path / source_id
                folder.mkdir(exist_ok=True)
                app.state.source_grant_store.grant(
                    user_id="local",
                    source_id=source_id,
                    root=folder,
                    candidate_kind=RootCandidateKind.DEFAULT,
                )
                evidence = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id=source_id,
                        conversation_id=f"conversation-{source_id}",
                        message_id=f"m-{source_id}",
                        correlation_id=f"m-{source_id}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"{source_id} 的真实对话内容。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                await _confirm(
                    app, client, f"{source_id} 的真实对话内容。", evidence.evidence_id, source_id
                )

            api_module._governed_graph_part = counting
            try:
                assert (await client.get("/api/v1/memories/graph")).status_code == 200
                app.state.source_grant_store.revoke(user_id="local", source_id="cursor")
                assert (await client.get("/api/v1/memories/graph")).status_code == 200
                assert len(calls) == 2

                # A second withdrawal with one already revoked. The library
                # itself has not changed, so only the grant fingerprint can
                # tell this apart from the previous call.
                app.state.source_grant_store.revoke(user_id="local", source_id="claude-code")
                body = await client.get("/api/v1/memories/graph")
            finally:
                api_module._governed_graph_part = real

            assert body.status_code == 200
            assert len(calls) == 3

    asyncio.run(scenario())
