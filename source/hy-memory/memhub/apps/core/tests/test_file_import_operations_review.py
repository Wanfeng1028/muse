"""Upload refusal/legacy compatibility review with bounded synthetic files only."""

import asyncio
import io
import json
import os
import struct
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from one_memory import file_imports
from one_memory.file_imports import FileImportStore, file_import_router
from tests.test_chat_exports import chatgpt_export


def export_bytes():
    return json.dumps(chatgpt_export()).encode()


def application(root):
    app = FastAPI()
    app.state.settings = SimpleNamespace(imports_enabled=True)
    app.state.file_import_store = FileImportStore(root)
    app.include_router(file_import_router([]))
    return app


def damaged_deflate_export():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("conversations.json", export_bytes())
    payload = bytearray(output.getvalue())
    filename_size, extra_size = struct.unpack_from("<HH", payload, 26)
    compressed_start = 30 + filename_size + extra_size
    # A damaged deflate block header, with a valid ZIP directory and entry name.
    payload[compressed_start] = (payload[compressed_start] & 0xF8) | 0x07
    return bytes(payload)


def test_corrupt_deflate_is_terminal_rejection_not_permanent_pending(tmp_path):
    async def scenario():
        root = tmp_path / "imports"
        app = application(root)
        operation = str(uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            # Positive control proves this exact parser accepts the undamaged format.
            good = io.BytesIO()
            with zipfile.ZipFile(good, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("conversations.json", export_bytes())
            positive = await client.post(
                "/api/v1/import-files",
                params={"filename": "good.zip", "operation_id": str(uuid4())},
                content=good.getvalue(),
            )
            assert positive.status_code == 201 and positive.json()["state"] == "completed"
            response = await client.post(
                "/api/v1/import-files",
                params={"filename": "damaged.zip", "operation_id": operation},
                content=damaged_deflate_export(),
            )
            current = FileImportStore(root).lookup_operation(operation)
            print("damaged ZIP:", response.status_code, current.model_dump(mode="json"))
            assert (response.status_code, current.state, current.code) == (
                201,
                "failed",
                "import_upload_invalid",
            )
            assert len(list((root / "staging").iterdir())) == 1

    asyncio.run(scenario())


def test_identified_upload_works_after_legacy_upload_with_normal_umask(tmp_path):
    async def scenario():
        root = tmp_path / "imports"
        app = application(root)
        operation = str(uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            legacy = await client.post(
                "/api/v1/import-files", params={"filename": "legacy.json"}, content=export_bytes()
            )
            assert legacy.status_code == 201 and "preview" in legacy.json()
            before = (root / "staging" / legacy.json()["upload_id"] / "original").read_bytes()
            response = await client.post(
                "/api/v1/import-files",
                params={"filename": "next.json", "operation_id": operation},
                content=export_bytes(),
            )
            current = FileImportStore(root).lookup_operation(operation)
            print("legacy staging mode:", oct((root / "staging").stat().st_mode & 0o777))
            print("new upload:", response.status_code, current.model_dump(mode="json"))
            assert (
                root / "staging" / legacy.json()["upload_id"] / "original"
            ).read_bytes() == before
            assert (response.status_code, current.state, current.upload_state) == (
                201,
                "completed",
                "staged",
            )

    # Only fixture filesystem creation is affected; restore immediately after the scenario.
    previous = os.umask(0o022)
    try:
        asyncio.run(scenario())
    finally:
        os.umask(previous)


@pytest.mark.parametrize("unsafe", ["writable", "symlink"])
def test_legacy_container_compatibility_keeps_unsafe_staging_blocked(tmp_path, unsafe):
    root = tmp_path / "imports"
    root.mkdir(mode=0o700)
    staging = root / "staging"
    if unsafe == "writable":
        staging.mkdir(mode=0o700)
        staging.chmod(0o777)
    else:
        outside = tmp_path / "outside"
        outside.mkdir(mode=0o700)
        staging.symlink_to(outside, target_is_directory=True)
    files = FileImportStore(root)
    with pytest.raises(file_imports.FileImportOperationUnavailable):
        files.prepare(export_bytes(), "export.json", operation_id=str(uuid4()))
    assert list(staging.iterdir()) == []


def test_legacy_corrupt_deflate_is_a_known_format_rejection(tmp_path):
    files = FileImportStore(tmp_path / "imports")
    with pytest.raises(ValueError, match="unsafe_export_archive"):
        files.prepare(damaged_deflate_export(), "damaged.zip")
    assert not files.root.exists()


@pytest.mark.parametrize("rejection", ["filename", "size"])
def test_pre_reserve_rejections_leave_operation_missing(tmp_path, monkeypatch, rejection):
    async def scenario():
        root = tmp_path / "imports"
        app = application(root)
        operation = str(uuid4())
        if rejection == "size":
            monkeypatch.setattr(file_imports, "MAX_UPLOAD_BYTES", 32)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/import-files",
                params={
                    "filename": "bad.exe" if rejection == "filename" else "export.json",
                    "operation_id": operation,
                },
                content=export_bytes(),
            )
            assert response.status_code == (422 if rejection == "filename" else 413)
            assert FileImportStore(root).lookup_operation(operation).state == "not_found"
            assert not root.exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["commit", "discard"])
def test_lookup_racing_existing_upload_action_does_not_return_staged(
    tmp_path, monkeypatch, mutation
):
    files = FileImportStore(tmp_path / "imports")
    operation = str(uuid4())
    result = files.prepare(export_bytes(), "export.json", operation_id=operation)
    original = file_imports._read_private_record
    changed = False

    def mutate_after_first_receipt_read(path):
        nonlocal changed
        contents = original(path)
        if path.name == "receipt.json" and not changed:
            changed = True
            getattr(files, mutation)(result.upload_id)
        return contents

    monkeypatch.setattr(file_imports, "_read_private_record", mutate_after_first_receipt_read)
    current = files.lookup_operation(operation)
    assert changed and current.state == "completed"
    assert current.upload_state in (
        {"unknown", "committed"} if mutation == "commit" else {"missing"}
    )
