import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)


def test_memory_governance_api_preserves_evidence_and_reports_cleanup(tmp_path) -> None:
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
                    conversation_id="conversation",
                    message_id="message",
                    correlation_id="message",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="Original private words; token=local-secret-value",
                    origin_meta={
                        EvidenceOrigin.FILE: OriginMetadata(
                            raw_meta={"absolute_path": "/must/not/leave/api"}
                        )
                    },
                )
            ).record
            created = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "create-1",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "Initial memory",
                        "scopes": ["all-apps"],
                        "evidence_ids": [evidence.evidence_id],
                    },
                },
            )
            assert created.status_code == 200
            memory_id = created.json()["memory_id"]

            assert created.json()["status"] == "confirmed"
            recalled = await client.post(
                "/api/v1/recall",
                json={"query": "Initial memory", "scope": "all-apps"},
            )
            assert recalled.status_code == 200
            assert recalled.json()["state"] == "grounded"
            assert recalled.json()["hits"][0]["memory_id"] == memory_id
            corrected = await client.post(
                f"/api/v1/memories/{memory_id}/correct",
                json={
                    "request_id": "correct-1",
                    "expected_revision": 1,
                    "content": "Corrected memory",
                    "scopes": ["cursor"],
                },
            )
            assert corrected.status_code == 200

            detail = await client.get(f"/api/v1/memories/{memory_id}")
            assert evidence.verbatim == "Original private words; token=local-secret-value"
            assert detail.json()["evidence"][0]["verbatim"] == (
                "Original private words; token=<redacted-secret>"
            )
            assert "absolute_path" not in detail.text
            assert detail.json()["history"][0]["action"] == "correct"

            graph = await client.get("/api/v1/memories/graph")
            assert graph.status_code == 200
            assert graph.json()["projected_memories"] == 1
            assert {node["node_type"] for node in graph.json()["nodes"]} == {"memory", "source"}
            assert graph.json()["edges"][0]["relation"] == "evidence_source"

            deleted = await client.post(
                f"/api/v1/memories/{memory_id}/actions/delete",
                json={"request_id": "delete-1", "expected_revision": 2},
            )
            assert deleted.json()["status"] == "deleted"
            cleanup = await client.get(f"/api/v1/memories/{memory_id}/deletion")
            assert cleanup.json()["status"] == "failed"
            assert cleanup.json()["last_error_code"] == "model_profile_not_active"

    asyncio.run(scenario())


def test_memory_validation_does_not_echo_content(tmp_path) -> None:
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
            response = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "create-1",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "secret body",
                        "scopes": [],
                        "evidence_ids": [],
                    },
                },
            )

            assert response.status_code == 422
            assert "secret body" not in response.text
            assert "input" not in response.text

    asyncio.run(scenario())
