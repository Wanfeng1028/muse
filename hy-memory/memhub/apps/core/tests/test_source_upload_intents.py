"""Upload identity binds retries without replacing file receipts or directory consent."""

import asyncio
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.access import source_root_identity
from one_memory.imports.connections import ConnectionIntentError, SourceConnectionStore
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.secrets import InMemorySecretStore


@pytest.fixture
def connection_store(tmp_path):
    home = tmp_path / "home"
    root = home / ".claude/projects"
    root.mkdir(parents=True)
    database = tmp_path / "data.sqlite"
    grants = SourceGrantStore(database, home=home)
    jobs = ImportJobStore(database)
    store = SourceConnectionStore(grants, jobs, home=home)
    catalog = build_source_catalog(home=home, environment={})
    options = dict(
        request_id="confirmed",
        registrations=(catalog["claude-code"],),
        source_roots={"claude-code": source_root_identity(root)},
        confirm_overrides=False,
        full_rescan=False,
    )
    return store, options, database


def test_default_connection_fingerprint_is_byte_compatible(connection_store):
    store, options, database = connection_store
    expected = hashlib.sha256(
        json.dumps(
            {
                "sources": ("claude-code",),
                "roots": options["source_roots"],
                "overrides": False,
                "full_rescan": False,
                "onboarding": False,
                "enable_sync": False,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    first = store.connect(**options)
    assert store.connect(**options, import_binding=None) == first
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT request_hash FROM source_connection_intents").fetchone() == (
            expected,
        )


@pytest.mark.parametrize("change", ["upload", "checksum", "remove"])
def test_same_request_cannot_change_upload_binding(connection_store, change):
    store, options, _ = connection_store
    binding = (str(uuid4()), "a" * 64)
    first = store.connect(**options, import_binding=binding)
    changed = {
        "upload": (str(uuid4()), binding[1]),
        "checksum": (binding[0], "b" * 64),
        "remove": None,
    }[change]
    before = store.grants.require_receipt(user_id="local", source_id="claude-code")
    with pytest.raises(ConnectionIntentError, match="source_intent_conflict"):
        store.connect(**options, import_binding=changed)
    assert store.get(options["request_id"]) == first
    assert len(store.jobs.list_jobs()) == 1
    assert store.grants.require_receipt(user_id="local", source_id="claude-code") == before


def test_concurrent_upload_retry_and_completed_replay_keep_one_job(connection_store):
    store, options, _ = connection_store
    binding = (str(uuid4()), "a" * 64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.connect, **options, import_binding=binding) for _ in range(2)]
        first, repeated = [future.result(timeout=10) for future in futures]
    assert first == repeated
    job_id = first.jobs[0].job_id
    store.jobs.claim(job_id)
    store.jobs.transition(job_id, ImportStatus.COMPLETED)
    replay = store.connect(**options, import_binding=binding)
    assert replay.jobs[0].job_id == job_id
    assert replay.jobs[0].status is ImportStatus.COMPLETED
    assert len(store.jobs.list_jobs()) == 1
    options["request_id"] = "next-reviewed-upload"
    next_upload = store.connect(**options, import_binding=(str(uuid4()), "b" * 64))
    assert next_upload.jobs[0].job_id != job_id
    assert len(store.jobs.list_jobs()) == 2
    assert not store.grants.require_receipt(user_id="local", source_id="claude-code").sync_enabled


def test_new_upload_does_not_bypass_an_active_source_job(connection_store):
    store, options, _ = connection_store
    first = store.connect(**options, import_binding=(str(uuid4()), "a" * 64))
    before = store.grants.require_receipt(user_id="local", source_id="claude-code")
    next_options = {**options, "request_id": "second-confirmed"}
    binding = (str(uuid4()), "b" * 64)
    busy = store.connect(**next_options, import_binding=binding)
    assert busy.accepted_source_ids == ()
    assert busy.failed_sources == {"claude-code": "source_import_busy"}
    assert busy.jobs == ()
    assert store.grants.require_receipt(user_id="local", source_id="claude-code") == before
    assert len(store.jobs.list_jobs()) == 1
    job_id = first.jobs[0].job_id
    store.jobs.claim(job_id)
    store.jobs.transition(job_id, ImportStatus.COMPLETED)
    assert store.connect(**next_options, import_binding=binding) == busy
    retried = store.connect(
        **{**next_options, "request_id": "explicit-failed-retry"}, import_binding=binding
    )
    assert retried.accepted_source_ids == ("claude-code",)
    assert retried.jobs[0].job_id != job_id
    assert len(store.jobs.list_jobs()) == 2


def upload_app(tmp_path, monkeypatch, *, foreign_ready=False):
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
    home = tmp_path / "home"
    (home / ".claude/projects").mkdir(parents=True)
    data = tmp_path / "data"
    ready = (tmp_path / "foreign" if foreign_ready else data / "import-files") / "ready"
    if foreign_ready:
        (ready / "generic-export").mkdir(parents=True)
    return create_app(
        Settings(
            data_dir=data,
            source_home=home,
            api_token=SecretStr("test-upload"),
            automatic_memory_processing=False,
            live_sync_enabled=False,
        ),
        source_catalog=build_source_catalog(home=home, environment={}, import_root=ready),
        secret_store=InMemorySecretStore(),
    )


@asynccontextmanager
async def upload_client(app):
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer test-upload"},
        ) as client,
    ):
        yield client


