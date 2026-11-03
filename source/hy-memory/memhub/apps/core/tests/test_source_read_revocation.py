import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.memory_governance import MemoryDraft, MemoryKind
from one_memory.memory_qa import _ModelAnswer
from one_memory.model_profiles import ModelCapabilities, ModelProfileInput, ProviderKind


def test_source_revocation_stops_every_outward_read_but_keeps_other_sources(tmp_path):
    async def scenario():
        home = tmp_path / "home"
        home.mkdir()
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={},
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            ids = []
            evidence = []
            for source, content in [("a", "项目周会 禁用信息"), ("b", "项目周会 保留信息")]:
                folder = home / source
                folder.mkdir()
                app.state.source_grant_store.grant(
                    user_id="local",
                    source_id=source,
                    root=folder,
                    candidate_kind=RootCandidateKind.DEFAULT,
                )
                item = app.state.evidence_store.put(
                    EvidenceInput(
                        source_id=source,
                        conversation_id=source,
                        message_id="m",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=content,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                evidence.append(item.evidence_id)
                memory = app.state.person_writes.create(
                    MemoryDraft(
                        user_id="local",
                        kind=MemoryKind.CHAT,
                        content=content,
                        scopes=("all-apps",),
                        evidence_ids=(item.evidence_id,),
                    ),
                    request_id=source,
                )
                ids.append(memory.memory_id)
            mixed = app.state.person_writes.create(
                MemoryDraft(
                    user_id="local",
                    kind=MemoryKind.CHAT,
                    content="项目周会 混合来源",
                    scopes=("all-apps",),
                    evidence_ids=tuple(evidence),
                ),
                request_id="mixed",
            )
            ids.append(mixed.memory_id)
            before = (await client.post("/api/v1/recall", json={"query": "项目周会"})).json()
            assert {hit["memory_id"] for hit in before["hits"]} == set(ids)
            app.state.source_grant_store.revoke(user_id="local", source_id="a")

            async def must_not_digest():
                raise AssertionError("Revoked source must not be sent to aggregate processing")

            app.state.memory_processing_supervisor.digest = must_not_digest
            assert (await client.post("/api/v1/memories/graph/digest")).status_code == 403
            recalled = (await client.post("/api/v1/recall", json={"query": "项目周会"})).json()
            assert [hit["memory_id"] for hit in recalled["hits"]] == [ids[1]]
            answer = (
                await client.post("/api/v1/memories/ask", json={"question": "项目周会"})
            ).json()
            assert "禁用信息" not in str(answer) and "保留信息" in str(answer)
            stream = await client.post("/api/v1/memories/ask/stream", json={"question": "项目周会"})
            assert "禁用信息" not in stream.text and "保留信息" in stream.text
            memories = (await client.get("/api/v1/memories")).json()
            assert [m["memory_id"] for m in memories] == [ids[1]]
            graph = (await client.get("/api/v1/memories/graph")).json()
            assert "禁用信息" not in str(graph)
            assert (await client.get("/api/v1/memories/" + ids[0])).status_code == 403
            found = (
                await client.get("/api/v1/conversations/search", params={"query": "项目周会"})
            ).json()
            assert [hit["evidence_id"] for hit in found["hits"]] == [evidence[1]]
            assert (await client.get("/api/v1/conversations/" + evidence[0])).status_code == 404
            assert app.state.evidence_store.get(evidence[0]) is not None
            assert app.state.memory_governance_store.get(ids[0], user_id="local") is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("stream", [False, True])
def test_revocation_during_model_wait_prevents_late_answer(tmp_path, stream):
    async def scenario():
        home = tmp_path / "home"
        home.mkdir()
        source = home / "source"
        source.mkdir()
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={},
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            app.state.source_grant_store.grant(
                user_id="local",
                source_id="a",
                root=source,
                candidate_kind=RootCandidateKind.DEFAULT,
            )
            item = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="a",
                    conversation_id="a",
                    message_id="m",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="项目周会 原文",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            memory = app.state.person_writes.create(
                MemoryDraft(
                    user_id="local",
                    kind=MemoryKind.CHAT,
                    content="项目周会 内容",
                    scopes=("all-apps",),
                    evidence_ids=(item.evidence_id,),
                ),
                request_id="m",
            )
            store = app.state.model_profile_store
            secrets = app.state.secret_store
            profile = store.create(
                ModelProfileInput(name="Test", provider_kind=ProviderKind.OLLAMA, model="test"),
                secrets,
            )
            store.record_capabilities(
                profile.profile_id,
                expected_revision=1,
                capabilities=ModelCapabilities(
                    endpoint_reachable=True, model_available=True, embedding_available=True
                ),
                secrets=secrets,
            )
            store.activate(profile.profile_id, secrets)
            permissions = app.state.model_content_permissions
            preview = permissions.snapshot(
                user_id="local",
                source_ids=("a",),
                profile=store.snapshot(profile.profile_id, profile.revision),
                evidence=(item,),
            )
            permissions.grant(preview, user_confirmed=True, expected_revision=0)
            entered = asyncio.Event()
            release = asyncio.Event()

            async def delayed(*args):
                entered.set()
                await release.wait()
                return _ModelAnswer(answer="迟到正文", citations=(memory.memory_id,))

            async def chunks(*args):
                value = await delayed()
                yield value.model_dump_json()

            app.state.memory_answerer._model_answer = delayed
            app.state.memory_answerer._model_chunks = chunks
            app.state.memory_answerer.semantic_search = None
            request = asyncio.create_task(
                client.post(
                    "/api/v1/memories/ask" + ("/stream" if stream else ""),
                    json={"question": "项目周会"},
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            app.state.source_grant_store.revoke(user_id="local", source_id="a")
            release.set()
            response = await request
            assert "迟到正文" not in response.text
            assert "memory_answer_context_changed" in response.text

    asyncio.run(scenario())
