"""Bounded synthetic uploads; operation identity is not a content dedup key."""

import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from one_memory import file_imports
from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.file_imports import FileImportStore
from one_memory.imports.models import EvidenceContentKind
from one_memory.secrets import InMemorySecretStore
from tests.test_chat_exports import chatgpt_export


@pytest.fixture
def files(tmp_path):
    return FileImportStore(tmp_path / "imports")


@pytest.fixture
def payload():
    return json.dumps(chatgpt_export()).encode()


def test_lookup_missing_does_not_create_directories(files):
    operation = str(uuid4())
    receipt = files.lookup_operation(operation)
    assert receipt.model_dump() == {
        "schema_version": 1,
        "operation_id": operation,
        "state": "not_found",
        "upload_id": None,
        "code": None,
        "upload_state": None,
    }
    assert not files.root.exists()


@pytest.mark.parametrize(
    "operation",
    [
        "../escape",
        "123",
        "123E4567-E89B-12D3-A456-426614174000",
        "123e4567e89b12d3a456426614174000",
    ],
)
def test_noncanonical_operation_rejected_before_any_write(files, payload, operation):
    with pytest.raises(ValueError, match="invalid_import_operation_id"):
        files.prepare(payload, "export.json", operation_id=operation)
    with pytest.raises(ValueError, match="invalid_import_operation_id"):
        files.lookup_operation(operation)
    assert not files.root.exists()


def test_completed_receipt_reopens_without_reparsing_or_content(files, payload, monkeypatch):
    operation = str(uuid4())
    first = files.prepare(payload, "private-filename.json", operation_id=operation)
    assert first.state == "completed" and first.upload_id
    assert set(first.model_dump()) == {
        "schema_version",
        "operation_id",
        "state",
        "upload_id",
        "code",
        "upload_state",
    }
    assert "private-filename" not in first.model_dump_json()
    assert "preview" not in first.model_dump_json() and "checksum" not in first.model_dump_json()
    monkeypatch.setattr(
        file_imports, "parse_chat_export", lambda *a: pytest.fail("operation replayed")
    )
    reopened = FileImportStore(files.root)
    assert reopened.lookup_operation(operation) == first
    assert reopened.prepare(payload, "private-filename.json", operation_id=operation) == first
    assert not reopened.get(first.upload_id).committed
    assert len(list((files.root / "staging").iterdir())) == 1


@pytest.mark.parametrize("changed", ["bytes", "filename", "input_kind"])
def test_same_operation_different_request_conflicts(files, payload, changed):
    operation = str(uuid4())
    first = files.prepare(payload, "export.json", operation_id=operation)
    with pytest.raises(file_imports.FileImportOperationConflict):
        files.prepare(
            payload + b" " if changed == "bytes" else payload,
            "other.json" if changed == "filename" else "export.json",
            input_kind=(
                EvidenceContentKind.MEMORY_CONTENT
                if changed == "input_kind"
                else EvidenceContentKind.RAW_CONVERSATION
            ),
            operation_id=operation,
        )
    assert files.lookup_operation(operation) == first


def test_reserve_precedes_staging_and_concurrent_call_never_replays(files, payload, monkeypatch):
    operation = str(uuid4())
    entered, release = Event(), Event()
    original = file_imports.parse_chat_export

    def hold(*args):
        assert files.lookup_operation(operation).state == "pending"
        assert not (files.root / "staging").exists()
        entered.set()
        assert release.wait(3)
        return original(*args)

    monkeypatch.setattr(file_imports, "parse_chat_export", hold)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(files.prepare, payload, "export.json", operation_id=operation)
        try:
            assert entered.wait(3)
            assert (
                FileImportStore(files.root)
                .prepare(payload, "export.json", operation_id=operation)
                .state
                == "pending"
            )
            with pytest.raises(file_imports.FileImportOperationConflict):
                files.prepare(payload + b" ", "export.json", operation_id=operation)
        finally:
            release.set()
        assert future.result(timeout=3).state == "completed"


def test_interruption_remains_pending_on_reopen_and_no_stage_guess(files, payload, monkeypatch):
    operation = str(uuid4())

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(file_imports, "parse_chat_export", interrupt)
    with pytest.raises(KeyboardInterrupt):
        files.prepare(payload, "export.json", operation_id=operation)
    reopened = FileImportStore(files.root)
    assert reopened.lookup_operation(operation).state == "pending"
    assert reopened.prepare(payload, "export.json", operation_id=operation).state == "pending"