async def prepare_upload(client, text="first upload", *, commit=True):
    response = await client.post(
        "/api/v1/import-files?filename=chat.txt",
        content=f"User: {text}\nAssistant: Acknowledged {text}.".encode(),
    )
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt["committed"] is False
    if commit:
        response = await client.post(
            f"/api/v1/import-files/{receipt['upload_id']}/commit", json={"confirmed": True}
        )
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["committed"] is True
    return receipt


async def checked_request(client, upload, *, sources=None, enable_sync=False):
    source_ids = sources if sources is not None else [upload["source_id"]]
    roots = {}
    for source_id in source_ids:
        found = await client.post(f"/api/v1/sources/{source_id}/location")
        assert found.status_code == 200, found.text
        roots[source_id] = found.json()["root_id"]
        assert roots[source_id]
    return {
        "source_ids": source_ids,
        "source_roots": roots,
        "request_id": str(uuid4()),
        "import_upload_id": upload["upload_id"],
        "enable_sync": enable_sync,
    }


def test_file_route_same_upload_replays_but_distinct_upload_imports_new_data(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client)
            request = await checked_request(client, first, enable_sync=True)
            connected = await client.post("/api/v1/sources/connect", json=request)
            assert connected.status_code == 200, connected.text
            job_id = connected.json()["jobs"][0]["job_id"]
            job = await app.state.import_supervisor.wait(job_id)
            assert job.status is ImportStatus.COMPLETED and job.stored == 2 and job.errors == 0
            assert app.state.evidence_store.count() == 2
            before = app.state.source_grant_store.require_receipt(
                user_id="local", source_id=first["source_id"]
            )
            replay = await client.post("/api/v1/sources/connect", json=request)
            assert replay.status_code == 200, replay.text
            assert replay.json()["jobs"][0]["job_id"] == job_id
            assert replay.json()["jobs"][0]["status"] == "completed"
            assert (
                app.state.source_grant_store.require_receipt(
                    user_id="local", source_id=first["source_id"]
                )
                == before
            )

            second = await prepare_upload(client, "second upload")
            next_request = await checked_request(client, second, enable_sync=True)
            assert second["checksum"] != first["checksum"]
            assert next_request["source_roots"] == request["source_roots"]
            assert app.state.evidence_store.count() == 2
            conflict = await client.post(
                "/api/v1/sources/connect", json={**request, "import_upload_id": second["upload_id"]}
            )
            assert conflict.status_code == 409, conflict.text
            assert conflict.json()["detail"] == "source_intent_conflict"
            assert len(app.state.import_job_store.list_jobs()) == 1
            next_connect = await client.post("/api/v1/sources/connect", json=next_request)
            assert next_connect.status_code == 200, next_connect.text
            next_job_id = next_connect.json()["jobs"][0]["job_id"]
            assert next_job_id != job_id
            next_job = await app.state.import_supervisor.wait(next_job_id)
            assert next_job.status is ImportStatus.COMPLETED
            assert next_job.stored == 2 and next_job.errors == 0
            assert app.state.evidence_store.count() == 4
            found = (
                await client.get("/api/v1/conversations/search", params={"query": "second upload"})
            ).json()
            assert found["hits"]
            for body, expected_job in [(request, job_id), (next_request, next_job_id)]:
                replay = await client.post("/api/v1/sources/connect", json=body)
                assert replay.status_code == 200, replay.text
                assert replay.json()["jobs"][0]["job_id"] == expected_job
            assert len(app.state.import_job_store.list_jobs()) == 2
            assert app.state.evidence_store.count() == 4
            grant = app.state.source_grant_store.require_receipt(
                user_id="local", source_id=first["source_id"]
            )
            assert grant.root_id == request["source_roots"][first["source_id"]]
            assert grant.sync_enabled
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            denied_sync = await client.post(
                "/api/v1/import-jobs", json={"source_id": first["source_id"], "operation": "sync"}
            )
            assert denied_sync.status_code == 200
            await app.state.import_supervisor.wait(denied_sync.json()["job_id"])

    asyncio.run(scenario())


