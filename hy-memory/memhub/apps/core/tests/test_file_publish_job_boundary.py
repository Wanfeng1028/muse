"""Staged uploads cannot widen an earlier directory import's uncaptured input."""

import asyncio
import multiprocessing
import os
import sqlite3
from contextlib import ExitStack, closing, contextmanager
from threading import Event
from uuid import UUID

import pytest
from filelock import FileLock

from one_memory.imports.connections import SourceConnectionStore
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import build_source_catalog
from tests.test_source_upload_intents import (
    checked_request,
    prepare_upload,
    upload_app,
    upload_client,
)


def test_pending_source_job_refuses_publication_before_its_snapshot(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client, "previously confirmed input")
            staged = await prepare_upload(client, "not in previous confirmation", commit=False)
            files = app.state.file_import_store
            directory = files.root / "staging" / staged["upload_id"]
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            request = await checked_request(client, first, enable_sync=True)
            supervisor = app.state.import_supervisor
            enqueue = supervisor.enqueue
            monkeypatch.setattr(supervisor, "enqueue", app.state.import_job_store.require)
            response = await client.post("/api/v1/sources/connect", json=request)
            assert response.status_code == 200, response.text
            job_id = response.json()["jobs"][0]["job_id"]
            assert app.state.import_job_store.require(job_id).status is ImportStatus.PENDING
            snapshots = app.state.settings.data_dir / "import-snapshots"
            assert not (snapshots / job_id / "manifest.json").exists()
            grant = app.state.source_grant_store.require_receipt(
                user_id="local", source_id=first["source_id"]
            )
            jobs = app.state.import_job_store.list_jobs()

            response = await client.post(
                f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
            )
            assert response.status_code == 409, response.text
            assert response.json()["detail"] == "import_source_busy"
            assert not files.get(UUID(staged["upload_id"])).committed
            assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
            ready = files.root / "ready" / first["source_id"]
            assert sorted(path.name for path in ready.iterdir()) == [f"{first['checksum']}.jsonl"]
            assert app.state.import_job_store.list_jobs() == jobs
            assert (
                app.state.source_grant_store.require_receipt(
                    user_id="local", source_id=first["source_id"]
                )
                == grant
            )
            assert grant.sync_enabled
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            assert app.state.evidence_store.count() == 0

            enqueue(job_id)
            job = await supervisor.wait(job_id)
            assert job.status is ImportStatus.COMPLETED
            assert job.stored == 2 and job.errors == 0
            assert app.state.evidence_store.count() == 2
            excluded = await client.get(
                "/api/v1/conversations/search", params={"query": "not in previous confirmation"}
            )
            assert excluded.status_code == 200, excluded.text
            assert excluded.json()["hits"] == []
            included = await client.get(
                "/api/v1/conversations/search", params={"query": "previously confirmed input"}
            )
            assert included.status_code == 200, included.text
            # Conversation search is grouped by conversation, while the store
            # count above proves both source messages were committed.
            assert len(included.json()["hits"]) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status", list(ImportStatus))
