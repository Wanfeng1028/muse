import json
import os

from one_memory.runtime_client import inspect_runtime


def write_runtime(tmp_path, **changes) -> None:
    receipt = {
        "schema_version": 1,
        "service": "one-memory-core",
        "instance_id": "runtime-test",
        "pid": 1234,
        "parent_pid": None,
        "host": "127.0.0.1",
        "port": 8765,
        "started_at": "2026-09-19T01:00:00Z",
        **changes,
    }
    (tmp_path / "runtime.json").write_text(json.dumps(receipt), encoding="utf-8")
    token = tmp_path / "runtime-token"
    token.write_text("runtime-secret", encoding="utf-8")
    if os.name == "posix":
        token.chmod(0o600)


def test_runtime_inspection_authenticates_the_discovered_instance(tmp_path) -> None:
    write_runtime(tmp_path)
    calls = []

    status = inspect_runtime(
        tmp_path,
        alive=lambda pid: pid == 1234,
        identity_probe=lambda host, port, token: (
            calls.append((host, port, token))
            or {
                "status": "ok",
                "service": "one-memory-core",
                "instance_id": "runtime-test",
                "version": "1.2.3",
            }
        ),
    )

    assert status.state == "running"
    assert status.version == "1.2.3"
    assert calls == [("127.0.0.1", 8765, "runtime-secret")]
    assert "runtime-secret" not in json.dumps(status.json_value())


def test_runtime_inspection_rejects_untrusted_receipts_without_probing(tmp_path) -> None:
    write_runtime(tmp_path, host="0.0.0.0")
    probed = []

    status = inspect_runtime(
        tmp_path,
        alive=lambda _pid: True,
        identity_probe=lambda *_args: probed.append(True) or {},
    )

    assert status.state == "untrusted"
    assert status.code == "runtime_receipt_invalid"
    assert probed == []


def test_runtime_inspection_distinguishes_stopped_and_identity_mismatch(tmp_path) -> None:
    assert inspect_runtime(tmp_path).code == "runtime_receipt_missing"
    write_runtime(tmp_path)
    stopped = inspect_runtime(tmp_path, alive=lambda _pid: False)
    assert stopped.state == "stopped"
    assert stopped.code == "runtime_process_not_running"

    mismatch = inspect_runtime(
        tmp_path,
        alive=lambda _pid: True,
        identity_probe=lambda *_args: {
            "status": "ok",
            "service": "one-memory-core",
            "instance_id": "someone-else",
        },
    )
    assert mismatch.state == "untrusted"
    assert mismatch.code == "runtime_identity_mismatch"
