import sqlite3
import threading

import pytest
from pydantic import ValidationError

from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.library_upgrade import LibraryUpgradeError
from one_memory.memory_governance import (
    CONTENT_CANDIDATE_UNION_VERSION,
    DeletionStatus,
    HySupersede,
    MemoryDraft,
    MemoryGovernanceStore,
    MemoryKind,
    MemoryMutationConflictError,
    MemoryMutationRequestConflictError,
    MemoryOrigin,
    MemoryStatus,
    content_candidate_plan,
    content_candidate_predicate,
    ensure_content_candidate_index,
)
from tests.person_door import as_person


def evidence(database, *, message_id: str, verbatim: str, user_id: str = "local") -> str:
    result = EvidenceStore(database).put(
        EvidenceInput(
            user_id=user_id,
            source_id="cursor",
            conversation_id="conversation",
            message_id=message_id,
            correlation_id=message_id,
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim=verbatim,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    )
    return result.record.evidence_id


def test_correction_keeps_verbatim_and_appends_history(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Original words")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="Initial extraction",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )

    corrected = as_person(store).correct(
        created.memory_id,
        user_id="local",
        request_id="correct-1",
        expected_revision=1,
        content="Corrected memory",
        scopes=("cursor", "claude-code"),
    )
    undone = as_person(store).undo(
        created.memory_id,
        user_id="local",
        request_id="undo-1",
        expected_revision=2,
    )

    assert created.status is MemoryStatus.CONFIRMED
    assert corrected.content == "Corrected memory"
    assert corrected.scopes == ("cursor", "claude-code")
    assert undone.content == "Initial extraction"
    assert undone.status is MemoryStatus.CONFIRMED
    assert [version.action for version in store.history(created.memory_id, user_id="local")] == [
        "undo",
        "correct",
        "create",
    ]
    assert EvidenceStore(database).get(evidence_id).verbatim == "Original words"  # type: ignore[union-attr]


def test_mutations_are_revision_checked_and_request_idempotent(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Original")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.WORKING,
            content="Candidate",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )

    first = as_person(store).delete(
        created.memory_id,
        user_id="local",
        request_id="delete-1",
        expected_revision=1,
    )
    duplicate = as_person(store).delete(
        created.memory_id,
        user_id="local",
        request_id="delete-1",
        expected_revision=1,
    )

    assert first == duplicate
    with pytest.raises(MemoryMutationConflictError):
        as_person(store).correct(
            created.memory_id,
            user_id="local",
            request_id="stale",
            expected_revision=1,
            content="Stale correction",
        )
    with pytest.raises(MemoryMutationRequestConflictError):
        as_person(store).undo(
            created.memory_id,
            user_id="local",
            request_id="delete-1",
            expected_revision=2,
        )
    with pytest.raises(MemoryMutationConflictError, match="memory_deleted"):
        as_person(store).correct(
            created.memory_id,
            user_id="local",
            request_id="deleted-correction",
            expected_revision=2,
            content="Must not be stored",
        )


def test_delete_result_survives_restart_and_request_replay(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="delete-replay", verbatim="Original")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.WORKING,
            content="Delete replay target",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-delete-replay",
    )
    first = as_person(store).delete(
        created.memory_id,
        user_id="local",
        request_id="delete-replay",
        expected_revision=created.revision,
    )

    reopened = MemoryGovernanceStore(database)
    after_restart = reopened.get(created.memory_id, user_id="local")
    assert after_restart is not None
    assert after_restart.status is MemoryStatus.DELETED
    assert reopened.deletion(created.memory_id, user_id="local") is not None

    replay = as_person(reopened).delete(
        created.memory_id,
        user_id="local",
        request_id="delete-replay",
        expected_revision=created.revision,
    )
    assert replay == first == after_restart


def test_repeated_undo_walks_back_distinct_revisions(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Original")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="A",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )
    second = as_person(store).correct(
        created.memory_id,
        user_id="local",
        request_id="correct-1",
        expected_revision=1,
        content="B",
    )
    third = as_person(store).correct(
        created.memory_id,
        user_id="local",
        request_id="correct-2",
        expected_revision=second.revision,
        content="C",
    )

    first_undo = as_person(store).undo(
        created.memory_id,
        user_id="local",
        request_id="undo-1",
        expected_revision=third.revision,
    )
    second_undo = as_person(store).undo(
        created.memory_id,
        user_id="local",
        request_id="undo-2",
        expected_revision=first_undo.revision,
    )

    assert first_undo.content == "B"
    assert second_undo.content == "A"
    with pytest.raises(MemoryMutationConflictError, match="memory_nothing_to_undo"):
        as_person(store).undo(
            created.memory_id,
            user_id="local",
            request_id="undo-3",
            expected_revision=second_undo.revision,
        )


def test_confirmed_content_shadow_follows_create_correct_and_delete(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="shadow", verbatim="原文保持不变")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-shadow",
    )

    found, more = store.find_confirmed_matching_terms(user_id="local", terms=("独特记忆目标短语",))
    assert [memory.memory_id for memory in found] == [created.memory_id]
    assert more is False

    corrected = as_person(store).correct(
        created.memory_id,
        user_id="local",
        request_id="correct-shadow",
        expected_revision=created.revision,
        content="更正后的不同短语",
    )
    assert (
        store.find_confirmed_matching_terms(user_id="local", terms=("独特记忆目标短语",))[0] == []
    )
    assert [
        memory.memory_id
        for memory in store.find_confirmed_matching_terms(
            user_id="local", terms=("更正后的不同短语",)
        )[0]
    ] == [created.memory_id]

    as_person(store).delete(
        corrected.memory_id,
        user_id="local",
        request_id="delete-shadow",
        expected_revision=corrected.revision,
    )
    assert (
        store.find_confirmed_matching_terms(user_id="local", terms=("更正后的不同短语",))[0] == []
    )


def test_superseded_memory_leaves_the_content_shadow_after_restart(tmp_path) -> None:
    """The derived candidate path must not resurrect a superseded memory."""
    database = tmp_path / "one-memory.sqlite3"
    old_evidence = evidence(database, message_id="supersede-shadow-old", verbatim="原文")
    new_evidence = evidence(database, message_id="supersede-shadow-new", verbatim="原文")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    old = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="旧版发布窗口是周四。",
            scopes=("all-apps",),
            evidence_ids=(old_evidence,),
        ),
        request_id="supersede-shadow-old",
    )
    new = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="新版发布窗口是周五。",
            scopes=("all-apps",),
            evidence_ids=(new_evidence,),
        ),
        request_id="supersede-shadow-new",
    )
    assert old.memory_id in {
        memory.memory_id
        for memory in store.find_confirmed_matching_terms(user_id="local", terms=("旧版发布",))[0]
    }
    store.write_from_hy(
        HySupersede(
            memory_id=old.memory_id,
            request_id="hy-supersede-shadow",
            expected_revision=old.revision,
            superseded_by=(new.memory_id,),
        ),
        user_id="local",
        derivation=store.hy_derivation((old_evidence, new_evidence)),
    )
    assert old.memory_id not in {
        memory.memory_id
        for memory in store.find_confirmed_matching_terms(user_id="local", terms=("旧版发布",))[0]
    }
    reopened = MemoryGovernanceStore(database)
    assert old.memory_id not in {
        memory.memory_id
        for memory in reopened.find_confirmed_matching_terms(user_id="local", terms=("旧版发布",))[
            0
        ]
    }


