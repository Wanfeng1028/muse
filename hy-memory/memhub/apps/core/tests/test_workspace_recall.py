"""Workspace memories were unreachable from every host; these pin the way in.

The design says a caller must pass the workspace scope
(docs/mvp/2026-09-03-workspace-memory.md), but a scope hashes an identity the
importing host chose, so no caller could produce one. On this machine's real
database that left 417 of 536 confirmed memories permanently unrecallable.

What must stay true after opening the door: a caller can name the directory
it sits in and nothing else.
"""

import hashlib
from pathlib import Path

import pytest

from one_memory.imports.access import opaque_workspace_id
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryDraft, MemoryGovernanceStore, MemoryKind
from one_memory.recall import GovernedRecallTarget, RecallRequest, RecallState
from one_memory.workspace_resolution import (
    KnownWorkspace,
    cursor_project_label,
    resolve_workspace_scopes,
)
from tests.person_door import as_person

PROJECT = "/Users/someone/work/api-service"
OTHER_PROJECT = "/Users/someone/work/billing-service"


def cursor_workspace(path: str) -> tuple[str, KnownWorkspace]:
    """The workspace a Cursor import of `path` would have recorded."""
    label = cursor_project_label(path)
    scope = opaque_workspace_id("cursor", label)
    assert scope is not None
    return scope, KnownWorkspace(source_id="cursor", workspace=scope, project=label)


def confirmed(
    recall: GovernedRecallTarget,
    evidence_store: EvidenceStore,
    content: str,
    scopes: tuple[str, ...],
) -> None:
    """A confirmed memory, bound to real evidence as the product requires."""
    key = hashlib.sha256(f"{scopes}:{content}".encode()).hexdigest()
    evidence = evidence_store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id=f"conversation:{key[:12]}",
            message_id=f"message:{key[:12]}",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim=content,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    as_person(recall.governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.WORKING,
            content=content,
            scopes=scopes,
            evidence_ids=(evidence.evidence_id,),
        ),
        request_id=f"create:{key}",
    )


def target(
    tmp_path: Path,
    known: tuple[KnownWorkspace, ...] = (),
) -> tuple[GovernedRecallTarget, EvidenceStore]:
    database = tmp_path / "one-memory.sqlite3"
    evidence_store = EvidenceStore(database)
    recall = GovernedRecallTarget(
        MemoryGovernanceStore(database),
        resolve_workspace=lambda path: resolve_workspace_scopes(path, known),
    )
    return recall, evidence_store


def test_a_host_reaches_the_project_it_is_working_in(tmp_path: Path) -> None:
    scope, known = cursor_workspace(PROJECT)
    recall, evidence_store = target(tmp_path, (known,))
    confirmed(recall, evidence_store, "接口错误码统一用 problem+json", (scope,))

    without = recall.recall(RecallRequest(query="错误码 约定"))
    with_path = recall.recall(RecallRequest(query="错误码 约定", workspace_path=PROJECT))

    # This is the whole defect: the default every installed host performs.
    assert without.state is RecallState.EMPTY
    assert [hit.content for hit in with_path.hits] == ["接口错误码统一用 problem+json"]


def test_naming_one_project_does_not_open_another(tmp_path: Path) -> None:
    mine, known_mine = cursor_workspace(PROJECT)
    theirs, known_theirs = cursor_workspace(OTHER_PROJECT)
    recall, evidence_store = target(tmp_path, (known_mine, known_theirs))
    confirmed(recall, evidence_store, "错误码 用于本项目", (mine,))
    confirmed(recall, evidence_store, "错误码 用于另一个项目", (theirs,))

    receipt = recall.recall(RecallRequest(query="错误码", workspace_path=PROJECT))

    assert [hit.content for hit in receipt.hits] == ["错误码 用于本项目"]


def test_the_person_profile_still_comes_through_with_a_project(tmp_path: Path) -> None:
    scope, known = cursor_workspace(PROJECT)
    recall, evidence_store = target(tmp_path, (known,))
    confirmed(recall, evidence_store, "用户偏好 用 axios 封装", ("all-apps",))
    confirmed(recall, evidence_store, "用户偏好 本项目走 grpc", (scope,))

    receipt = recall.recall(RecallRequest(query="用户偏好", workspace_path=PROJECT))

    # Being in a project must not cost the caller the cross-app memories it
    # already had; a host wants both.
    assert {hit.content for hit in receipt.hits} == {
        "用户偏好 用 axios 封装",
        "用户偏好 本项目走 grpc",
    }


