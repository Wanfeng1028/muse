"""Revoking a source parks its unfinished extraction instead of failing it (D73).

Revocation is the user's node: originals already imported stay readable, but
nothing from that source may reach the model again until the person authorizes
it. Parking reuses the waiting state, so the work survives, is not counted as
a failure, and resumes on re-authorization.
"""

import asyncio
import json

import pytest

from one_memory.imports.models import (
    EvidenceContentKind,
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_tasks import MemoryTaskKind, MemoryTaskStatus, MemoryTaskStore
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore
from tests.source_consent import authorized_request, thaw_source


@pytest.fixture
def library(tmp_path):
    class Fixture:
        def __init__(self):
            self.database = tmp_path / "one-memory.sqlite3"
            self.evidence = EvidenceStore(self.database)
            self.profiles = ModelProfileStore(self.database)
            self.secrets = InMemorySecretStore()
            self.tasks = MemoryTaskStore(self.database)
            profile = self.profiles.create(
                ModelProfileInput(
                    name="Synthetic",
                    provider_kind=ProviderKind.OLLAMA,
                    model="test-model",
                    embedding_provider_kind=ProviderKind.LOCAL_ONNX,
                    embedding_model="test-local-embedding",
                ),
                self.secrets,
            )
            self.profiles.record_capabilities(
                profile.profile_id,
                expected_revision=profile.revision,
                capabilities=ModelCapabilities(
                    endpoint_reachable=True,
                    model_available=True,
                    embedding_available=True,
                ),
                secrets=self.secrets,
            )
            self.profile = self.profiles.activate(profile.profile_id, self.secrets)

        def put(self, key, *, source):
            return self.evidence.put(
                EvidenceInput(
                    source_id=source,
                    conversation_id=f"conversation-{source}",
                    message_id=key,
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim=f"Synthetic original {key}",
                    content_kind=EvidenceContentKind.RAW_CONVERSATION,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record

        def task(self, record):
            return self.tasks.create(
                request_id=f"revocation:{record.evidence_id}",
                user_id="local",
                kind=MemoryTaskKind.EXTRACT,
                input_ref=record.evidence_id,
                profile=self.profile,
                input_records=(record,),
            )

    return Fixture()


def test_revocation_parks_only_that_source_and_never_fails(library):
    revoked = library.put("revoked-turn", source="cursor")
    other = library.put("kept-turn", source="workbuddy")
    revoked_task = library.task(revoked)
    other_task = library.task(other)

    parked = library.tasks.park_source_for_permission(
        source_id="cursor", error_code="model_content_permission_required"
    )
    assert parked == 1

    assert (
        library.tasks.require(revoked_task.task_id).status
        is MemoryTaskStatus.WAITING_FOR_PERMISSION
    )
    assert (
        library.tasks.require(revoked_task.task_id).last_error_code
        == "model_content_permission_required"
    )
    # A deliberate user stop may not read as a broken pipeline.
    assert not library.tasks.list(statuses=(MemoryTaskStatus.FAILED,))
    # Another source's work is untouched: revocation is per source.
    assert library.tasks.require(other_task.task_id).status is MemoryTaskStatus.PENDING


def test_the_revoke_route_parks_that_sources_work(tmp_path):
    """The route, not only the store: revoking parks extraction for that source."""
    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr

    from one_memory.api import create_app
    from one_memory.config import Settings
    from one_memory.imports.sources.registry import build_source_catalog

    async def scenario():
        home = tmp_path / "home"
        projects = home / ".claude" / "projects"
        projects.mkdir(parents=True)
        (projects / "session.jsonl").write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "session",
                    "uuid": "message",
                    "message": {"content": "Remember this"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        settings = Settings(
            data_dir=tmp_path / "data",
            source_home=home,
            api_token=SecretStr("test-token"),
        )
        app = create_app(settings, source_catalog=build_source_catalog(home=home, environment={}))
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-token"},
            ) as client,
        ):
            authorized = await client.post(
                "/api/v1/sources/claude-code/authorize",
                json=await authorized_request(client, "claude-code"),
            )
            assert authorized.status_code == 200, authorized.text
            await thaw_source(client, "claude-code", authorized.json())
            created = await client.post("/api/v1/import-jobs", json={"source_id": "claude-code"})
            assert created.status_code == 200
            job = await app.state.import_supervisor.wait(created.json()["job_id"])
            assert job.status == "completed" and job.stored == 1
            calls = []
            store = app.state.memory_task_store
            original = store.park_source_for_permission

            def spied(**kwargs):
                calls.append(kwargs)
                return original(**kwargs)

            store.park_source_for_permission = spied
            revoked = await client.post("/api/v1/sources/claude-code/revoke")
            assert revoked.status_code == 200
            # The route parks that source's unfinished work; the store test
            # above pins what parking means.
            assert [call["source_id"] for call in calls] == ["claude-code"]
            assert calls[0]["error_code"] == "model_content_permission_required"
            assert not store.list(statuses=(MemoryTaskStatus.FAILED,))

    asyncio.run(scenario())
