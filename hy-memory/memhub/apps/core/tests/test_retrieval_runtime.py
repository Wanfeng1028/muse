import asyncio
import json
import os
import shutil
import socket
import sqlite3
import threading
import time
from contextlib import closing

import pytest

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.imports.storage import EvidenceStore
from one_memory.retrieval import runtime
from one_memory.retrieval.index_store import RetrievalIndexStore
from one_memory.retrieval.index_worker import IndexWorkResult, LocalRetrievalEncoder
from one_memory.retrieval.runtime import ExistingRetrievalRuntime
from one_memory.retrieval.vector_store import RawVectorStore
from tests.test_retrieval_index_store import put


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("offline runtime test")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)


def configured(tmp_path, *, version=2, collection=True):
    path = tmp_path / "one-memory.sqlite3"
    evidence = EvidenceStore(path)
    identity = LocalRetrievalEncoder(content_version=version).identity
    store = RetrievalIndexStore(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)
        store.migrate_v2(db)
        generation = store.create_generation(db, identity)
    store.activate_generation(generation)
    if collection:
        vectors = RawVectorStore.create(
            tmp_path / "retrieval-vectors", generation_id=generation, dimensions=identity.dimensions
        )
        vectors.close()
    return store, evidence, generation


async def until(predicate):
    end = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < end
        await asyncio.sleep(0.01)


def test_constructor_and_missing_start_create_nothing(tmp_path):
    target = tmp_path / "missing"
    handle = ExistingRetrievalRuntime(target)
    assert not target.exists()
    assert not asyncio.run(handle.start())
    assert handle.snapshot().state == "not_initialized"
    assert not target.exists()
    asyncio.run(handle.stop())


def test_stop_releases_supervisor_worker_but_preserves_immutable_snapshot(tmp_path):
    configured(tmp_path)
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)

    async def scenario():
        assert await handle.start()
        assert handle._supervisor is not None
        await handle.stop()

    asyncio.run(scenario())
    assert handle._supervisor is None
    assert handle.snapshot().supervisor is not None
    assert not handle.snapshot().supervisor.thread_alive


@pytest.mark.parametrize(
    "kind",
    ["schema1", "no_active", "missing_collection", "bad_identity", "extra_identity", "two_active"],
)
def test_not_initialized_or_invalid_configuration_never_creates_index(tmp_path, kind):
    store, _, gen = configured(tmp_path, collection=False)
    with closing(sqlite3.connect(store.database_path)) as db, db:
        if kind == "schema1":
            db.execute("UPDATE retrieval_index_state SET schema_version=1")
        elif kind == "no_active":
            db.execute("UPDATE retrieval_index_generations SET state='building'")
        elif kind in ("bad_identity", "extra_identity"):
            raw = json.loads(
                db.execute("SELECT identity_json FROM retrieval_index_generations").fetchone()[0]
            )
            if kind == "bad_identity":
                raw["encoder_digest"] = "0" * 64
            else:
                raw["unexpected"] = "nope"
            db.execute("UPDATE retrieval_index_generations SET identity_json=?", (json.dumps(raw),))
        elif kind == "two_active":
            db.execute("DROP INDEX retrieval_one_active")
            db.execute(
                "INSERT INTO retrieval_index_generations SELECT 'other',identity_json,state,"
                "created_at FROM retrieval_index_generations"
            )
        before = db.execute("SELECT * FROM retrieval_index_generations").fetchall()
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().state in {"not_initialized", "failed"}
    assert not (tmp_path / "retrieval-vectors").exists()
    with closing(sqlite3.connect(store.database_path)) as db:
        assert db.execute("SELECT * FROM retrieval_index_generations").fetchall() == before
    assert str(tmp_path) not in repr(handle.snapshot())


def test_low_disk_rejects_before_open_writer(tmp_path, monkeypatch):
    configured(tmp_path)
    monkeypatch.setattr(
        runtime.shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(1000, 999, 1)
    )
    monkeypatch.setattr(
        runtime.RawVectorStore,
        "open_writer_existing",
        lambda *a, **k: pytest.fail("opened on low disk"),
    )
    handle = ExistingRetrievalRuntime(tmp_path)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_low_disk"


