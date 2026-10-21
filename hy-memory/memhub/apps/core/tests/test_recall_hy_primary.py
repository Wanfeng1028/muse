"""Host recall: HY search decides the order, the ledger only filters.

User decision 09-24 13:50: "以 HY 搜索为主，账本只做授权和删除过滤，HY 不可用时才用关键词".
Every "never appears" assertion below is preceded, in the same test, by the
same recall returning that memory before it was revoked, deleted or replaced,
so an absence can only mean the filter fired.
"""

import asyncio
import contextlib
import hashlib
import time

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.hy_memory_bridge import _joined_thread
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import (
    HySupersede,
    MemoryDraft,
    MemoryGovernanceStore,
    MemoryKind,
)
from one_memory.recall import (
    GovernedRecallTarget,
    RecallRequest,
    RecallState,
    TruncationBudget,
)
from one_memory.semantic_deadline import SemanticMemoryHit
from tests.person_door import as_person
from tests.test_external_endpoint_scopes import ALL_SCOPES, call_tool, envelope, library


def _evidence(store: EvidenceStore, source_id: str = "cursor", conversation: str = "c"):
    return store.put(
        EvidenceInput(
            source_id=source_id,
            conversation_id=conversation,
            message_id="m",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="发布讨论。",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record


def _confirmed(governance, evidence_id: str, content: str, scope: str = "all-apps"):
    key = hashlib.sha256(f"{scope}:{content}".encode()).hexdigest()
    return as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content=content,
            scopes=(scope,),
            evidence_ids=(evidence_id,),
        ),
        request_id=f"create:{key}",
    )


def _library(tmp_path):
    database = tmp_path / "one-memory.sqlite3"
    evidence = EvidenceStore(database)
    governance = MemoryGovernanceStore(database)
    return governance, _evidence(evidence).evidence_id


def _recall(target: GovernedRecallTarget, **request):
    return asyncio.run(target.recall_async(RecallRequest(**request)))


def _hy(*memory_ids: str):
    async def search(_query: str) -> tuple[object, ...]:
        return tuple(
            (memory_id, 1.0 - index / max(1, len(memory_ids)))
            for index, memory_id in enumerate(memory_ids)
        )

    return search


def _formatted_hy(
    memory_id: str,
    content: str,
    *,
    member_ids: tuple[str, ...] = (),
):
    async def search(_query: str) -> tuple[SemanticMemoryHit, ...]:
        return (
            SemanticMemoryHit(
                memory_id=memory_id,
                score=0.9,
                formatted_content=content,
                member_ids=member_ids,
                sdk_formatted=True,
                formatting_complete=True,
            ),
        )

    return search


QUERY = "发布流程 签名 公证"