def test_delete_atomically_creates_cleanup_without_erasing_shared_evidence(
    tmp_path,
) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Shared original")
    store = MemoryGovernanceStore(database)
    memories = [
        as_person(store).create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=content,
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"create-{index}",
        )
        for index, content in enumerate(("First", "Second"))
    ]

    deleted = as_person(store).delete(
        memories[0].memory_id,
        user_id="local",
        request_id="delete-1",
        expected_revision=1,
    )
    cleanup = store.deletion(memories[0].memory_id, user_id="local")

    assert deleted.status is MemoryStatus.DELETED
    assert cleanup is not None
    assert cleanup.status is DeletionStatus.PENDING
    assert EvidenceStore(database).get(evidence_id) is not None
    assert store.get(memories[1].memory_id, user_id="local") is not None


def test_batch_delete_keeps_shared_verbatim_until_the_last_reference_goes(
    tmp_path,
) -> None:
    """RL-27's reference-count constraint, exercised the way the bulk UI works.

    The UI has no batch endpoint; it deletes one memory at a time. So the case
    that matters is the intermediate state: two of three references gone, one
    still standing. The verbatim has to survive that, and only that survival
    is what makes bulk delete safe to offer at all.

    Verified non-vacuous by mutation. Worth recording what the mutation had to
    do to get there: a plain `DELETE FROM evidence` in `delete` cannot even
    run, because the surviving memory's link row holds a foreign key on it. To
    lose the verbatim the mutation has to drop every link first — so today the
    schema, not any reference count, is what keeps shared originals alive.
    """
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Shared original")
    store = MemoryGovernanceStore(database)
    memories = [
        as_person(store).create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=content,
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"create-{index}",
        )
        for index, content in enumerate(("First", "Second", "Third"))
    ]

    for index, target in enumerate(memories[:2]):
        as_person(store).delete(
            target.memory_id,
            user_id="local",
            request_id=f"bulk-delete-{index}",
            expected_revision=1,
        )

    survivor = store.get(memories[2].memory_id, user_id="local")
    assert survivor is not None
    assert survivor.status is MemoryStatus.CONFIRMED
    assert EvidenceStore(database).get(evidence_id) is not None
    assert store.has_evidence_link(evidence_id) is True


def test_list_is_user_scoped_and_escapes_wildcards(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="Original")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="Uses 100% local processing",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )

    assert len(store.list(user_id="local", query="100%")) == 1
    assert store.list(user_id="another-user") == []


def test_a_memory_says_how_it_got_here(tmp_path) -> None:
    """回填进来的答案要和抽出来的记忆分得开。

    分不开的后果是具体的：记忆一经写入就进召回，看不出这条是模型写的
    综述还是你自己说过的话，别的 AI 就会把它当成你本人的判决读回去。
    """
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="周末不排评审会")
    store = MemoryGovernanceStore(database)

    extracted = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户周末不安排评审会。",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-extracted",
    )
    answered = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="综上，用户的排期习惯是把评审集中在工作日。",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
            origin=MemoryOrigin.ANSWERED,
        ),
        request_id="create-answered",
    )

    assert extracted.origin is MemoryOrigin.EXTRACTED
    assert answered.origin is MemoryOrigin.ANSWERED
    stored = {item.memory_id: item.origin for item in store.list(user_id="local")}
    assert stored[extracted.memory_id] is MemoryOrigin.EXTRACTED
    assert stored[answered.memory_id] is MemoryOrigin.ANSWERED


def test_a_library_written_before_this_column_existed_still_opens(tmp_path) -> None:
    """老库里的每一条都是抽出来的，因为那时候没有别的来路。

    正向对照在上一条：新写进去的 answered 读回来必须还是 answered，
    否则这条测的只是「全都读成 extracted」。
    """
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="周末不排评审会")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户周末不安排评审会。",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )

    # 把这一列真的拆掉，模拟一个这轮改动之前写下的库。
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE governed_memories DROP COLUMN origin")
    columns = {
        row[1] for row in sqlite3.connect(database).execute("PRAGMA table_info(governed_memories)")
    }
    assert "origin" not in columns

    reopened = MemoryGovernanceStore(database)
    memory = reopened.get(created.memory_id, user_id="local")

    assert memory is not None
    assert memory.origin is MemoryOrigin.EXTRACTED


def test_a_made_up_origin_is_refused(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="周末不排评审会")
    MemoryGovernanceStore(database)

    with pytest.raises(ValidationError):
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="随便写的",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
            origin="模型瞎编的来路",
        )