def test_source_job_states_and_committed_retries(tmp_path, monkeypatch, status):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client)
            staged = await prepare_upload(client, "next upload", commit=False)
            jobs = app.state.import_job_store
            monkeypatch.setattr(app.state.import_supervisor, "enqueue", jobs.require)
            response = await client.post(
                "/api/v1/sources/connect",
                json=await checked_request(client, first),
            )
            assert response.status_code == 200, response.text
            job_id = response.json()["jobs"][0]["job_id"]
            if status in {
                ImportStatus.RUNNING,
                ImportStatus.INTERRUPTED,
                ImportStatus.FAILED,
                ImportStatus.COMPLETED,
            }:
                jobs.claim(job_id)
            if status not in {ImportStatus.PENDING, ImportStatus.RUNNING}:
                jobs.transition(job_id, status)
            before_jobs = jobs.list_jobs()
            grant = app.state.source_grant_store.require_receipt(
                user_id="local", source_id=first["source_id"]
            )
            files = app.state.file_import_store
            directory = files.root / "staging" / staged["upload_id"]
            before_staging = {path.name: path.read_bytes() for path in directory.iterdir()}
            # An already committed upload must not even need the held DB writer.
            with jobs._connect(writing=True):
                replay = await client.post(
                    f"/api/v1/import-files/{first['upload_id']}/commit", json={"confirmed": True}
                )
            assert replay.status_code == 200, replay.text
            assert replay.json() == first
            response = await client.post(
                f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
            )
            allowed = status in {ImportStatus.COMPLETED, ImportStatus.CANCELLED}
            assert response.status_code == (200 if allowed else 409), response.text
            target = files.root / "ready" / staged["source_id"] / f"{staged['checksum']}.jsonl"
            assert target.exists() is allowed
            assert files.get(UUID(staged["upload_id"])).committed is allowed
            if not allowed:
                assert response.json()["detail"] == "import_source_busy"
                assert {
                    path.name: path.read_bytes() for path in directory.iterdir()
                } == before_staging
            assert jobs.list_jobs() == before_jobs
            assert (
                app.state.source_grant_store.require_receipt(
                    user_id="local", source_id=first["source_id"]
                )
                == grant
            )
            assert not grant.sync_enabled
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            assert app.state.evidence_store.count() == 0
            assert not app.state.import_supervisor._tasks

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["history", "sync"])
@pytest.mark.parametrize("same_source", [True, False])
def test_job_lookup_uses_source_identity_across_users(
    tmp_path, monkeypatch, operation, same_source
):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            staged = await prepare_upload(client, commit=False)
            jobs = app.state.import_job_store
            job = jobs.create(
                user_id="other-user",
                source_id=staged["source_id"] if same_source else "claude-code",
                operation=operation,
            )
            response = await client.post(
                f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
            )
            assert response.status_code == (409 if same_source else 200), response.text
            assert (
                app.state.file_import_store.get(UUID(staged["upload_id"])).committed
                is not same_source
            )
            assert jobs.list_jobs() == [job]
            assert (
                app.state.source_grant_store.receipt(user_id="local", source_id=staged["source_id"])
                is None
            )
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            assert app.state.evidence_store.count() == 0

    asyncio.run(scenario())


def _held_connect(database, home, ready, source_id, root_id, entered, release, rollback):
    """A separate process owns the real connect transaction until the test releases it."""
    grants = SourceGrantStore(database, home=home)
    jobs = ImportJobStore(database)
    connections = SourceConnectionStore(grants, jobs, home=home)
    receipt = connections._receipt

    def held_receipt(row, db):
        result = receipt(row, db)
        assert db.in_transaction and len(result.jobs) == 1
        entered.set()
        assert release.wait(10), "connect transaction was not released"
        if rollback:
            raise sqlite3.OperationalError("injected connection rollback")
        return result

    connections._receipt = held_receipt
    catalog = build_source_catalog(home=home, environment={}, import_root=ready)
    try:
        connections.connect(
            request_id="held-connect",
            registrations=(catalog[source_id],),
            source_roots={source_id: root_id},
            confirm_overrides=False,
            full_rescan=False,
        )
    except sqlite3.OperationalError as error:
        if not rollback or str(error) != "injected connection rollback":
            raise


@pytest.mark.parametrize("rollback", [False, True])
def test_connect_in_another_process_serializes_before_publish(tmp_path, monkeypatch, rollback):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client)
            staged = await prepare_upload(client, "next upload", commit=False)
            request = await checked_request(client, first)
            files = app.state.file_import_store
            jobs = app.state.import_job_store
            context = multiprocessing.get_context("spawn")
            entered, release = context.Event(), context.Event()
            process = context.Process(
                target=_held_connect,
                args=(
                    jobs.database_path,
                    app.state.settings.source_home,
                    files.root / "ready",
                    first["source_id"],
                    request["source_roots"][first["source_id"]],
                    entered,
                    release,
                    rollback,
                ),
            )
            attempting = Event()
            original_connect = jobs._connect

            def observed_connect(*, initialize=False, writing=False):
                if writing:
                    attempting.set()
                return original_connect(initialize=initialize, writing=writing)

            monkeypatch.setattr(jobs, "_connect", observed_connect)
            process.start()
            pending = None
            target = files.root / "ready" / staged["source_id"] / f"{staged['checksum']}.jsonl"
            try:
                assert await asyncio.to_thread(entered.wait, 10), "connect did not acquire writer"
                assert jobs.list_jobs() == []  # Its new job is still uncommitted.
                pending = asyncio.create_task(
                    client.post(
                        f"/api/v1/import-files/{staged['upload_id']}/commit",
                        json={"confirmed": True},
                    )
                )
                assert await asyncio.to_thread(attempting.wait, 5), "publication skipped DB writer"
                assert not pending.done()
                assert not target.exists()
            finally:
                release.set()
                await asyncio.to_thread(process.join, 10)
                if process.is_alive():
                    process.terminate()
                    await asyncio.to_thread(process.join, 5)
                if pending is not None:
                    response = await pending
            assert process.exitcode == 0
            assert response.status_code == (200 if rollback else 409), response.text
            assert target.exists() is rollback
            assert files.get(UUID(staged["upload_id"])).committed is rollback
            assert len(jobs.list_jobs()) == (0 if rollback else 1)
            grant = app.state.source_grant_store.receipt(
                user_id="local", source_id=first["source_id"]
            )
            assert (grant is None) is rollback
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            assert app.state.evidence_store.count() == 0

    asyncio.run(scenario())


