"""删除发件箱：一条删除同一时刻只归一个执行者，结果只由持有领取凭证的那个写。

时间一律走注入的虚拟时钟：退避 30 秒起、翻倍、6 小时封顶是精确断言，
不靠真实 sleep 去碰运气。
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from one_memory.hy_memory_bridge import HyMemoryBridge, HyMemoryBridgeError
from one_memory.memory_governance import DeletionStatus, MemoryGovernanceStore
from one_memory.model_profiles import ProviderKind
from tests.hy_stores import chroma_store, kuzu_store
from tests.test_hy_memory_bridge import FakeHyMemoryClient, snapshot
from tests.test_memory_no_candidate import _deleted, _Hy, _supervisor
from tests.test_memory_processing import _setup


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _clocked(tmp_path):
    stores = _setup(tmp_path)
    clock = _Clock()
    governance = MemoryGovernanceStore(tmp_path / "one-memory.sqlite3", clock=clock)
    return stores, clock, governance


def test_a_failed_deletion_is_due_again_exactly_after_its_backoff(tmp_path) -> None:
    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)

    waits = []
    for _attempt in range(12):
        (claim,) = governance.claim_deletions(user_id="local")
        failed = governance.settle_deletion(
            claim, user_id="local", error_code="hy_memory_delete_failed"
        )
        assert failed.status is DeletionStatus.FAILED
        retry_at = governance.deletion_retry_at(memory_id, user_id="local")
        waits.append((retry_at - clock()).total_seconds())
        clock.now = retry_at - timedelta(microseconds=1)
        assert governance.claim_deletions(user_id="local") == []
        clock.now = retry_at

    assert waits == [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 21600, 21600]


class _Stop(Exception):
    pass


def test_the_deletion_sync_tries_again_exactly_when_each_wait_runs_out(tmp_path) -> None:
    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)
    supervisor = _supervisor(stores, governance)
    tried: list[datetime] = []

    class _Down(_Hy):
        async def delete(self, memory_id: str) -> dict[str, object]:
            tried.append(clock())
            return await super().delete(memory_id)

    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = _Down(available=False)

    async def wait(timeout: float) -> None:
        if len(tried) == 13:
            raise _Stop
        clock.advance(timeout)

    supervisor._wait_for_deletions = wait

    with pytest.raises(_Stop):
        asyncio.run(supervisor.keep_deletions_in_sync())

    gaps = [
        (later - earlier).total_seconds() for earlier, later in zip(tried, tried[1:], strict=False)
    ]
    assert gaps == [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 21600, 21600]
    assert governance.deletion(memory_id, user_id="local").attempts == 13


class _GatedHy:
    """First call lands late and succeeds; a second one, if made, fails later still."""

    def __init__(self) -> None:
        self.calls = 0
        self.entered = [asyncio.Event(), asyncio.Event()]
        self.gates = [asyncio.Event(), asyncio.Event()]

    async def delete(self, memory_id: str) -> dict[str, object]:
        index = self.calls
        self.calls += 1
        self.entered[index].set()
        await self.gates[index].wait()
        if index:
            raise HyMemoryBridgeError("hy_memory_delete_failed")
        return {"success": True}

    async def close(self) -> None:
        return None


def test_the_api_and_the_sync_never_work_the_same_deletion_at_once(tmp_path) -> None:
    stores = _setup(tmp_path)
    (memory_id,) = _deleted(stores, 1)
    supervisor = _supervisor(stores)
    hy = _GatedHy()
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = hy

    async def scenario() -> None:
        immediate = asyncio.create_task(supervisor.finish_deletion(memory_id))
        await hy.entered[0].wait()
        sweep = asyncio.create_task(supervisor.finish_deletions())
        for _ in range(500):
            if sweep.done() or hy.entered[1].is_set():
                break
            await asyncio.sleep(0.005)
        hy.gates[0].set()
        await immediate
        hy.gates[1].set()
        await sweep

    asyncio.run(scenario())

    assert hy.calls == 1
    assert stores[3].deletion(memory_id, user_id="local").status is DeletionStatus.COMPLETED


def test_a_claim_that_was_taken_over_cannot_overwrite_the_outcome(tmp_path) -> None:
    from one_memory.memory_governance import DELETION_LEASE

    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)

    (first,) = governance.claim_deletions(user_id="local")
    assert governance.claim_deletions(user_id="local") == []
    assert governance.deletion(memory_id, user_id="local").status is DeletionStatus.RUNNING
    # Its holder died: once the lease runs out someone else may take it.
    clock.advance(DELETION_LEASE.total_seconds())
    (second,) = governance.claim_deletions(user_id="local")
    assert second.token != first.token

    done = governance.settle_deletion(second, user_id="local", error_code=None)
    assert done.status is DeletionStatus.COMPLETED
    assert governance.settle_deletion(first, user_id="local", error_code="late") is None
    assert governance.deletion(memory_id, user_id="local").status is DeletionStatus.COMPLETED


# ------------------------------------------------------------ HY 说没删成


class _DeleteClient(FakeHyMemoryClient):
    def __init__(self, *, deleted: bool, held: bool) -> None:
        super().__init__({"success": True})
        self.deleted = deleted
        self.held = held
        self._loop_thread = SimpleNamespace(run=asyncio.run)
        self._vector_store = chroma_store(
            lambda *, ids, include=None: {"ids": list(ids) if self.held else []}
        )
        self._graph_store = None

    def delete(self, memory_id: str):
        self.calls.append({"delete_memory_id": memory_id})
        return {"success": self.deleted, "deleted_count": int(self.deleted)}

    def get(self, memory_id: str):
        return {"memory_id": memory_id} if self.held else None


def _bridge(tmp_path, client) -> HyMemoryBridge:
    return HyMemoryBridge(
        profile=snapshot(ProviderKind.OLLAMA, base_url="http://127.0.0.1:11434", has_api_key=False),
        api_key=None,
        data_dir=tmp_path,
        client=client,
    )


def test_hy_answering_that_it_did_not_delete_a_memory_it_holds_is_a_failure(tmp_path) -> None:
    bridge = _bridge(tmp_path, _DeleteClient(deleted=False, held=True))

    with pytest.raises(HyMemoryBridgeError) as error:
        asyncio.run(bridge.delete("still-there"))

    assert str(error.value) == "hy_memory_delete_rejected"


@pytest.mark.parametrize("deleted", [True, False], ids=["deleted-now", "never-held"])
def test_a_memory_hy_no_longer_holds_counts_as_deleted(tmp_path, deleted) -> None:
    bridge = _bridge(tmp_path, _DeleteClient(deleted=deleted, held=False))

    asyncio.run(bridge.delete("gone"))


def test_hy_reporting_success_for_a_memory_it_still_holds_is_a_failure(tmp_path) -> None:
    """HY 的 success 不是判据，删完之后它手里没有这条才是：success=true、删了 0 条、还读得到。"""

    class _Claims(_DeleteClient):
        def delete(self, memory_id: str):
            self.calls.append({"delete_memory_id": memory_id})
            return {"success": True, "deleted_count": 0}

    bridge = _bridge(tmp_path, _Claims(deleted=True, held=True))

    with pytest.raises(HyMemoryBridgeError) as error:
        asyncio.run(bridge.delete("still-there"))

    assert str(error.value) == "hy_memory_delete_rejected"


# ------------------------------------------------------------ 读不到不等于没有
#
# 回归场景表明：锁定版本的公开 SDK 会让 get 里的 Graph 查询吞掉异常并返回 None。
# VDB 已无记录、Graph 删除失败且 Graph 查询也失败时，get 答 None，删除被记成完成，
# 而那条记忆还在 Graph 里。完成只能由两路各自明确答「没有」来证明。


class _SdkShapedClient(FakeHyMemoryClient):
    """锁定版 SDK 的两路存储（真的 Chroma / Kuzu 存储类，底下换成可控的集合与连接）。

    每路可设为 held / absent / error，Graph 另有 unavailable。`get` 与 SDK 一样：
    Chroma 的 get_by_id 吞掉读错误、Kuzu 不可用时答 None、Graph 查询失败也当没有。
    """

    def __init__(self, *, vdb: str, graph: str) -> None:
        super().__init__({"success": True})
        self.state = {"vdb": vdb, "graph": graph}
        self._loop_thread = SimpleNamespace(run=asyncio.run)
        self._vector_store = chroma_store(self._vector_get)
        self._graph_store = kuzu_store(self._graph_execute, available=graph != "unavailable")

    def _vector_get(self, *, ids, include=None):
        if self.state["vdb"] == "error":
            raise RuntimeError("vdb unreachable")
        return {"ids": list(ids) if self.state["vdb"] == "held" else []}

    def _graph_execute(self, query, params=None):
        if self.state["graph"] == "error":
            raise RuntimeError("graph unreachable")
        held = int(self.state["graph"] == "held")
        return SimpleNamespace(get_next=lambda: [held])

    def delete(self, memory_id: str):
        self.calls.append({"delete_memory_id": memory_id})
        return {"success": True, "deleted_count": 1}

    def get(self, memory_id: str):
        held = "held" in self.state.values()
        return {"memory_id": memory_id} if held else None


@pytest.mark.parametrize(
    ("vdb", "graph", "outcome"),
    [
        ("absent", "absent", None),
        ("held", "absent", "hy_memory_delete_rejected"),
        ("absent", "held", "hy_memory_delete_rejected"),
        ("absent", "error", "hy_memory_delete_unconfirmed"),
        ("absent", "unavailable", "hy_memory_delete_unconfirmed"),
        ("error", "absent", "hy_memory_delete_unconfirmed"),
        ("held", "error", "hy_memory_delete_rejected"),
    ],
)
def test_a_deletion_is_done_only_when_both_stores_say_it_is_gone(
    tmp_path, vdb, graph, outcome
) -> None:
    client = _SdkShapedClient(vdb=vdb, graph=graph)
    bridge = _bridge(tmp_path, client)
    if vdb == "absent" and graph in {"error", "unavailable"}:
        # 正向前提：这正是 SDK 的 get 会答「没有」的情形。
        assert client.get("m") is None

    if outcome is None:
        asyncio.run(bridge.delete("m"))
        return
    with pytest.raises(HyMemoryBridgeError) as error:
        asyncio.run(bridge.delete("m"))
    assert str(error.value) == outcome


@pytest.mark.parametrize("which", ["vector", "graph"])
def test_a_store_that_is_not_the_pinned_one_cannot_confirm_a_deletion(tmp_path, which) -> None:
    """认不出的存储（例如被换上的包装层）读到「没有」也证明不了没有。"""
    client = _SdkShapedClient(vdb="absent", graph="absent")

    async def nothing(_memory_id: str):
        return None

    if which == "vector":
        client._vector_store = SimpleNamespace(get_by_id=nothing)
    else:
        client._graph_store = SimpleNamespace(get_node=nothing)

    with pytest.raises(HyMemoryBridgeError) as error:
        asyncio.run(_bridge(tmp_path, client).delete("m"))
    assert str(error.value) == "hy_memory_delete_unconfirmed"


def test_an_unreadable_graph_keeps_the_deletion_failed_and_due_again(tmp_path) -> None:
    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)
    supervisor = _supervisor(stores, governance)
    client = _SdkShapedClient(vdb="absent", graph="error")
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = _bridge(
        tmp_path, client
    )

    asyncio.run(supervisor.finish_deletion(memory_id))

    failed = governance.deletion(memory_id, user_id="local")
    assert (failed.status, failed.last_error_code) == (
        DeletionStatus.FAILED,
        "hy_memory_delete_unconfirmed",
    )
    retry_at = governance.deletion_retry_at(memory_id, user_id="local")
    assert retry_at is not None

    client.state["graph"] = "absent"
    clock.now = retry_at
    asyncio.run(supervisor.finish_deletions())

    done = governance.deletion(memory_id, user_id="local")
    assert (done.status, done.attempts) == (DeletionStatus.COMPLETED, 2)


def test_hy_failing_delete_for_an_absent_memory_completes_it(tmp_path) -> None:
    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)
    supervisor = _supervisor(stores, governance)

    class _Raises(_DeleteClient):
        def delete(self, memory_id: str):
            self.calls.append({"delete_memory_id": memory_id})
            raise RuntimeError("HY lost track of it")

    holding = _Raises(deleted=False, held=True)
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = _bridge(
        tmp_path, holding
    )
    asyncio.run(supervisor.finish_deletion(memory_id))
    assert governance.deletion(memory_id, user_id="local").status is DeletionStatus.FAILED

    gone = _Raises(deleted=False, held=False)
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = _bridge(tmp_path, gone)
    clock.now = governance.deletion_retry_at(memory_id, user_id="local")
    asyncio.run(supervisor.finish_deletions())
    done = governance.deletion(memory_id, user_id="local")
    assert (done.status, done.last_error_code) == (DeletionStatus.COMPLETED, None)


def test_a_deletion_that_keeps_failing_stops_for_attention(tmp_path) -> None:
    from one_memory.memory_governance import DELETION_MAX_ATTEMPTS

    stores, clock, governance = _clocked(tmp_path)
    (memory_id,) = _deleted(stores, 1)
    supervisor = _supervisor(stores, governance)
    tried: list[datetime] = []

    class _Counting(_Hy):
        async def delete(self, memory_id: str) -> dict[str, object]:
            tried.append(clock())
            return await super().delete(memory_id)

    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = _Counting(
        available=False
    )

    for _ in range(DELETION_MAX_ATTEMPTS + 3):
        due = governance.next_deletion_due(user_id="local")
        if due is None:
            break
        clock.now = max(clock.now, due)
        asyncio.run(supervisor.finish_deletions())

    assert len(tried) == DELETION_MAX_ATTEMPTS
    final = governance.deletion(memory_id, user_id="local")
    assert final.status is DeletionStatus.FAILED
    assert final.attempts == DELETION_MAX_ATTEMPTS
    assert final.last_error_code == "hy_memory_delete_needs_attention"
    assert governance.next_deletion_due(user_id="local") is None
    clock.advance(365 * 24 * 3600)
    assert governance.claim_deletions(user_id="local") == []