def test_topic_tags_survive_a_round_trip(tmp_path) -> None:
    """HY 每条记忆都带 tags，而边界上一直全丢。

    它抽取前会先把库里已有的标签收集起来喂进 prompt 引导复用，所以这套
    聚类其实一直在跑，只是从没浮到产品层。
    """
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="周末不排评审会")
    store = MemoryGovernanceStore(database)

    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户周末不安排评审会。",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
            tags=("排期", "工作习惯"),
        ),
        request_id="create-1",
    )

    assert created.tags == ("排期", "工作习惯")
    assert store.get(created.memory_id, user_id="local").tags == ("排期", "工作习惯")


def test_a_memory_with_no_tags_reads_as_none_rather_than_breaking(tmp_path) -> None:
    """正向对照在上一条：带标签的读回来必须还带着，否则这条测的只是「全是空」。"""
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="m1", verbatim="周末不排评审会")
    store = MemoryGovernanceStore(database)
    created = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户周末不安排评审会。",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-1",
    )

    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE governed_memories DROP COLUMN tags_json")

    reopened = MemoryGovernanceStore(database)

    assert reopened.get(created.memory_id, user_id="local").tags == ()
    assert created.tags == ()


def test_content_candidate_predicate_is_optional_and_stable(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="predicate", verbatim="原文")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="create-predicate",
    )

    with store._connection() as connection:
        predicate, values = content_candidate_predicate(connection, ("独特", "特记", "记忆"))

    assert predicate is not None
    assert "governed_memories_terms" in predicate
    assert values == ("独特", "特记", "记忆")


def test_content_candidate_union_keeps_or_semantics_across_terms(tmp_path) -> None:
    assert CONTENT_CANDIDATE_UNION_VERSION >= 1
    database = tmp_path / "one-memory.sqlite3"
    first_evidence = evidence(database, message_id="candidate-a", verbatim="甲")
    second_evidence = evidence(database, message_id="candidate-b", verbatim="乙")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    first = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="稀有术语 甲",
            scopes=("all-apps",),
            evidence_ids=(first_evidence,),
        ),
        request_id="candidate-a",
    )
    second = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="常见词分支 乙",
            scopes=("all-apps",),
            evidence_ids=(second_evidence,),
        ),
        request_id="candidate-b",
    )

    found, more = store.find_confirmed_matching_terms(user_id="local", terms=("有术", "见词"))

    assert {memory.memory_id for memory in found} == {first.memory_id, second.memory_id}
    assert more is False


def test_partially_indexed_terms_fall_back_to_like_instead_of_dropping_matches(tmp_path) -> None:
    """A mixed term set must not silently drop the non-indexed terms' matches.

    Contract guard, not a live reproduction: the shadow indexes CJK bigrams and
    latin tokens of length >= 2 only, and a bounded candidate set built from
    just the indexed terms would drop a row whose sole match is a non-indexed
    term. Today the only production caller (recall) passes `_terms()` output,
    which is always indexable, so the mixed case is unreachable in production;
    this pins the store's behaviour for a future direct caller instead of
    relying on every caller to filter first.
    """
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    single = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="张 的偏好",
            scopes=("all-apps",),
            evidence_ids=(evidence(database, message_id="partial-single", verbatim="甲"),),
        ),
        request_id="partial-single",
    )
    shared = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="shared target",
            scopes=("all-apps",),
            evidence_ids=(evidence(database, message_id="partial-shared", verbatim="乙"),),
        ),
        request_id="partial-shared",
    )

    # The single character alone matches on the exact path.
    only_single, _ = store.find_confirmed_matching_terms(user_id="local", terms=("张",))
    assert {memory.memory_id for memory in only_single} == {single.memory_id}

    # Mixed with an indexable bigram it must still find both memories.
    mixed, more = store.find_confirmed_matching_terms(user_id="local", terms=("张", "shared"))
    assert {memory.memory_id for memory in mixed} == {single.memory_id, shared.memory_id}
    assert more is False


def test_a_query_over_the_term_cap_reports_truncation_instead_of_a_clean_empty(tmp_path) -> None:
    """Dropping terms past the cap must set `more`, not read as a complete result.

    The candidate union only takes 32 distinct terms. Recall passes every term
    it extracted, so a long query can exceed that bound; the dropped terms were
    silently discarded and recall answered empty with `truncated=False` even
    when a memory matched only a dropped term. The store now reports that
    truncation through `more`, so recall says "I did not finish looking".
    """
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="zeta unique",
            scopes=("all-apps",),
            evidence_ids=(evidence(database, message_id="term-cap", verbatim="甲"),),
        ),
        request_id="term-cap",
    )
    # 33 alphabetically-earlier latin terms, then the matching one. Under the
    # cap the 33rd.. terms (including "zeta") are dropped.
    terms = tuple(f"term{i:02d}" for i in range(33)) + ("zeta",)
    found, more = store.find_confirmed_matching_terms(user_id="local", terms=terms)
    assert found == []
    assert more is True

    # A query within the cap stays a clean complete answer.
    found_within, more_within = store.find_confirmed_matching_terms(
        user_id="local", terms=("zeta", "alpha")
    )
    assert [memory.content for memory in found_within] == ["zeta unique"]
    assert more_within is False

    # Exactly at the cap nothing is dropped, so the answer must not claim
    # truncation: 32 distinct terms is still a complete search of all of them.
    at_cap = tuple(f"term{i:02d}" for i in range(32))
    _, more_at_cap = store.find_confirmed_matching_terms(user_id="local", terms=at_cap)
    assert more_at_cap is False


def test_content_candidate_shadow_honors_a_larger_caller_limit(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(250):
        evidence_id = evidence(database, message_id=f"limit-shadow-{index}", verbatim="甲")
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"共享目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"limit-shadow-{index}",
        )

    found, more = store.find_confirmed_matching_terms(user_id="local", terms=("共享",), limit=300)

    assert len(found) == 250
    assert more is False