def test_parse_rejection_has_fixed_terminal_receipt_and_no_stage(files):
    operation = str(uuid4())
    result = files.prepare(b"not JSON private content", "export.json", operation_id=operation)
    assert result.state == "failed" and result.code == "import_upload_invalid"
    assert result.upload_id is None
    assert "private" not in result.model_dump_json()
    assert files.lookup_operation(operation) == result
    assert not (files.root / "staging").exists()


@pytest.mark.parametrize("boundary", ["reserve_sync", "stage_sync", "terminal_replace"])
def test_durability_failure_never_returns_success_or_replays(files, payload, monkeypatch, boundary):
    operation = str(uuid4())
    sync = file_imports._sync_directory
    replace = os.replace

    def fail_sync(path):
        if (boundary == "reserve_sync" and path.name == "operations") or (
            boundary == "stage_sync" and path.parent.name == "staging"
        ):
            raise OSError("private error text")
        sync(path)

    def fail_replace(source, destination):
        if boundary == "terminal_replace":
            raise OSError("private error text")
        return replace(source, destination)

    monkeypatch.setattr(file_imports, "_sync_directory", fail_sync)
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(
        file_imports.FileImportOperationUnavailable, match="^import_upload_operation_unavailable$"
    ):
        files.prepare(payload, "export.json", operation_id=operation)
    reopened = FileImportStore(files.root)
    assert reopened.lookup_operation(operation).state == "pending"
    monkeypatch.setattr(
        file_imports, "parse_chat_export", lambda *a: pytest.fail("unknown upload replayed")
    )
    assert reopened.prepare(payload, "export.json", operation_id=operation).state == "pending"
    if boundary == "reserve_sync":
        assert not (files.root / "staging").exists()


