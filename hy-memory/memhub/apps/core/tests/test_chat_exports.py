import asyncio
import copy
import io
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.file_imports import FileImportStore
from one_memory.imports.chat_exports import parse_chat_export
from one_memory.imports.models import MAX_VERBATIM_CHARACTERS
from one_memory.secrets import InMemorySecretStore
from tests.source_consent import connection_request


def chatgpt_export():
    return [
        {
            "id": "chat-1",
            "title": "产品发布",
            "mapping": {
                "root": {"message": None, "parent": None},
                "u1": {
                    "parent": "root",
                    "message": {
                        "id": "u1",
                        "author": {"role": "user"},
                        "create_time": 1726100000,
                        "content": {"parts": ["项目周会不安排在周五。"]},
                    },
                },
                "a1": {
                    "parent": "u1",
                    "message": {
                        "id": "a1",
                        "author": {"role": "assistant"},
                        "create_time": None,
                        "content": {"parts": ["可以安排到周三。"]},
                    },
                },
                "alternate": {
                    "parent": "u1",
                    "message": {
                        "id": "a2",
                        "author": {"role": "assistant"},
                        "content": {"parts": ["另一个分支建议周四。"]},
                    },
                },
            },
            "current_node": "a1",
        }
    ]


def test_chatgpt_preserves_authorship_unknown_time_and_branch_identity():
    result = parse_chat_export(json.dumps(chatgpt_export()).encode(), "conversations.json")
    assert result.vendor == "chatgpt"
    assert len(result.messages) == 3
    assert [message.written_by for message in result.messages] == ["person", "agent", "agent"]
    assert result.messages[1].created_at is None
    assert result.messages[2].conversation_id != result.messages[1].conversation_id
    assert result.messages[0].verbatim == "项目周会不安排在周五。"


def test_claude_and_unsupported_formats_are_not_guessed():
    data = [
        {
            "uuid": "c1",
            "name": "产品设计",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "sender": "human",
                    "text": "保留原话。",
                    "created_at": "2026-09-11T00:00:00Z",
                },
                {"uuid": "m2", "sender": "assistant", "text": "建议使用引用。", "created_at": None},
            ],
        }
    ]
    result = parse_chat_export(json.dumps(data).encode(), "conversations.json")
    assert result.vendor == "claude" and len(result.messages) == 2
    with pytest.raises(ValueError, match="unsupported_export_schema"):
        parse_chat_export(b'{"text": "not a vendor conversation"}', "data.json")


def test_message_order_uses_parent_links_not_json_object_order():
    data = chatgpt_export()
    data[0]["mapping"] = dict(reversed(list(data[0]["mapping"].items())))
    result = parse_chat_export(json.dumps(data).encode(), "conversations.json")
    assert result.messages[0].message_id == "u1"
    data[0]["mapping"]["u1"]["parent"] = "a1"
    with pytest.raises(ValueError, match="invalid_export_branch"):
        parse_chat_export(json.dumps(data).encode(), "conversations.json")


def test_duplicate_json_keys_cannot_silently_replace_a_message():
    payload = json.dumps(chatgpt_export()).replace(
        '"parts": [', '"parts": ["hidden text"], "parts": [', 1
    )
    with pytest.raises(ValueError, match="^invalid_export_json$"):
        parse_chat_export(payload.encode(), "conversations.json")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_numbers_are_not_silently_treated_as_missing_time(constant):
    payload = json.dumps(chatgpt_export()).replace("1726100000", constant)
    with pytest.raises(ValueError, match="^invalid_export_json$"):
        parse_chat_export(payload.encode(), "conversations.json")


@pytest.mark.parametrize("duplicate", ["conversation", "chatgpt-message", "claude-message"])
def test_duplicate_source_identities_are_rejected_before_the_preview(duplicate):
    data = chatgpt_export()
    if duplicate == "conversation":
        data.append(copy.deepcopy(data[0]))
    elif duplicate == "chatgpt-message":
        data[0]["mapping"]["a1"]["message"]["id"] = "u1"
    else:
        data = [
            {
                "uuid": "c1",
                "chat_messages": [
                    {"uuid": "m1", "sender": "human", "text": "Original message"},
                    {"uuid": "m1", "sender": "assistant", "text": "A different message"},
                ],
            }
        ]
    with pytest.raises(ValueError, match="^duplicate_export_identity$"):
        parse_chat_export(json.dumps(data).encode(), "conversations.json")