def test_public_candidate_index_initializer_backfills_a_bare_schema(tmp_path) -> None:
    """The public initializer repairs rows only after migration owns the tables.

    A bare business table is not a schema. Before migration 32, the initializer
    must fail with a stable machine code instead of becoming a second schema
    owner; after migration 32, it backfills normally.
    """
    database = tmp_path / "one-memory.sqlite3"
    EvidenceStore(database)
    with sqlite3.connect(database) as connection, connection:
        connection.execute(
            "CREATE TABLE governed_memories ("
            "memory_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,kind TEXT NOT NULL,"
            "status TEXT NOT NULL,content TEXT NOT NULL,scopes_json TEXT NOT NULL,"
            "origin TEXT,tags_json TEXT,revision INTEGER NOT NULL,"
            "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,"
            "undo_cursor_revision INTEGER)"
        )
        with pytest.raises(LibraryUpgradeError, match="governance_schema_missing"):
            ensure_content_candidate_index(connection)

    MemoryGovernanceStore(database)
    with sqlite3.connect(database) as connection, connection:
        connection.execute(
            "INSERT INTO governed_memories VALUES "
            "('m1','local','working','confirmed','独特记忆目标短语','[\"all-apps\"]',"
            "'extracted','[]',1,'now','now',NULL,NULL)"
        )
        ensure_content_candidate_index(connection)
        assert connection.execute("SELECT count(*) FROM governed_memories_terms").fetchone()[0] > 0


def test_frequency_threshold_keeps_a_common_term_on_the_like_path(tmp_path, monkeypatch) -> None:
    database = tmp_path / "one-memory.sqlite3"
    first_evidence = evidence(database, message_id="common-a", verbatim="甲")
    second_evidence = evidence(database, message_id="common-b", verbatim="乙")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index, (evidence_id, content) in enumerate(
        ((first_evidence, "common alpha"), (second_evidence, "common beta"))
    ):
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=content,
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"common-{index}",
        )

    monkeypatch.setattr("one_memory.memory_governance._MAX_CANDIDATE_TERM_DOCS", 1)
    found, more = store.find_confirmed_matching_terms(user_id="local", terms=("common",))

    assert len(found) == 2
    assert more is False


def test_coverage_aware_candidate_plan_marks_a_truncated_union(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    first_evidence = evidence(database, message_id="plan-a", verbatim="甲")
    second_evidence = evidence(database, message_id="plan-b", verbatim="乙")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index, evidence_id in enumerate((first_evidence, second_evidence)):
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"unique plan term {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"plan-{index}",
        )
    with store._connection() as connection:
        truncated = content_candidate_plan(connection, ("unique",), alias="m", limit=1)
        complete = content_candidate_plan(connection, ("unique",), alias="m", limit=2)
        legacy = content_candidate_predicate(connection, ("unique",), alias="m")

    assert truncated is not None and truncated.complete is False
    assert truncated.candidate_count == 2
    assert complete is not None and complete.complete is True
    assert len(legacy) == 2


def test_plan_is_incomplete_when_one_or_term_is_filtered(tmp_path, monkeypatch) -> None:
    database = tmp_path / "one-memory.sqlite3"
    first_evidence = evidence(database, message_id="mix-a", verbatim="甲")
    second_evidence = evidence(database, message_id="mix-b", verbatim="乙")
    third_evidence = evidence(database, message_id="mix-c", verbatim="丙")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    memories = []
    for index, (evidence_id, content) in enumerate(
        (
            (first_evidence, "common alpha"),
            (second_evidence, "common beta"),
            (third_evidence, "rare gamma"),
        )
    ):
        memories.append(
            door.create(
                MemoryDraft(
                    user_id="local",
                    kind=MemoryKind.CHAT,
                    content=content,
                    scopes=("all-apps",),
                    evidence_ids=(evidence_id,),
                ),
                request_id=f"mix-{index}",
            )
        )

    monkeypatch.setattr("one_memory.memory_governance._MAX_CANDIDATE_TERM_DOCS", 1)
    with store._connection() as connection:
        plan = content_candidate_plan(connection, ("common", "rare"), alias="m", limit=200)

    assert plan is not None
    assert plan.complete is False
    found, _ = store.find_confirmed_matching_terms(user_id="local", terms=("common", "rare"))
    assert {memory.memory_id for memory in found} == {memory.memory_id for memory in memories}


def test_opening_a_legacy_library_does_not_backfill_the_candidate_shadow(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="legacy-shadow", verbatim="原文")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="legacy-shadow",
    )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")

    reopened = MemoryGovernanceStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM governed_memories_terms").fetchone()[0] == 0
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='governed_memories_terms_meta'"
        ).fetchone()
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 1
        )
    found, _ = reopened.find_confirmed_matching_terms(
        user_id="local", terms=("独特", "特记", "记忆")
    )
    assert [memory.content for memory in found] == ["独特记忆目标短语"]

    with reopened._connection() as connection:
        ensure_content_candidate_index(connection)
        assert connection.execute("SELECT count(*) FROM governed_memories_terms").fetchone()[0] > 0
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 1
        )


def test_content_candidate_backfill_runs_off_the_startup_path(tmp_path) -> None:
    import time

    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="background-shadow", verbatim="原文")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="background-shadow",
    )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")

    assert store.start_content_candidate_backfill() is True
    assert store.start_content_candidate_backfill() is False
    deadline = time.monotonic() + 5
    while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.content_candidate_backfill_state() == "ready"
    assert store.content_candidate_backfill_failure() is None
    assert store.wait_content_candidate_backfill(timeout=0) is True


def test_content_candidate_backfill_waits_for_startup_writes_to_finish(
    tmp_path, monkeypatch
) -> None:
    """A long rebuild must not hold the write checkout while startup still needs it."""
    database = tmp_path / "one-memory.sqlite3"
    EvidenceStore(database)
    store = MemoryGovernanceStore(database)
    entered = threading.Event()
    release = threading.Event()

    def hold_then_finish(_self) -> None:
        entered.set()
        release.wait(10)

    monkeypatch.setattr(MemoryGovernanceStore, "_rebuild_content_shadow_batched", hold_then_finish)
    assert store.start_content_candidate_backfill(hold_until_startup_release=True) is True
    assert entered.wait(2) is False, "backfill acquired the writer before startup released it"
    store.release_content_backfill_startup_gate()
    assert entered.wait(2) is True
    release.set()
    assert store.wait_content_candidate_backfill(timeout=2) is True


