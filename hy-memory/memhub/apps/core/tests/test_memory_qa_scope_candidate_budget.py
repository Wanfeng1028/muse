"""The light Q&A path spends its candidate page the same way recall did.

`GovernedRecallTarget` filtered scope after SQL had already taken the newest
page, so memories from other projects crowded out readable ones. The answerer
reads `governance.list(..., limit=500)` — the whole library's newest page, with
no term filter at all — and then narrows by scope in Python, which is the same
defect with a wider page and no truncation signal on the receipt.
"""

import asyncio

from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.memory_qa import MemoryAnswerer
from one_memory.model_profiles import ModelProfileStore
from one_memory.secrets import InMemorySecretStore

QUESTION = "看板要用真实数据还是 mock 数据？"
CONTENT = "用户要求产品看板使用真实数据，不能使用 mock 数据。"


def library(tmp_path, *, crowd: int):
    """One older readable memory, buried under newer ones from another project."""
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    rows = [
        (
            "accessible",
            "local",
            "working",
            "confirmed",
            CONTENT,
            '["all-apps"]',
            1,
            "2026-01-01",
            "2026-01-01",
        ),
        *[
            (
                f"private-{index}",
                "local",
                "working",
                "confirmed",
                CONTENT,
                '["private-project"]',
                1,
                "2026-09-01",
                "2026-09-01",
            )
            for index in range(crowd)
        ],
    ]
    with store._connection() as connection:
        connection.executemany(
            "INSERT INTO governed_memories (memory_id,user_id,kind,status,content,scopes_json,"
            "revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return MemoryAnswerer(
        governance=store,
        profiles=ModelProfileStore(database),
        secrets=InMemorySecretStore(),
    )


def retrieved(answerer, **kwargs):
    return [memory.memory_id for memory in asyncio.run(answerer.retrieve(QUESTION, **kwargs))]


def test_a_small_library_finds_the_readable_memory(tmp_path):
    """The positive control.

    Without it, the test below could pass because the question never matched
    anything rather than because scope narrowing happens early enough.
    """
    assert retrieved(library(tmp_path, crowd=3)) == ["accessible"]


def test_other_scopes_cannot_consume_the_answer_candidate_page(tmp_path):
    """Same memory, same question, only the unreadable neighbours grew."""
    assert retrieved(library(tmp_path, crowd=520)) == ["accessible"]


def test_no_readable_scope_lists_nothing_rather_than_the_whole_library(tmp_path):
    """The empty set is an answer, not a missing filter.

    Asserted on the store because the answerer always carries at least its
    own scope, so nothing above it can reach this case today. Read as "no
    narrowing requested" it would hand back the entire confirmed library.
    """
    store = library(tmp_path, crowd=3).governance
    assert store.list(user_id="local", scopes=()) == []
    assert [memory.memory_id for memory in store.list(user_id="local")] != []
