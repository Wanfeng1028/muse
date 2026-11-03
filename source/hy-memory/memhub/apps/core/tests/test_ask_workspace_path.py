"""Ask must honour the same workspace_path expansion recall uses.

Without this, om_ask can only see all-apps memories even when the host
injects the project directory — weaker isolation than om_recall.
"""

from __future__ import annotations

import asyncio

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
from one_memory.memory_qa import MemoryAnswerer
from one_memory.model_profiles import ModelProfileStore
from one_memory.secrets import InMemorySecretStore
from tests.person_door import as_person


def test_ask_with_workspace_path_can_ground_on_project_memory(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    evidence_store = EvidenceStore(database)
    governance = MemoryGovernanceStore(database)
    evidence = evidence_store.put(
        EvidenceInput(
            source_id="cursor",
            workspace="workspace:v1:project",
            conversation_id="conversation",
            message_id="message",
            correlation_id="message",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="项目决定使用本地优先架构。",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.WORKING,
            content=evidence.verbatim,
            scopes=("workspace:v1:project",),
            evidence_ids=(evidence.evidence_id,),
        ),
        request_id="create-workspace-memory",
    )
    answerer = MemoryAnswerer(
        governance=governance,
        profiles=ModelProfileStore(database),
        secrets=InMemorySecretStore(),
        resolve_workspace=lambda _path: ("workspace:v1:project",),
    )

    refused = asyncio.run(answerer.answer("项目采用什么架构？"))
    assert refused.mode == "empty"

    grounded = asyncio.run(
        answerer.answer(
            "项目采用什么架构？",
            workspace_path="/Users/example/hy-memory-admin",
        )
    )
    assert grounded.mode == "extractive"
    assert grounded.memories[0].content == "项目决定使用本地优先架构。"
    assert "本地优先" in grounded.answer


def test_ask_does_not_invent_answer_when_workspace_path_misses(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    answerer = MemoryAnswerer(
        governance=MemoryGovernanceStore(database),
        profiles=ModelProfileStore(database),
        secrets=InMemorySecretStore(),
        resolve_workspace=lambda _path: ("workspace:v1:other",),
    )
    result = asyncio.run(
        answerer.answer(
            "我下周的航班是什么？",
            workspace_path="/tmp/elsewhere",
        )
    )
    assert result.answer == "现有记忆不足以回答这个问题。"
    assert result.mode == "empty"