def test_content_candidate_backfill_failure_is_observable_and_non_blocking(
    tmp_path, monkeypatch
) -> None:
    import time

    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="background-failure", verbatim="原文")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="background-failure",
    )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")

    def fail_locked(_self) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        "one_memory.memory_governance.MemoryGovernanceStore._rebuild_content_shadow_batched",
        fail_locked,
    )
    assert store.start_content_candidate_backfill() is True
    deadline = time.monotonic() + 5
    while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert store.content_candidate_backfill_state() == "failed"
    assert store.content_candidate_backfill_failure() == "database_locked"
    assert store.wait_content_candidate_backfill(timeout=0) is True
    found, _ = store.find_confirmed_matching_terms(user_id="local", terms=("独特", "记忆"))
    assert [memory.content for memory in found] == ["独特记忆目标短语"]


def test_content_candidate_backfill_rejects_a_negative_timeout(tmp_path) -> None:
    store = MemoryGovernanceStore(tmp_path / "one-memory.sqlite3")
    with pytest.raises(ValueError, match="invalid_content_backfill_timeout"):
        store.wait_content_candidate_backfill(timeout=-0.1)


def test_content_candidate_backfill_rebuilds_stale_terms_not_only_empty_memories(
    tmp_path,
) -> None:
    import time

    database = tmp_path / "one-memory.sqlite3"
    first_evidence = evidence(database, message_id="stale-shadow-a", verbatim="原文")
    second_evidence = evidence(database, message_id="stale-shadow-b", verbatim="原文")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    stale = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="旧版本短语",
            scopes=("all-apps",),
            evidence_ids=(first_evidence,),
        ),
        request_id="stale-shadow",
    )
    door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="新鲜目标短语",
            scopes=("all-apps",),
            evidence_ids=(second_evidence,),
        ),
        request_id="fresh-shadow",
    )
    # Simulate a crash between the ledger update and its derived-row update:
    # one old term survives and makes the memory look already backfilled.
    with sqlite3.connect(database) as connection, connection:
        connection.execute(
            "UPDATE governed_memories SET content=?, updated_at=? WHERE memory_id=?",
            ("全新目标短语", "2099-01-01T00:00:00+00:00", stale.memory_id),
        )
        connection.execute(
            "UPDATE governed_memories_terms_meta SET content_hash=? WHERE memory_id=?",
            ("stale-hash", stale.memory_id),
        )
        connection.execute(
            "DELETE FROM governed_memories_terms WHERE memory_id=? AND term!=?",
            (stale.memory_id, "旧版"),
        )

    assert store.start_content_candidate_backfill() is True
    deadline = time.monotonic() + 5
    while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        terms = {
            row[0]
            for row in connection.execute(
                "SELECT term FROM governed_memories_terms WHERE memory_id=?",
                (stale.memory_id,),
            )
        }
    assert "全新" in terms and "目标" in terms
    assert not {"旧版", "版短"} & terms
    found, _ = store.find_confirmed_matching_terms(user_id="local", terms=("全新", "目标"))
    assert stale.memory_id in {memory.memory_id for memory in found}


def test_content_candidate_backfill_is_idempotent_after_content_hash_exists(tmp_path) -> None:
    import time

    database = tmp_path / "one-memory.sqlite3"
    evidence_id = evidence(database, message_id="idempotent-shadow", verbatim="原文")
    store = MemoryGovernanceStore(database)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="独特记忆目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="idempotent-shadow",
    )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    def wait_ready() -> None:
        deadline = time.monotonic() + 5
        while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert store.content_candidate_backfill_state() == "ready"

    assert store.start_content_candidate_backfill() is True
    wait_ready()
    with sqlite3.connect(database) as connection:
        first = set(
            connection.execute("SELECT term,memory_id FROM governed_memories_terms").fetchall()
        )
    assert store.start_content_candidate_backfill() is False
    with sqlite3.connect(database) as connection:
        before = connection.total_changes
        ensure_content_candidate_index(connection)
        assert connection.total_changes == before
        second = set(
            connection.execute("SELECT term,memory_id FROM governed_memories_terms").fetchall()
        )
    assert second == first


def test_content_candidate_backfill_commits_between_batches_and_releases_writer(
    tmp_path, monkeypatch
) -> None:
    """Each batch acquires and returns the writer instead of holding one transaction."""
    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(6):
        evidence_id = evidence(database, message_id=f"batch-{index}", verbatim="原文")
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"批量目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"batch-{index}",
        )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_ROWS", 2, raising=False)
    connections: list[int] = []
    original = governance.MemoryGovernanceStore._connection

    from contextlib import contextmanager

    @contextmanager
    def observed(self, *, writing=True, keep_journal_mode=False):
        with original(self, writing=writing, keep_journal_mode=keep_journal_mode) as connection:
            connections.append(id(connection))
            yield connection

    monkeypatch.setattr(governance.MemoryGovernanceStore, "_connection", observed)
    assert store.start_content_candidate_backfill() is True
    assert store.wait_content_candidate_backfill(timeout=10) is True
    assert store.content_candidate_backfill_state() == "ready"
    # Six rows at two rows per batch means at least three separate writer
    # checkouts; a single long transaction would show one connection.
    assert len(connections) >= 3
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 6
        )