def test_the_same_directory_is_reached_whichever_app_recorded_it(tmp_path: Path) -> None:
    # Same folder, opened in Claude Code, which records the path itself.
    claude = opaque_workspace_id("claude-code", PROJECT)
    assert claude is not None
    recall, evidence_store = target(tmp_path)
    confirmed(recall, evidence_store, "结论 部署走蓝绿", (claude,))

    receipt = recall.recall(RecallRequest(query="结论 部署", workspace_path=PROJECT))

    assert [hit.content for hit in receipt.hits] == ["结论 部署走蓝绿"]


@pytest.mark.parametrize("source", ["qwen-code", "codex"])
def test_source_project_memory_is_recalled_only_in_its_project(tmp_path: Path, source: str) -> None:
    mine = opaque_workspace_id(source, PROJECT)
    theirs = opaque_workspace_id(source, OTHER_PROJECT)
    assert mine is not None and theirs is not None
    recall, evidence_store = target(tmp_path)
    confirmed(recall, evidence_store, "项目周会 避开周五", (mine,))
    confirmed(recall, evidence_store, "项目周会 安排周五", (theirs,))
    result = recall.recall(RecallRequest(query="项目周会", workspace_path=PROJECT))
    assert [hit.content for hit in result.hits] == ["项目周会 避开周五"]
    assert not recall.recall(RecallRequest(query="项目周会")).hits


def test_cursors_own_chat_store_is_reached_too(tmp_path: Path) -> None:
    # Cursor's other store keys a workspace by md5 of the path; 42 evidence
    # rows on this machine come from it.
    digest = hashlib.md5(PROJECT.encode(), usedforsecurity=False).hexdigest()
    scope = opaque_workspace_id("cursor", digest)
    assert scope is not None
    recall, evidence_store = target(tmp_path)
    confirmed(recall, evidence_store, "结论 缓存放 redis", (scope,))

    receipt = recall.recall(RecallRequest(query="结论 缓存", workspace_path=PROJECT))

    assert [hit.content for hit in receipt.hits] == ["结论 缓存放 redis"]


def test_the_wildcard_keeps_meaning_everything(tmp_path: Path) -> None:
    scope, known = cursor_workspace(PROJECT)
    recall, evidence_store = target(tmp_path, (known,))
    confirmed(recall, evidence_store, "结论 属于某个项目", (scope,))

    receipt = recall.recall(RecallRequest(query="结论", scope="*"))

    assert receipt.state is RecallState.GROUNDED


class TestCursorTruncatedNames:
    """Cursor shortens long names and appends a hash of its own making.

    Example: `Users-example-example-admin-app-api-reports-month-8327df8`.
    The hash cannot be reproduced from outside, so only the visible part can
    be compared — and that has to be done carefully, because the hash is
    there precisely because prefixes can collide.
    """

    long_path = "/Users/example/example-admin-app/api/reports/monthly/archive"

    def truncated(self, suffix: str) -> KnownWorkspace:
        label = cursor_project_label(self.long_path)[:49]
        project = f"{label}-{suffix}"
        scope = opaque_workspace_id("cursor", project)
        assert scope is not None
        return KnownWorkspace(source_id="cursor", workspace=scope, project=project)

    def test_a_shortened_name_still_resolves(self) -> None:
        known = self.truncated("8327df8")

        assert resolve_workspace_scopes(self.long_path, (known,)) != ()
        assert known.workspace in resolve_workspace_scopes(self.long_path, (known,))

    def test_two_projects_sharing_a_prefix_resolve_to_neither(self) -> None:
        first = self.truncated("8327df8")
        second = self.truncated("99aa11b")

        resolved = resolve_workspace_scopes(self.long_path, (first, second))

        # Returning both would show one project's memories inside another.
        # Returning none costs the caller context; that is the cheaper loss.
        assert first.workspace not in resolved
        assert second.workspace not in resolved

    def test_an_exact_name_wins_over_a_shortened_one(self) -> None:
        label = cursor_project_label(self.long_path)
        exact_scope = opaque_workspace_id("cursor", label)
        assert exact_scope is not None
        exact = KnownWorkspace(source_id="cursor", workspace=exact_scope, project=label)

        resolved = resolve_workspace_scopes(self.long_path, (exact, self.truncated("8327df8")))

        assert exact_scope in resolved
        assert self.truncated("8327df8").workspace not in resolved


@pytest.mark.parametrize(
    "path",
    ["", "   ", "relative/path", "~nonexistent-user/x"],
)
def test_a_path_that_names_no_directory_resolves_to_nothing(path: str) -> None:
    # A caller that cannot say where it is gets the cross-app scope only,
    # never a guess.
    assert resolve_workspace_scopes(path) == ()


def test_the_label_matches_cursor_path_encoding() -> None:
    assert (
        cursor_project_label("/Users/example/example-admin-app")
        == "Users-example-example-admin-app"
    )
    assert (
        cursor_project_label("/Users/example/example-admin-app/api/reports/产品示例")
        == "Users-example-example-admin-app-api-reports"
    )
