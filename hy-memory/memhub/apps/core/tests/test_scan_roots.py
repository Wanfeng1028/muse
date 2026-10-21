"""A4-01: scan root configuration."""

from __future__ import annotations

import pytest

from one_memory.memory_server.scan_roots import (
    ScanRoot,
    ScanRootConfig,
    add_root,
    canonical,
    changed_since,
    enabled_roots,
    remove_root,
    roots_for_source,
    set_enabled,
    validate,
)


def _root(root_id: str, path: str, **kwargs: object) -> ScanRoot:
    return ScanRoot(root_id=root_id, path=path, **kwargs)  # type: ignore[arg-type]


def test_paths_are_canonicalised() -> None:
    assert canonical("/tmp/a/") == "/tmp/a"
    assert canonical(" /tmp/a ") == "/tmp/a"


def test_an_empty_config_is_valid() -> None:
    assert validate(ScanRootConfig()) == []


def test_a_negative_revision_is_a_problem() -> None:
    assert validate(ScanRootConfig(revision=-1)) == ["revision must not be negative"]


def test_adding_a_root_bumps_the_revision() -> None:
    """Adapters need a revision to know their view is stale."""
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert config.revision == 1


def test_a_duplicate_path_is_refused() -> None:
    """One directory twice would be swept twice and counted twice."""
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    with pytest.raises(ValueError):
        add_root(config, _root("r2", "/tmp/a/"))


def test_a_duplicate_id_is_refused() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    with pytest.raises(ValueError):
        add_root(config, _root("r1", "/tmp/b"))


def test_an_empty_path_is_refused() -> None:
    with pytest.raises(ValueError):
        add_root(ScanRootConfig(), _root("r1", " "))


def test_scan_root_state_removal_bumps_the_revision() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert remove_root(config, "r1").revision == 2


def test_removing_an_unknown_root_changes_nothing() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert remove_root(config, "nope") is config


def test_disabling_a_root_bumps_the_revision() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert set_enabled(config, "r1", False).revision == 2


def test_disabling_to_the_same_value_changes_nothing() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert set_enabled(config, "r1", True) is config


def test_enabled_roots_excludes_disabled() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert enabled_roots(set_enabled(config, "r1", False)) == ()


def test_roots_can_be_selected_by_source() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a", source_id="cursor"))
    assert [root.root_id for root in roots_for_source(config, "cursor")] == ["r1"]
    assert roots_for_source(config, "codex") == ()


def test_changed_since_detects_stale_views() -> None:
    config = add_root(ScanRootConfig(), _root("r1", "/tmp/a"))
    assert changed_since(config, 0) is True
    assert changed_since(config, 1) is False