def test_content_candidate_backfill_resumes_after_partial_batch(tmp_path, monkeypatch) -> None:
    """A crash between batches leaves already-derived rows and resumes the rest."""
    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(5):
        evidence_id = evidence(database, message_id=f"resume-{index}", verbatim="原文")
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"恢复目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"resume-{index}",
        )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_ROWS", 2, raising=False)
    calls = {"count": 0}
    original_upsert = governance.MemoryGovernanceStore._content_shadow_upsert

    def crash_after_three(connection, memory_id, content):
        calls["count"] += 1
        if calls["count"] > 3:
            raise RuntimeError("simulated crash between batches")
        return original_upsert(connection, memory_id, content)

    monkeypatch.setattr(
        governance.MemoryGovernanceStore, "_content_shadow_upsert", staticmethod(crash_after_three)
    )
    assert store.start_content_candidate_backfill() is True
    assert store.wait_content_candidate_backfill(timeout=10) is True
    assert store.content_candidate_backfill_state() == "failed"

    monkeypatch.setattr(
        governance.MemoryGovernanceStore, "_content_shadow_upsert", staticmethod(original_upsert)
    )
    resumed = MemoryGovernanceStore(database)
    assert resumed.start_content_candidate_backfill() is True
    assert resumed.wait_content_candidate_backfill(timeout=10) is True
    assert resumed.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 5
        )
    found, _ = resumed.find_confirmed_matching_terms(user_id="local", terms=("恢复目标",))
    assert len(found) == 5


def test_content_candidate_backfill_handles_a_single_oversized_memory(
    tmp_path, monkeypatch
) -> None:
    """A record bigger than the char budget is processed alone, never split."""
    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    evidence_id = evidence(database, message_id="huge", verbatim="原文")
    huge = "巨大目标短语" + ("内容" * 400_000)
    as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content=huge,
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="huge",
    )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")
    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_CHARS", 10, raising=False)
    assert store.start_content_candidate_backfill() is True
    assert store.wait_content_candidate_backfill(timeout=30) is True
    assert store.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 1
        )
        assert connection.execute("SELECT count(*) FROM governed_memories_terms").fetchone()[0] > 0


def test_content_candidate_backfill_pauses_between_batches_and_lets_a_writer_in(
    tmp_path, monkeypatch
) -> None:
    """The writer is free in the gap after a committed batch, not only at the end."""
    import time

    import one_memory.memory_governance as governance
    from one_memory.database_access import main_database

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(4):
        evidence_id = evidence(database, message_id=f"gap-{index}", verbatim="原文")
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"批间目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"gap-{index}",
        )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    from contextlib import contextmanager

    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_ROWS", 1, raising=False)
    batch_committed = threading.Event()
    release_second_batch = threading.Event()
    original_connection = governance.MemoryGovernanceStore._connection
    writes = {"count": 0}

    @contextmanager
    def pause_after_first_commit(self, *, writing=True, keep_journal_mode=False):
        with original_connection(
            self, writing=writing, keep_journal_mode=keep_journal_mode
        ) as connection:
            yield connection
        if writing:
            writes["count"] += 1
            if writes["count"] == 1:
                batch_committed.set()
                assert release_second_batch.wait(10)

    monkeypatch.setattr(
        governance.MemoryGovernanceStore,
        "_connection",
        pause_after_first_commit,
    )
    assert store.start_content_candidate_backfill() is True
    assert batch_committed.wait(5)
    # The first batch has committed; this write must not wait for the whole
    # rebuild even though the second batch is paused.
    started = time.monotonic()
    with main_database(database).write(busy_timeout_ms=250) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE governed_memories SET updated_at=? WHERE memory_id='gap-0'",
            ("2026-10-01T00:00:00+00:00",),
        )
        connection.execute("COMMIT")
    assert (time.monotonic() - started) < 0.2
    release_second_batch.set()
    assert store.wait_content_candidate_backfill(timeout=10) is True
    assert store.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM governed_memories_terms_meta").fetchone()[0]
            == 4
        )


def test_content_candidate_backfill_handles_cursor_front_and_back_mutations(
    tmp_path, monkeypatch
) -> None:
    """Changes behind and ahead of the cursor end with the writer path authoritative."""
    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    created: dict[str, str] = {}
    for index in range(4):
        evidence_id = evidence(database, message_id=f"cursor-{index}", verbatim="原文")
        memory = door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"游标目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"cursor-{index}",
            memory_id=f"{index + 1:03d}",
        )
        created[f"cursor-{index}"] = memory.memory_id
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    from contextlib import contextmanager

    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_ROWS", 1, raising=False)
    first_batch_committed = threading.Event()
    release = threading.Event()
    original_connection = governance.MemoryGovernanceStore._connection
    writes = {"count": 0}

    @contextmanager
    def pause_after_first_commit(self, *, writing=True, keep_journal_mode=False):
        with original_connection(
            self, writing=writing, keep_journal_mode=keep_journal_mode
        ) as connection:
            yield connection
        if writing:
            writes["count"] += 1
            if writes["count"] == 1:
                first_batch_committed.set()
                assert release.wait(10)

    monkeypatch.setattr(
        governance.MemoryGovernanceStore,
        "_connection",
        pause_after_first_commit,
    )
    assert store.start_content_candidate_backfill() is True
    assert first_batch_committed.wait(5)

    # Behind the cursor: correct one already-scanned row.
    door.correct(
        created["cursor-0"],
        user_id="local",
        request_id="cursor-correct-behind",
        expected_revision=1,
        content="游标目标已更正 0",
    )
    # Ahead of the cursor: create and delete rows the sweep has not reached.
    extra_evidence = evidence(database, message_id="cursor-extra", verbatim="原文")
    extra = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="游标新增短语",
            scopes=("all-apps",),
            evidence_ids=(extra_evidence,),
        ),
        request_id="cursor-extra",
    )
    delete_evidence = evidence(database, message_id="cursor-delete", verbatim="原文")
    deleted = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="游标待删除短语",
            scopes=("all-apps",),
            evidence_ids=(delete_evidence,),
        ),
        request_id="cursor-delete",
    )
    door.delete(
        deleted.memory_id,
        user_id="local",
        request_id="cursor-delete-action",
        expected_revision=1,
    )
    release.set()
    assert store.wait_content_candidate_backfill(timeout=10) is True
    assert store.content_candidate_backfill_state() == "ready"

    found, _ = store.find_confirmed_matching_terms(user_id="local", terms=("游标目标", "游标新增"))
    ids = {memory.memory_id for memory in found}
    assert created["cursor-0"] in ids
    assert extra.memory_id in ids
    assert deleted.memory_id not in ids
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM governed_memories_terms WHERE memory_id=?", (deleted.memory_id,)
            ).fetchone()
            is None
        )