@pytest.mark.parametrize("kind", ["root", "database", "vectors"])
def test_symlink_rejected(tmp_path, kind):
    actual = tmp_path / "actual"
    actual.mkdir()
    configured(actual)
    selected = actual
    if kind == "root":
        selected = tmp_path / "link"
        selected.symlink_to(actual, target_is_directory=True)
    else:
        path = actual / ("one-memory.sqlite3" if kind == "database" else "retrieval-vectors")
        moved = tmp_path / "moved"
        path.rename(moved)
        path.symlink_to(moved, target_is_directory=kind == "vectors")
    handle = ExistingRetrievalRuntime(selected, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_unsafe_path"


def test_local_existing_integration_indexes_only_after_explicit_start(tmp_path):
    store, evidence, gen = configured(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    SourceGrantStore(store.database_path, home=tmp_path).grant(
        user_id="local", source_id="codex", root=source, candidate_kind=RootCandidateKind.DEFAULT
    )
    row = put(evidence, "before token=private after")

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert store.status(gen)["ready"] == 0
        assert await handle.start()
        try:
            await until(lambda: store.status(gen)["ready"] == 1)
            assert len(store.active_chunks(gen)) == 2
            assert handle.snapshot().generation_id == gen
            with pytest.raises(RuntimeError, match="already_started"):
                await handle.start()
        finally:
            await handle.stop()
        assert handle.snapshot().state == "stopped"
        assert not handle.snapshot().supervisor.thread_alive
        assert evidence.get(row.evidence_id).verbatim == row.verbatim

    asyncio.run(run())


def fake_resources(tmp_path, monkeypatch, *, fail_worker=False, block_open=False, version=2):
    configured(tmp_path, version=version)
    entered, release, exited, opened = (threading.Event() for _ in range(4))
    events = []

    class Vectors:
        def close(self):
            events.append("close")

    def open_vectors(*args, **kwargs):
        opened.set()
        if block_open:
            assert release.wait(5)
        return Vectors()

    class Worker:
        def __init__(self, *args, **kwargs):
            if fail_worker:
                raise RuntimeError("SECRET failure")

        def run_once(self, *, cancel):
            entered.set()
            while not cancel.is_set():
                time.sleep(0.001)
            events.append("cancel")
            assert release.wait(5)
            events.append("exit")
            exited.set()
            return IndexWorkResult("cancelled")

    monkeypatch.setattr(runtime.RawVectorStore, "open_writer_existing", open_vectors)
    monkeypatch.setattr(runtime, "RetrievalIndexWorker", Worker)
    return entered, release, exited, opened, events


def test_partial_start_failure_closes_owned_vectors(tmp_path, monkeypatch):
    *_, events = fake_resources(tmp_path, monkeypatch, fail_worker=True)
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert events == ["close"]
    assert handle.snapshot().error_code == "retrieval_runtime_start_failed"
    assert "SECRET" not in repr(handle.snapshot())


def test_cancelled_stop_drains_before_close(tmp_path, monkeypatch):
    entered, release, exited, _, events = fake_resources(tmp_path, monkeypatch)

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert await handle.start()
        await until(entered.is_set)
        task = asyncio.create_task(handle.stop())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await until(lambda: "cancel" in events)
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done() and "close" not in events
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert exited.is_set() and events == ["cancel", "exit", "close"]
        await handle.stop()
        assert events.count("close") == 1

    asyncio.run(run())


def test_cancelled_start_drains_open_and_cleans_resources(tmp_path, monkeypatch):
    _, release, _, opened, events = fake_resources(
        tmp_path, monkeypatch, fail_worker=True, block_open=True
    )

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        task = asyncio.create_task(handle.start())
        await until(opened.is_set)
        task.cancel()
        try:
            await asyncio.sleep(0.03)
            assert not task.done() and not events
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert events == ["close"]

    asyncio.run(run())


def test_cancelled_successful_open_does_not_start_worker_and_closes_once(tmp_path, monkeypatch):
    entered, release, _, opened, events = fake_resources(tmp_path, monkeypatch, block_open=True)

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        starting = asyncio.create_task(handle.start())
        await until(opened.is_set)
        starting.cancel()
        await asyncio.sleep(0.02)
        starting.cancel()
        try:
            await asyncio.sleep(0.02)
            assert not starting.done() and not events and not entered.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await starting
        assert events == ["close"] and not entered.is_set()
        assert handle.snapshot().state == "stopped"
        await handle.stop()
        assert events == ["close"]

    asyncio.run(run())


def test_old_identity_one_recovers_without_generation_upgrade(tmp_path, monkeypatch):
    entered, release, _, _, events = fake_resources(tmp_path, monkeypatch, version=1)
    path = tmp_path / "one-memory.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        before = db.execute("SELECT * FROM retrieval_index_generations").fetchall()

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert await handle.start()
        await until(entered.is_set)
        release.set()
        await handle.stop()

    asyncio.run(run())
    assert events == ["cancel", "exit", "close"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT * FROM retrieval_index_generations").fetchall() == before


def test_missing_identity_fields_fail_even_when_dataclass_defaults_match(tmp_path):
    store, _, _ = configured(tmp_path, version=1, collection=False)
    with closing(sqlite3.connect(store.database_path)) as db, db:
        raw = json.loads(
            db.execute("SELECT identity_json FROM retrieval_index_generations").fetchone()[0]
        )
        raw.pop("normalizer_version")
        db.execute("UPDATE retrieval_index_generations SET identity_json=?", (json.dumps(raw),))
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_invalid_index"


def test_valid_hash_but_foreign_encoder_never_opens_vectors(tmp_path, monkeypatch):
    from dataclasses import asdict

    from one_memory.retrieval.index_store import EncoderIdentity, digest

    store, _, _ = configured(tmp_path)
    with closing(sqlite3.connect(store.database_path)) as db, db:
        raw = json.loads(
            db.execute("SELECT identity_json FROM retrieval_index_generations").fetchone()[0]
        )
        raw["encoder_digest"] = "0" * 64
        identity = EncoderIdentity(**raw)
        store_id = db.execute("SELECT data_store_id FROM retrieval_index_state").fetchone()[0]
        db.execute(
            "UPDATE retrieval_index_generations SET generation_id=?,identity_json=?",
            (digest([store_id, asdict(identity)]), json.dumps(raw)),
        )
    monkeypatch.setattr(
        runtime.RawVectorStore,
        "open_writer_existing",
        lambda *a, **k: pytest.fail("foreign encoder opened"),
    )
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_encoder_mismatch"


def test_concurrent_stop_waits_start_and_runs_cleanup_once(tmp_path, monkeypatch):
    entered, release, _, opened, events = fake_resources(tmp_path, monkeypatch, block_open=True)

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        starting = asyncio.create_task(handle.start())
        await until(opened.is_set)
        stops = [asyncio.create_task(handle.stop()), asyncio.create_task(handle.stop())]
        try:
            await asyncio.sleep(0.03)
            assert all(not task.done() for task in stops)
        finally:
            release.set()
            await asyncio.gather(*stops)
            assert not await starting
        assert events == ["close"] and not entered.is_set()

    asyncio.run(run())


def test_stop_before_start_never_opens_resources(tmp_path):
    handle = ExistingRetrievalRuntime(tmp_path)
    asyncio.run(handle.stop())
    with pytest.raises(RuntimeError, match="already_started"):
        asyncio.run(handle.start())
    assert not list(tmp_path.iterdir())


def test_missing_collection_in_existing_chroma_does_not_create_collection(tmp_path):
    store, _, gen = configured(tmp_path)
    with closing(sqlite3.connect(tmp_path / "retrieval-vectors" / "chroma.sqlite3")) as db, db:
        db.execute("UPDATE collections SET name='foreign_collection'")
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().state == "not_initialized"
    with closing(sqlite3.connect(tmp_path / "retrieval-vectors" / "chroma.sqlite3")) as db:
        assert db.execute("SELECT name FROM collections").fetchall() == [("foreign_collection",)]


@pytest.mark.parametrize("target", ["root", "database", "vectors", "vector_database"])
def test_group_writable_paths_rejected_without_open(tmp_path, monkeypatch, target):
    configured(tmp_path)
    paths = {
        "root": tmp_path,
        "database": tmp_path / "one-memory.sqlite3",
        "vectors": tmp_path / "retrieval-vectors",
        "vector_database": tmp_path / "retrieval-vectors/chroma.sqlite3",
    }
    path = paths[target]
    original_mode = path.stat().st_mode & 0o777
    path.chmod(original_mode | 0o020)
    monkeypatch.setattr(
        runtime.RawVectorStore,
        "open_writer_existing",
        lambda *a, **k: pytest.fail("unsafe resource opened"),
    )
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    try:
        assert not asyncio.run(handle.start())
        assert handle.snapshot().error_code == "retrieval_runtime_unsafe_path"
    finally:
        path.chmod(original_mode)


def test_foreign_uid_and_windows_are_failclosed(tmp_path, monkeypatch):
    configured(tmp_path)
    uid = os.getuid()
    monkeypatch.setattr(runtime.os, "getuid", lambda: uid + 1)
    handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_unsafe_path"
    monkeypatch.setattr(runtime.os, "getuid", lambda: uid)
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    windows = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
    assert not asyncio.run(windows.start())
    assert windows.snapshot().error_code == "retrieval_runtime_platform_unsupported"


@pytest.mark.parametrize("target", ["root", "database"])
def test_identical_store_id_copy_replacement_during_open_is_rejected(tmp_path, monkeypatch, target):
    root = tmp_path / "profile"
    root.mkdir()
    configured(root)
    closed = []

    class Vectors:
        def close(self):
            closed.append(True)

    def replace_path(*args, **kwargs):
        if target == "database":
            path = root / "one-memory.sqlite3"
            copy = root / "replacement.sqlite3"
            shutil.copy2(path, copy)
            os.replace(copy, path)
        else:
            old = tmp_path / "old-profile"
            root.rename(old)
            shutil.copytree(old, root)
        return Vectors()

    monkeypatch.setattr(runtime.RawVectorStore, "open_writer_existing", replace_path)
    handle = ExistingRetrievalRuntime(root, minimum_free_bytes=0)
    assert not asyncio.run(handle.start())
    assert handle.snapshot().error_code == "retrieval_runtime_index_changed"
    assert closed == [True]


def test_failed_drain_keeps_live_worker_vectors_open_and_raises_fixed_code(tmp_path, monkeypatch):
    entered, release, _, _, events = fake_resources(tmp_path, monkeypatch)
    actual = runtime.RetrievalIndexSupervisor
    instances = []

    class BadStop(actual):
        def __init__(self, worker, **kwargs):
            super().__init__(worker, **kwargs)
            instances.append(self)

        async def stop(self):
            raise RuntimeError("SECRET_STOP_ERROR")

    monkeypatch.setattr(runtime, "RetrievalIndexSupervisor", BadStop)

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert await handle.start()
        await until(entered.is_set)
        try:
            with pytest.raises(RuntimeError, match="^retrieval_runtime_stop_failed$"):
                await handle.stop()
            assert "close" not in events
            assert handle.snapshot().supervisor.thread_alive
            assert handle.snapshot().state == "failed"
            assert "SECRET" not in repr(handle.snapshot())
        finally:
            release.set()
            await actual.stop(instances[0])
            # Test alone owns cleanup of the intentionally broken supervisor.
            handle._vectors.close()

    asyncio.run(run())


def test_stop_error_after_confirmed_exit_still_closes_vectors(tmp_path, monkeypatch):
    entered, release, _, _, events = fake_resources(tmp_path, monkeypatch)
    actual = runtime.RetrievalIndexSupervisor

    class BadStop(actual):
        async def stop(self):
            await super().stop()
            raise RuntimeError("SECRET_AFTER_EXIT")

    monkeypatch.setattr(runtime, "RetrievalIndexSupervisor", BadStop)

    async def run():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert await handle.start()
        await until(entered.is_set)
        release.set()
        with pytest.raises(RuntimeError, match="^retrieval_runtime_stop_failed$"):
            await handle.stop()
        assert events == ["cancel", "exit", "close"]
        assert not handle.snapshot().supervisor.thread_alive

    asyncio.run(run())
