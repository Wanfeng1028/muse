"""Atomic snapshot publication plus frozen manifest, path, mode, and per-file checksum guards."""

import hashlib
import json
import multiprocessing
import os
import shutil
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
import zstandard

from one_memory.diagnostic_log import configure_diagnostics, reset_diagnostics
from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
    SourceAccessErrorCode,
)
from one_memory.imports.readers import RawRecord, read_jsonl, read_zstd_jsonl
from one_memory.imports.snapshots import (
    SnapshotError,
    SnapshotErrorCode,
    SnapshotLimits,
    SnapshotMode,
    SourceSnapshotStore,
)


def _sqlite_writer_process(path, pipe):
    connection = sqlite3.connect(path, autocommit=True)
    try:
        while (statement := pipe.recv()) is not None:
            try:
                pipe.send(connection.execute(statement).fetchall())
            except Exception as error:
                pipe.send(str(error))
    finally:
        connection.close()
        pipe.close()


@contextmanager
def host_sqlite_writer(path):
    """A native host writer in another process, without shared SQLite VFS state."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_sqlite_writer_process, args=(path, child))
    process.start()
    child.close()

    def execute(statement):
        parent.send(statement)
        assert parent.poll(10), "Native SQLite fixture writer did not respond"
        result = parent.recv()
        assert isinstance(result, list), result
        return result

    try:
        yield execute
    finally:
        parent.send(None)
        parent.close()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        assert process.exitcode == 0


def closed_wal_database(path, *, payload_bytes=0):
    connection = sqlite3.connect(path, autocommit=True)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body BLOB)")
        connection.executemany(
            "INSERT INTO messages VALUES (?,?)",
            [(1, b"checkpointed-user"), (2, b"checkpointed-assistant")],
        )
        if payload_bytes:
            connection.execute("INSERT INTO messages VALUES (3, zeroblob(?))", (payload_bytes,))
    finally:
        connection.close()
    assert path.read_bytes()[18:20] == b"\x02\x02"
    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def fixture_fingerprints(root):
    result = {}
    for path in root.rglob("*"):
        if path.is_file():
            details = path.stat()
            result[path.relative_to(root).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                details.st_dev,
                details.st_ino,
                details.st_size,
                details.st_mtime_ns,
                details.st_ctime_ns,
                details.st_mode,
            )
    return result


@pytest.fixture(autouse=True)
def writable_fixture_cleanup(tmp_path):
    yield
    _remove_owned_fixture(tmp_path)


def _remove_owned_fixture(root):
    # Never traverse a link or reset a linked inode outside this test's tree.
    # Remove our own artifacts now, not through global pytest garbage collection.
    assert not root.is_symlink()
    for directory, _, files, descriptor in os.fwalk(root, follow_symlinks=False):
        # fwalk opens the directory without following linked directories; using
        # its fd avoids the unsupported chmod(path, follow_symlinks=False) API.
        os.fchmod(descriptor, 0o700)
        for filename in files:
            path = Path(directory) / filename
            details = path.lstat()
            if stat.S_ISREG(details.st_mode) and details.st_nlink == 1:
                # lstat excludes symlinks and nlink==1 excludes the hard-link
                # sentinel used by the safety test, so chmod cannot alter a
                # fixture outside this owned tree.
                os.chmod(path, 0o600)
    shutil.rmtree(root)


def test_fixture_teardown_removes_readonly_artifacts_without_following_links(tmp_path):
    owned = tmp_path / "owned-fixture"
    snapshot = owned / "core/private-job/job-123/files"
    snapshot.mkdir(parents=True)
    (snapshot / "a.jsonl").write_bytes(b"fixture\n")
    (snapshot / "a.jsonl").chmod(0o400)
    outside = tmp_path / "outside-fixture"
    outside.mkdir()
    sentinel = outside / "untouched.jsonl"
    sentinel.write_bytes(b"untouched\n")
    sentinel.chmod(0o400)
    (snapshot / "linked.jsonl").symlink_to(sentinel)
    (snapshot / "linked-directory").symlink_to(outside, target_is_directory=True)
    (snapshot / "hardlinked.jsonl").hardlink_to(sentinel)
    snapshot.chmod(0o500)
    outside.chmod(0o500)

    _remove_owned_fixture(owned)

    assert not owned.exists()
    assert sentinel.read_bytes() == b"untouched\n"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o400
    assert stat.S_IMODE(outside.stat().st_mode) == 0o500


def setup_snapshot(tmp_path, **limits):
    root = tmp_path / "source"
    root.mkdir()
    jobs = tmp_path / "core" / "private-job"
    jobs.mkdir(parents=True, mode=0o700)
    grant = AuthorizedSourceRoot.grant(
        source_id="fixture",
        root=root,
        user_confirmed=True,
        home=tmp_path / "other-home",
    )
    store = SourceSnapshotStore(jobs, limits=SnapshotLimits(min_free_bytes=0, **limits))
    intent = {
        "snapshot_id": "job-123",
        "source_id": "fixture",
        "grant": grant,
        "selection_id": "adapter-files:v1",
        "suffix_modes": {".jsonl": SnapshotMode.BYTE_EXTENT},
    }
    return root, jobs, store, intent


def capture(store, intent, **kwargs):
    return store.capture(**intent, file_predicate=lambda _: True, **kwargs)


def assert_no_artifact(jobs):
    entries = list(jobs.iterdir())
    assert all(path.name.endswith(".attempt.json") for path in entries), (
        "Failed capture left a committed or uncommitted payload copy"
    )
    assert all(path.is_file() and path.stat().st_size < 16_384 for path in entries)


def test_byte_extent_reopens_independently_and_excludes_appends_and_new_files(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    relative = Path("projects/work/agent-transcripts/session.jsonl")
    original = root / relative
    original.parent.mkdir(parents=True)
    before = b'{"id":1}\n{"id":'
    original.write_bytes(before)
    original_file = intent["grant"].authorize_file(relative)

    capture(store, intent)
    with original.open("ab") as output:
        output.write(b"2}\n")
    (root / "new.jsonl").write_bytes(b'{"id":3}\n')
    reopened = store.reopen(**intent)
    frozen = reopened.grant.authorize_file(relative)

    assert frozen.safe_id == original_file.safe_id
    assert frozen.file_identity != original_file.file_identity
    assert frozen.path.read_bytes() == before
    assert [event.value for event in read_jsonl(frozen) if isinstance(event, RawRecord)] == [
        {"id": 1}
    ]
    assert [item.relative_path for item in reopened.manifest.files] == [relative.as_posix()]
    assert reopened.manifest.files[0].source_file_identity == original_file.file_identity
    assert reopened.manifest.files[0].source_size == len(before)
    assert reopened.manifest.intent.root_identity == intent["grant"].root_identity
    assert stat.S_IMODE(frozen.path.stat().st_mode) == 0o400
    assert stat.S_IMODE(reopened.root.stat().st_mode) == 0o500
    assert reopened.root.is_relative_to(jobs)


def test_large_extent_copy_rechecks_authority_per_block_not_per_small_chunk(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "session.jsonl").write_bytes(b'{"id":1}\n' * (16 * 1024 * 1024 // 9))
    calls = []
    intent["grant"] = replace(intent["grant"], access_check=lambda: calls.append(1))

    snapshot = capture(store, intent)

    assert snapshot.manifest.files[0].source_size >= 16 * 1024 * 1024 - 9
    assert calls, "Copy must still recheck authority while it runs"
    assert len(calls) <= 64, f"{len(calls)} authority rechecks for 16 MiB"


def test_snapshot_logs_discovery_and_copy_metrics_without_paths(tmp_path, monkeypatch):
    root, _, store, intent = setup_snapshot(tmp_path)
    private_marker = "private-user-path-marker"
    source = root / private_marker / "session.jsonl"
    source.parent.mkdir()
    source.write_text('{"id":1}\n')
    monkeypatch.setenv("ONE_MEMORY_DIAGNOSTICS", "1")
    receipt = configure_diagnostics(tmp_path / "diagnostics")
    try:
        capture(store, intent)
    finally:
        reset_diagnostics()
    written = receipt.path.read_text()
    events = [json.loads(line) for line in written.splitlines()]
    assert [event["event"] for event in events] == [
        "import.discovery.completed",
        "import.snapshot.completed",
    ]
    assert events[0]["details"]["file_count"] == 1
    assert events[1]["details"]["copied_bytes"] == len(source.read_bytes())
    assert private_marker not in written


def test_zstd_extent_is_copied_without_reencoding_or_reading_later_frames(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".zstd": SnapshotMode.BYTE_EXTENT}
    compressor = zstandard.ZstdCompressor(write_checksum=True)
    before = compressor.compress(b'{"id":1}\n')
    source = root / "session.jsonl.zstd"
    source.write_bytes(before)

    snapshot = capture(store, intent)
    with source.open("ab") as output:
        output.write(compressor.compress(b'{"id":2}\n'))
    frozen = snapshot.grant.authorize_file(Path("session.jsonl.zstd"))

    assert frozen.path.read_bytes() == before
    assert [event.value for event in read_zstd_jsonl(frozen) if isinstance(event, RawRecord)] == [
        {"id": 1}
    ]


def test_all_byte_extents_are_chosen_before_copying_the_first_file(tmp_path, monkeypatch):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b'{"id":1}\n')
    second = root / "b.jsonl"
    second.write_bytes(b'{"id":2}\n')
    original_open = AuthorizedSourceFile.open_binary
    appended = False

    def append_on_first_open(source_file):
        nonlocal appended
        stream = original_open(source_file)
        if source_file.root == root and not appended:
            appended = True
            with second.open("ab") as output:
                output.write(b'{"id":3}\n')
        return stream

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", append_on_first_open)
    snapshot = capture(store, intent)

    assert appended
    assert (snapshot.root / "b.jsonl").read_bytes() == b'{"id":2}\n'


def test_sqlite_backup_includes_committed_wal_not_uncommitted_or_later_rows(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "chats" / "session" / "store.db"
    database.parent.mkdir(parents=True)
    with host_sqlite_writer(database) as execute:
        execute("PRAGMA journal_mode=WAL")
        execute("PRAGMA wal_autocheckpoint=0")
        execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT)")
        execute("PRAGMA wal_checkpoint(TRUNCATE)")
        execute("INSERT INTO messages VALUES (1, 'committed-in-wal')")
        wal = database.with_name("store.db-wal")
        assert wal.stat().st_size > 32
        shm = database.with_name("store.db-shm")
        execute("BEGIN")
        execute("INSERT INTO messages VALUES (2, 'uncommitted')")
        before_main, before_wal, before_shm = (
            database.read_bytes(),
            wal.read_bytes(),
            shm.read_bytes(),
        )

        snapshot = capture(store, intent)

        assert database.read_bytes() == before_main
        assert wal.read_bytes() == before_wal
        assert shm.read_bytes() == before_shm
        execute("ROLLBACK")
        execute("INSERT INTO messages VALUES (3, 'later')")
        copied = snapshot.root / "chats/session/store.db"
        with sqlite3.connect(f"{copied.as_uri()}?mode=ro&immutable=1", uri=True) as reader:
            assert reader.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert reader.execute("SELECT * FROM messages").fetchall() == [(1, "committed-in-wal")]
        assert [item.relative_path for item in snapshot.manifest.files] == [
            "chats/session/store.db"
        ]
        assert not list(snapshot.root.rglob("*-wal"))
        assert not list(snapshot.root.rglob("*-shm"))


def test_selector_reads_no_unselected_bodies_and_keeps_only_adapter_metadata(tmp_path, monkeypatch):
    root, _, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"][".json"] = SnapshotMode.BYTE_EXTENT
    (root / "history.jsonl").write_bytes(b'{"id":1}\n')
    (root / "history.meta.json").write_bytes(b'{"cwd":"/fixture"}')
    (root / "credentials.json").write_bytes(b"must-not-open")
    (root / "configuration.toml").write_bytes(b"must-not-open")
    (root / "archive.zip").write_bytes(b"must-not-open")
    opened = []
    original_open = AuthorizedSourceFile.open_binary

    def observe(source_file):
        if source_file.root == root:
            opened.append(source_file.relative_path.name)
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observe)
    snapshot = store.capture(
        **intent,
        file_predicate=lambda item: (
            item.relative_path.name in {"history.jsonl", "history.meta.json"}
        ),
    )

    assert set(opened) == {"history.jsonl", "history.meta.json"}
    assert {item.relative_path for item in snapshot.manifest.files} == set(opened)


@pytest.mark.parametrize("suffix", [".zip", ".pem", ".toml", ".unknown"])
def test_unknown_file_modes_and_config_formats_are_not_generic_byte_copies(tmp_path, suffix):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {suffix: SnapshotMode.BYTE_EXTENT}
    (root / f"selected{suffix}").write_bytes(b"not-a-transcript")
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.UNSUPPORTED_MODE
    assert_no_artifact(jobs)


def test_unknown_enum_mode_is_rejected(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "history.jsonl").write_bytes(b"hello\n")
    intent["suffix_modes"] = {".jsonl": "auto-detect"}
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.UNSUPPORTED_MODE
    assert_no_artifact(jobs)


@pytest.mark.parametrize("kind", ["file", "directory", "root", "wal"])
def test_symlinks_are_rejected_not_silently_omitted(tmp_path, kind):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    target = tmp_path / "other"
    target.mkdir()
    (target / "history.jsonl").write_bytes(b"outside\n")
    if kind == "file":
        (root / "history.jsonl").symlink_to(target / "history.jsonl")
    elif kind == "directory":
        (root / "nested").symlink_to(target, target_is_directory=True)
    elif kind == "root":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        intent["grant"] = AuthorizedSourceRoot.grant(
            source_id="fixture", root=alias, user_confirmed=True, home=tmp_path / "elsewhere"
        )
    else:
        database = root / "store.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE data (value TEXT)")
        (root / "store.db-wal").symlink_to(target / "history.jsonl")
        intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    with pytest.raises(SourceAccessError) as caught:
        capture(store, intent)
    assert caught.value.code == SourceAccessErrorCode.SYMLINK_NOT_ALLOWED
    assert_no_artifact(jobs)


@pytest.mark.parametrize(
    ("limits", "code"),
    [
        ({"max_files": 1}, SnapshotErrorCode.FILE_LIMIT),
        ({"max_file_bytes": 3}, SnapshotErrorCode.FILE_LIMIT),
        ({"max_total_bytes": 6}, SnapshotErrorCode.TOTAL_LIMIT),
        ({"max_disk_bytes": 6}, SnapshotErrorCode.DISK_BUDGET),
        ({"max_scan_entries": 1}, SnapshotErrorCode.SCAN_LIMIT),
    ],
)
def test_limits_reject_entire_capture_instead_of_committing_partial_results(tmp_path, limits, code):
    root, jobs, store, intent = setup_snapshot(tmp_path, **limits)
    (root / "a.jsonl").write_bytes(b"1234")
    (root / "b.jsonl").write_bytes(b"5678")
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == code
    assert_no_artifact(jobs)


def test_disk_reserve_uses_actual_free_space(tmp_path):
    root, jobs, _, intent = setup_snapshot(tmp_path)
    (root / "session.jsonl").write_bytes(b"1234")
    store = SourceSnapshotStore(jobs, limits=SnapshotLimits(min_free_bytes=2**63 - 1))
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.DISK_BUDGET
    assert_no_artifact(jobs)


def test_sqlite_limits_count_wal_pages_not_just_main_database_size(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path, max_file_bytes=32 * 1024)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    with host_sqlite_writer(database) as execute:
        execute("PRAGMA journal_mode=WAL")
        execute("PRAGMA wal_autocheckpoint=0")
        execute("CREATE TABLE messages (body BLOB)")
        execute("INSERT INTO messages VALUES (zeroblob(131072))")
        assert database.stat().st_size < 32 * 1024
        with pytest.raises(SnapshotError) as caught:
            capture(store, intent)
        assert caught.value.code == SnapshotErrorCode.FILE_LIMIT
        assert_no_artifact(jobs)


def test_cancel_during_copy_cleans_partial_bytes_without_manifest(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "session.jsonl").write_bytes(b"x" * (1024 * 1024))
    saw_partial = False

    def cancelled():
        nonlocal saw_partial
        saw_partial = any(path.stat().st_size > 0 for path in jobs.rglob("session.jsonl"))
        return saw_partial

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=cancelled)
    assert caught.value.code == SnapshotErrorCode.CANCELLED
    assert saw_partial, "Cancellation must exercise an actual partially copied file"
    assert_no_artifact(jobs)


@pytest.mark.parametrize("change", ["replace-root", "revoke", "symlink-parent"])
def test_mid_copy_authority_changes_stop_before_further_io_and_clean_up(tmp_path, change):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    folder = root / "nested"
    folder.mkdir()
    (folder / "session.jsonl").write_bytes(b"x" * (1024 * 1024))
    changed = False

    def permission_check():
        nonlocal changed
        if changed and change == "revoke":
            raise SourceAccessError(SourceAccessErrorCode.SOURCE_PERMISSION_CHANGED)

    def mutate_after_first_write():
        nonlocal changed
        if not changed and any(path.stat().st_size for path in jobs.rglob("session.jsonl")):
            changed = True
            if change == "replace-root":
                root.rename(root.with_name("previous-source"))
                root.mkdir()
            elif change == "symlink-parent":
                previous = root / "previous-nested"
                folder.rename(previous)
                folder.symlink_to(previous, target_is_directory=True)
        return False

    intent["grant"] = replace(intent["grant"], access_check=permission_check)
    with pytest.raises(SourceAccessError):
        capture(store, intent, cancelled=mutate_after_first_write)
    assert changed
    assert_no_artifact(jobs)


def test_exception_during_copy_never_publishes_and_cleans_staging(tmp_path, monkeypatch):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"complete-first-file\n")
    (root / "b.jsonl").write_bytes(b"fail-second-file\n")
    original_open = AuthorizedSourceFile.open_binary

    def interrupted(source_file):
        if source_file.root == root and source_file.relative_path.name == "b.jsonl":
            raise InterruptedError("test interruption")
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", interrupted)
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.IO_ERROR
    assert_no_artifact(jobs)


@pytest.mark.parametrize(
    ("tamper", "code"),
    [
        ("checksum", SnapshotErrorCode.CHECKSUM_MISMATCH),
        ("write-bit", SnapshotErrorCode.NOT_READ_ONLY),
        ("extra-file", SnapshotErrorCode.INVALID_MANIFEST),
        ("manifest", SnapshotErrorCode.INVALID_MANIFEST),
        ("symlink", SnapshotErrorCode.NOT_READ_ONLY),
    ],
)
def test_reopen_validates_checksums_modes_paths_and_exact_file_set(tmp_path, tamper, code):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b'{"id":1}\n')
    snapshot = capture(store, intent)
    path = snapshot.root / "a.jsonl"
    if tamper == "checksum":
        path.chmod(0o600)
        path.write_bytes(b'{"id":9}\n')
        path.chmod(0o400)
    elif tamper == "write-bit":
        path.chmod(0o600)
    elif tamper == "extra-file":
        snapshot.root.chmod(0o700)
        (snapshot.root / "extra.jsonl").write_bytes(b"extra\n")
        (snapshot.root / "extra.jsonl").chmod(0o400)
        snapshot.root.chmod(0o500)
    elif tamper == "symlink":
        snapshot.root.chmod(0o700)
        path.unlink()
        path.symlink_to(root / "a.jsonl")
        snapshot.root.chmod(0o500)
    else:
        path = snapshot.root.parent / "manifest.json"
        path.chmod(0o600)
        manifest = json.loads(path.read_bytes())
        manifest["files"][0]["relative_path"] = "../a.jsonl"
        path.write_text(json.dumps(manifest))
        path.chmod(0o400)
    with pytest.raises(SnapshotError) as caught:
        store.reopen(**intent)
    assert caught.value.code == code


def test_same_intent_is_idempotent_without_rescanning_or_reading_source(tmp_path, monkeypatch):
    root, _, store, intent = setup_snapshot(tmp_path)
    source = root / "a.jsonl"
    source.write_bytes(b"first\n")
    snapshot = capture(store, intent)
    source.write_bytes(b"changed-after-capture\n")
    (root / "later.jsonl").write_bytes(b"later\n")
    original_open = AuthorizedSourceFile.open_binary

    def no_original_reads(source_file):
        assert source_file.root != root, "A committed intent reopened live history"
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", no_original_reads)
    repeated = capture(store, intent)
    assert repeated.root == snapshot.root
    assert repeated.manifest == snapshot.manifest
    assert (repeated.root / "a.jsonl").read_bytes() == b"first\n"


@pytest.mark.parametrize("field", ["selection_id", "source_id"])
def test_repeated_snapshot_id_with_different_intent_conflicts(tmp_path, field):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    capture(store, intent)
    changed = intent | {field: "different"}
    if field == "source_id":
        changed["grant"] = replace(intent["grant"], source_id="different")
    with pytest.raises(SnapshotError) as caught:
        capture(store, changed)
    assert caught.value.code == SnapshotErrorCode.CONFLICT


def test_reopen_and_retained_replay_grant_reject_root_replacement(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    snapshot = capture(store, intent)
    retained_file = snapshot.grant.authorize_file(Path("a.jsonl"))
    root.rename(root.with_name("old-source"))
    root.mkdir()
    with pytest.raises(SourceAccessError):
        store.reopen(**intent)
    with pytest.raises(SourceAccessError):
        retained_file.open_binary()


def test_destination_must_be_private_nonoverlapping_and_not_symlinked(tmp_path):
    root, jobs, _, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    jobs.chmod(0o755)
    with pytest.raises(SnapshotError):
        SourceSnapshotStore(jobs)
    jobs.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(jobs, target_is_directory=True)
    with pytest.raises((SnapshotError, SourceAccessError)):
        SourceSnapshotStore(alias)
    nested = root / "private-job"
    nested.mkdir(mode=0o700)
    with pytest.raises(SnapshotError):
        capture(SourceSnapshotStore(nested), intent)


def test_manifest_and_size_totals_cover_exact_stored_bytes(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "empty.jsonl").write_bytes(b"")
    (root / "a.jsonl").write_bytes(b"1234")
    snapshot = capture(store, intent)
    raw_manifest = (jobs / intent["snapshot_id"] / "manifest.json").read_bytes()
    assert json.loads(raw_manifest) == snapshot.manifest.model_dump(mode="json")
    assert snapshot.manifest.total_bytes == 4
    assert snapshot.disk_bytes == len(raw_manifest) + 4
    assert len(snapshot.manifest.files) == 2
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o400 for path in snapshot.root.iterdir())
    assert os.stat(root / "a.jsonl").st_ino != os.stat(snapshot.root / "a.jsonl").st_ino


def test_native_backup_pins_transaction_before_a_concurrent_wal_commit(tmp_path, monkeypatch):
    import one_memory.imports.snapshots as snapshots

    root, _, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    real_open = snapshots._open_sqlite_snapshot_source
    changed = False

    with host_sqlite_writer(database) as execute:
        execute("PRAGMA journal_mode=WAL")
        execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body BLOB)")
        execute("INSERT INTO messages VALUES (1, zeroblob(1048576))")

        @contextmanager
        def concurrent_writer(source_file, check):
            with real_open(source_file, check) as connection:

                def trace(sql):
                    nonlocal changed
                    if sql == "PRAGMA page_count" and not changed:
                        changed = True
                        execute("INSERT INTO messages VALUES (2, zeroblob(1048576))")

                connection.set_trace_callback(trace)
                yield connection

        monkeypatch.setattr(snapshots, "_open_sqlite_snapshot_source", concurrent_writer)
        snapshot = capture(store, intent)
        assert changed
        assert execute("SELECT count(*) FROM messages") == [(2,)]
        with sqlite3.connect(snapshot.root / "store.db") as copied:
            assert copied.execute("SELECT id, length(body) FROM messages").fetchall() == [
                (1, 1048576)
            ]


def test_sqlite_cancel_after_destination_has_bytes_never_commits_manifest(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    with sqlite3.connect(root / "store.db") as connection:
        connection.execute("CREATE TABLE messages (body BLOB)")
        connection.execute("INSERT INTO messages VALUES (zeroblob(4194304))")
    saw_partial = False

    def cancelled():
        nonlocal saw_partial
        saw_partial = any(path.stat().st_size > 0 for path in jobs.rglob("store.db"))
        return saw_partial

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=cancelled)
    assert caught.value.code == SnapshotErrorCode.CANCELLED
    assert saw_partial
    assert_no_artifact(jobs)


def test_closed_wal_without_sidecars_backs_up_identical_records_without_source_writes(
    tmp_path, monkeypatch
):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database)
    original = fixture_fingerprints(root)
    real_connect = sqlite3.connect
    opened = []

    def private_connections_only(path, *args, **kwargs):
        assert str(path) != str(database)
        assert not str(path).startswith(database.as_uri())
        opened.append(str(path))
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", private_connections_only)
    snapshot = capture(store, intent)

    assert any("immutable=1" in path for path in opened)
    assert fixture_fingerprints(root) == original
    copied = snapshot.root / "store.db"
    with real_connect(f"{copied.as_uri()}?mode=ro&immutable=1", uri=True) as reader:
        assert reader.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert reader.execute("SELECT * FROM messages ORDER BY id").fetchall() == [
            (1, b"checkpointed-user"),
            (2, b"checkpointed-assistant"),
        ]
    assert [item.relative_path for item in snapshot.manifest.files] == ["store.db"]
    assert snapshot.manifest.files[0].mode == SnapshotMode.SQLITE_BACKUP
    assert {path.name for path in snapshot.root.iterdir()} == {"store.db"}
    assert {path.name for path in jobs.iterdir()} == {intent["snapshot_id"]}
    assert store.reopen(**intent).manifest == snapshot.manifest


@pytest.mark.parametrize("when", ["copy", "private-open"])
def test_closed_wal_concurrent_native_wal_creation_aborts_and_requires_new_confirmation(
    tmp_path, monkeypatch, when
):
    import one_memory.imports.snapshots as snapshots

    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database, payload_bytes=1024 * 1024)
    real_copy = snapshots._copy_extent
    real_connect = sqlite3.connect
    changed = False
    after_writer = None

    with host_sqlite_writer(database) as execute:
        assert not (root / "store.db-wal").exists()

        def commit_in_wal():
            nonlocal changed, after_writer
            if not changed:
                changed = True
                execute("INSERT INTO messages VALUES (4, 'concurrent-committed-wal')")
                assert (root / "store.db-wal").stat().st_size > 32
                after_writer = fixture_fingerprints(root)

        def copy_then_commit(*args, **kwargs):
            digest = real_copy(*args, **kwargs)
            if when == "copy":
                commit_in_wal()
            return digest

        def open_then_commit(path, *args, **kwargs):
            if when == "private-open" and "immutable=1" in str(path):
                commit_in_wal()
            return real_connect(path, *args, **kwargs)

        monkeypatch.setattr(snapshots, "_copy_extent", copy_then_commit)
        monkeypatch.setattr(sqlite3, "connect", open_then_commit)
        with pytest.raises(SnapshotError) as caught:
            capture(store, intent)
        assert caught.value.code == SnapshotErrorCode.SOURCE_CHANGED
        assert changed, "The concurrent writer must actually commit before rejection"
        assert fixture_fingerprints(root) == after_writer
        assert_no_artifact(jobs)

        def must_not_rediscover(_):
            pytest.fail("Changed closed WAL was rediscovered without fresh confirmation")

        with pytest.raises(SnapshotError) as retry:
            store.capture(**intent, file_predicate=must_not_rediscover)
        assert retry.value.code == SnapshotErrorCode.INCOMPLETE


@pytest.mark.parametrize("change", ["append", "replace", "rewrite-restored-mtime"])
@pytest.mark.parametrize("when", ["before-copy", "after-copy", "private-open"])
def test_closed_wal_source_changes_never_publish(tmp_path, monkeypatch, change, when):
    import one_memory.imports.snapshots as snapshots

    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database, payload_bytes=1024 * 1024)
    before = database.read_bytes()
    metadata = database.stat()
    real_copy = snapshots._copy_extent
    real_connect = sqlite3.connect
    changed = False

    def mutate():
        nonlocal changed
        assert not changed
        changed = True
        if change == "append":
            with database.open("ab") as output:
                output.write(b"not-in-the-confirmed-extent")
        elif change == "replace":
            database.rename(root / "original")
            database.write_bytes(before)
        else:
            altered = before.replace(b"checkpointed-user", b"checkpointed-USER")
            assert altered != before and len(altered) == len(before)
            database.write_bytes(altered)
        os.utime(database, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))

    def copy_and_mutate(*args, **kwargs):
        if when == "before-copy":
            mutate()
        result = real_copy(*args, **kwargs)
        if when == "after-copy":
            mutate()
        return result

    def open_and_mutate(path, *args, **kwargs):
        if when == "private-open" and "immutable=1" in str(path):
            mutate()
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(snapshots, "_copy_extent", copy_and_mutate)
    monkeypatch.setattr(sqlite3, "connect", open_and_mutate)
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.SOURCE_CHANGED
    assert changed
    assert_no_artifact(jobs)


@pytest.mark.parametrize("sidecar", ["-wal", "-shm", "-journal"])
def test_closed_wal_with_only_one_sidecar_is_refused_unchanged(tmp_path, sidecar):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database)
    with host_sqlite_writer(database) as execute:
        execute("INSERT INTO messages VALUES (3, 'committed-only-in-wal')")
        main = database.read_bytes()
        wal = (root / "store.db-wal").read_bytes()
        shm = (root / "store.db-shm").read_bytes()
    database.write_bytes(main)
    (root / ("store.db" + sidecar)).write_bytes(wal if sidecar == "-wal" else shm)
    original = fixture_fingerprints(root)

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.SQLITE_UNAVAILABLE
    assert fixture_fingerprints(root) == original
    assert_no_artifact(jobs)


def test_a_live_sqlite_does_not_drop_the_transcripts_beside_it(tmp_path):
    """Cursor's open database must not throw away the transcripts next to it.

    One unavailable SQLite used to fail the whole snapshot. The job then
    stored nothing, and every retry of that same attempt was incomplete.
    """

    root, _jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {
        ".jsonl": SnapshotMode.BYTE_EXTENT,
        ".db": SnapshotMode.SQLITE_BACKUP,
    }
    (root / "session.jsonl").write_text('{"text":"hello"}\n')
    database = root / "store.db"
    closed_wal_database(database)
    with host_sqlite_writer(database) as execute:
        execute("INSERT INTO messages VALUES (3, 'committed-only-in-wal')")
        main = database.read_bytes()
        wal = (root / "store.db-wal").read_bytes()
    database.write_bytes(main)
    (root / "store.db-wal").write_bytes(wal)
    (root / "store.db-shm").unlink(missing_ok=True)

    snapshot = capture(store, intent)

    assert [item.relative_path for item in snapshot.manifest.files] == ["session.jsonl"]


@pytest.mark.parametrize("phase", ["staging", "backup"])
def test_closed_wal_cancellation_cleans_staging_and_destination(tmp_path, phase):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database, payload_bytes=4 * 1024 * 1024)
    original = fixture_fingerprints(root)
    saw_partial = False

    def cancel_after_bytes():
        nonlocal saw_partial
        for path in jobs.rglob("*"):
            wanted = (
                path.name == "store.db" if phase == "backup" else path.suffix == ".sqlite-stage"
            )
            if wanted and path.is_file() and path.stat().st_size > 0:
                saw_partial = True
                return True
        return False

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=cancel_after_bytes)
    assert caught.value.code == SnapshotErrorCode.CANCELLED
    assert saw_partial
    assert fixture_fingerprints(root) == original
    assert_no_artifact(jobs)


@pytest.mark.parametrize("enough_space", [False, True])
def test_closed_wal_disk_budget_counts_staging_plus_backup_not_double_payload(
    tmp_path, enough_space
):
    root, jobs, _, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database, payload_bytes=1024 * 1024)
    size = database.stat().st_size
    original = fixture_fingerprints(root)
    store = SourceSnapshotStore(
        jobs,
        limits=SnapshotLimits(
            max_file_bytes=size,
            max_total_bytes=size,
            max_disk_bytes=size * (2 if enough_space else 1) + 8192,
            min_free_bytes=0,
        ),
    )
    if enough_space:
        snapshot = capture(store, intent)
        assert snapshot.manifest.total_bytes == size
        assert snapshot.disk_bytes < size + 8192
        assert {path.name for path in snapshot.root.iterdir()} == {"store.db"}
    else:
        with pytest.raises(SnapshotError) as caught:
            capture(store, intent)
        assert caught.value.code == SnapshotErrorCode.DISK_BUDGET
        assert_no_artifact(jobs)
    assert fixture_fingerprints(root) == original


def test_closed_wal_native_integrity_failure_is_not_a_successful_empty_snapshot(
    tmp_path, monkeypatch
):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    database = root / "store.db"
    closed_wal_database(database)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        connection.execute("CREATE TABLE checked (value INTEGER CHECK (value > 0))")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("INSERT INTO checked VALUES (-1)")
    finally:
        connection.close()
    original = fixture_fingerprints(root)
    real_connect = sqlite3.connect
    statements = []

    def traced_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.SQLITE_UNAVAILABLE
    assert "PRAGMA integrity_check" in statements, "Exercise SQLite's actual integrity validator"
    assert fixture_fingerprints(root) == original
    assert_no_artifact(jobs)


def test_in_process_writable_wal_mapping_is_rejected_without_source_mutation(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    intent["suffix_modes"] = {".db": SnapshotMode.SQLITE_BACKUP}
    connection = sqlite3.connect(root / "store.db")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE data (value TEXT)")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("INSERT INTO data VALUES ('in-wal')")
        connection.commit()
        original = {path.name: path.read_bytes() for path in root.iterdir()}
        with pytest.raises(SnapshotError) as caught:
            capture(store, intent)
        assert caught.value.code == SnapshotErrorCode.SQLITE_UNAVAILABLE
        assert {path.name: path.read_bytes() for path in root.iterdir()} == original
        assert_no_artifact(jobs)
    finally:
        connection.close()


def test_manifest_itself_must_fit_disk_budget_and_cleanup_sealed_files(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path, max_disk_bytes=32)
    (root / "a.jsonl").write_bytes(b"first\n")
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.DISK_BUDGET
    assert_no_artifact(jobs)


def test_failed_atomic_publication_cleans_files_and_manifest(tmp_path, monkeypatch):
    import one_memory.imports.snapshots as snapshots

    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    saw_sealed = False

    def fail_rename(source, destination):
        nonlocal saw_sealed
        saw_sealed = stat.S_IMODE((source / "files/a.jsonl").stat().st_mode) == 0o400
        assert (source / "manifest.json").is_file()
        raise OSError("synthetic rename failure")

    monkeypatch.setattr(snapshots.os, "rename", fail_rename)
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.IO_ERROR
    assert saw_sealed
    assert_no_artifact(jobs)


def test_concurrent_same_intent_has_one_immutable_winner(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    barrier = Barrier(2)

    def competing_capture():
        barrier.wait(timeout=5)
        try:
            return capture(store, intent)
        except SnapshotError as error:
            assert error.code == SnapshotErrorCode.INCOMPLETE
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(competing_capture) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    committed = [result for result in results if result is not None]
    assert committed
    replay = capture(store, intent)
    assert all(result.manifest == replay.manifest for result in committed)
    assert all(result.root == replay.root for result in committed)
    assert {path.name for path in jobs.iterdir()} == {intent["snapshot_id"]}


@pytest.mark.parametrize("change", ["truncate", "replace-file"])
def test_mid_copy_file_changes_fail_without_publishing(tmp_path, change):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    source = root / "a.jsonl"
    source.write_bytes(b"x" * (1024 * 1024))
    changed = False

    def mutate_after_write():
        nonlocal changed
        if not changed and any(path.stat().st_size for path in jobs.rglob("a.jsonl")):
            changed = True
            if change == "replace-file":
                source.rename(root / "original")
            source.write_bytes(b"replacement\n")
        return False

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=mutate_after_write)
    assert caught.value.code == SnapshotErrorCode.SOURCE_CHANGED
    assert changed
    assert_no_artifact(jobs)


def test_selected_nonregular_file_does_not_block_open_or_get_skipped(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    os.mkfifo(root / "pipe.jsonl")
    with pytest.raises(SourceAccessError) as caught:
        capture(store, intent)
    assert caught.value.code == SourceAccessErrorCode.NOT_REGULAR_FILE
    assert_no_artifact(jobs)


def test_identity_and_grant_changes_between_file_open_and_sink_creation_stop_writes(
    tmp_path, monkeypatch
):
    import one_memory.imports.snapshots as snapshots

    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    original_open = AuthorizedSourceFile.open_binary
    created = []
    real_create = snapshots._create_file

    def replace_root_after_open(source_file):
        stream = original_open(source_file)
        if source_file.root == root:
            root.rename(root.with_name("original-source"))
            root.mkdir()
        return stream

    def observe_create(path):
        created.append(path)
        return real_create(path)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", replace_root_after_open)
    monkeypatch.setattr(snapshots, "_create_file", observe_create)
    with pytest.raises(SourceAccessError):
        capture(store, intent)
    assert all(path.name.endswith(".attempt.json") for path in created), (
        "Source root changed after opening; a payload sink must not be created"
    )
    assert_no_artifact(jobs)


def test_destination_file_symlink_swap_cannot_chmod_or_write_the_original(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    original = root / "a.jsonl"
    original.write_bytes(b"first\n")
    original_mode = stat.S_IMODE(original.stat().st_mode)
    swapped = False

    def swap_after_copy():
        nonlocal swapped
        for path in jobs.rglob("a.jsonl"):
            if not swapped and path.stat().st_size:
                swapped = True
                path.unlink()
                path.symlink_to(original)
        return False

    with pytest.raises(SourceAccessError) as caught:
        capture(store, intent, cancelled=swap_after_copy)
    assert caught.value.code == SourceAccessErrorCode.SYMLINK_NOT_ALLOWED
    assert swapped
    assert original.read_bytes() == b"first\n"
    assert stat.S_IMODE(original.stat().st_mode) == original_mode
    assert_no_artifact(jobs)


@pytest.mark.parametrize("field", ["state", "format_version"])
def test_manifest_requires_explicit_completion_and_format_version(tmp_path, field):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    snapshot = capture(store, intent)
    path = snapshot.root.parent / "manifest.json"
    manifest = json.loads(path.read_bytes())
    del manifest[field]
    path.chmod(0o600)
    path.write_text(json.dumps(manifest))
    path.chmod(0o400)
    with pytest.raises(SnapshotError) as caught:
        store.reopen(**intent)
    assert caught.value.code == SnapshotErrorCode.INVALID_MANIFEST


def test_store_grant_revocation_does_not_invalidate_bound_snapshot_file(tmp_path):
    from one_memory.imports.grants import SourceGrantStore
    from one_memory.imports.sources.registry import RootCandidateKind

    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    grants = SourceGrantStore(tmp_path / "grants.db", home=tmp_path / "other-home")
    grants.grant(
        user_id="local", source_id="fixture", root=root, candidate_kind=RootCandidateKind.DEFAULT
    )
    intent["grant"] = grants.authorized_root(user_id="local", source_id="fixture")
    snapshot = capture(store, intent)
    retained = snapshot.grant.authorize_file(Path("a.jsonl"))
    with retained.open_binary() as source:
        assert source.read() == b"first\n"
    grants.revoke(user_id="local", source_id="fixture")
    with retained.open_binary() as source:
        assert source.read() == b"first\n"
    assert grants.authorized_root(user_id="local", source_id="fixture") is None


def test_empty_selection_has_an_explicit_complete_empty_manifest(tmp_path):
    _, _, store, intent = setup_snapshot(tmp_path)
    capture(store, intent)
    reopened = store.reopen(**intent)
    assert reopened.manifest.files == ()
    assert reopened.manifest.total_bytes == 0
    assert reopened.manifest.state == "complete"


def test_reopen_rejects_readonly_file_replacement_during_hashing(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"x" * (1024 * 1024))
    snapshot = capture(store, intent)
    candidate = snapshot.root / "a.jsonl"
    swapped = False

    def replace_after_open():
        nonlocal swapped
        for name in os.listdir("/dev/fd"):
            try:
                details = os.fstat(int(name))
                identity = candidate.stat()
            except (ValueError, OSError):
                continue
            if not swapped and (details.st_dev, details.st_ino) == (
                identity.st_dev,
                identity.st_ino,
            ):
                swapped = True
                snapshot.root.chmod(0o700)
                candidate.unlink()
                candidate.write_bytes(b"y" * (1024 * 1024))
                candidate.chmod(0o400)
                snapshot.root.chmod(0o500)
                break
        return False

    with pytest.raises(SnapshotError):
        store.reopen(**intent, cancelled=replace_after_open)
    assert swapped


def test_reopen_rejects_manifest_inode_replacement_during_read(tmp_path):
    root, _, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    snapshot = capture(store, intent)
    path = snapshot.root.parent / "manifest.json"
    swapped = False

    def replace_after_open():
        nonlocal swapped
        for name in os.listdir("/dev/fd"):
            try:
                details = os.fstat(int(name))
                identity = path.stat()
            except (ValueError, OSError):
                continue
            if not swapped and (details.st_dev, details.st_ino) == (
                identity.st_dev,
                identity.st_ino,
            ):
                swapped = True
                path.unlink()
                path.write_bytes(b"{}")
                path.chmod(0o400)
                break
        return False

    with pytest.raises(SnapshotError):
        store.reopen(**intent, cancelled=replace_after_open)
    assert swapped


def test_cancelled_capture_id_cannot_recapture_appends_even_after_store_restart(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    original = root / "a.jsonl"
    original.write_bytes(b"x" * (1024 * 1024))

    def cancel_after_write():
        return any(path.stat().st_size for path in jobs.rglob("a.jsonl"))

    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=cancel_after_write)
    assert caught.value.code == SnapshotErrorCode.CANCELLED
    assert_no_artifact(jobs)
    with original.open("ab") as output:
        output.write(b"later\n")
    (root / "later.jsonl").write_bytes(b"later\n")
    restarted = SourceSnapshotStore(jobs, limits=store.limits)

    def must_not_rediscover(_):
        pytest.fail("Interrupted capture rediscovered live files using the same confirmed intent")

    with pytest.raises(SnapshotError) as retry:
        restarted.capture(**intent, file_predicate=must_not_rediscover)
    assert retry.value.code == SnapshotErrorCode.INCOMPLETE


def test_interrupted_capture_marker_is_not_treated_as_fresh_permission(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    attempt = jobs / f".{intent['snapshot_id']}.attempt.json"
    attempt.write_bytes(b'{"interrupted-write":')
    attempt.chmod(0o400)
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent)
    assert caught.value.code == SnapshotErrorCode.INCOMPLETE
    assert_no_artifact(jobs)


def test_cancellation_before_discovery_also_requires_new_confirmation(tmp_path):
    root, jobs, store, intent = setup_snapshot(tmp_path)
    (root / "a.jsonl").write_bytes(b"first\n")
    with pytest.raises(SnapshotError) as caught:
        capture(store, intent, cancelled=lambda: True)
    assert caught.value.code == SnapshotErrorCode.CANCELLED
    (root / "later.jsonl").write_bytes(b"later\n")
    with pytest.raises(SnapshotError) as retry:
        capture(SourceSnapshotStore(jobs, limits=store.limits), intent)
    assert retry.value.code == SnapshotErrorCode.INCOMPLETE
    assert_no_artifact(jobs)