def test_content_candidate_backfill_repeat_is_a_no_op_after_ready(tmp_path) -> None:
    """A second scheduled run does not rewrite derived rows or change counts."""
    import time

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    for index in range(3):
        evidence_id = evidence(database, message_id=f"repeat-{index}", verbatim="原文")
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"重复目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"repeat-{index}",
        )
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")
    assert store.start_content_candidate_backfill() is True
    deadline = time.monotonic() + 10
    while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        before = connection.execute(
            "SELECT term,memory_id FROM governed_memories_terms ORDER BY term,memory_id"
        ).fetchall()
    assert store.start_content_candidate_backfill() is False
    with sqlite3.connect(database) as connection:
        after = connection.execute(
            "SELECT term,memory_id FROM governed_memories_terms ORDER BY term,memory_id"
        ).fetchall()
    assert after == before


def test_content_candidate_backfill_meta_hash_is_the_derivation_rule(tmp_path) -> None:
    """A stale hash re-derives its row; a matching hash is left untouched."""
    import time

    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    evidence_id = evidence(database, message_id="hash-rule", verbatim="原文")
    memory = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="hash 派生目标短语",
            scopes=("all-apps",),
            evidence_ids=(evidence_id,),
        ),
        request_id="hash-rule",
    )
    expected_terms = governance._shadow_terms("hash 派生目标短语")
    expected_hash = governance._shadow_content_hash("hash 派生目标短语")
    with sqlite3.connect(database) as connection, connection:
        assert (
            connection.execute(
                "SELECT content_hash FROM governed_memories_terms_meta WHERE memory_id=?",
                (memory.memory_id,),
            ).fetchone()[0]
            == expected_hash
        )
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT term FROM governed_memories_terms WHERE memory_id=?",
                (memory.memory_id,),
            )
        }
        assert actual == expected_terms
        # Simulate an old hash and an extra stale term; the sweep must rebuild
        # from content, not trust a surviving term row.
        connection.execute(
            "UPDATE governed_memories_terms_meta SET content_hash='stale' WHERE memory_id=?",
            (memory.memory_id,),
        )
        connection.execute(
            "INSERT INTO governed_memories_terms(term,memory_id) VALUES ('旧派',?)",
            (memory.memory_id,),
        )
    assert store.start_content_candidate_backfill() is True
    deadline = time.monotonic() + 10
    while store.content_candidate_backfill_state() == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.content_candidate_backfill_state() == "ready"
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT content_hash FROM governed_memories_terms_meta WHERE memory_id=?",
                (memory.memory_id,),
            ).fetchone()[0]
            == expected_hash
        )
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT term FROM governed_memories_terms WHERE memory_id=?",
                (memory.memory_id,),
            )
        }
    assert actual == expected_terms


def test_content_candidate_backfill_does_not_revive_a_concurrently_deleted_memory(
    tmp_path, monkeypatch
) -> None:
    """A delete committed between batches cannot be undone by the sweep cursor."""
    import one_memory.memory_governance as governance

    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    created: list[str] = []
    for index in range(4):
        evidence_id = evidence(database, message_id=f"delete-race-{index}", verbatim="原文")
        memory = door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"删除竞态目标短语 {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"delete-race-{index}",
            memory_id=f"{index + 1:03d}",
        )
        created.append(memory.memory_id)
    with sqlite3.connect(database) as connection, connection:
        connection.execute("DELETE FROM governed_memories_terms")
        connection.execute("DELETE FROM governed_memories_terms_meta")

    from contextlib import contextmanager

    monkeypatch.setattr(governance, "_CONTENT_BACKFILL_BATCH_ROWS", 1, raising=False)
    first_batch_committed = threading.Event()
    release = threading.Event()
    original_connection = governance.MemoryGovernanceStore._connection
    writes = {"count": 0}

    @contextmanager
    def pause_after_first_commit(self, *, writing=True, keep_journal_mode=False):
        with original_connection(
            self, writing=writing, keep_journal_mode=keep_journal_mode
        ) as connection:
            yield connection
        if writing:
            writes["count"] += 1
            if writes["count"] == 1:
                first_batch_committed.set()
                assert release.wait(10)

    monkeypatch.setattr(governance.MemoryGovernanceStore, "_connection", pause_after_first_commit)
    assert store.start_content_candidate_backfill() is True
    assert first_batch_committed.wait(5)
    # Delete a row ahead of the cursor while the sweep is paused.
    door.delete(
        created[3],
        user_id="local",
        request_id="delete-race-action",
        expected_revision=1,
    )
    release.set()
    assert store.wait_content_candidate_backfill(timeout=10) is True
    assert store.content_candidate_backfill_state() == "ready"
    found, _ = store.find_confirmed_matching_terms(user_id="local", terms=("删除竞态",))
    assert created[3] not in {memory.memory_id for memory in found}
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM governed_memories_terms WHERE memory_id=?", (created[3],)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM governed_memories_terms_meta WHERE memory_id=?", (created[3],)
            ).fetchone()
            is None
        )