@pytest.mark.parametrize("invalid", ["title", "text", "unicode"])
def test_unimportable_records_do_not_produce_a_successful_preview_or_staged_files(
    tmp_path, invalid
):
    data = chatgpt_export()
    if invalid == "title":
        data[0]["title"] = "Private title " * 100
    elif invalid == "text":
        data[0]["mapping"]["a1"]["message"]["content"]["parts"] = [
            "x" * (MAX_VERBATIM_CHARACTERS + 1)
        ]
    else:
        data[0]["mapping"]["a1"]["message"]["content"]["parts"] = ["unpaired surrogate \ud800"]
    files = FileImportStore(tmp_path / "imports")
    with pytest.raises(ValueError, match="^export_record_invalid$"):
        files.prepare(json.dumps(data).encode(), "conversations.json")
    assert not files.root.exists()


def test_cancelling_a_duplicate_upload_does_not_treat_it_as_already_confirmed(tmp_path):
    files = FileImportStore(tmp_path / "imports")
    payload = json.dumps(chatgpt_export()).encode()
    first = files.prepare(payload, "first.json")
    first = files.commit(first.upload_id)
    assert first.committed
    source = files.root / "ready" / first.source_id / f"{first.checksum}.jsonl"
    before = source.read_bytes()
    duplicate = files.prepare(payload, "second.json")
    assert duplicate.upload_id != first.upload_id
    assert not files.get(duplicate.upload_id).committed
    files.discard(duplicate.upload_id)
    with pytest.raises(KeyError):
        files.get(duplicate.upload_id)
    assert files.get(first.upload_id).committed
    assert source.read_bytes() == before


def test_confirmed_duplicate_upload_has_its_own_durable_receipt(tmp_path):
    root = tmp_path / "imports"
    files = FileImportStore(root)
    payload = json.dumps(chatgpt_export()).encode()
    first = files.prepare(payload, "first.json")
    files.commit(first.upload_id)
    duplicate = files.prepare(payload, "second.json")
    assert files.commit(duplicate.upload_id).committed
    assert FileImportStore(root).get(duplicate.upload_id).committed
    assert len(list((root / "ready" / first.source_id).glob("*.jsonl"))) == 1
    with pytest.raises(ValueError, match="already_committed"):
        files.discard(duplicate.upload_id)


def test_legacy_hardlinked_receipt_is_still_recognized_as_confirmed(tmp_path):
    files = FileImportStore(tmp_path / "imports")
    first = files.prepare(json.dumps(chatgpt_export()).encode(), "first.json")
    target = files.root / "ready" / first.source_id
    target.mkdir(parents=True)
    os.link(
        files.root / "staging" / str(first.upload_id) / "messages.jsonl",
        target / f"{first.checksum}.jsonl",
    )
    assert not json.loads(
        (files.root / "staging" / str(first.upload_id) / "receipt.json").read_text()
    )["committed"]
    assert files.get(first.upload_id).committed
    with pytest.raises(ValueError, match="already_committed"):
        files.discard(first.upload_id)


def test_discard_cannot_remove_staging_while_commit_publishes_it(tmp_path, monkeypatch):
    files = FileImportStore(tmp_path / "imports")
    receipt = files.prepare(json.dumps(chatgpt_export()).encode(), "first.json")
    entered, release, cancelling = Event(), Event(), Event()
    original_link = os.link

    def held_link(*args, **kwargs):
        entered.set()
        assert release.wait(3), "test did not release commit"
        return original_link(*args, **kwargs)

    def cancel():
        cancelling.set()
        files.discard(receipt.upload_id)

    monkeypatch.setattr(os, "link", held_link)
    with ThreadPoolExecutor(max_workers=2) as executor:
        commit = executor.submit(files.commit, receipt.upload_id)
        assert entered.wait(3)
        discard = executor.submit(cancel)
        try:
            assert cancelling.wait(3)
            with pytest.raises(TimeoutError):
                discard.result(timeout=0.1)
        finally:
            release.set()
        assert commit.result(timeout=3).committed
        with pytest.raises(ValueError, match="already_committed"):
            discard.result(timeout=3)
    assert files.get(receipt.upload_id).committed


def test_a_receipt_disappearing_during_read_is_still_reported_as_missing(tmp_path, monkeypatch):
    files = FileImportStore(tmp_path / "imports")
    receipt = files.prepare(json.dumps(chatgpt_export()).encode(), "first.json")
    original_read = Path.read_text
    target = files.root / "staging" / str(receipt.upload_id) / "receipt.json"

    def read_after_discard(path, *args, **kwargs):
        if path == target:
            path.unlink()
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_after_discard)
    with pytest.raises(KeyError):
        files.get(receipt.upload_id)


