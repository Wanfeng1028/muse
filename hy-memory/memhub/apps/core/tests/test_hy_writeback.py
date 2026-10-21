"""HY 的结果只有一扇门进治理表，而且每次进门都带着调用开始时的证据快照。

回归测试覆盖了多条曾漏检的写回路径（抽取的四处、digest、retired、supersede），
说明问题在路径分散，不在某一处。这里一边用静态扫描守住「只有一扇门」，
一边把 digest、retired、supersede 在 HY 调用途中被人改判的场景逐个复现。
"""

import ast
import asyncio
import re
import sqlite3
from pathlib import Path

import pytest

import one_memory
from one_memory.hy_memory_bridge import HyGraphNode, HyMemoryIngestResult, HyMemoryOutput
from one_memory.imports.models import WrittenBy
from one_memory.memory_governance import (
    HyCreate,
    MemoryEvidenceOverriddenError,
    MemoryGovernanceStore,
    MemoryStatus,
)
from one_memory.memory_processing import MemoryProcessingSupervisor
from tests.person_door import as_person
from tests.test_memory_no_candidate import _HeldBridge, _manual, _overrule_mid_call
from tests.test_memory_processing import FakeBridge, _put, _runner, _setup, _task

SOURCE = Path(one_memory.__file__).parent
#: What a person does to a memory.
PERSON_WRITES = ("create", "correct", "set_scopes", "undo", "delete")
#: Ways HY results used to reach governance directly. None may exist any more.
DIRECT_HY_WRITES = {
    "reconcile_hy",
    "supersede",
    "link_evidence",
    "complete_deletion",
    "fail_deletion",
}


# ------------------------------------------------------------ 运行时的门：不靠静态扫描
#
# 回归场景表明：按属性名加接收者文本匹配的扫描，别名、getattr、经类调用、
# 先存绑定方法四种写法都认不出。所以安全边界放在运行时：治理 store 本身不再有人工写方法，
# 人工写入只能经它发出一次的 PersonWrites（Core 的 API 启动时领走）。


def _seed_record(tmp_path):
    stores = _setup(tmp_path)
    evidence, _profiles, _tasks, governance, _secrets, _profile = stores
    record = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    return governance, record


def _alias(governance, draft):
    store = governance
    return store.create(draft, request_id="alias")


def _getattr(governance, draft):
    return getattr(governance, "create")(draft, request_id="getattr")  # noqa: B009


def _through_the_class(governance, draft):
    return MemoryGovernanceStore.create(governance, draft, request_id="class")


def _bound_first(governance, draft):
    write = governance.create
    return write(draft, request_id="bound")


@pytest.mark.parametrize(
    "bypass",
    [_alias, _getattr, _through_the_class, _bound_first],
    ids=["alias", "getattr", "through-class", "bound-method"],
)
def test_code_holding_only_the_store_cannot_write_as_the_person(tmp_path, bypass) -> None:
    governance, record = _seed_record(tmp_path)

    with pytest.raises(AttributeError):
        bypass(governance, _draft(record, "绕过人工入口写进来的记忆"))

    assert governance.list(user_id="local") == []


@pytest.mark.parametrize("name", PERSON_WRITES)
def test_the_store_has_no_person_write_of_its_own(name) -> None:
    assert not hasattr(MemoryGovernanceStore, name)


def test_the_person_door_is_issued_once_and_cannot_be_forged(tmp_path) -> None:
    from one_memory.memory_governance import PersonWrites

    governance, record = _seed_record(tmp_path)
    with pytest.raises(ValueError, match="actor"):
        governance.claim_person_writes("hy")
    door = governance.claim_person_writes("user")
    # 正向前提：领到的门确实能写。
    written = door.create(_draft(record, "人自己写的记忆"), request_id="door")
    assert governance.get(written.memory_id, user_id="local") == written

    with pytest.raises(PermissionError, match="person_writes_already_claimed"):
        governance.claim_person_writes("user")
    with pytest.raises(PermissionError, match="person_writes_not_issued"):
        PersonWrites(governance, "user", key=object())


