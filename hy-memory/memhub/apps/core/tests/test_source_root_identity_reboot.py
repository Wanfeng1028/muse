import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from one_memory.imports.access import SourceAccessError, SourceAccessErrorCode
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.sources.registry import RootCandidateKind


def _identity_recorded_on_another_boot(root: Path, *, inode_offset: int = 0) -> str:
    """The stable formula a previous boot recorded, without that boot's device number."""
    resolved = root.resolve(strict=True)
    details = resolved.stat()
    identity = (
        f"{resolved}\0{details.st_ino + inode_offset}:"
        f"{details.st_mode}:{details.st_uid}:{details.st_gid}"
    )
    return "root:v2:" + hashlib.sha256(identity.encode()).hexdigest()


def _granted_before_reboot(tmp_path: Path, *, inode_offset: int = 0):
    home = tmp_path / "home"
    source = home / ".codebuddy" / "projects"
    source.mkdir(parents=True)
    database = tmp_path / "one-memory.sqlite3"
    store = SourceGrantStore(database, home=home)
    store.grant(
        user_id="local",
        source_id="workbuddy",
        root=source,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    recorded = _identity_recorded_on_another_boot(source, inode_offset=inode_offset)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE source_grants SET root_identity=? WHERE source_id='workbuddy'",
            (recorded,),
        )
    return store, recorded


def test_a_grant_survives_the_volume_being_renumbered_after_a_restart(tmp_path) -> None:
    store, recorded = _granted_before_reboot(tmp_path)

    assert store.authorized_root(user_id="local", source_id="workbuddy") is not None
    assert store.require_receipt(user_id="local", source_id="workbuddy").root_id == recorded


def test_a_replaced_directory_is_still_refused_after_a_restart(tmp_path) -> None:
    store, _ = _granted_before_reboot(tmp_path, inode_offset=1)

    with pytest.raises(SourceAccessError) as refused:
        store.authorized_root(user_id="local", source_id="workbuddy")
    assert refused.value.code is SourceAccessErrorCode.SOURCE_IDENTITY_CHANGED


def test_the_identity_no_longer_depends_on_the_device_number(tmp_path) -> None:
    from one_memory.imports.access import source_root_identity

    root = tmp_path / "root"
    root.mkdir()
    details = os.stat(root)
    with_device = (
        f"{root.resolve()}\0{details.st_dev}:{details.st_ino}:"
        f"{details.st_mode}:{details.st_uid}:{details.st_gid}"
    )
    assert source_root_identity(root) != (
        "root:v2:" + hashlib.sha256(with_device.encode()).hexdigest()
    )