def test_completed_lookup_is_readonly_and_reports_current_commit(files, payload, monkeypatch):
    operation = str(uuid4())
    result = files.prepare(payload, "export.json", operation_id=operation)
    assert result.upload_state == "staged"
    files.commit(result.upload_id)
    before = {
        str(path.relative_to(files.root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files.root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        file_imports, "_sync_directory", lambda *a: pytest.fail("lookup writes directory")
    )
    receipt = FileImportStore(files.root).lookup_operation(operation)
    assert receipt.state == "completed" and receipt.upload_state == "committed"
    after = {
        str(path.relative_to(files.root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files.root.rglob("*")
        if path.is_file()
    }
    assert before and after == before


def test_changed_preview_identity_is_unknown_not_available(files, payload):
    operation = str(uuid4())
    result = files.prepare(payload, "export.json", operation_id=operation)
    path = files.root / "staging" / str(result.upload_id) / "receipt.json"
    receipt = json.loads(path.read_bytes())
    receipt["filename"] = "unrelated.json"
    path.write_text(json.dumps(receipt))
    observed = files.lookup_operation(operation)
    assert observed.state == "completed" and observed.upload_state == "unknown"


def test_symlink_store_root_is_not_followed(files, payload, tmp_path):
    target = tmp_path / "other"
    target.mkdir()
    files.root.symlink_to(target, target_is_directory=True)
    operation = str(uuid4())
    with pytest.raises(file_imports.FileImportOperationUnavailable):
        files.lookup_operation(operation)
    with pytest.raises(file_imports.FileImportOperationUnavailable):
        files.prepare(payload, "export.json", operation_id=operation)
    assert list(target.iterdir()) == []


def test_staging_finished_but_operation_not_published_stays_pending(files, payload, monkeypatch):
    operation = str(uuid4())
    write = files._write_operation

    def interrupt(record, *, reserve):
        if not reserve:
            raise KeyboardInterrupt
        return write(record, reserve=reserve)

    monkeypatch.setattr(files, "_write_operation", interrupt)
    with pytest.raises(KeyboardInterrupt):
        files.prepare(payload, "export.json", operation_id=operation)
    assert len(list((files.root / "staging").glob("*/receipt.json"))) == 1
    reopened = FileImportStore(files.root)
    assert reopened.lookup_operation(operation).state == "pending"
    monkeypatch.setattr(
        file_imports, "parse_chat_export", lambda *a: pytest.fail("orphan stage replayed")
    )
    assert reopened.prepare(payload, "export.json", operation_id=operation).state == "pending"


def test_lookup_disappearing_known_record_is_unavailable(files, payload, monkeypatch):
    operation = str(uuid4())
    files.prepare(payload, "export.json", operation_id=operation)
    original = file_imports._read_private_record

    def vanish(path):
        if path.name == f"{operation}.json":
            path.unlink()
        return original(path)

    monkeypatch.setattr(file_imports, "_read_private_record", vanish)
    with pytest.raises(file_imports.FileImportOperationUnavailable):
        files.lookup_operation(operation)


def test_identical_content_different_operations_keep_per_upload_confirmation(files, payload):
    first = files.prepare(payload, "export.json", operation_id=str(uuid4()))
    second_operation = str(uuid4())
    second = files.prepare(payload, "export.json", operation_id=second_operation)
    assert first.upload_id != second.upload_id
    assert files.commit(first.upload_id).committed
    assert not files.get(second.upload_id).committed
    files.discard(second.upload_id)
    historical = files.lookup_operation(second_operation)
    assert historical.state == "completed" and historical.upload_id == second.upload_id
    assert historical.upload_state == "missing"
    with pytest.raises(KeyError):
        files.get(second.upload_id)
    assert files.get(first.upload_id).committed


@pytest.mark.parametrize(
    "corruption",
    [
        "partial",
        "identity",
        "permissions",
        "symlink",
        "hardlink",
        "oversize",
        "duplicate_key",
        "fifo",
    ],
)
def test_broken_operation_is_unavailable_not_missing(files, payload, corruption):
    operation = str(uuid4())
    files.prepare(payload, "export.json", operation_id=operation)
    path = files.root / "operations" / f"{operation}.json"
    if corruption == "partial":
        path.write_bytes(b'{"state":')
    elif corruption == "identity":
        body = json.loads(path.read_bytes())
        body["operation_id"] = str(uuid4())
        path.write_text(json.dumps(body))
    elif corruption == "permissions":
        path.chmod(0o644)
    elif corruption == "symlink":
        target = path.with_suffix(".target")
        path.rename(target)
        path.symlink_to(target)
    elif corruption == "hardlink":
        path.with_suffix(".link").hardlink_to(path)
    elif corruption == "oversize":
        path.write_bytes(b" " * 16_385)
    elif corruption == "duplicate_key":
        path.write_text('{"state":"pending",' + path.read_text()[1:])
    else:
        path.unlink()
        os.mkfifo(path, mode=0o600)
    with pytest.raises(file_imports.FileImportOperationUnavailable):
        files.lookup_operation(operation)


def test_authenticated_operation_route_recovers_without_auto_commit(tmp_path, payload):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path / "synthetic-home",
                api_token="upload-test-token",
                automatic_memory_processing=False,
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
            lookup = f"/api/v1/import-files/operations/{operation}"
            assert (await client.get(lookup)).status_code == 401
            client.headers["Authorization"] = "Bearer upload-test-token"
            preflight = await client.get(lookup)
            assert preflight.status_code == 200 and preflight.json()["state"] == "not_found"
            response = await client.post(
                "/api/v1/import-files",
                params={"filename": "export.json", "operation_id": operation},
                content=payload,
            )
            assert response.status_code == 201, response.text
            receipt = response.json()
            assert receipt["state"] == "completed"
            recovered = await client.get(lookup)
            assert recovered.json() == receipt
            assert recovered.headers["cache-control"] == "no-store"
            upload = await client.get(f"/api/v1/import-files/{receipt['upload_id']}")
            assert upload.status_code == 200 and not upload.json()["committed"]
            assert not (tmp_path / "data/import-files/ready").exists()
            conflict = await client.post(
                "/api/v1/import-files",
                params={"filename": "export.json", "operation_id": operation},
                content=payload + b" ",
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"] == "import_upload_operation_conflict"
            discarded = await client.delete(f"/api/v1/import-files/{receipt['upload_id']}")
            assert discarded.status_code == 204
            missing = (await client.get(lookup)).json()
            assert missing["state"] == "completed" and missing["upload_state"] == "missing"
            malformed = await client.get("/api/v1/import-files/operations/not-a-uuid")
            assert malformed.status_code == 422
            legacy = await client.post(
                "/api/v1/import-files", params={"filename": "legacy.json"}, content=payload
            )
            assert legacy.status_code == 201 and "preview" in legacy.json()
            assert "state" not in legacy.json() and "operation_id" not in legacy.json()
            original_get = await client.get(f"/api/v1/import-files/{legacy.json()['upload_id']}")
            assert original_get.status_code == 200 and original_get.json() == legacy.json()

    asyncio.run(scenario())
