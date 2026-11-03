import hashlib

import pytest

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryDraft, MemoryGovernanceStore, MemoryKind
from one_memory.recall import (
    GovernedRecallTarget,
    RecallRequest,
    RecallState,
    TruncationBudget,
)
from tests.person_door import as_person

pytestmark = pytest.mark.contract


def _confirmed(governance, evidence_id, *, content: str, scope: str = "all-apps"):
    key = hashlib.sha256(f"{scope}:{content}".encode()).hexdigest()
    memory = as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content=content,
            scopes=(scope,),
            evidence_ids=(evidence_id,),
        ),
        request_id=f"create:{key}",
    )
    return memory


def _library(tmp_path, *, filler: int):
    """A memory the query matches, buried under `filler` newer memories."""
    database = tmp_path / "one-memory.sqlite3"
    evidence = (
        EvidenceStore(database)
        .put(
            EvidenceInput(
                source_id="cursor",
                conversation_id="c",
                message_id="m",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="我的花名是麒麟。",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            )
        )
        .record
    )
    governance = MemoryGovernanceStore(database)
    target = _confirmed(governance, evidence.evidence_id, content="用户的花名是麒麟")
    for index in range(filler):
        _confirmed(governance, evidence.evidence_id, content=f"无关记忆条目 filler{index}")
    return governance, target


def test_recall_reaches_a_memory_that_is_not_among_the_newest_500(tmp_path) -> None:
    """Recall must not go silently blind once the library outgrows one page.

    `GovernedRecallTarget` scores whatever `governance.list` hands back, and
    that list is one `ORDER BY updated_at DESC LIMIT 500` page. Everything
    older than the newest 500 confirmed memories stops being reachable, and
    the caller is told `empty` rather than told it was truncated — the one
    failure mode this product cannot afford, because it looks exactly like
    "you have no such memory".

    501 is deliberate: with 500 the same query still succeeds, so this pins
    the boundary rather than merely a large library.
    """
    governance, target = _library(tmp_path, filler=500)

    receipt = GovernedRecallTarget(governance).recall(RecallRequest(query="花名"))

    assert receipt.state is RecallState.GROUNDED
    assert target.memory_id in {hit.memory_id for hit in receipt.hits}


@pytest.mark.anyio
async def test_semantic_recall_reaches_a_memory_outside_the_newest_500(tmp_path) -> None:
    """A precise HY semantic hit must survive the page boundary.

    Semantic ids are only consulted while iterating the same 500-row page
    (`recall.py`, `semantic_rank.get`), so a memory HY ranked first is
    dropped for the sole reason that it is not recent. This is the path
    users reach for when literal wording fails, so losing it here removes
    the fallback exactly when it is needed.
    """
    governance, target = _library(tmp_path, filler=600)

    async def semantic_search(_query: str) -> tuple[str, ...]:
        return (target.memory_id,)

    receipt = await GovernedRecallTarget(
        governance,
        semantic_search=semantic_search,
    ).recall_async(RecallRequest(query="这个人平时都怎么被称呼"))

    assert receipt.state is RecallState.GROUNDED
    assert target.memory_id in {hit.memory_id for hit in receipt.hits}


def test_recall_still_works_just_below_the_boundary(tmp_path) -> None:
    """Control: proves the two tests above fail on size, not on wording.

    Without this a broken query or a bad fixture would look identical to the
    defect, and the fix could be declared done by making recall match nothing.
    """
    governance, target = _library(tmp_path, filler=499)

    receipt = GovernedRecallTarget(governance).recall(RecallRequest(query="花名"))

    assert receipt.state is RecallState.GROUNDED
    assert target.memory_id in {hit.memory_id for hit in receipt.hits}


def test_recall_reaches_a_memory_in_a_5000_library(tmp_path) -> None:
    """Acceptance: filter pushdown must not degrade into a deferred cliff at 5k.

    Fillers are bulk-inserted so the test measures recall, not confirm latency.
    """
    governance, target = _library(tmp_path, filler=0)
    _bulk_filler(governance, count=5_000)

    receipt = GovernedRecallTarget(governance).recall(RecallRequest(query="花名"))

    assert receipt.state is RecallState.GROUNDED
    assert target.memory_id in {hit.memory_id for hit in receipt.hits}


def test_character_budget_names_the_budget_that_fired(tmp_path) -> None:
    """Truncation must say which of the three budgets stopped the reply."""
    governance, target = _library(tmp_path, filler=0)
    evidence_id = target.evidence_ids[0]
    _confirmed(
        governance,
        evidence_id,
        content="花名" + ("详" * 300),
    )

    receipt = GovernedRecallTarget(governance).recall(
        RecallRequest(query="花名", character_budget=200)
    )

    assert receipt.state is RecallState.GROUNDED
    assert receipt.truncated is True
    assert receipt.truncated_by is TruncationBudget.CHARACTER
    assert target.memory_id in {hit.memory_id for hit in receipt.hits}


def _bulk_filler(governance: MemoryGovernanceStore, *, count: int) -> None:
    """Insert confirmed filler rows without per-row create/confirm overhead."""
    now = "2026-09-07T12:00:00+00:00"
    rows = [
        (
            f"filler-{index:05d}",
            "local",
            "chat",
            "confirmed",
            f"无关记忆条目 filler{index}",
            '["all-apps"]',
            1,
            now,
            now,
        )
        for index in range(count)
    ]
    with governance._connection() as connection:
        connection.executemany(
            """
            INSERT INTO governed_memories (
                memory_id, user_id, kind, status, content, scopes_json,
                revision, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
