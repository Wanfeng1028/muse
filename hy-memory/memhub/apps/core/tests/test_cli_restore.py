import io

from one_memory import cli
from one_memory.config import Settings
from one_memory.runtime_client import RuntimeStatus


def test_restore_requires_a_source(tmp_path, monkeypatch) -> None:
    output = io.StringIO()
    assert cli.run(["restore"], output=output) == 2
    assert "--source" in output.getvalue()


def test_restore_refuses_while_the_runtime_is_running(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(_env_file=None, data_dir=tmp_path))
    monkeypatch.setattr(
        cli,
        "inspect_runtime",
        lambda _data_dir: RuntimeStatus("running", "runtime_verified"),
    )
    output = io.StringIO()

    code = cli.run(
        ["restore", "--source", "backups/x.sqlite3", "--yes", "--json"],
        output=output,
    )
    assert code == 4
    assert "backup_restore_runtime_running" in output.getvalue()


def test_restore_previews_without_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(_env_file=None, data_dir=tmp_path))
    monkeypatch.setattr(
        cli,
        "inspect_runtime",
        lambda _data_dir: RuntimeStatus("stopped", "runtime_receipt_missing"),
    )
    output = io.StringIO()

    assert cli.run(["restore", "--source", "backups/x.sqlite3", "--json"], output=output) == 4
    assert '"state": "preview"' in output.getvalue() or '"state":"preview"' in output.getvalue()


def test_restore_success_returns_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(_env_file=None, data_dir=tmp_path))
    monkeypatch.setattr(
        cli,
        "inspect_runtime",
        lambda _data_dir: RuntimeStatus("stopped", "runtime_receipt_missing"),
    )

    class Result:
        restored_bytes = 123
        previous_backup_path = tmp_path / "backups" / "pre.sqlite3"
        source_schema_version = 36

    monkeypatch.setattr(
        "one_memory.managed_restore.restore_managed_backup",
        lambda **_kwargs: Result(),
    )
    output = io.StringIO()

    code = cli.run(
        ["restore", "--source", "backups/x.sqlite3", "--yes", "--json"],
        output=output,
    )
    assert code == 0
    assert '"state":"restored"' in output.getvalue().replace(" ", "")
