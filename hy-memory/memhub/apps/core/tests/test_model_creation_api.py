"""Normal protected model creation routes with temporary data and in-memory secrets."""

import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.secrets import InMemorySecretStore


def test_creation_receipt_api_replay_and_delete(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token="test",
                imports_enabled=False,
                live_sync_enabled=False,
            ),
            source_catalog={},
            secret_store=InMemorySecretStore(),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            operation = str(uuid4())
            url = "/api/v1/model-profile-creations/" + operation
            assert (await client.get(url)).status_code == 401
            client.headers["Authorization"] = "Bearer test"
            assert (await client.get(url)).json() == {
                "operation_id": operation,
                "state": "not_found",
                "profile_id": None,
                "created_revision": None,
            }
            assert (
                await client.get("/api/v1/model-profile-creations/not-a-uuid")
            ).status_code == 422
            body = {
                "name": "Temporary",
                "provider_kind": "ollama",
                "model": "fake",
                "creation_operation_id": operation,
            }
            created = await client.post("/api/v1/model-profiles", json=body)
            assert created.status_code == 200, created.text
            profile = created.json()
            receipt = await client.get(url)
            assert receipt.json() == {
                "operation_id": operation,
                "state": "committed",
                "profile_id": profile["profile_id"],
                "created_revision": 1,
            }
            replay = await client.post("/api/v1/model-profiles", json=body)
            assert replay.status_code == 409
            assert replay.json()["detail"] == "model_creation_operation_conflict"
            assert len((await client.get("/api/v1/model-profiles")).json()) == 1
            assert (
                await client.delete("/api/v1/model-profiles/" + profile["profile_id"])
            ).status_code == 204
            assert (await client.get(url)).json()["state"] == "deleted"
            assert (await client.post("/api/v1/model-profiles", json=body)).status_code == 409
            assert app.state.memory_task_store.list() == []

    asyncio.run(scenario())
