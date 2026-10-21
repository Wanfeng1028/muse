"""3925a kernel item 2 (BUG-01, backend half): WorkBuddy import root.

WorkBuddy's transcripts live in `$HOME/.workbuddy/projects`. `~/.codebuddy`
is the CLI's own config directory; it is not an import root, and choosing
between the two by newest mtime gave a leftover CLI test session the power to
outrank the app's real history and put a folder choice in front of the user
that has exactly one right answer.

This module pins the new contract: one root, no mtime, no `.codebuddy`, and a
session count the authorization page can show.
"""

from __future__ import annotations

import os
from pathlib import Path

from one_memory.imports.sources.registry import (
    RootCandidateKind,
    build_source_catalog,
    workbuddy_default_homes,
)


def _candidate(home: Path, environment: dict[str, str] | None = None):
    return build_source_catalog(home=home, environment=environment or {})["workbuddy"].candidate


def test_codebuddy_is_never_the_import_root(tmp_path) -> None:
    """The only thing in `~/.codebuddy` is the CLI's own state."""
    home = tmp_path / "home"
    codebuddy = home / ".codebuddy" / "projects"
    workbuddy = home / ".workbuddy" / "projects"
    codebuddy.mkdir(parents=True)
    (codebuddy / "session.jsonl").write_text("{}\n", encoding="utf-8")

    assert _candidate(home).path == workbuddy


def test_a_newer_codebuddy_session_does_not_outvote_the_real_root(tmp_path) -> None:
    """mtime is not evidence of where the app writes.

    A CLI test run is newer than the app's last session and still says nothing
    about which directory is the import root.
    """
    home = tmp_path / "home"
    codebuddy = home / ".codebuddy" / "projects"
    workbuddy = home / ".workbuddy" / "projects"
    for directory in (codebuddy, workbuddy):
        directory.mkdir(parents=True)
        (directory / "session.jsonl").write_text("{}\n", encoding="utf-8")
    os.utime(codebuddy / "session.jsonl", (1_900_000_000, 1_900_000_000))
    os.utime(workbuddy / "session.jsonl", (1_600_000_000, 1_600_000_000))

    assert _candidate(home).path == workbuddy


def test_an_empty_workbuddy_root_still_beats_a_populated_codebuddy(tmp_path) -> None:
    """Installed with no sessions yet is not "look somewhere else"."""
    home = tmp_path / "home"
    codebuddy = home / ".codebuddy" / "projects"
    workbuddy = home / ".workbuddy" / "projects"
    codebuddy.mkdir(parents=True)
    workbuddy.mkdir(parents=True)
    (codebuddy / "session.jsonl").write_text("{}\n", encoding="utf-8")

    candidate = _candidate(home)

    assert candidate.path == workbuddy
    assert candidate.kind is RootCandidateKind.DEFAULT


def test_the_root_is_the_workbuddy_home_on_a_machine_with_nothing_installed(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    assert _candidate(home).path == home / ".workbuddy" / "projects"


def test_an_explicit_config_dir_still_overrides(tmp_path) -> None:
    home = tmp_path / "home"
    configured = tmp_path / "configured"

    candidate = _candidate(home, {"WORKBUDDY_CONFIG_DIR": str(configured)})

    assert candidate.path == configured / "projects"
    assert candidate.kind is RootCandidateKind.ENVIRONMENT_OVERRIDE


def test_declared_default_homes_still_pair_the_two_directories(tmp_path) -> None:
    """`follow_default_home` moves grants between the app's own homes.

    `.codebuddy` remains listed so an existing grant recorded against it can
    still be followed to the new root; keeping it here is not a second
    candidate.
    """
    home = tmp_path / "home"

    assert workbuddy_default_homes(home) == (
        home / ".codebuddy" / "projects",
        home / ".workbuddy" / "projects",
    )
