import json

from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import (
    MemoryDraft,
    MemoryGovernanceStore,
    MemoryKind,
)
from one_memory.recall import GovernedRecallTarget, RecallRequest
from tests.person_door import as_person


def evidence(database, *, message_id: str, verbatim: str) -> str:
    return (
        EvidenceStore(database)
        .put(
            EvidenceInput(
                source_id="cursor",
                conversation_id="c",
                message_id=message_id,
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim=verbatim,
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            )
        )
        .record.evidence_id
    )


def library(tmp_path):
    store = MemoryGovernanceStore(tmp_path / "synthetic.sqlite3")
    rows = [
        (
            "accessible",
            "local",
            "chat",
            "confirmed",
            "Project meeting Friday",
            '["all-apps"]',
            1,
            "2026-01-01",
            "2026-01-01",
        ),
        *[
            (
                f"private-{i}",
                "local",
                "chat",
                "confirmed",
                "Project meeting Friday",
                '["private-project"]',
                1,
                "2026-09-01",
                "2026-09-01",
            )
            for i in range(205)
        ],
    ]
    with store._connection() as connection:
        connection.executemany(
            "INSERT INTO governed_memories (memory_id,user_id,kind,status,content,scopes_json,"
            "revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return store


def test_other_scopes_cannot_consume_the_recall_candidate_budget(tmp_path):
    result = GovernedRecallTarget(library(tmp_path)).recall(RecallRequest(query="Project meeting"))
    assert [hit.memory_id for hit in result.hits] == ["accessible"]
    assert result.truncated is False
    assert result.unexamined_count == 0


def test_internal_wildcard_still_reports_real_candidate_truncation(tmp_path):
    result = GovernedRecallTarget(library(tmp_path)).recall(
        RecallRequest(query="Project meeting", scope="*")
    )
    assert result.hits
    assert result.truncated is True


def test_workspace_resolution_does_not_remove_shared_results(tmp_path):
    store = library(tmp_path)
    with store._connection() as connection:
        connection.execute(
            "UPDATE governed_memories SET scopes_json=? WHERE memory_id='private-0'",
            (json.dumps(["workspace-target"]),),
        )
    result = GovernedRecallTarget(store, resolve_workspace=lambda _: ("workspace-target",)).recall(
        RecallRequest(query="Project meeting", workspace_path="/synthetic/project")
    )
    assert {hit.memory_id for hit in result.hits} == {"accessible", "private-0"}


def test_empty_or_unknown_scope_never_falls_back_to_all_scopes(tmp_path):
    store = library(tmp_path)
    result = GovernedRecallTarget(store).recall(
        RecallRequest(query="Project meeting", scope="unavailable")
    )
    assert result.hits == ()
    assert result.truncated is False


def scoped(tmp_path, *scopes):
    """One confirmed memory per scope, all matching the same query."""
    store = MemoryGovernanceStore(tmp_path / "scoped.sqlite3")
    with store._connection() as connection:
        connection.executemany(
            "INSERT INTO governed_memories (memory_id,user_id,kind,status,content,scopes_json,"
            "revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    f"memory-{index}",
                    "local",
                    "chat",
                    "confirmed",
                    "Project meeting Friday",
                    json.dumps([scope]),
                    1,
                    "2026-01-01",
                    "2026-01-01",
                )
                for index, scope in enumerate(scopes)
            ],
        )
    return store


def test_no_readable_scope_returns_nothing_rather_than_the_whole_library(tmp_path):
    """The empty set is an answer, not a missing filter.

    A caller that resolves to no readable scope is asking for nothing. Read
    as "no narrowing requested" it would instead hand back every confirmed
    memory in the library, so this is asserted at the store rather than
    through recall, which today always carries at least its own scope.
    """
    store = library(tmp_path)
    assert store.find_confirmed_matching_terms(user_id="local", terms=["project"], scopes=()) == (
        [],
        False,
    )


def readable_ids(store, *scopes):
    """What the candidate query itself considers readable.

    Asserted here rather than through `recall` on purpose. `_recall` keeps a
    second scope check in Python over whatever the query returns, so an
    over-broad SQL predicate still produces the right hits while quietly
    spending the candidate budget on rows that get dropped. Going through
    recall would therefore pass no matter what this predicate does, which is
    the bug being guarded against, not a guard.
    """
    matches, more = store.find_confirmed_matching_terms(
        user_id="local", terms=["project"], scopes=scopes
    )
    return [memory.memory_id for memory in matches], more


def test_a_scope_that_is_a_prefix_of_another_does_not_read_it(tmp_path):
    """Scope membership, not string containment.

    Workspace scopes are opaque ids that share long prefixes, so matching
    the stored JSON as text would let one project read another's memories.
    """
    store = scoped(tmp_path, "private-project", "private-project-archive")
    assert readable_ids(store, "private-project") == (["memory-0"], False)


def test_scope_names_with_quotes_and_wildcards_match_literally(tmp_path):
    """Neither SQL quoting nor LIKE wildcards get a say in what is readable."""
    store = scoped(tmp_path, "team's %-project", "team-any-project")
    assert readable_ids(store, "team's %-project") == (["memory-0"], False)


def test_scope_matching_is_case_sensitive(tmp_path):
    """Opaque ids differing only in case are different scopes, not the same one."""
    store = scoped(tmp_path, "All-Apps")
    assert readable_ids(store, "all-apps") == ([], False)


def test_a_selective_terms_only_match_is_not_crowded_out_by_a_common_term(tmp_path):
    """Every query term with an eligible match must be represented.

    The shadow candidate set used to take one global `ORDER BY count(*) DESC
    LIMIT n`, so when a common term had `n` matching memories the page filled
    before a rarer term's single match — the user's exact word was unreachable
    at the default cap even though `terms=("rare",)` found it. Candidate
    selection now reserves one representative per distinct term with an
    eligible match, then fills the rest by the existing match-count ranking.
    """
    database = tmp_path / "crowding.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(300):
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"common seed {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence(database, message_id=f"common-{index}", verbatim="甲"),),
            ),
            request_id=f"common-{index}",
            memory_id=f"common-{index:04d}",
        )
    door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="the rare zeta decision",
            scopes=("all-apps",),
            evidence_ids=(evidence(database, message_id="rare-1", verbatim="乙"),),
        ),
        request_id="rare-1",
        memory_id="zzz-rare",
    )
    # Confirm the maintained shadow is trusted, so this exercises the candidate
    # path and not the exact LIKE fallback.
    with store._connection() as connection:
        covered = connection.execute(
            "SELECT (SELECT count(*) FROM governed_memories_terms_meta)"
            " = (SELECT count(*) FROM governed_memories WHERE status != 'deleted')"
        ).fetchone()[0]
    assert bool(covered) is True

    # Rare alone is found.
    only, _ = store.find_confirmed_matching_terms(user_id="local", terms=("rare",))
    assert {m.memory_id for m in only} == {"zzz-rare"}

    # With the common term crowding the page (limit below the common count),
    # the rare term's only match must still be present, in either order.
    for terms in (("rare", "common"), ("common", "rare")):
        found, more = store.find_confirmed_matching_terms(user_id="local", terms=terms, limit=200)
        assert "zzz-rare" in {m.memory_id for m in found}, terms
        assert more is True  # the common term has more matches than the page
