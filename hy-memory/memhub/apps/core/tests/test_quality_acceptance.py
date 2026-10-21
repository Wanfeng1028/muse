from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryDraft, MemoryGovernanceStore, MemoryKind
from one_memory.memory_tasks import MemoryTaskStore
from one_memory.quality_acceptance import build_acceptance_pack, score_acceptance_pack
from tests.person_door import as_person


def _put(store: EvidenceStore, message_id: str, text: str, written_by=WrittenBy.PERSON):
    return store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="conversation",
            message_id=message_id,
            role="user",
            written_by=written_by,
            verbatim=text,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record


def test_acceptance_pack_is_deterministic_and_scores_personal_boundary(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence = EvidenceStore(database)
    MemoryTaskStore(database)
    personal = _put(evidence, "personal", "我是一个产品经理")
    task = _put(evidence, "task", "请优化这个页面")
    agent = _put(evidence, "agent", "我是一个产品经理", WrittenBy.AGENT)
    governance = MemoryGovernanceStore(database)
    as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户是一名产品经理",
            scopes=("all-apps",),
            evidence_ids=(personal.evidence_id,),
        ),
        request_id="create-personal",
    )

    rows = build_acceptance_pack(database, sample_size=3)
    repeated = build_acceptance_pack(database, sample_size=3)

    assert [row.evidence_id for row in rows] == [row.evidence_id for row in repeated]
    assert all(row.verbatim is None for row in rows)
    labels = {
        personal.evidence_id: {
            "disposition": "personal",
            "provenance_ok": True,
            "author_ok": True,
        },
        task.evidence_id: {"disposition": "noop"},
        agent.evidence_id: {"disposition": "noop"},
    }
    score = score_acceptance_pack(rows, labels)
    assert score.passed is True
    assert score.precision == 1
    assert score.omission_rate == 0


def test_acceptance_score_fails_missing_personal_memory(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence = EvidenceStore(database)
    MemoryGovernanceStore(database)
    MemoryTaskStore(database)
    personal = _put(evidence, "personal", "我是一个产品经理")
    row = build_acceptance_pack(database, sample_size=1)[0]

    score = score_acceptance_pack(
        [row],
        {personal.evidence_id: {"disposition": "personal"}},
    )

    assert score.passed is False
    assert score.false_negative == 1
    assert score.failures == ("omission_rate_above_threshold",)
