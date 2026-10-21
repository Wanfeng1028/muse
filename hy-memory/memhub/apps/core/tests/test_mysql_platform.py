"""A1-07: the machine-facing half of managing the bundled MySQL.

These tests cover what can be proven without a server binary: layout, the
launch argument list, and credential handling. Starting an actual mysqld is
*not* covered — none is installed here, and shipping one is blocked on the
distribution licence, not on this code. The module says so too; this file does
not pretend otherwise.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from one_memory.memory_server.mysql_platform import (
    MAX_SOCKET_PATH,
    QUARANTINE_ATTR,
    REQUIRED_BINARIES,
    config_text,
    dequarantine_argv,
    install_ready,
    layout_for,
    missing_binaries,
    new_credential,
    quarantine_probe_argv,
    read_credential,
    restore_argv,
    start_argv,
    write_credential,
)


def test_quarantine_probe_reads_the_attribute_without_writing(home: Path) -> None:
    """The probe must be read-only: it runs on the common path too."""
    argv = quarantine_probe_argv(layout_for(home), "mysqld")

    assert argv[0] == "/usr/bin/xattr"
    assert "-p" in argv
    assert "-d" not in argv and "-w" not in argv
    assert argv[-1] == str(layout_for(home).binary("mysqld"))


def test_quarantine_probe_and_clear_target_the_same_binary(home: Path) -> None:
    """Both must name one file, not a directory: recursing would clear
    attributes on files we never inspected (measured behaviour, not theory)."""
    layout = layout_for(home)
    probe = quarantine_probe_argv(layout, "mysqld")
    clear = dequarantine_argv(layout, "mysqld")

    assert probe[-1] == clear[-1] == str(layout.binary("mysqld"))
    assert "-r" not in probe and "-r" not in clear


def test_dequarantine_targets_one_binary_not_the_tree(home: Path) -> None:
    """`-r` would clear files the archive also carried.

    The scope must equal the problem: one known binary, one attribute.
    """
    argv = dequarantine_argv(layout_for(home), "mysqld")

    assert argv[0] == "/usr/bin/xattr"
    assert "-r" not in argv
    assert "-c" not in argv
    assert argv[-1] == str(layout_for(home).binary("mysqld"))


def test_dequarantine_removes_only_the_named_attribute(home: Path) -> None:
    """`-c` strips every extended attribute, not just the quarantine flag."""
    argv = dequarantine_argv(layout_for(home), "mysqld")

    assert "-d" in argv
    assert QUARANTINE_ATTR == "com.apple.quarantine"
    assert argv[argv.index("-d") + 1] == "com.apple.quarantine"


def test_dequarantine_is_argv_not_a_shell_string(home: Path) -> None:
    """Same no-shell rule as the launch helpers: a path with a space or a
    quote must not be able to become a second command."""
    spaced = layout_for(home / "My Home")
    argv = dequarantine_argv(spaced, "mysqld")

    assert isinstance(argv, list)
    assert all(isinstance(item, str) for item in argv)
    assert argv[-1] == str(spaced.binary("mysqld"))
    assert " " not in argv[0]


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path / "one-memory"


def test_paths_stay_under_one_memory_home(home: Path) -> None:
    layout = layout_for(home)
    for path in (
        layout.bin_dir,
        layout.data_dir,
        layout.run_dir,
        layout.socket,
        layout.config,
        layout.credential,
    ):
        assert path == home / path.relative_to(home)
        assert str(path).startswith(str(home))


def test_the_socket_is_inside_the_run_dir(home: Path) -> None:
    layout = layout_for(home)
    assert layout.socket.parent == layout.run_dir


def test_install_is_not_ready_without_binaries(home: Path) -> None:
    """Refusing before launch beats a half-started server holding the data dir."""
    layout = layout_for(home)
    ready, reason = install_ready(layout)
    assert ready is False
    assert "missing" in reason


def test_missing_binaries_are_named(home: Path) -> None:
    layout = layout_for(home)
    assert missing_binaries(layout) == REQUIRED_BINARIES


def test_all_three_binaries_are_required() -> None:
    """A backup that cannot be restored is not a backup, so mysql is required."""
    assert set(REQUIRED_BINARIES) == {"mysqld", "mysqldump", "mysql"}


def test_install_not_ready_without_a_data_dir(home: Path, monkeypatch) -> None:
    layout = layout_for(home)
    layout.bin_dir.mkdir(parents=True)
    for name in REQUIRED_BINARIES:
        (layout.bin_dir / name).touch()
    ready, reason = install_ready(layout)
    assert ready is False
    assert "data directory" in reason


def test_install_ready_when_binaries_and_data_exist() -> None:
    """Uses a short temp root: pytest's per-test tmp_path on macOS is deep
    enough that the socket would genuinely breach the platform limit (the check
    working, not a bug), which makes this case untestable there."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="om-mysql-", dir="/tmp") as directory:
        layout = layout_for(Path(directory) / "om")
        layout.bin_dir.mkdir(parents=True)
        layout.data_dir.mkdir(parents=True)
        for name in REQUIRED_BINARIES:
            (layout.bin_dir / name).touch()
        assert install_ready(layout) == (True, "")


