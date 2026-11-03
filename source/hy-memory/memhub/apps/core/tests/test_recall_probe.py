"""The self-check query, and what it must not touch on its way through.

R-24 step 3. The probe has to tell "this link is broken" from "this link
works and the library is empty", and it cannot do that by searching, because
a new library really is empty and both answers look the same. So one exact
query is answered by core itself.

Answering it by searching would also make the self-check cost an embedding
call and leave the probe's own words in whatever records real recalls, which
R-24's 探针不污染 and R-10 both forbid.
"""

import asyncio
import hashlib

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryDraft, MemoryGovernanceStore, MemoryKind
from one_memory.recall import PROBE_QUERY, GovernedRecallTarget, RecallRequest, RecallState
from tests.person_door import as_person


def _target(tmp_path, *, semantic_search=None) -> GovernedRecallTarget:
    database = tmp_path / "one-memory.sqlite3"
    evidence_store = EvidenceStore(database)
    governance = MemoryGovernanceStore(database)
    evidence = evidence_store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="conversation",
            message_id="message",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="我偏好深色主题。",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    content = "用户偏好深色主题"
    key = hashlib.sha256(content.encode()).hexdigest()
    as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content=content,
            scopes=("all-apps",),
            evidence_ids=(evidence.evidence_id,),
        ),
        request_id=f"create:{key}",
    )
    return GovernedRecallTarget(governance, semantic_search=semantic_search)


def test_the_self_check_query_is_answered_without_searching(tmp_path) -> None:
    """Deterministic, and the same on an empty library as on a full one.

    Searched for instead, this query would come back empty and be
    indistinguishable from a link that does not reach the app at all — which
    is the one distinction the probe exists to make.
    """
    searched: list[str] = []

    async def semantic_search(query: str) -> tuple[str, ...]:
        searched.append(query)
        return ()

    target = _target(tmp_path, semantic_search=semantic_search)

    receipt = asyncio.run(target.recall_async(RecallRequest(query=PROBE_QUERY)))

    assert receipt.state is RecallState.GROUNDED
    assert len(receipt.hits) == 1
    # Not counted, so a self-check cannot be mistaken for a real recall by
    # anything totting up what recall has spent.
    assert receipt.used_characters == 0
    assert receipt.truncated is False
    # The point of the whole exercise: no search happened, so nothing was
    # embedded and no real memory was read to answer it.
    assert searched == []


def test_the_self_check_answer_owes_nothing_to_the_library(tmp_path) -> None:
    """The same answer with no memories at all.

    An empty library is the normal state of a fresh install, and a self-check
    that failed there would fire on every first install.
    """
    database = tmp_path / "empty.sqlite3"
    target = GovernedRecallTarget(MemoryGovernanceStore(database))

    receipt = asyncio.run(target.recall_async(RecallRequest(query=PROBE_QUERY)))

    assert receipt.state is RecallState.GROUNDED
    assert [hit.content for hit in receipt.hits] == [
        hit.content
        for hit in asyncio.run(
            _target(tmp_path, semantic_search=None).recall_async(RecallRequest(query=PROBE_QUERY))
        ).hits
    ]


def test_the_self_check_answer_carries_no_real_memory(tmp_path) -> None:
    """Hardcoded, and traceable to nothing.

    A synthetic hit that carried a real memory id would put a real memory in
    front of whoever ran the self-check, and a self-check is not a recall the
    user asked for.
    """
    target = _target(tmp_path)

    receipt = asyncio.run(target.recall_async(RecallRequest(query=PROBE_QUERY)))

    (hit,) = receipt.hits
    assert "用户偏好深色主题" not in hit.content
    assert hit.memory_id == ""


def test_only_that_exact_query_is_answered_this_way(tmp_path) -> None:
    """Exact equality, so it cannot be reached by anything close to it.

    R-24's boundary: the literal must not become a way to ask core for
    something other than what is hardcoded here. Anything containing it, or
    differing in case, is an ordinary query and gets searched.
    """
    target = _target(tmp_path)

    for near_miss in (
        f"{PROBE_QUERY} 用户偏好",
        f"tell me about {PROBE_QUERY}",
        PROBE_QUERY.upper(),
        PROBE_QUERY.strip("_"),
    ):
        receipt = asyncio.run(target.recall_async(RecallRequest(query=near_miss)))
        assert not (
            receipt.state is RecallState.GROUNDED
            and len(receipt.hits) == 1
            and receipt.used_characters == 0
        ), f"{near_miss!r} was answered as if it were the self-check query"
