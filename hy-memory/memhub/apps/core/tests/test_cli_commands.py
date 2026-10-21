import io

from one_memory import cli
from one_memory.runtime_client import RuntimeStatus


def test_status_reports_the_verified_runtime_as_json(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "inspect_runtime",
        lambda _data_dir: RuntimeStatus(
            "running",
            "runtime_verified",
            instance_id="shared-runtime",
            host="127.0.0.1",
            port=8765,
            version="1.2.3",
        ),
    )
    output = io.StringIO()

    assert cli.run(["status", "--json"], output=output) == 0
    assert '"state": "running"' in output.getvalue()
    assert '"instance_id": "shared-runtime"' in output.getvalue()


def test_doctor_fails_when_runtime_identity_cannot_be_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "inspect_runtime",
        lambda _data_dir: RuntimeStatus("untrusted", "runtime_identity_mismatch"),
    )
    output = io.StringIO()

    assert cli.run(["doctor"], output=output) == 1
    assert "runtime_identity_mismatch" in output.getvalue()


def test_serve_and_legacy_empty_command_share_the_same_entry(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "serve", lambda **_kwargs: calls.append("serve"))

    assert cli.run([]) == 0
    assert cli.run(["serve"]) == 0
    assert calls == ["serve", "serve"]


def test_unknown_command_returns_usage_error() -> None:
    output = io.StringIO()

    assert cli.run(["install"], output=output) == 2
    assert output.getvalue().startswith("Usage: one-memory")
    assert cli.run(["status", "--json", "--json"], output=io.StringIO()) == 2