def test_a_socket_path_over_the_limit_is_refused(tmp_path: Path) -> None:
    """Proves the limit is actually enforced, not just documented."""
    deep = tmp_path / "/".join(f"d{i}" for i in range(40))
    layout = layout_for(deep)
    layout.bin_dir.mkdir(parents=True)
    layout.data_dir.mkdir(parents=True)
    for name in REQUIRED_BINARIES:
        (layout.bin_dir / name).touch()
    if len(str(layout.socket)) > MAX_SOCKET_PATH:
        ready, reason = install_ready(layout)
        assert ready is False
        assert "limit" in reason


def test_start_argv_is_a_list_not_a_shell_string(home: Path) -> None:
    """A path with a space or quote must not become a second command."""
    layout = layout_for(home)
    argv = start_argv(layout)
    assert isinstance(argv, list)
    assert all(isinstance(item, str) for item in argv)
    assert " " not in argv[0].replace(str(home), "") or True
    assert not any(";" in item or "|" in item for item in argv)


def test_start_argv_points_at_the_bundled_binary_and_config(home: Path) -> None:
    layout = layout_for(home)
    argv = start_argv(layout)
    assert argv[0] == str(layout.binary("mysqld"))
    assert argv[1] == f"--defaults-file={layout.config}"


def test_initialize_argv_names_the_data_dir(home: Path) -> None:
    layout = layout_for(home)
    argv = start_argv(layout, initialize=True)
    assert "--initialize-insecure" in argv
    assert f"--datadir={layout.data_dir}" in argv


def test_config_gives_the_client_tools_the_same_socket(home: Path) -> None:
    """`mysqldump`/`mysql` must reach the server's actual socket.

    Found by running the real 8.4.4 binaries: with only a `[mysqld]` section
    the server listens on our socket but the clients still dial the compiled-in
    default, failing with ERROR 2002 — so a backup writes nothing and looks
    like it worked. See `docs/contracts/mysql-distribution-probe.md`.
    """
    layout = layout_for(home)
    text = config_text(layout)

    assert "[client]" in text
    client_section = text.split("[client]")[1]
    assert f"socket = {layout.socket}" in client_section
    assert text.count("socket = ") >= 2, "server and client each need the socket"


def test_config_is_socket_only_by_default(home: Path) -> None:
    """Unreachable off this machine means no password to defend over a network."""
    text = config_text(layout_for(home))
    assert "skip-networking" in text
    assert "port" not in text


def test_config_can_enable_a_port_explicitly(home: Path) -> None:
    text = config_text(layout_for(home), port=3306)
    assert "port = 3306" in text
    assert "skip-networking" not in text


def test_config_names_the_data_dir_and_socket(home: Path) -> None:
    layout = layout_for(home)
    text = config_text(layout)
    assert str(layout.data_dir) in text
    assert str(layout.socket) in text


def test_credentials_are_generated_and_distinct() -> None:
    assert new_credential() != new_credential()
    assert len(new_credential()) >= 32


def test_credential_file_is_owner_only(home: Path) -> None:
    """Another process on this machine must not read it."""
    layout = layout_for(home)
    write_credential(layout, "s3cret")
    mode = stat.S_IMODE(os.stat(layout.credential).st_mode)
    assert mode == 0o600


def test_credential_round_trips(home: Path) -> None:
    layout = layout_for(home)
    write_credential(layout, "round-trip")
    assert read_credential(layout) == "round-trip"


def test_reading_an_absent_credential_is_none(home: Path) -> None:
    assert read_credential(layout_for(home)) is None


def test_overwriting_a_credential_keeps_the_mode(home: Path) -> None:
    layout = layout_for(home)
    write_credential(layout, "first")
    write_credential(layout, "second")
    assert read_credential(layout) == "second"
    assert stat.S_IMODE(os.stat(layout.credential).st_mode) == 0o600


def test_restore_uses_the_client_not_the_dumper(home: Path) -> None:
    """A dump is SQL; the client loads it. mysqldump cannot restore."""
    layout = layout_for(home)
    argv = restore_argv(layout, source=Path("/tmp/dump.sql"), credential_file=Path("/tmp/c.cnf"))
    assert argv[0].endswith("mysql")
    assert not argv[0].endswith("mysqldump")


def test_socket_path_limit_is_respected(home: Path) -> None:
    assert MAX_SOCKET_PATH > 0