def test_zip_reads_conversation_payload_only_and_refuses_unsafe_or_ambiguous_files():
    def packed(entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return output.getvalue()

    text = json.dumps(chatgpt_export())
    result = parse_chat_export(
        packed({"conversations.json": text, "photo.png": b"ignored"}), "export.zip"
    )
    assert result.ignored_files == 1 and len(result.messages) == 3
    for entries in (
        {"../escape": "bad", "conversations.json": text},
        {"a/conversations.json": text, "b/conversations.json": text},
        {"..\\escape": "bad", "conversations.json": text},
    ):
        with pytest.raises(ValueError):
            parse_chat_export(packed(entries), "export.zip")


def test_upload_preview_then_authorize_and_import_through_normal_runner(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path / "home",
                api_token=SecretStr("test-export"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            secret_store=InMemorySecretStore(),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-export"},
            ) as client,
        ):
            upload = await client.post(
                "/api/v1/import-files?filename=conversations.json",
                content=json.dumps(chatgpt_export()).encode(),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert upload.status_code == 201
            receipt = upload.json()
            assert receipt["messages"] == 3
            assert app.state.evidence_store.count() == 0
            assert (
                app.state.source_grant_store.receipt(
                    user_id="local", source_id=receipt["source_id"]
                )
                is None
            )
            endpoint = f"/api/v1/import-files/{receipt['upload_id']}/commit"
            assert (await client.post(endpoint, json={"confirmed": False})).status_code == 422
            assert (await client.post(endpoint, json={"confirmed": True})).status_code == 200
            connected = await client.post(
                "/api/v1/sources/connect",
                json=await connection_request(
                    client,
                    [receipt["source_id"]],
                    confirm_environment_overrides=False,
                    enable_sync=True,
                ),
            )
            assert connected.status_code == 200 and connected.json()["failed_sources"] == {}
            job_id = connected.json()["jobs"][0]["job_id"]
            job = await app.state.import_supervisor.wait(job_id)
            assert job.status == "completed"
            assert app.state.evidence_store.count() == 3
            duplicate = await client.post(
                "/api/v1/import-files?filename=conversations.json",
                content=json.dumps(chatgpt_export()).encode(),
                headers={"Content-Type": "application/octet-stream"},
            )
            duplicate_id = duplicate.json()["upload_id"]
            assert not (await client.get(f"/api/v1/import-files/{duplicate_id}")).json()[
                "committed"
            ]
            assert (await client.delete(f"/api/v1/import-files/{duplicate_id}")).status_code == 204
            assert app.state.evidence_store.count() == 3
            again = await client.post(
                "/api/v1/import-jobs", json={"source_id": receipt["source_id"]}
            )
            await app.state.import_supervisor.wait(again.json()["job_id"])
            assert app.state.evidence_store.count() == 3
            assert (
                await client.post(f"/api/v1/sources/{receipt['source_id']}/revoke", json={})
            ).status_code == 200
            assert receipt["source_id"] not in app.state.import_supervisor.adapters

    asyncio.run(scenario())


def test_bad_uploads_report_safe_errors_and_leave_no_partial_source(tmp_path):
    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path / "home",
                api_token=SecretStr("test-export"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            secret_store=InMemorySecretStore(),
        )
        valid = chatgpt_export()
        duplicate = [valid[0], valid[0]]
        invalid_record = copy.deepcopy(valid)
        invalid_record[0]["title"] = "DO_NOT_LEAK_PRIVATE_SOURCE " * 100
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-export"},
            ) as client,
        ):
            for value, code in [
                (duplicate, "duplicate_export_identity"),
                (invalid_record, "export_record_invalid"),
            ]:
                response = await client.post(
                    "/api/v1/import-files?filename=export.json",
                    content=json.dumps(value).encode(),
                    headers={"Content-Type": "application/octet-stream"},
                )
                assert response.status_code == 422
                assert response.json() == {"detail": code}
                assert "DO_NOT_LEAK_PRIVATE_SOURCE" not in response.text
                assert app.state.evidence_store.count() == 0
                assert (await client.get("/api/v1/import-jobs")).json() == []
                assert not app.state.file_import_store.root.exists()

    asyncio.run(scenario())
