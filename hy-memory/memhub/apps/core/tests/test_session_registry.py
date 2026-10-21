"""Trusted session identity is not a workspace path."""

import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from one_memory.session_registry import (
    AmbiguousWorkspace,
    ForgedSession,
    SessionRegistry,
)


def database(tmp_path):
    path = tmp_path / "one-memory.sqlite3"
    with closing(sqlite3.connect(path)):
        pass
    registry = SessionRegistry(path)
    registry.initialize()
    return registry


def test_same_directory_does_not_collapse_two_main_sessions(tmp_path) -> None:
    registry = database(tmp_path)
    installation = str(uuid4())
    shared = dict(
        installation_id=installation,
        host_id="workbuddy",
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    first = registry.open(**shared, native_session_id="session-a")
    second = registry.open(**shared, native_session_id="session-b")

    assert first.session_key != second.session_key
    with pytest.raises(AmbiguousWorkspace):
        registry.sole_session("/work/same-project")


def test_forged_session_key_is_rejected(tmp_path) -> None:
    registry = database(tmp_path)
    with pytest.raises(ForgedSession):
        registry.require("0" * 64)


def test_resume_keeps_the_same_trusted_session(tmp_path) -> None:
    registry = database(tmp_path)
    shared = dict(
        installation_id=str(uuid4()),
        host_id="workbuddy",
        native_session_id="session-a",
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    first = registry.open(**shared)
    again = registry.open(**shared)
    assert again.session_key == first.session_key
    assert len(registry.in_workspace("/work/same-project")) == 1
