"""3925a kernel item 1: two-level discovery.

"Installed but no sessions yet" and "not installed at all" are different
answers. `detect()` used to collapse them: it returned True only when a
`.jsonl` was found, so a host directory that exists and is empty read as
absent, and the UI could only say "not found".

The agreed-on contract:
  * the agreed root directory existing means "installed, no sessions found"
    -> `detect()` returns True;
  * zero sessions in the default root falls back to the host's translated
    home (`$HOME/.tcodex`, else `$HOME/.tclaude`) by a deterministic rule,
    never by guessing which directory was written last;
  * a cached "not discovered" must be invalidatable, so installing after a
    first probe is visible on the next probe.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from one_memory.imports.access import AuthorizedSourceRoot
from one_memory.imports.sources.codex import CODEX_DESCRIPTOR, create_codex_adapter
from one_memory.imports.sources.common import JsonlSourceAdapter
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog


def _grant(source_id: str, root: Path, home: Path) -> AuthorizedSourceRoot:
    return AuthorizedSourceRoot.grant(
        source_id=source_id,
        root=root,
        user_confirmed=True,
        home=home,
    )


def _codex_adapter(root: Path, home: Path) -> JsonlSourceAdapter:
    return create_codex_adapter(_grant(CODEX_DESCRIPTOR.source_id, root, home))


def test_detect_is_true_when_the_agreed_root_exists_with_zero_sessions(tmp_path) -> None:
    """The first red assertion: an existing but empty root is "installed"."""
    home = tmp_path / "home"
    root = home / ".codex" / "sessions"
    root.mkdir(parents=True)

    assert asyncio.run(_codex_adapter(root, home).detect()) is True


def test_detect_reports_installed_and_session_count_separately(tmp_path) -> None:
    """Two levels: install state is not the same number as sessions found."""
    home = tmp_path / "home"
    root = home / ".codex" / "sessions"
    root.mkdir(parents=True)

    empty = asyncio.run(_codex_adapter(root, home).install_state())
    assert empty.installed is True
    assert empty.session_count == 0
    assert empty.detected is True

    (root / "rollout-one.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "rollout-two.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "unrelated.txt").write_text("notes", encoding="utf-8")
    filled = asyncio.run(_codex_adapter(root, home).install_state())
    assert filled.installed is True
    assert filled.session_count == 2


def test_a_cached_not_discovered_answer_can_be_invalidated(tmp_path) -> None:
    """Installing after a first probe must be visible on the next probe."""
    home = tmp_path / "home"
    root = home / ".codex" / "sessions"
    root.mkdir(parents=True)
    adapter = _codex_adapter(root, home)

    assert asyncio.run(adapter.detect()) is True

    (root / "rollout-later.jsonl").write_text("{}\n", encoding="utf-8")
    state = asyncio.run(adapter.install_state())

    assert state.detected is True
    assert state.session_count == 1


def test_detect_does_not_read_conversation_contents(tmp_path) -> None:
    """Metadata only: install detection stays a directory-level answer."""
    home = tmp_path / "home"
    root = home / ".codex" / "sessions"
    root.mkdir(parents=True)
    secret = root / "rollout-secret.jsonl"
    secret.write_text('{"secret":"private"}\n', encoding="utf-8")

    opened: list[Path] = []
    real_open = os.open

    def traced_open(path, *args, **kwargs):
        opened.append(Path(path))
        return real_open(path, *args, **kwargs)

    adapter = _codex_adapter(root, home)
    os.open = traced_open  # type: ignore[assignment]
    try:
        assert asyncio.run(adapter.detect()) is True
    finally:
        os.open = real_open  # type: ignore[assignment]

    assert secret not in opened


def test_zero_sessions_falls_back_to_a_translated_home_in_declared_order(tmp_path) -> None:
    """No mtime guessing: `.tcodex` before `.tclaude`, whichever exists.

    Both orders of `st_mtime` must give the same answer, because "written
    most recently" says nothing about where the history lives.
    """
    home = tmp_path / "home"
    agreed = home / ".codex" / "sessions"
    agreed.mkdir(parents=True)
    tcodex = home / ".tcodex" / "sessions"
    tclaude = home / ".tclaude" / "sessions"
    tcodex.mkdir(parents=True)
    tclaude.mkdir(parents=True)
    for directory in (tcodex, tclaude):
        (directory / "rollout-x.jsonl").write_text("{}\n", encoding="utf-8")

    def resolve(newest_first: bool) -> Path:
        newest, oldest = (tclaude, tcodex) if newest_first else (tcodex, tclaude)
        for index, directory in enumerate((newest, oldest)):
            for child in directory.iterdir():
                os.utime(child, (1_800_000_000 - index, 1_800_000_000 - index))
        return build_source_catalog(home=home, environment={})["codex"].candidate.path

    assert resolve(newest_first=True) == tcodex
    assert resolve(newest_first=False) == tcodex


def test_an_empty_translated_home_does_not_replace_the_agreed_root(tmp_path) -> None:
    """A translated home with no transcripts is not a better answer."""
    home = tmp_path / "home"
    agreed = home / ".codex" / "sessions"
    agreed.mkdir(parents=True)
    (home / ".tcodex" / "sessions").mkdir(parents=True)

    candidate = build_source_catalog(home=home, environment={})["codex"].candidate

    assert candidate.path == agreed
    assert candidate.kind is RootCandidateKind.DEFAULT


def test_the_agreed_root_with_sessions_beats_a_translated_home(tmp_path) -> None:
    home = tmp_path / "home"
    agreed = home / ".codex" / "sessions"
    agreed.mkdir(parents=True)
    (agreed / "rollout-agreed.jsonl").write_text("{}\n", encoding="utf-8")
    translated = home / ".tcodex" / "sessions"
    translated.mkdir(parents=True)
    (translated / "rollout-translated.jsonl").write_text("{}\n", encoding="utf-8")
    os.utime(translated / "rollout-translated.jsonl", (1_900_000_000, 1_900_000_000))

    candidate = build_source_catalog(home=home, environment={})["codex"].candidate

    assert candidate.path == agreed


@pytest.mark.parametrize("contents", [(), ("subdirectory",)])
def test_install_state_is_installed_for_any_existing_root(tmp_path, contents) -> None:
    home = tmp_path / "home"
    root = home / ".codex" / "sessions"
    root.mkdir(parents=True)
    for name in contents:
        (root / name).mkdir()

    state = asyncio.run(_codex_adapter(root, home).install_state())

    assert state.installed is True
    assert state.detected is True
    assert state.session_count == 0