def test_upload_binding_keeps_committed_directory_scope_and_excludes_staging(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client, "earlier committed file")
            second = await prepare_upload(client, "later committed file")
            staged = await prepare_upload(client, "unconfirmed file", commit=False)
            assert first["source_id"] == second["source_id"] == staged["source_id"]
            request = await checked_request(client, second, enable_sync=True)
            connected = await client.post("/api/v1/sources/connect", json=request)
            assert connected.status_code == 200, connected.text
            job = await app.state.import_supervisor.wait(connected.json()["jobs"][0]["job_id"])
            assert job.status is ImportStatus.COMPLETED
            assert job.stored == 4 and job.errors == 0
            assert app.state.evidence_store.count() == 4
            for phrase, expected_count in [
                ("earlier committed file", 1),
                ("later committed file", 1),
                ("unconfirmed file", 0),
            ]:
                response = await client.get(
                    "/api/v1/conversations/search", params={"query": phrase}
                )
                assert response.status_code == 200, response.text
                assert len(response.json()["hits"]) == expected_count
            authorized = app.state.source_grant_store.authorized_root(
                user_id="local", source_id=second["source_id"]
            )
            assert (
                authorized.root
                == (app.state.file_import_store.root / "ready" / second["source_id"]).resolve()
            )
            assert app.state.source_grant_store.require_receipt(
                user_id="local", source_id=second["source_id"]
            ).sync_enabled
            assert app.state.model_content_permissions.receipt(user_id="local") is None

    asyncio.run(scenario())


def test_new_confirmed_upload_of_identical_bytes_retains_evidence_dedup(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client)
            first_request = await checked_request(client, first, enable_sync=True)
            first_connect = await client.post("/api/v1/sources/connect", json=first_request)
            assert first_connect.status_code == 200, first_connect.text
            first_job_id = first_connect.json()["jobs"][0]["job_id"]
            first_job = await app.state.import_supervisor.wait(first_job_id)
            assert first_job.stored == 2 and first_job.status is ImportStatus.COMPLETED
            second = await prepare_upload(client)
            assert second["upload_id"] != first["upload_id"]
            assert second["checksum"] == first["checksum"]
            second_request = await checked_request(client, second, enable_sync=True)
            conflict = await client.post(
                "/api/v1/sources/connect",
                json={**first_request, "import_upload_id": second["upload_id"]},
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"] == "source_intent_conflict"
            connected = await client.post("/api/v1/sources/connect", json=second_request)
            assert connected.status_code == 200, connected.text
            job_id = connected.json()["jobs"][0]["job_id"]
            assert job_id != first_job_id
            job = await app.state.import_supervisor.wait(job_id)
            assert job.status is ImportStatus.COMPLETED and job.stored == 0 and job.errors == 0
            assert app.state.evidence_store.count() == 2
            assert len(app.state.import_job_store.list_jobs()) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "scope", ["uncommitted", "unknown", "other-source", "extra-source", "foreign-ready"]
)
def test_file_route_refuses_mismatched_receipt_or_scope_without_grants(
    tmp_path, monkeypatch, scope
):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch, foreign_ready=scope == "foreign-ready")
        async with upload_client(app) as client:
            upload = await prepare_upload(client)
            if scope == "uncommitted":
                duplicate = await prepare_upload(client, commit=False)
                assert duplicate["checksum"] == upload["checksum"]
                upload = duplicate
            if scope == "unknown":
                upload = {**upload, "upload_id": str(uuid4())}
            sources = {
                "other-source": ["claude-code"],
                "extra-source": [upload["source_id"], "claude-code"],
            }.get(scope)
            request = await checked_request(client, upload, sources=sources)
            denied = await client.post("/api/v1/sources/connect", json=request)
            assert denied.status_code == 409, denied.text
            assert denied.json()["detail"] == "import_upload_scope_mismatch"
            assert app.state.source_connection_store.get(request["request_id"]) is None
            assert app.state.import_job_store.list_jobs() == []
            assert app.state.evidence_store.count() == 0
            for source_id in [upload["source_id"], "claude-code"]:
                assert (
                    app.state.source_grant_store.receipt(user_id="local", source_id=source_id)
                    is None
                )
            assert app.state.model_content_permissions.receipt(user_id="local") is None

    asyncio.run(scenario())


def test_committed_upload_does_not_bypass_checked_root_identity(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            upload = await prepare_upload(client)
            request = await checked_request(client, upload)
            ready = app.state.file_import_store.root / "ready" / upload["source_id"]
            ready.rename(ready.with_name("previous-ready"))
            ready.mkdir()
            response = await client.post("/api/v1/sources/connect", json=request)
            assert response.status_code == 200, response.text
            assert response.json()["accepted_source_ids"] == []
            assert response.json()["failed_sources"] == {
                upload["source_id"]: "source_identity_changed"
            }
            assert app.state.import_job_store.list_jobs() == []
            assert (
                app.state.source_grant_store.receipt(user_id="local", source_id=upload["source_id"])
                is None
            )

    asyncio.run(scenario())
