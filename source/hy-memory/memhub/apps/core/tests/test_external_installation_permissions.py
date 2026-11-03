import asyncio
import json
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy


def headers(*, scopes=("all-apps",), tools=("om_recall",)):
    return {
        "x-one-memory-read-context": "external",
        "x-one-memory-installation-id": str(uuid4()),
        "x-one-memory-installation-revision": "1",
        "x-one-memory-allowed-scopes": json.dumps(scopes),
        "x-one-memory-allowed-tools": json.dumps(tools),
    }


def test_external_marker_is_not_an_installation_grant(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path,
                source_home=tmp_path,
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
            missing = await client.post(
                "/api/v1/recall",
                json={"query": "history"},
                headers={"x-one-memory-read-context": "external"},
            )
            assert missing.status_code == 403
            approved = await client.post(
                "/api/v1/recall", json={"query": "history"}, headers=headers()
            )
            assert approved.status_code == 200
            denied_tool = await client.post(
                "/api/v1/memories/ask", json={"question": "history"}, headers=headers()
            )
            assert denied_tool.status_code == 403
            no_raw = await client.get(
                "/api/v1/conversations/search",
                params={"query": "history"},
                headers=headers(tools=("om_conversations",)),
            )
            assert no_raw.status_code == 403

    asyncio.run(scenario())


def test_external_diagnostic_trace_uses_its_own_read_only_tool(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path,
                source_home=tmp_path,
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
            allowed = await client.post(
                "/api/v1/diagnostics/trace",
                json={"trace_id": "missing-trace"},
                headers=headers(tools=("om_diagnostic_trace",)),
            )
            assert allowed.status_code == 200
            assert allowed.json()["state"] == "disabled"
            denied = await client.post(
                "/api/v1/diagnostics/trace",
                json={"trace_id": "missing-trace"},
                headers=headers(tools=("om_recall",)),
            )
            assert denied.status_code == 403

    asyncio.run(scenario())


def test_raw_source_grants_filter_before_limit_and_private_body_loading(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path,
                source_home=tmp_path,
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
            for source in ("allowed", "denied"):
                app.state.evidence_store.put(
                    EvidenceInput(
                        source_id=source,
                        conversation_id="one",
                        message_id="one",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim="needle " + source,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                )
            result = await client.get(
                "/api/v1/conversations/search",
                params={"query": "needle", "limit": 1},
                headers=headers(scopes=("all-apps", "source:allowed"), tools=("om_conversations",)),
            )
            assert result.status_code == 200
            assert result.json()["imported_messages"] == 1
            assert [hit["source_id"] for hit in result.json()["hits"]] == ["allowed"]
            assert "needle denied" not in result.text

    asyncio.run(scenario())