def test_core_takes_the_person_door_before_anything_else_can(tmp_path) -> None:
    from tests.test_memory_no_candidate import _app

    async def scenario():
        app = _app(tmp_path)
        async with app.router.lifespan_context(app):
            assert app.state.person_writes.actor == "api"
            with pytest.raises(PermissionError, match="person_writes_already_claimed"):
                app.state.memory_governance_store.claim_person_writes("user")

    asyncio.run(scenario())


# ------------------------------------------------------------ 静态扫描：只作补充


def _governance_private_names() -> set[str]:
    """治理层自己的私有成员里，别的模块没有同名定义的那些——出现在别处就只能是伸手进来。"""
    from one_memory.memory_governance import PersonWrites

    own = {
        name
        for cls in (MemoryGovernanceStore, PersonWrites)
        for name in vars(cls)
        if name.startswith("_") and not name.startswith("__")
    } | {"_person_key", "_person_claimed"}
    elsewhere = set()
    for path in SOURCE.rglob("*.py"):
        if path.name == "memory_governance.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                elsewhere.add(node.name)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                elsewhere.add(node.attr)
    return own - elsewhere


def _reaches_into_governance(source: str, private: set[str]) -> list[tuple[int, str]]:
    """属性引用与字符串常量都算：别名、getattr、经类调用、存绑定方法都逃不掉名字本身。"""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in private | {"claim_person_writes"}:
            found.append((node.lineno, node.attr))
        elif isinstance(node, ast.Constant) and node.value in private | {"claim_person_writes"}:
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.Call) and ast.unparse(node.func).endswith("PersonWrites"):
            # Naming the type is harmless; building one is reaching in.
            found.append((node.lineno, "PersonWrites"))
    return found


def test_the_scan_sees_every_bypass_shape() -> None:
    private = _governance_private_names()
    # 正向前提：写入口本身的私有名字都在清单里，没被"别处同名"误删。
    assert {"_create", "_mutate", "_person_key"} <= private
    for shape in (
        "store = processor.governance\nstore._create(d, request_id='r')",
        "getattr(processor.governance, '_mutate')(m)",
        "MemoryGovernanceStore._create(processor.governance, d)",
        "write = processor.governance._mutate\nwrite(m)",
        "processor.governance.claim_person_writes('api')",
        "PersonWrites(store, 'api', key=store._person_key)",
    ):
        assert _reaches_into_governance(shape, private), shape


def test_only_the_api_takes_the_person_door_and_nothing_reaches_into_governance() -> None:
    private = _governance_private_names()
    found = {
        path.relative_to(SOURCE).as_posix(): hits
        for path in sorted(SOURCE.rglob("*.py"))
        if path.name != "memory_governance.py"
        and (hits := _reaches_into_governance(path.read_text(encoding="utf-8"), private))
    }
    api_hits = {name for _line, name in found.pop("api.py", [])}
    assert api_hits == {"claim_person_writes"}
    assert found == {}


def test_governance_has_one_public_door_for_hy_results() -> None:
    public = {
        name
        for name, value in vars(MemoryGovernanceStore).items()
        if callable(value) and not name.startswith("_")
    }
    assert "write_from_hy" in public
    assert public & DIRECT_HY_WRITES == set()


# ------------------------------------------------------------ 绕过门直接写 SQL
#
# 回归场景表明：门守住了 Python 调用，守不住有人自己拼一句 UPDATE governed_memories。
# 这里扫生产源码里的 SQL 文本，作为补充；表名在运行时才拼出来的写法它看不见，不是唯一防线。

GOVERNANCE_TABLES = (
    "governed_memories",
    "governed_memory_versions",
    "governed_memory_evidence",
    "governed_memory_mutations",
    "governed_memory_supersessions",
    "memory_deletions",
    "memory_index_syncs",
)
_GOVERNANCE_WRITE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM"
    r"|DROP\s+TABLE(?:\s+IF\s+EXISTS)?|ALTER\s+TABLE)\s+[\"`\[]?(?:main\.)?(?:"
    + "|".join(GOVERNANCE_TABLES)
    + r")\b",
    re.IGNORECASE,
)


