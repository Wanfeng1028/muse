"""Revocation is the node: nothing from that source is read afterwards (D73).

Both the memory page and the host read path drop a revoked source's memories,
so a revoked citation is never handed out again. Note for D73 point 4: the
decision says memories generated before the node stay; the shipped read paths
filter by grant instead, so they hide them too. This test locks the shipped
behaviour; keeping pre-revocation memories visible is a separate product call.
"""

import sqlite3
from contextlib import closing

import pytest

from one_memory.memory_library import read_memory_library
from one_memory.source_read_access import SourceReadAccess
from tests.test_memory_library import NOW, put
from tests.test_memory_library import database as library_fixture  # noqa: F401


@pytest.fixture
def database(library_fixture):  # noqa: F811
    return library_fixture


def test_a_revoked_source_is_not_read_by_the_page_or_the_host(database):
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "kept", links=("e2",))
        put(db, "revoked-source-memory", links=("e1",))
        db.execute(
            "INSERT INTO source_grants(user_id,source_id,root_path,candidate_kind,"
            "granted_at,revoked_at) VALUES('local','cursor','/synthetic','default',?,?)",
            (NOW, NOW),
        )

    page = read_memory_library(database)
    # Revoked citations are not handed out, by the page or by a host.
    assert {item.memory_id for item in page.items} == {"kept"}

    # The read path a host uses does drop the revoked source's memory.
    readable = {item.memory_id for item in SourceReadAccess(database).memories(page.items)}
    assert readable == {"kept"}
