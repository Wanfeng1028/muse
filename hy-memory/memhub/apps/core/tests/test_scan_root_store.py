"""A4-01: scan-root configuration persists, and refuses what it must."""

import tempfile
from pathlib import Path

import pytest

from one_memory.memory_server.scan_root_store import ScanRootStore, new_root_id
from one_memory.memory_server.scan_roots import ScanRoot, ScanRootConfig


def _store(tmp_path: Path) -> ScanRootStore:
    store = ScanRootStore(tmp_path / "scan_roots.sqlite3")
    store.initialize()
    return store


def test_a_root_survives_a_new_store(tmp_path) -> None:
    """Registered directories are user intent; losing them on restart would
    silently stop importing and look like a scanning bug."""
    path = tempfile.mkdtemp()
    root = ScanRoot(root_id=new_root_id(path, "codex"), path=path, source_id="codex")
    store = _store(tmp_path)
    store.save(ScanRootConfig(roots=(root,), revision=1))

    reopened = _store(tmp_path)
    config = reopened.get()
    assert [(item.path, item.source_id) for item in config.roots] == [(path, "codex")]
    assert config.revision == 1


def test_the_same_directory_twice_is_refused(tmp_path) -> None:
    """One directory registered twice would be swept twice and every file
    counted twice, which presents as a scanning bug rather than the
    configuration mistake it is."""
    path = tempfile.mkdtemp()
    root = ScanRoot(root_id=new_root_id(path, "codex"), path=path, source_id="codex")
    store = _store(tmp_path)
    store.save(ScanRootConfig(roots=(root,), revision=1))
    with pytest.raises(ValueError, match="duplicate"):
        store.save(ScanRootConfig(roots=(root, root), revision=2))


def test_scan_root_store_persists_the_removal_revision(tmp_path) -> None:
    """Adapters read roots as intent; without a revision they cannot tell a
    stale view from a current one."""
    path = tempfile.mkdtemp()
    root = ScanRoot(root_id=new_root_id(path, "codex"), path=path, source_id="codex")
    store = _store(tmp_path)
    store.save(ScanRootConfig(roots=(root,), revision=1))
    store.save(ScanRootConfig(roots=(), revision=2))
    config = store.get()
    assert config.roots == ()
    assert config.revision == 2


def test_an_empty_database_reads_as_no_configuration(tmp_path) -> None:
    store = ScanRootStore(tmp_path / "fresh.sqlite3")
    config = store.get()
    assert config.roots == ()
    assert config.revision == 0