def _governance_writes(source: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value if isinstance(part, ast.Constant) else "?" for part in node.values
            )
        else:
            continue
        if _GOVERNANCE_WRITE.search(text):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    "sample",
    [
        'db.execute("UPDATE governed_memories SET status = ?", (s,))',
        "db.execute('delete from memory_deletions where memory_id = ?', (m,))",
        'db.execute("INSERT OR REPLACE INTO governed_memory_evidence VALUES (?, ?, 1)")',
        'db.execute("REPLACE INTO \\"governed_memory_versions\\" VALUES (?)")',
        'db.execute("UPDATE main.governed_memory_mutations SET x = 1")',
        'db.execute("UPDATE "\n    "governed_memories SET content = ?")',
        'db.execute(f"DELETE FROM governed_memory_supersessions WHERE id = {i}")',
        'db.executescript("DROP TABLE IF EXISTS memory_index_syncs;")',
        'db.execute("ALTER TABLE governed_memories ADD COLUMN x")',
    ],
)
def test_the_sql_scan_sees_a_write_to_a_governance_table(sample) -> None:
    assert _governance_writes(sample) != []


@pytest.mark.parametrize(
    "sample",
    [
        'db.execute("SELECT * FROM governed_memories WHERE memory_id = ?")',
        'db.execute("SELECT 1 FROM x JOIN governed_memory_evidence USING(memory_id)")',
        'db.execute("CREATE TRIGGER t AFTER UPDATE ON governed_memory_versions BEGIN END")',
        'db.execute("INSERT INTO evidence VALUES (?) ON CONFLICT DO UPDATE SET x = 1")',
    ],
)
def test_reading_a_governance_table_is_not_a_write(sample) -> None:
    assert _governance_writes(sample) == []


def test_only_governance_writes_to_its_own_tables() -> None:
    offenders = []
    own = []
    for path in sorted(SOURCE.rglob("*.py")):
        found = _governance_writes(path.read_text(encoding="utf-8"))
        if path.name in {"memory_governance.py", "migrations.py"}:
            own = found
            continue
        offenders += [f"{path.relative_to(SOURCE)}:{line}" for line in found]
    # 基数非零：扫描在治理模块自己身上确实认得出写语句，下面的空表才有意义。
    assert len(own) >= 10
    assert offenders == []


# ------------------------------------------------------------------ digest


class _HeldDigest(FakeBridge):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def digest(self, *, user_id: str, agent_id: str) -> dict[str, object]:
        self.entered.set()
        await self.release.wait()
        return await super().digest(user_id=user_id, agent_id=agent_id)