def test_hy_order_leads_even_against_a_full_keyword_match(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    first = _confirmed(governance, evidence_id, "产物要先过苹果那边的检查才能给别人装。")
    second = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    third = _confirmed(governance, evidence_id, "发版前跑许可证与 SBOM 审计。")
    keyword_only = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    result = _recall(
        GovernedRecallTarget(
            governance,
            semantic_search=_hy(first.memory_id, second.memory_id, third.memory_id),
        ),
        query=QUERY,
    )

    ids = [hit.memory_id for hit in result.hits]
    # Blend mode: the full keyword match outranks the HY hits it beats on
    # score; the HY hits keep their own order among themselves.
    assert ids == [keyword_only.memory_id, first.memory_id, second.memory_id, third.memory_id]
    scores = [hit.score for hit in result.hits]
    assert scores == sorted(scores, reverse=True)
    assert result.truncated is False


def test_tiered_mode_keeps_the_hy_lane_ahead_of_keywords(tmp_path, monkeypatch) -> None:
    """`ONE_MEMORY_RECALL_BLEND=tiered` is the shipped two-tier order."""

    monkeypatch.setenv("ONE_MEMORY_RECALL_BLEND", "tiered")
    governance, evidence_id = _library(tmp_path)
    first = _confirmed(governance, evidence_id, "产物要先过苹果那边的检查才能给别人装。")
    second = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    third = _confirmed(governance, evidence_id, "发版前跑许可证与 SBOM 审计。")
    keyword_only = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    result = _recall(
        GovernedRecallTarget(
            governance,
            semantic_search=_hy(first.memory_id, second.memory_id, third.memory_id),
        ),
        query=QUERY,
    )

    assert [hit.memory_id for hit in result.hits] == [
        first.memory_id,
        second.memory_id,
        third.memory_id,
        keyword_only.memory_id,
    ]
    scores = [hit.score for hit in result.hits]
    assert scores == sorted(scores, reverse=True)
    assert result.truncated is False


def test_a_hy_hit_that_also_matches_keywords_keeps_its_hy_position(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    first = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    second = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    result = _recall(
        GovernedRecallTarget(governance, semantic_search=_hy(first.memory_id, second.memory_id)),
        query=QUERY,
    )

    assert [hit.memory_id for hit in result.hits] == [first.memory_id, second.memory_id]


def test_hy_hit_uses_sdk_formatted_content_without_rebuilding_time(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    memory = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    formatted = "Memory: 证书放在钥匙串里，不进仓库。\nWhen: 2026-09-12 08:00:00 UTC"

    result = _recall(
        GovernedRecallTarget(
            governance,
            semantic_search=_formatted_hy(memory.memory_id, formatted),
        ),
        query=QUERY,
    )

    assert result.hits[0].content == formatted
    assert result.hits[0].content_format == "hy-sdk"
    assert result.used_characters == len(formatted)


def test_hy_composite_falls_back_when_a_member_is_no_longer_readable(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    root = _confirmed(governance, evidence_id, "当前发布使用团队证书。")
    history = _confirmed(governance, evidence_id, "旧发布使用个人证书。")
    formatted = (
        "Current: 当前发布使用团队证书。\n"
        "When: 2026-09-12 08:00:00 UTC\n"
        "History:\n- 旧发布使用个人证书。\nWhen: 2026-08-12 08:00:00 UTC"
    )
    target = GovernedRecallTarget(
        governance,
        semantic_search=_formatted_hy(
            root.memory_id,
            formatted,
            member_ids=(history.memory_id,),
        ),
    )

    before = _recall(target, query=QUERY)
    assert before.hits[0].content == formatted
    assert before.hits[0].content_format == "hy-sdk"

    as_person(governance).delete(
        history.memory_id,
        user_id="local",
        request_id="delete-composite-history",
        expected_revision=history.revision,
    )
    after = _recall(target, query=QUERY)

    assert after.hits[0].content == root.content
    assert after.hits[0].content_format == "plain"


def test_hy_ranked_first_but_out_of_scope_never_appears(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    other = _confirmed(governance, evidence_id, "别的项目的发布密钥位置。", scope="workspace:other")
    mine = _confirmed(governance, evidence_id, "本项目发布前先跑审计。", scope="workspace:mine")
    target = GovernedRecallTarget(governance, semantic_search=_hy(other.memory_id, mine.memory_id))

    everywhere = _recall(target, query=QUERY, scope="*")
    assert [hit.memory_id for hit in everywhere.hits][0] == other.memory_id

    scoped = _recall(target, query=QUERY, scope="workspace:mine")
    assert [hit.memory_id for hit in scoped.hits] == [mine.memory_id]


def test_recall_api_filters_a_deleted_hy_ranked_memory(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    doomed = _confirmed(governance, evidence_id, "旧的签名证书在桌面上。")
    kept = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    # HY still ranks it: its index has not caught up with the deletion.
    target = GovernedRecallTarget(governance, semantic_search=_hy(doomed.memory_id, kept.memory_id))

    before = _recall(target, query=QUERY)
    assert [hit.memory_id for hit in before.hits] == [doomed.memory_id, kept.memory_id]

    as_person(governance).delete(
        doomed.memory_id,
        user_id="local",
        request_id="delete-doomed",
        expected_revision=doomed.revision,
    )
    after = _recall(target, query=QUERY)
    assert [hit.memory_id for hit in after.hits] == [kept.memory_id]


def test_hy_ranked_first_but_superseded_never_appears(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    old = _confirmed(governance, evidence_id, "发布用个人证书签名。")
    new = _confirmed(governance, evidence_id, "发布改用团队证书签名。")
    target = GovernedRecallTarget(governance, semantic_search=_hy(old.memory_id, new.memory_id))

    before = _recall(target, query=QUERY)
    assert [hit.memory_id for hit in before.hits] == [old.memory_id, new.memory_id]

    governance.write_from_hy(
        HySupersede(
            memory_id=old.memory_id,
            request_id="supersede-old",
            expected_revision=old.revision,
            superseded_by=(new.memory_id,),
        ),
        user_id="local",
        derivation=governance.hy_derivation(),
    )
    after = _recall(target, query=QUERY)
    assert [hit.memory_id for hit in after.hits] == [new.memory_id]


def test_hy_failure_falls_back_to_keywords(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    async def broken(_query: str) -> tuple[str, ...]:
        raise RuntimeError("hy down")

    result = _recall(GovernedRecallTarget(governance, semantic_search=broken), query=QUERY)

    assert result.state is RecallState.GROUNDED
    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]


@pytest.mark.parametrize("answer", (None, 42))
def test_a_malformed_hy_answer_falls_back_to_keywords(tmp_path, answer) -> None:
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    async def malformed(_query: str):
        return answer

    result = _recall(GovernedRecallTarget(governance, semantic_search=malformed), query=QUERY)

    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]


def test_a_stuck_keyword_read_does_not_outlast_the_timeout(tmp_path, monkeypatch) -> None:
    governance, evidence_id = _library(tmp_path)
    ranked = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    read_keywords = governance.find_confirmed_matching_terms

    def stuck_keywords(**kwargs):
        time.sleep(3)
        return read_keywords(**kwargs)

    monkeypatch.setattr(governance, "find_confirmed_matching_terms", stuck_keywords)

    async def timed():
        started = time.monotonic()
        result = await GovernedRecallTarget(
            governance, semantic_search=_hy(ranked.memory_id)
        ).recall_async(RecallRequest(query=QUERY, timeout_ms=400))
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(timed())

    assert elapsed < 1.0
    assert [hit.memory_id for hit in result.hits] == [ranked.memory_id]
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_a_stuck_authorization_filter_fails_closed_within_the_timeout(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    ranked = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    blocked = {"on": False}

    def source_filter(memories):
        if blocked["on"]:
            time.sleep(3)
        return tuple(memories)

    target = GovernedRecallTarget(
        governance, semantic_search=_hy(ranked.memory_id), filter_memories=source_filter
    )

    async def timed():
        started = time.monotonic()
        result = await target.recall_async(RecallRequest(query=QUERY, timeout_ms=400))
        return result, time.monotonic() - started

    before, _ = asyncio.run(timed())
    assert [hit.memory_id for hit in before.hits] == [ranked.memory_id]

    blocked["on"] = True
    result, elapsed = asyncio.run(timed())

    assert elapsed < 1.0
    assert result.hits == ()
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_a_stuck_workspace_resolution_fails_closed_within_the_timeout(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    ranked = _confirmed(governance, evidence_id, "本项目发布前先跑审计。", scope="workspace:mine")
    blocked = {"on": False}

    def resolve(_path: str) -> tuple[str, ...]:
        if blocked["on"]:
            time.sleep(3)
        return ("workspace:mine",)

    target = GovernedRecallTarget(
        governance, semantic_search=_hy(ranked.memory_id), resolve_workspace=resolve
    )

    async def timed():
        started = time.monotonic()
        result = await target.recall_async(
            RecallRequest(query=QUERY, workspace_path="/work/mine", timeout_ms=400)
        )
        return result, time.monotonic() - started

    before, _ = asyncio.run(timed())
    assert [hit.memory_id for hit in before.hits] == [ranked.memory_id]

    blocked["on"] = True
    result, elapsed = asyncio.run(timed())

    assert elapsed < 1.0
    assert result.hits == ()
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_cancelling_the_recall_while_the_ledger_is_stuck_cancels_the_hy_search(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    ranked = _confirmed(governance, evidence_id, "本项目发布前先跑审计。", scope="workspace:mine")
    blocked = {"on": False}
    hy_state = {"started": False, "cancelled": False}

    async def slow_hy(_query: str) -> tuple[str, ...]:
        hy_state["started"] = True
        try:
            await asyncio.sleep(5 if blocked["on"] else 0)
        except asyncio.CancelledError:
            hy_state["cancelled"] = True
            raise
        return (ranked.memory_id,)

    def resolve(_path: str) -> tuple[str, ...]:
        if blocked["on"]:
            time.sleep(3)
        return ("workspace:mine",)

    target = GovernedRecallTarget(governance, semantic_search=slow_hy, resolve_workspace=resolve)
    request = RecallRequest(query=QUERY, workspace_path="/work/mine", timeout_ms=2000)

    async def cancel_midway():
        recalling = asyncio.ensure_future(target.recall_async(request))
        await asyncio.sleep(0.1)
        recalling.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recalling
        await asyncio.sleep(0.05)
        # Read before asyncio.run tears down, which cancels leftovers itself.
        return dict(hy_state)

    before = asyncio.run(target.recall_async(request))
    assert [hit.memory_id for hit in before.hits] == [ranked.memory_id]

    blocked["on"] = True
    hy_state["started"] = False

    assert asyncio.run(cancel_midway()) == {"started": True, "cancelled": True}


def test_hy_timeout_falls_back_to_keywords_and_says_it_did_not_finish(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    async def stuck(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(5)
        return ()

    result = _recall(
        GovernedRecallTarget(governance, semantic_search=stuck), query=QUERY, timeout_ms=800
    )

    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]
    assert result.truncated is True
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_hy_wait_stays_inside_the_callers_timeout(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    async def stuck(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(5)
        return ()

    started = time.monotonic()
    result = _recall(
        GovernedRecallTarget(governance, semantic_search=stuck), query=QUERY, timeout_ms=500
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.7
    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]


def test_keyword_lane_runs_alongside_hy_instead_of_after_it(tmp_path, monkeypatch) -> None:
    # A slow keyword read that only starts once HY has given up leaves the
    # fallback whatever sliver of the budget HY did not use.
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")
    read_keywords = governance.find_confirmed_matching_terms

    def slow_keywords(**kwargs):
        time.sleep(0.3)
        return read_keywords(**kwargs)

    monkeypatch.setattr(governance, "find_confirmed_matching_terms", slow_keywords)

    async def stuck(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(5)
        return ()

    async def timed():
        started = time.monotonic()
        result = await GovernedRecallTarget(governance, semantic_search=stuck).recall_async(
            RecallRequest(query=QUERY, timeout_ms=600)
        )
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(timed())

    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]
    assert elapsed < 0.62


def test_cancelling_the_recall_cancels_the_hy_search(tmp_path) -> None:
    governance, _evidence_id = _library(tmp_path)
    cancelled = False

    async def slow(_query: str) -> tuple[str, ...]:
        nonlocal cancelled
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return ()

    async def scenario():
        recall = asyncio.ensure_future(
            GovernedRecallTarget(governance, semantic_search=slow).recall_async(
                RecallRequest(query=QUERY)
            )
        )
        await asyncio.sleep(0.05)
        recall.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recall
        await asyncio.sleep(0.01)
        return cancelled

    assert asyncio.run(scenario()) is True


def test_hy_timeout_stays_the_reason_when_the_count_budget_also_fires(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")
    _confirmed(governance, evidence_id, "发布流程里签名之后再公证。")

    async def stuck(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(5)
        return ()

    result = _recall(
        GovernedRecallTarget(governance, semantic_search=stuck),
        query=QUERY,
        timeout_ms=800,
        limit=1,
    )

    assert len(result.hits) == 1
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_hy_timeout_stays_the_reason_when_the_character_budget_also_fires(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。" + "细节" * 150)
    short = _confirmed(governance, evidence_id, "发布流程：签名、公证。")

    async def stuck(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(5)
        return ()

    result = _recall(
        GovernedRecallTarget(governance, semantic_search=stuck),
        query=QUERY,
        timeout_ms=800,
        character_budget=200,
    )

    assert [hit.memory_id for hit in result.hits] == [short.memory_id]
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_a_repeated_hy_id_keeps_its_first_position(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    first = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")
    second = _confirmed(governance, evidence_id, "发版前跑许可证与 SBOM 审计。")

    result = _recall(
        GovernedRecallTarget(
            governance, semantic_search=_hy(first.memory_id, second.memory_id, first.memory_id)
        ),
        query=QUERY,
    )

    assert [hit.memory_id for hit in result.hits] == [first.memory_id, second.memory_id]


def test_hy_that_refuses_cancellation_still_cannot_hold_recall_past_its_timeout(tmp_path) -> None:
    # The real bridge runs HY in a thread it will not abandon half-way
    # (`_joined_thread`), so cancelling the search does not end it. A deadline
    # that waits for the cancelled search is not a deadline.
    governance, evidence_id = _library(tmp_path)
    keyword = _confirmed(governance, evidence_id, "发布流程包括签名和公证两步。")

    async def uncancellable(_query: str) -> tuple[str, ...]:
        await _joined_thread(time.sleep, 3)
        return ()

    async def timed():
        # Timed inside the loop: `asyncio.run` itself waits for the HY thread
        # when it shuts down, which a long-running Core never does.
        started = time.monotonic()
        result = await GovernedRecallTarget(governance, semantic_search=uncancellable).recall_async(
            RecallRequest(query=QUERY, timeout_ms=500)
        )
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(timed())

    assert elapsed < 1.0
    assert [hit.memory_id for hit in result.hits] == [keyword.memory_id]
    assert result.truncated_by is TruncationBudget.TIMEOUT


def test_hy_that_answers_in_time_is_not_reported_as_truncated(tmp_path) -> None:
    governance, evidence_id = _library(tmp_path)
    hy = _confirmed(governance, evidence_id, "证书放在钥匙串里，不进仓库。")

    async def slow_but_in_time(_query: str) -> tuple[str, ...]:
        await asyncio.sleep(0.05)
        return (hy.memory_id,)

    result = _recall(
        GovernedRecallTarget(governance, semantic_search=slow_but_in_time),
        query=QUERY,
        timeout_ms=1_000,
    )

    assert [hit.memory_id for hit in result.hits] == [hy.memory_id]
    assert result.truncated is False


def test_hy_ranked_first_but_outside_the_installation_grant_never_appears(tmp_path) -> None:
    async def scenario():
        async with library(tmp_path) as (app, client, _records, memories, _matters):
            order = ("workspace", "private", "other", "survivor", "shared")
            app.state.recall_target.semantic_search = _hy(
                *(memories[name].memory_id for name in order)
            )

            async def recalled(scopes):
                response = await call_tool(
                    client, "om_recall", envelope(tools=("om_recall",), scopes=scopes)
                )
                assert response.status_code == 200, response.text
                return [hit["memory_id"] for hit in response.json()["hits"]]

            return memories, await recalled(ALL_SCOPES), await recalled(("all-apps",))

    memories, broad, restricted = asyncio.run(scenario())

    assert broad[0] == memories["workspace"].memory_id
    assert restricted == [memories["survivor"].memory_id, memories["shared"].memory_id]


def test_hy_ranked_first_but_source_revoked_never_appears_through_the_api(tmp_path) -> None:
    async def scenario():
        home = tmp_path / "home"
        home.mkdir()
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={},
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            ids = {}
            for source, content in [("a", "来源甲的发布证书位置。"), ("b", "来源乙的审计步骤。")]:
                folder = home / source
                folder.mkdir()
                app.state.source_grant_store.grant(
                    user_id="local",
                    source_id=source,
                    root=folder,
                    candidate_kind=RootCandidateKind.DEFAULT,
                )
                record = _evidence(app.state.evidence_store, source_id=source, conversation=source)
                ids[source] = _confirmed(
                    app.state.person_writes, record.evidence_id, content
                ).memory_id
            app.state.recall_target.semantic_search = _hy(ids["a"], ids["b"])

            before = (await client.post("/api/v1/recall", json={"query": QUERY})).json()
            app.state.source_grant_store.revoke(user_id="local", source_id="a")
            after = (await client.post("/api/v1/recall", json={"query": QUERY})).json()
            return ids, before, after

    ids, before, after = asyncio.run(scenario())

    assert [hit["memory_id"] for hit in before["hits"]] == [ids["a"], ids["b"]]
    assert [hit["memory_id"] for hit in after["hits"]] == [ids["b"]]