def test_publish_holds_writer_until_link_then_later_connect_captures_both(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            first = await prepare_upload(client)
            staged = await prepare_upload(client, "published before connect", commit=False)
            entered, release = Event(), Event()
            link = os.link

            def held_link(*args, **kwargs):
                entered.set()
                assert release.wait(10), "publication was not released"
                return link(*args, **kwargs)

            monkeypatch.setattr(os, "link", held_link)
            pending = asyncio.create_task(
                client.post(
                    f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                with (
                    closing(
                        sqlite3.connect(app.state.import_job_store.database_path, timeout=0)
                    ) as db,
                    pytest.raises(sqlite3.OperationalError, match="locked"),
                ):
                    db.execute("BEGIN IMMEDIATE")
            finally:
                release.set()
                response = await pending
            assert response.status_code == 200, response.text
            assert app.state.import_job_store.list_jobs() == []
            connected = await client.post(
                "/api/v1/sources/connect",
                json=await checked_request(client, first, enable_sync=True),
            )
            assert connected.status_code == 200, connected.text
            job = await app.state.import_supervisor.wait(connected.json()["jobs"][0]["job_id"])
            assert job.status is ImportStatus.COMPLETED
            assert job.stored == 4 and job.errors == 0
            assert app.state.evidence_store.count() == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["database-lock", "upload-lock", "job-query"])
def test_publish_lock_and_query_errors_leave_staging_for_explicit_retry(
    tmp_path, monkeypatch, failure
):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        async with upload_client(app) as client:
            staged = await prepare_upload(client, commit=False)
            files = app.state.file_import_store
            jobs = app.state.import_job_store
            directory = files.root / "staging" / staged["upload_id"]
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            with monkeypatch.context() as patch, ExitStack() as stack:
                if failure == "database-lock":
                    stack.enter_context(jobs._connect(writing=True))
                elif failure == "upload-lock":
                    held = stack.enter_context(files._lock(UUID(staged["upload_id"])))
                    patch.setattr(files, "_lock", lambda _: FileLock(held.lock_file, timeout=0))
                else:
                    original_connect = jobs._connect

                    @contextmanager
                    def failed_query(*, initialize=False, writing=False):
                        with original_connect(initialize=initialize, writing=writing) as db:
                            if writing:
                                db.set_progress_handler(lambda: 1, 1)
                            yield db

                    patch.setattr(jobs, "_connect", failed_query)
                response = await client.post(
                    f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
                )
            assert response.status_code == 503, response.text
            expected = "import_file_busy" if failure == "upload-lock" else "local_store_unavailable"
            assert response.json()["detail"] == expected
            assert not files.get(UUID(staged["upload_id"])).committed
            assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
            assert not list((files.root / "ready").rglob("*.jsonl"))
            assert jobs.list_jobs() == []
            assert (
                app.state.source_grant_store.receipt(user_id="local", source_id=staged["source_id"])
                is None
            )
            assert app.state.model_content_permissions.receipt(user_id="local") is None
            assert app.state.evidence_store.count() == 0
            retried = await client.post(
                f"/api/v1/import-files/{staged['upload_id']}/commit", json={"confirmed": True}
            )
            assert retried.status_code == 200, retried.text
            assert jobs.list_jobs() == []

    asyncio.run(scenario())