def _digest_scene(tmp_path):
    stores = _setup(tmp_path)
    evidence, profiles, tasks, governance, secrets, profile = stores
    record = _put(
        evidence,
        message_id="m1",
        role="user",
        written_by=WrittenBy.PERSON,
        content="项目范围内的事实。",
        workspace="workspace:v1:project",
    )
    for key in ("seed", "doomed"):
        as_person(governance).create(
            _draft(record, f"记忆 {key}", scopes=("workspace:v1:project",)),
            request_id=f"create-{key}",
            memory_id=key,
        )
    supervisor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
    )
    bridge = _HeldDigest(
        outputs=(),
        graph_nodes=(
            HyGraphNode(node_id="schema-1", content="用户偏好可验证的结论。", layer="l6_schema"),
        ),
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = bridge
    return governance, supervisor, bridge


def _draft(record, content, *, scopes=("all-apps",)):
    from one_memory.memory_governance import MemoryDraft, MemoryKind

    return MemoryDraft(
        user_id="local",
        kind=MemoryKind.CHAT,
        content=content,
        scopes=scopes,
        evidence_ids=(record.evidence_id,),
    )


def _delete(governance, memory_id):
    memory = governance.get(memory_id, user_id="local")
    as_person(governance).delete(
        memory_id,
        user_id="local",
        request_id=f"delete-{memory_id}",
        expected_revision=memory.revision,
    )


def test_a_schema_digested_while_its_evidence_is_overruled_is_not_recorded(tmp_path) -> None:
    governance, supervisor, bridge = _digest_scene(tmp_path)

    async def scenario():
        running = asyncio.create_task(supervisor.digest())
        await bridge.entered.wait()
        _delete(governance, "doomed")
        bridge.release.set()
        return await running

    result = asyncio.run(scenario())

    assert bridge.digest_calls, "HY 必须真的被调用过"
    assert governance.get("schema-1", user_id="local") is None
    assert result["schemas_recorded"] == 0


def test_a_deletion_before_the_digest_began_does_not_hold_the_schema_back(tmp_path) -> None:
    """快照之前的改判已由上下文把关；写入时只看调用途中的改判，否则碰过删除的证据永远写不进。"""
    governance, supervisor, bridge = _digest_scene(tmp_path)
    _delete(governance, "doomed")
    bridge.release.set()

    result = asyncio.run(supervisor.digest())

    assert result["schemas_recorded"] == 1
    assert governance.get("schema-1", user_id="local").status is MemoryStatus.CONFIRMED


# ------------------------------------------------------------ retired / supersede


class _HeldResult(_HeldBridge):
    """HY 调用停在半路，回来时报告它删掉或取代了哪些记忆。"""

    def __init__(self, *, retired=(), superseded=None) -> None:
        super().__init__(outputs=())
        self.retired = retired
        self.superseded = superseded or {}

    async def ingest(self, request):
        self.entered.set()
        await self.release.wait()
        self.requests.append(request)
        return HyMemoryIngestResult(
            success=True,
            retired_memory_ids=self.retired,
            superseded_memory_ids=self.superseded,
        )


def _turn(stores):
    evidence, _profiles, _tasks, governance, _secrets, _profile = stores
    elsewhere = _put(
        evidence, message_id="u0", role="user", written_by=WrittenBy.PERSON, content="别处的原话"
    )
    record = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    doomed = _manual(governance, record, "用户在杭州。", "seed-doomed")
    return elsewhere, record, doomed


def test_hy_retiring_a_memory_mid_call_is_refused_once_its_evidence_is_overruled(tmp_path) -> None:
    stores = _setup(tmp_path)
    _evidence, _profiles, tasks, governance, _secrets, profile = stores
    elsewhere, record, doomed = _turn(stores)
    retiring = _manual(governance, elsewhere, "用户住在上海。", "seed-retiring")
    bridge = _HeldResult(retired=(retiring.memory_id,))
    task = _task(tasks, profile, record)

    _overrule_mid_call(
        stores, bridge, doomed, lambda: _runner(tmp_path, stores, bridge).run(task.task_id)
    )

    assert governance.get(retiring.memory_id, user_id="local").status is MemoryStatus.CONFIRMED
    assert tasks.get(task.task_id).status == "unknown"
    assert tasks.get(task.task_id).last_error_code == "hy_memory_evidence_changed"


def test_hy_superseding_a_memory_mid_call_is_refused_once_its_evidence_is_overruled(
    tmp_path,
) -> None:
    stores = _setup(tmp_path)
    _evidence, _profiles, tasks, governance, _secrets, profile = stores
    elsewhere, record, doomed = _turn(stores)
    old = _manual(governance, elsewhere, "用户住在上海。", "seed-old")
    head = _manual(governance, elsewhere, "用户搬到了杭州。", "seed-head")
    bridge = _HeldResult(superseded={old.memory_id: (head.memory_id,)})
    task = _task(tasks, profile, record)

    _overrule_mid_call(
        stores, bridge, doomed, lambda: _runner(tmp_path, stores, bridge).run(task.task_id)
    )

    assert governance.get(old.memory_id, user_id="local").status is MemoryStatus.CONFIRMED
    assert tasks.get(task.task_id).status == "unknown"
    assert tasks.get(task.task_id).last_error_code == "hy_memory_evidence_changed"


def test_what_hy_itself_retired_in_a_turn_does_not_block_the_rest_of_that_turn(tmp_path) -> None:
    """HY 自己的删除不是人的改判：同一轮里它删一条、取代一条，两件都要落地。"""
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    record = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    retired = _manual(governance, record, "用户住在上海。", "seed-retired")
    old = _manual(governance, record, "用户在上海工作。", "seed-old")
    head = _manual(governance, record, "用户在杭州工作。", "seed-head")
    bridge = _HeldResult(
        retired=(retired.memory_id,), superseded={old.memory_id: (head.memory_id,)}
    )
    bridge.release.set()
    task = _task(tasks, profile, record)

    finished = asyncio.run(_runner(tmp_path, stores, bridge).run(task.task_id))

    assert (finished.status, finished.last_error_code) == ("completed", None)
    assert governance.get(retired.memory_id, user_id="local").status is MemoryStatus.DELETED
    assert governance.get(old.memory_id, user_id="local").status is MemoryStatus.SUPERSEDED


# ------------------------------------------------------------ 墓碑判定只看在用的证据


@pytest.mark.parametrize("still_resting", [True, False], ids=["resting", "moved-away"])
def test_only_evidence_a_deleted_memory_still_rests_on_is_held_back(
    tmp_path, still_resting
) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    first = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    later = _put(
        evidence,
        message_id="u9",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我搬到上海了。",
        conversation_id="elsewhere",
    )
    memory = _manual(governance, first, "用户住在杭州。", "seed-memory")
    if not still_resting:
        # HY 重新整合时换掉一条记忆的证据就是这样：旧链接留作历史、不再在用。
        with sqlite3.connect(tmp_path / "one-memory.sqlite3") as db:
            db.execute(
                "UPDATE governed_memory_evidence SET active=0 WHERE memory_id=?",
                (memory.memory_id,),
            )
            db.execute(
                "INSERT INTO governed_memory_evidence (memory_id,evidence_id,active) "
                "VALUES (?,?,1)",
                (memory.memory_id, later.evidence_id),
            )
    _delete(governance, memory.memory_id)
    bridge = FakeBridge(
        outputs=(
            HyMemoryOutput(memory_id="hy-new", content="用户在杭州生活。", layer="L0_BASIC_INFO"),
        )
    )
    task = _task(tasks, profile, first)

    finished = asyncio.run(_runner(tmp_path, stores, bridge).run(task.task_id))

    if still_resting:
        assert (finished.status, finished.last_error_code) == (
            "cancelled",
            "hy_memory_evidence_changed",
        )
    else:
        assert (finished.status, finished.last_error_code) == ("completed", None)
        assert governance.get("hy-new", user_id="local").status is MemoryStatus.CONFIRMED


@pytest.mark.parametrize("still_resting", [True, False], ids=["resting", "moved-away"])
def test_a_deletion_mid_call_holds_back_only_evidence_the_memory_still_rests_on(
    tmp_path, still_resting
) -> None:
    """同一条判据在写事务里再查一次：调用途中被删的记忆若早已换了证据，旧证据不受牵连。"""
    stores = _setup(tmp_path)
    evidence, _profiles, _tasks, governance, _secrets, _profile = stores
    first = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    later = _put(
        evidence,
        message_id="u9",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我搬到上海了。",
        conversation_id="elsewhere",
    )
    memory = _manual(governance, first, "用户住在杭州。", "seed-memory")
    if not still_resting:
        with sqlite3.connect(tmp_path / "one-memory.sqlite3") as db:
            db.execute(
                "UPDATE governed_memory_evidence SET active=0 WHERE memory_id=?",
                (memory.memory_id,),
            )
            db.execute(
                "INSERT INTO governed_memory_evidence (memory_id,evidence_id,active) "
                "VALUES (?,?,1)",
                (memory.memory_id, later.evidence_id),
            )
    derivation = governance.hy_derivation((first.evidence_id,))
    _delete(governance, memory.memory_id)

    def write():
        return governance.write_from_hy(
            HyCreate(
                draft=_draft(first, "用户在杭州生活。"),
                request_id="hy-create",
                memory_id="hy-new",
            ),
            user_id="local",
            derivation=derivation,
        )

    if still_resting:
        with pytest.raises(MemoryEvidenceOverriddenError):
            write()
        assert governance.get("hy-new", user_id="local") is None
    else:
        assert write().status is MemoryStatus.CONFIRMED


# ------------------------------------------------------------ 事项发现补关联


def test_matter_discovery_does_not_link_evidence_overruled_while_it_reviewed(
    tmp_path, monkeypatch
) -> None:
    """事项核对通过的引文会补成记忆的证据；核对途中人删了建在这条原话上的记忆，就不能再补。"""
    from one_memory.matters import discovery as discovery_module
    from one_memory.matters.discovery import MatterDiscovery
    from one_memory.matters.model import MatterModel
    from one_memory.matters.models import Citation, Claim, DiscoveryInput
    from one_memory.matters.store import MatterStore
    from tests.test_matter_hy_integration import Bridge
    from tests.test_matter_hy_integration import setup as matter_setup

    def run(overrule: bool) -> tuple[object, object, object]:
        root = tmp_path / ("overruled" if overrule else "plain")
        root.mkdir()

        async def scenario():
            processor, _record, _ = matter_setup(root, Bridge())
            linked: dict[str, object] = {}

            async def classify(_model, memories, refs, _records, **_kwargs):
                # 抽取之后才有这条原话，HY 的记忆本来没建在它上面，补关联才有事可做。
                quoted = _put(
                    processor.evidence,
                    message_id="q1",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    content="Atlas仅在本机保存资料。",
                    conversation_id="atlas",
                )
                linked["resting"] = _manual(
                    processor.governance, quoted, "用户只在本机存资料。", "resting"
                )
                key = next(iter(memories))
                assert quoted.evidence_id not in memories[key].evidence_ids
                linked["memory_id"], linked["quoted"] = key, quoted
                claim = Claim(
                    statement=memories[key].content,
                    kind="constraint",
                    citations=[Citation(evidence_id=quoted.evidence_id, quote="Atlas仅在本机")],
                    memory_refs=[refs[key]],
                )
                return {"c0": claim}, {}, 0

            async def review(_self, claims, *_args, **_kwargs):
                if overrule:
                    _delete(processor.governance, linked["resting"].memory_id)
                return claims, 0

            monkeypatch.setattr(discovery_module, "classify_memories", classify)
            monkeypatch.setattr(MatterDiscovery, "_review_and_repair", review)
            store = MatterStore(processor.tasks.database_path)
            service = MatterDiscovery(
                store, MatterModel(processor.profiles, processor.secrets), processor
            )
            try:
                result = await service.run(DiscoveryInput(max_chars=10_000))
                memory = processor.governance.get(linked["memory_id"], user_id="local")
                return result, memory, linked["quoted"]
            finally:
                await processor.shutdown()

        return asyncio.run(scenario())

    # 正向前提：不改判时，这条引文确实会被补成证据。
    _plain, memory, quoted = run(overrule=False)
    assert quoted.evidence_id in memory.evidence_ids

    result, memory, quoted = run(overrule=True)
    assert quoted.evidence_id not in memory.evidence_ids
    assert (result.status, result.error) == ("failed", "matter_memory_changed_during_generation")


# ------------------------------------------------------------ 检查的是写进去的全部证据
#
# 回归场景表明：编码层修订写入「旧证据 ∪ 新证据」，调用方却只拿新证据去查。
# 调用途中人删了另一条建在旧证据上的记忆，修订照写，被改判的原话又被接回去。
# 让每个调用方记得传全，和上一轮「每条路径各自记得查」是同一个病，所以由门自己补全。


def _written_evidence_scene(tmp_path):
    stores = _setup(tmp_path)
    evidence, _profiles, _tasks, governance, _secrets, _profile = stores
    old = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    new = _put(
        evidence,
        message_id="u2",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我在杭州工作。",
        conversation_id="elsewhere",
    )
    target = _manual(governance, old, "用户住在杭州。", "seed-target")
    doomed = _manual(governance, old, "用户家在杭州。", "seed-doomed")
    return governance, old, new, target, doomed


def _change(kind, old, new, target):
    from one_memory.memory_governance import HyLink, HyRevise

    if kind == "create":
        return HyCreate(
            draft=_draft(old, "用户在杭州生活。"), request_id="hy-create", memory_id="hy-new"
        )
    if kind == "revise":
        return HyRevise(
            memory_id=target.memory_id,
            request_id="hy-revise",
            expected_revision=target.revision,
            content="用户住在杭州并在那里工作。",
            evidence_ids=(old.evidence_id, new.evidence_id),
        )
    return HyLink(memory_id="hy-new", evidence_id=old.evidence_id)


@pytest.mark.parametrize("kind", ["create", "revise", "link"])
@pytest.mark.parametrize("cited", ["everything", "only-new"])
def test_a_write_is_checked_against_every_evidence_it_writes(tmp_path, kind, cited) -> None:
    governance, old, new, target, doomed = _written_evidence_scene(tmp_path)
    if kind == "link":
        governance.write_from_hy(
            HyCreate(draft=_draft(new, "用户在杭州工作。"), request_id="seed", memory_id="hy-new"),
            user_id="local",
            derivation=governance.hy_derivation((new.evidence_id,)),
        )
    derivation = governance.hy_derivation((old.evidence_id, new.evidence_id))
    if cited == "only-new":
        derivation = derivation.citing((new.evidence_id,))
    before = governance.get("hy-new" if kind != "revise" else target.memory_id, user_id="local")
    _delete(governance, doomed.memory_id)

    with pytest.raises(MemoryEvidenceOverriddenError):
        governance.write_from_hy(
            _change(kind, old, new, target), user_id="local", derivation=derivation
        )

    assert (
        governance.get("hy-new" if kind != "revise" else target.memory_id, user_id="local")
        == before
    )


@pytest.mark.parametrize("kind", ["create", "revise", "link"])
def test_citing_only_new_evidence_still_writes_when_nothing_was_overruled(tmp_path, kind) -> None:
    """补全证据只是多查，不是多拦：没人改判时照常落地。"""
    governance, old, new, target, _doomed = _written_evidence_scene(tmp_path)
    if kind == "link":
        governance.write_from_hy(
            HyCreate(draft=_draft(new, "用户在杭州工作。"), request_id="seed", memory_id="hy-new"),
            user_id="local",
            derivation=governance.hy_derivation((new.evidence_id,)),
        )
    derivation = governance.hy_derivation((old.evidence_id, new.evidence_id)).citing(
        (new.evidence_id,)
    )

    written = governance.write_from_hy(
        _change(kind, old, new, target), user_id="local", derivation=derivation
    )

    assert old.evidence_id in written.evidence_ids


# ------------------------------------------------------------ HY 自己删的不算人的改判
#
# 回归场景表明：调用前的把关把任何 status=deleted 的记忆都当成人删的，
# 于是 HY 自己退役的记忆，会让它的原话在之后每一轮都被扣下。写事务里的检查已经排除了
# by_model，调用前的把关要用同一条判据。


@pytest.mark.parametrize("by", ["person", "hy"])
def test_only_the_persons_deletion_holds_evidence_back_from_the_next_call(tmp_path, by) -> None:
    from one_memory.memory_governance import HyRetire

    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    record = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    memory = _manual(governance, record, "用户住在杭州。", "seed-memory")
    if by == "person":
        _delete(governance, memory.memory_id)
    else:
        governance.write_from_hy(
            HyRetire(
                memory_id=memory.memory_id,
                request_id="hy-retire",
                expected_revision=memory.revision,
            ),
            user_id="local",
            derivation=governance.hy_derivation((record.evidence_id,)),
        )
    assert governance.get(memory.memory_id, user_id="local").status is MemoryStatus.DELETED
    bridge = FakeBridge(
        outputs=(
            HyMemoryOutput(memory_id="hy-new", content="用户在杭州生活。", layer="L0_BASIC_INFO"),
        )
    )
    task = _task(tasks, profile, record)

    blocked = governance.blocked_source_ids(user_id="local", evidence_ids=(record.evidence_id,))
    finished = asyncio.run(_runner(tmp_path, stores, bridge).run(task.task_id))

    if by == "person":
        assert blocked == {record.evidence_id}
        assert (finished.status, finished.last_error_code) == (
            "cancelled",
            "hy_memory_evidence_changed",
        )
    else:
        assert blocked == set()
        assert (finished.status, finished.last_error_code) == ("completed", None)