def test_a_partial_candidate_shadow_falls_back_to_like_instead_of_dropping_matches(
    tmp_path,
) -> None:
    """A partially indexed shadow must not answer as if it were complete.

    The candidate shadow lets recall skip a full `content LIKE` scan, but only
    when it covers every current memory. A freshly opened existing library, or
    one whose background backfill is still running, can be missing whole
    memories from the shadow. Per-term counts cannot see that loss, so a
    bounded candidate query would return a smaller set while still reporting
    `complete`. The read path must fall back to the exact `LIKE` answer.
    """
    database = tmp_path / "one-memory.sqlite3"
    first = evidence(database, message_id="partial-a", verbatim="shared target phrase alpha")
    second = evidence(database, message_id="partial-b", verbatim="shared target phrase beta")
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    memories = [
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"shared target phrase {suffix}",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id=f"partial-{suffix}",
        )
        for evidence_id, suffix in ((first, "alpha"), (second, "beta"))
    ]

    expected = {memory.memory_id for memory in memories}
    complete, _ = store.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), scopes=("all-apps",)
    )
    assert {memory.memory_id for memory in complete} == expected

    # Model a crash/partial backfill: one memory has neither shadow terms nor a
    # meta row, the exact state the batched rebuild leaves between commits.
    with store._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        victim = memories[0].memory_id
        connection.execute("DELETE FROM governed_memories_terms WHERE memory_id=?", (victim,))
        connection.execute("DELETE FROM governed_memories_terms_meta WHERE memory_id=?", (victim,))

    reopened = MemoryGovernanceStore(database)
    found, more = reopened.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), scopes=("all-apps",)
    )
    assert {memory.memory_id for memory in found} == expected
    assert more is False

    # The plan API must report the same truthfulness, not a "complete" claim.
    with reopened._connection() as connection:
        plan = content_candidate_plan(connection, ("shared",))
    assert plan is None

    # An explicit rebuild restores the shadow fast path without losing rows.
    with reopened._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ensure_content_candidate_index(connection)
    rebuilt, _ = reopened.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), scopes=("all-apps",)
    )
    assert {memory.memory_id for memory in rebuilt} == expected


def test_another_workspace_cannot_spend_the_shadow_candidate_budget(tmp_path) -> None:
    """Scope narrowing must reach inside the shadow subquery, not filter after it.

    The shadow fast path returns `memory_id IN (SELECT ... LIMIT N)`. If the
    scope predicate is applied outside that subquery, a crowded workspace fills
    all N candidate slots first and a readable match from another workspace is
    dropped — reported as an honest-looking empty result with `more=False`.
    """
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    limit = 200

    # A crowded workspace whose ids sort first.
    for index in range(limit):
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"shared target phrase b{index}",
                scopes=("project:b",),
                evidence_ids=(evidence(database, message_id=f"crowd-{index}", verbatim="原文"),),
            ),
            request_id=f"crowd-{index}",
            memory_id=f"aaa-{index:04d}",
        )
    readable = door.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="shared target phrase readable",
            scopes=("project:a",),
            evidence_ids=(evidence(database, message_id="crowd-readable", verbatim="原文"),),
        ),
        request_id="crowd-readable",
        memory_id="zzz-readable",
    )

    found, more = store.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), limit=limit, scopes=("project:a",)
    )
    assert {memory.memory_id for memory in found} == {readable.memory_id}
    assert more is False


def test_shadow_path_reports_truncation_like_the_like_fallback(tmp_path) -> None:
    """A capped candidate pool must say "more remain", not silently drop them.

    The shadow subquery used to be capped at exactly `limit`, so the outer
    `LIMIT limit + 1` could never see an extra row and `more` was always False
    on the fast path — recall then reported a truncated answer as complete.
    The LIKE fallback never had that bug; the two paths must agree.
    """
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    door = as_person(store)
    total = 5
    for index in range(total):
        door.create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"shared target phrase {index}",
                scopes=("all-apps",),
                evidence_ids=(evidence(database, message_id=f"trunc-{index}", verbatim="原文"),),
            ),
            request_id=f"trunc-{index}",
            memory_id=f"m{index:04d}",
        )

    capped, capped_more = store.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), limit=2
    )
    assert len(capped) == 2
    assert capped_more is True

    exact, exact_more = store.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), limit=total
    )
    assert len(exact) == total
    assert exact_more is False

    roomy, roomy_more = store.find_confirmed_matching_terms(
        user_id="local", terms=("shared",), limit=total + 5
    )
    assert len(roomy) == total
    assert roomy_more is False


def test_blocked_source_ids_tracks_the_person_deleting_their_own_evidence(tmp_path) -> None:
    """Deleting or correcting now must block the Evidence the memory rests on.

    Pins both branches of `_overridden_evidence` and its `memory.user_id=?`
    predicate. Drop the delete branch and a deleted memory keeps feeding HY;
    drop the correct branch and a corrected memory's evidence is ignored; drop
    the user predicate and another user's overrule blocks this user's write.
    """
    database = tmp_path / "one-memory.sqlite3"
    deleted_evidence = evidence(database, message_id="del-e", verbatim="delete me")
    corrected_evidence = evidence(database, message_id="cor-e", verbatim="correct me")
    other_evidence = evidence(
        database, message_id="other-e", verbatim="other person words", user_id="other"
    )
    store = MemoryGovernanceStore(database)
    person = as_person(store)
    deleted = person.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="will be deleted",
            scopes=("all-apps",),
            evidence_ids=(deleted_evidence,),
        ),
        request_id="d-1",
    )
    corrected = person.create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="will be corrected",
            scopes=("all-apps",),
            evidence_ids=(corrected_evidence,),
        ),
        request_id="c-1",
    )
    other_memory = person.create(
        MemoryDraft(
            user_id="other",
            kind=MemoryKind.CHAT,
            content="other person's memory",
            scopes=("all-apps",),
            evidence_ids=(other_evidence,),
        ),
        request_id="o-1",
    )
    person.delete(
        deleted.memory_id,
        user_id="local",
        request_id="d-2",
        expected_revision=deleted.revision,
    )
    person.correct(
        corrected.memory_id,
        user_id="local",
        request_id="c-2",
        expected_revision=corrected.revision,
        content="corrected content",
        scopes=("all-apps",),
    )
    # Both of `local`'s own mutations block their evidence.
    assert store.blocked_source_ids(
        user_id="local", evidence_ids=(deleted_evidence, corrected_evidence)
    ) == {deleted_evidence, corrected_evidence}
    # The other user corrects their own memory, so its evidence IS overridden
    # for them. The `memory.user_id=?` predicate must keep it out of `local`'s
    # result, otherwise one user's correction would suppress another's write.
    person.correct(
        other_memory.memory_id,
        user_id="other",
        request_id="o-2",
        expected_revision=other_memory.revision,
        content="other corrected",
        scopes=("all-apps",),
    )
    assert store.blocked_source_ids(user_id="other", evidence_ids=(other_evidence,)) == {
        other_evidence
    }
    assert store.blocked_source_ids(user_id="local", evidence_ids=(other_evidence,)) == set()
