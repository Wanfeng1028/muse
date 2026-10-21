"""新记忆一经创建即有效；「待确认」「已拒绝」只作为旧库迁移的输入存在。

旧库里的行用原始 SQL 写入，而不是调用治理接口：这样同一份测试在
去掉 candidate 之前的代码上也能构造出待确认 / 已拒绝的记忆，用来证明
每条断言在旧实现下都会失败。
"""

import asyncio
import hashlib
import json
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.database_access import MainDatabase, main_database
from one_memory.hy_memory_bridge import (
    HY_WORKING_FACT_LAYER,
    HyGraphNode,
    HyMemoryBridgeError,
    HyMemoryOutput,
)
from one_memory.imports.grants import GRANT_SCHEMA
from one_memory.imports.models import EvidenceContentKind, WrittenBy
from one_memory.memory_governance import (
    DeletionStatus,
    MemoryDraft,
    MemoryGovernanceStore,
    MemoryKind,
    MemoryOrigin,
    MemoryStatus,
)
from one_memory.memory_processing import MemoryProcessingSupervisor
from tests.person_door import as_person
from tests.test_memory_processing import FakeBridge, _put, _runner, _setup, _task

CONTRACTS = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "src"
LEGACY_SCHEMA = Path(__file__).with_name("legacy_schema_f6d624a.sql")
T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-02T00:00:00+00:00"
T2 = "2026-09-03T00:00:00+00:00"

# (action, status) per revision, as the pre-RC4a store wrote them.
LEGACY_HISTORIES = {
    "candidate": (("create", "candidate"),),
    "corrected-candidate": (("create", "candidate"), ("correct", "candidate")),
    "rejected": (("create", "candidate"), ("reject", "rejected")),
    "confirmed": (("create", "candidate"), ("confirm", "confirmed")),
    "deleted": (("create", "candidate"), ("delete", "deleted")),
}
# 旧回执里已不存在的操作，迁移后在 v2 里的写法。
LEGACY_OPERATIONS = {"reject": "delete", "confirm": "legacy"}


def _legacy_memory(
    database: Path,
    *,
    memory_id: str,
    history: tuple[tuple[str, str], ...],
    evidence_id: str,
    content: str,
    origin: str | None = None,
    scopes: tuple[str, ...] = ("all-apps",),
) -> None:
    status = history[-1][1]
    stamps = (T0, T1, T2)
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO governed_memories (memory_id,user_id,kind,status,content,scopes_json,"
            "origin,tags_json,revision,created_at,updated_at,deleted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                memory_id,
                "local",
                "chat",
                status,
                content,
                json.dumps(list(scopes)),
                origin,
                json.dumps(["legacy-tag"]),
                len(history),
                T0,
                stamps[len(history) - 1],
                stamps[len(history) - 1] if status == "deleted" else None,
            ),
        )
        for revision, (action, version_status) in enumerate(history, start=1):
            version_content = content if revision == len(history) else f"{content}（旧）"
            connection.execute(
                "INSERT INTO governed_memory_versions (memory_id,revision,action,status,"
                "content,scopes_json,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    memory_id,
                    revision,
                    action,
                    version_status,
                    version_content,
                    json.dumps(list(scopes)),
                    stamps[revision - 1],
                ),
            )
            connection.execute(
                "INSERT INTO governed_memory_mutations (user_id,request_id,memory_id,"
                "operation,result_revision,created_at) VALUES (?,?,?,?,?,?)",
                (
                    "local",
                    f"{action}:{memory_id}",
                    memory_id,
                    action,
                    revision,
                    stamps[revision - 1],
                ),
            )
        connection.execute(
            "INSERT INTO governed_memory_evidence (memory_id,evidence_id) VALUES (?,?)",
            (memory_id, evidence_id),
        )
    connection.close()


def _tables(database: Path) -> dict[str, list[tuple[object, ...]]]:
    connection = sqlite3.connect(database)
    try:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in (
                "governed_memories",
                "governed_memory_versions",
                "governed_memory_evidence",
                "governed_memory_mutations",
                "memory_deletions",
                "evidence",
            )
        }
    finally:
        connection.close()


def _rows(database: Path, table: str) -> list[dict[str, object]]:
    """按列名读，迁移前的表可能还没有迁移要加的列。"""
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2")]
    finally:
        connection.close()
    if table == "governed_memory_versions":
        for row in rows:
            row.setdefault("migrated_from", None)
            row.setdefault("by_model", 0)
    return rows


def _backups(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "backups").glob("pre-drop-candidate-*.sqlite3"))


def _f6d624a_library(database: Path, journal: str = "wal") -> None:
    """按固定的旧版表结构建一个空库，不经过当前的任何 store。

    `journal` 是库文件原本的日志模式：更早的库没切过 WAL，升级前的备份要照原样保留它。
    """
    connection = sqlite3.connect(database)
    try:
        connection.execute(f"PRAGMA journal_mode={journal}")
        connection.executescript(LEGACY_SCHEMA.read_text())
    finally:
        connection.close()


def _open(database: Path) -> MemoryGovernanceStore:
    """先走升级前那一步再开治理 store，和 Core 启动的顺序一样。"""
    from one_memory.library_upgrade import prepare_library

    return MemoryGovernanceStore(database, prepared=prepare_library(database))


def _legacy_evidence(database: Path, *, index: int, content: str) -> str:
    evidence_id = f"legacy-evidence-{index}"
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO evidence (evidence_id,idempotency_key,user_id,source_id,conversation_id,"
            "message_id,role,written_by,verbatim,content_hash,revision,imported_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                evidence_id,
                f"legacy:{index}",
                "local",
                "cursor",
                "conversation",
                f"m{index}",
                "user",
                "person",
                content,
                hashlib.sha256(content.encode()).hexdigest(),
                1,
                T0,
                T0,
            ),
        )
    connection.close()
    return evidence_id


def _legacy_library(
    tmp_path: Path, stores=None, *, journal: str = "wal"
) -> tuple[Path, dict[str, str]]:
    """不给 stores 时构造固定旧库；给了则在当前库里写旧状态的行。"""
    database = tmp_path / "one-memory.sqlite3"
    if stores is None:
        _f6d624a_library(database, journal)
    ids: dict[str, str] = {}
    for index, name in enumerate(LEGACY_HISTORIES):
        if stores is None:
            evidence_id = _legacy_evidence(database, index=index, content=f"原话 {name}")
        else:
            evidence_id = _put(
                stores[0],
                message_id=f"m{index}",
                role="user",
                written_by=WrittenBy.PERSON,
                content=f"原话 {name}",
            ).evidence_id
        _legacy_memory(
            database,
            memory_id=name,
            history=LEGACY_HISTORIES[name],
            evidence_id=evidence_id,
            content=f"记忆 {name}",
            origin="agent" if name == "candidate" else None,
        )
        ids[name] = evidence_id
    return database, ids


def _schema(database: Path) -> set[tuple[str, str, str | None]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return set(connection.execute("SELECT type, name, sql FROM sqlite_master"))
    finally:
        connection.close()


# ---------------------------------------------------------------- creation


def test_a_new_hy_memory_is_confirmed_from_its_first_revision(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    record = _put(
        evidence,
        message_id="u1",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我偏好本地优先。",
    )
    asyncio.run(_runner(tmp_path, stores, FakeBridge()).run(_task(tasks, profile, record).task_id))

    (memory,) = governance.list(user_id="local")
    assert memory.status is MemoryStatus.CONFIRMED
    assert memory.revision == 1
    history = governance.history(memory.memory_id, user_id="local")
    assert [(v.action, v.status) for v in history] == [("create", MemoryStatus.CONFIRMED)]


@pytest.mark.parametrize("path", ["agent-report", "imported-report"])
def test_linking_to_a_legacy_pending_memory_leaves_it_confirmed(tmp_path, path) -> None:
    """The one path that used to skip auto-confirm: HY returns the id of a
    memory still pending from an older version, and the new support is an
    assistant turn or an imported memory report."""
    stores = _setup(tmp_path)
    evidence, profiles, tasks, _governance, secrets, profile = stores
    if path == "agent-report":
        record = _put(
            evidence,
            message_id="a1",
            role="assistant",
            written_by=WrittenBy.AGENT,
            content="The assistant reports that the deployment finished.",
        )
        memory_id = "same-report"
        bridge = FakeBridge(
            outputs=(HyMemoryOutput(memory_id=memory_id, content=record.verbatim, owner="agent"),)
        )
    else:
        record = _put(
            evidence,
            message_id="r1",
            role="memory",
            written_by=WrittenBy.UNKNOWN,
            content="A proposed choice from an imported report.",
            content_kind=EvidenceContentKind.MEMORY_CONTENT,
        )
        memory_id = "hy-imported-0"
        bridge = FakeBridge()
    _legacy_memory(
        tmp_path / "one-memory.sqlite3",
        memory_id=memory_id,
        history=LEGACY_HISTORIES["candidate"],
        evidence_id=record.evidence_id,
        content=record.verbatim,
        origin="agent",
    )
    governance = _open(tmp_path / "one-memory.sqlite3")
    stores = (evidence, profiles, tasks, governance, secrets, profile)

    asyncio.run(_runner(tmp_path, stores, bridge).run(_task(tasks, profile, record).task_id))

    current = governance.get(memory_id, user_id="local")
    assert current is not None
    assert current.status is MemoryStatus.CONFIRMED
    assert current.origin is MemoryOrigin.AGENT
    history = governance.history(memory_id, user_id="local")
    assert {v.status for v in history} == {MemoryStatus.CONFIRMED}


def test_a_digested_schema_is_confirmed_from_its_first_revision(tmp_path) -> None:
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
    _legacy_memory(
        tmp_path / "one-memory.sqlite3",
        memory_id="seed",
        history=(("create", "confirmed"),),
        evidence_id=record.evidence_id,
        content="记忆 seed",
        scopes=("workspace:v1:project",),
    )
    supervisor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = FakeBridge(
        outputs=(),
        graph_nodes=(
            HyGraphNode(node_id="schema-1", content="用户偏好可验证的结论。", layer="l6_schema"),
        ),
    )

    assert asyncio.run(supervisor.digest())["schemas_recorded"] == 1

    schema = governance.get("schema-1", user_id="local")
    assert schema is not None
    assert (schema.status, schema.revision) == (MemoryStatus.CONFIRMED, 1)
    assert [v.status for v in governance.history("schema-1", user_id="local")] == [
        MemoryStatus.CONFIRMED
    ]


def _client(app) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer local-token", "Origin": "http://127.0.0.1:5173"},
    )


def _app(tmp_path: Path):
    return create_app(
        Settings(
            data_dir=tmp_path / "data",
            source_home=tmp_path,
            api_token=SecretStr("local-token"),
        )
    )


def test_api_created_memory_is_confirmed_and_confirm_reject_are_gone(tmp_path) -> None:
    async def scenario() -> None:
        app = _app(tmp_path)
        async with app.router.lifespan_context(app), _client(app) as client:
            record = _put(
                app.state.evidence_store,
                message_id="m1",
                role="user",
                written_by=WrittenBy.PERSON,
                content="手写的一条记忆的原话",
            )
            created = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "create-1",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "手写记忆",
                        "scopes": ["all-apps"],
                        "evidence_ids": [record.evidence_id],
                    },
                },
            )
            assert created.status_code == 200
            assert (created.json()["status"], created.json()["revision"]) == ("confirmed", 1)
            memory_id = created.json()["memory_id"]
            for action in ("confirm", "reject"):
                refused = await client.post(
                    f"/api/v1/memories/{memory_id}/actions/{action}",
                    json={"request_id": f"{action}-1", "expected_revision": 1},
                )
                assert refused.status_code == 422, action
            # The operations that stay keep working on a memory born confirmed.
            corrected = await client.post(
                f"/api/v1/memories/{memory_id}/correct",
                json={"request_id": "correct-1", "expected_revision": 1, "content": "改过的"},
            )
            assert corrected.status_code == 200
            assert corrected.json()["status"] == "confirmed"

    asyncio.run(scenario())


# ---------------------------------------------------------------- contract


def _ts_union(source: str, name: str) -> set[str]:
    match = re.search(rf"export type {name} =([^;]+);", source)
    assert match, name
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_contract_has_no_pending_or_rejected_state_nor_confirm_reject(tmp_path) -> None:
    spec = _app(tmp_path).openapi()
    schemas = spec["components"]["schemas"]
    statuses = set(schemas["MemoryStatus"]["enum"])
    assert statuses == {"confirmed", "deleted", "superseded"}
    assert set(schemas["MemoryRef"]["properties"]["status"].get("enum", ["confirmed"])) == {
        "confirmed"
    }

    action = next(
        parameter
        for parameter in spec["paths"]["/api/v1/memories/{memory_id}/actions/{action}"]["post"][
            "parameters"
        ]
        if parameter["name"] == "action"
    )
    assert set(action["schema"]["enum"]) == {"undo", "delete"}
    graph = spec["paths"]["/api/v1/memories/graph"]["get"]["parameters"]
    assert "include_candidates" not in {parameter["name"] for parameter in graph}

    index = (CONTRACTS / "index.ts").read_text()
    assert _ts_union(index, "MemoryStatus") == statuses
    matters = (CONTRACTS / "matters.ts").read_text()
    ref = re.search(r"export interface MemoryRef \{(.+?)\n\}", matters, re.S)
    assert ref and re.search(r'\n\s*status: "confirmed";', ref.group(1))


# ---------------------------------------------------------------- migration


def test_legacy_pending_and_rejected_memories_are_migrated_in_place(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    before = _tables(database)
    versions_before = _rows(database, "governed_memory_versions")
    mutations_before = _rows(database, "governed_memory_mutations")
    assert before["memory_deletions"] == []

    store = _open(database)

    after = _tables(database)
    rows = {row[0]: row for row in after["governed_memories"]}
    old = {row[0]: row for row in before["governed_memories"]}
    columns = [
        row[1] for row in sqlite3.connect(database).execute("PRAGMA table_info(governed_memories)")
    ]
    status, deleted_at, updated_at = (
        columns.index("status"),
        columns.index("deleted_at"),
        columns.index("updated_at"),
    )

    def without(row, *indexes):
        return tuple(value for position, value in enumerate(row) if position not in indexes)

    for name in ("candidate", "corrected-candidate"):
        assert rows[name][status] == "confirmed"
        assert rows[name][deleted_at] is None
        assert without(rows[name], status) == without(old[name], status)
    assert rows["rejected"][status] == "deleted"
    assert rows["rejected"][deleted_at] == old["rejected"][updated_at]
    assert without(rows["rejected"], status, deleted_at) == without(
        old["rejected"], status, deleted_at
    )
    assert rows["confirmed"] == old["confirmed"]
    assert rows["deleted"] == old["deleted"]

    statuses = {"candidate": "confirmed", "rejected": "deleted"}
    assert _rows(database, "governed_memory_versions") == [
        {
            **row,
            "action": LEGACY_OPERATIONS.get(row["action"], row["action"]),
            "status": statuses.get(row["status"], row["status"]),
            "migrated_from": row["action"] if row["action"] in LEGACY_OPERATIONS else None,
        }
        for row in versions_before
    ]
    assert _rows(database, "governed_memory_mutations") == [
        {**row, "operation": LEGACY_OPERATIONS.get(row["operation"], row["operation"])}
        for row in mutations_before
    ]
    for table in ("governed_memory_evidence", "evidence"):
        assert after[table] == before[table], table
    # 旧版拒绝从不通知 HY 删除，迁移成 deleted 时补登一条待删除，由删除同步去做。
    assert [(row[0], row[1]) for row in after["memory_deletions"]] == [("rejected", "pending")]

    # Every memory now reads through the enum, history included.
    for name in LEGACY_HISTORIES:
        memory = store.get(name, user_id="local")
        assert memory is not None
        store.history(name, user_id="local")
    assert store.get("rejected", user_id="local").status is MemoryStatus.DELETED
    assert store.get("candidate", user_id="local").origin is MemoryOrigin.AGENT


def test_migration_backs_up_first_and_is_idempotent(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    before = _tables(database)
    schema = _schema(database)

    _open(database)

    (backup,) = _backups(tmp_path)
    assert _schema(backup) == schema
    assert _tables(backup) == before
    migrated = _tables(database)
    _open(database)
    assert _tables(database) == migrated
    assert _backups(tmp_path) == [backup]


def test_a_library_without_legacy_states_is_not_backed_up(tmp_path) -> None:
    stores = _setup(tmp_path)
    record = _put(
        stores[0], message_id="m1", role="user", written_by=WrittenBy.PERSON, content="原话"
    )
    _legacy_memory(
        tmp_path / "one-memory.sqlite3",
        memory_id="current",
        history=(("create", "confirmed"),),
        evidence_id=record.evidence_id,
        content="记忆",
    )
    before = _tables(tmp_path / "one-memory.sqlite3")

    _open(tmp_path / "one-memory.sqlite3")

    assert _backups(tmp_path) == []
    assert _tables(tmp_path / "one-memory.sqlite3") == before


def test_undo_on_a_migrated_memory_never_restores_a_pending_state(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    store = _open(database)

    undone = as_person(store).undo(
        "corrected-candidate", user_id="local", request_id="undo-1", expected_revision=2
    )

    assert undone.status is MemoryStatus.CONFIRMED
    assert undone.content == "记忆 corrected-candidate（旧）"


def test_a_matter_saved_with_a_pending_reference_still_reads_as_confirmed() -> None:
    """事项正文里存着引用当时的记忆状态；迁移后同一修订的记忆已是 confirmed。"""
    from one_memory.matters.models import MemoryRef

    saved = {
        "memory_id": "m-1",
        "revision": 1,
        "status": "candidate",
        "content_hash": "0" * 64,
        "task_id": "t-1",
        "hy_memory_id": "m-1",
        "engine_version": "hy",
        "profile_id": "p-1",
        "profile_revision": 1,
        "model": "m",
    }

    assert MemoryRef.model_validate(saved).status == "confirmed"
    with pytest.raises(ValueError):
        MemoryRef.model_validate({**saved, "status": "rejected"})


# ---------------------------------------------------------------- 回归：一个启动迁移事务


def _old_schema(database: Path) -> None:
    """还没有 `mutations.created_at` 的早期数据库。"""
    connection = sqlite3.connect(database)
    try:
        connection.execute("ALTER TABLE governed_memory_mutations DROP COLUMN created_at")
    finally:
        connection.close()


def _columns(database: Path, table: str) -> set[str]:
    connection = sqlite3.connect(database)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_a_library_without_the_ledger_timestamp_still_migrates(tmp_path) -> None:
    """补 `created_at` 的 UPDATE 会隐式开事务，之后再 BEGIN IMMEDIATE 就报错。"""
    database, _evidence = _legacy_library(tmp_path)
    _old_schema(database)

    store = _open(database)

    assert store.get("candidate", user_id="local").status is MemoryStatus.CONFIRMED
    assert store.get("rejected", user_id="local").status is MemoryStatus.DELETED
    assert "created_at" in _columns(database, "governed_memory_mutations")
    assert len(_backups(tmp_path)) == 1


def test_core_starts_on_a_library_without_the_ledger_timestamp(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database, _evidence = _legacy_library(data_dir)
    _old_schema(database)

    async def scenario() -> None:
        app = _app(tmp_path)
        async with app.router.lifespan_context(app), _client(app) as client:
            detail = await client.get("/api/v1/memories/candidate")
            assert detail.status_code == 200
            assert detail.json()["memory"]["status"] == "confirmed"

    asyncio.run(scenario())


@pytest.mark.parametrize("aged", [False, True], ids=["f6d624a", "without-ledger-timestamp"])
def test_core_start_backs_up_the_library_before_anything_changes_it(tmp_path, aged) -> None:
    """备份是这次启动之前的库：本次启动里任何 store 建的表、索引都不在备份里。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database, _evidence = _legacy_library(data_dir)
    if aged:
        _old_schema(database)
    schema = _schema(database)
    before = _tables(database)

    async def scenario() -> None:
        app = _app(tmp_path)
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(scenario())

    (backup,) = _backups(data_dir)
    assert _schema(backup) == schema
    assert _tables(backup) == before
    assert _schema(database) != schema


def _journal_mode(database: Path) -> str:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()


def test_a_failed_migration_leaves_the_library_exactly_as_it_was(tmp_path) -> None:
    """建表、补列、状态迁移、回执改写在同一个事务里：半路失败全部回滚，日志模式也不动。"""
    database, _evidence = _legacy_library(tmp_path, journal="delete")
    _old_schema(database)
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TRIGGER refuse AFTER UPDATE ON governed_memory_versions "
        "BEGIN SELECT RAISE(ABORT, 'refused'); END"
    )
    connection.close()
    before = _tables(database)
    schema = _schema(database)
    # 文件头第 18、19 字节是读写版本：1 为回滚日志，2 为 WAL。
    header = database.read_bytes()[18:20]
    assert (header, _journal_mode(database)) == (b"\x01\x01", "delete")

    with pytest.raises(sqlite3.DatabaseError, match="refused"):
        _open(database)

    assert database.read_bytes()[18:20] == header
    assert _journal_mode(database) == "delete"
    assert _schema(database) == schema
    assert _tables(database) == before
    assert "created_at" not in _columns(database, "governed_memory_mutations")
    assert "migrated_from" not in _columns(database, "governed_memory_versions")


def test_a_successful_migration_leaves_the_library_in_wal(tmp_path) -> None:
    """迁移提交后才切 WAL，但必须切：只开治理 store、没有别的 store 帮忙时也一样。"""
    database, _evidence = _legacy_library(tmp_path, journal="delete")
    _old_schema(database)
    assert _journal_mode(database) == "delete"

    _open(database)

    assert _journal_mode(database) == "wal"
    assert database.read_bytes()[18:20] == b"\x02\x02"


# ---------------------------------------------------------------- 回归：旧拒绝残留在 HY


class _Hy:
    def __init__(self, *, available: bool) -> None:
        self.available = available
        self.deletes: list[str] = []

    async def delete(self, memory_id: str) -> dict[str, object]:
        if not self.available:
            raise HyMemoryBridgeError("hy_memory_delete_failed")
        self.deletes.append(memory_id)
        return {"success": True}

    async def close(self) -> None:
        return None


def _supervisor(stores, governance=None) -> MemoryProcessingSupervisor:
    evidence, profiles, tasks, own_governance, secrets, _profile = stores
    return MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance or own_governance,
        data_dir=evidence.database_path.parent,
    )


def _deleted(stores, count: int) -> list[str]:
    evidence, _profiles, _tasks, governance, _secrets, _profile = stores
    ids = []
    for index in range(count):
        record = _put(
            evidence,
            message_id=f"gone-{index}",
            role="user",
            written_by=WrittenBy.PERSON,
            content=f"要删的原话 {index}",
        )
        memory = as_person(governance).create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content=f"要删的记忆 {index}",
                scopes=("all-apps",),
                evidence_ids=(record.evidence_id,),
            ),
            request_id=f"create-gone-{index}",
        )
        as_person(governance).delete(
            memory.memory_id,
            user_id="local",
            request_id=f"delete-gone-{index}",
            expected_revision=memory.revision,
        )
        ids.append(memory.memory_id)
    return ids


def _time_passes(database: Path) -> None:
    """把所有待重试删除的下次时间拨到过去，代替真的等退避过去。"""
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "UPDATE memory_deletions SET next_attempt_at = ? WHERE status != 'completed'",
            (T0,),
        )
    connection.close()


def test_a_legacy_rejection_is_deleted_from_hy_and_retried_until_it_lands(tmp_path) -> None:
    stores = _setup(tmp_path)
    database, _evidence = _legacy_library(tmp_path, stores)
    governance = _open(database)
    supervisor = _supervisor(stores, governance)
    hy = _Hy(available=False)
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = hy

    asyncio.run(supervisor.finish_deletions())
    failed = governance.deletion("rejected", user_id="local")
    assert failed is not None and failed.status is DeletionStatus.FAILED

    hy.available = True
    _time_passes(database)
    asyncio.run(supervisor.finish_deletions())
    done = governance.deletion("rejected", user_id="local")
    assert done is not None and done.status is DeletionStatus.COMPLETED
    assert hy.deletes == ["rejected"]

    _time_passes(database)
    asyncio.run(supervisor.finish_deletions())
    assert hy.deletes == ["rejected"]


def test_a_deletion_not_yet_due_is_not_tried(tmp_path) -> None:
    stores = _setup(tmp_path)
    supervisor = _supervisor(stores)
    hy = _Hy(available=False)
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = hy
    (memory_id,) = _deleted(stores, 1)

    asyncio.run(supervisor.finish_deletions())
    assert stores[3].deletion(memory_id, user_id="local").attempts == 1

    hy.available = True
    asyncio.run(supervisor.finish_deletions())
    assert hy.deletes == []
    assert stores[3].deletion(memory_id, user_id="local").attempts == 1

    _time_passes(stores[0].database_path)
    asyncio.run(supervisor.finish_deletions())
    assert hy.deletes == [memory_id]


def test_one_round_of_deletion_sync_takes_a_bounded_batch(tmp_path) -> None:
    from one_memory.memory_governance import DELETION_BATCH

    stores = _setup(tmp_path)
    supervisor = _supervisor(stores)
    hy = _Hy(available=True)
    supervisor._bridges[(stores[5].profile_id, stores[5].revision, None)] = hy
    ids = _deleted(stores, DELETION_BATCH + 5)

    asyncio.run(supervisor.finish_deletions())
    assert len(hy.deletes) == DELETION_BATCH

    asyncio.run(supervisor.finish_deletions())
    assert sorted(hy.deletes) == sorted(ids)


def _app_with_hy(tmp_path: Path, monkeypatch, hy: _Hy):
    async def delete_hy_memory(self, memory_id: str) -> dict[str, object]:
        return await hy.delete(memory_id)

    monkeypatch.setattr(MemoryProcessingSupervisor, "delete_hy_memory", delete_hy_memory)
    return _app(tmp_path)


async def _until(check, *, seconds: float = 5.0) -> None:
    for _ in range(int(seconds / 0.01)):
        if check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never held")


def test_a_deletion_that_failed_at_one_start_lands_after_the_next(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database, _evidence = _legacy_library(data_dir)
    hy = _Hy(available=False)

    async def first_start() -> None:
        app = _app_with_hy(tmp_path, monkeypatch, hy)
        async with app.router.lifespan_context(app):
            store = app.state.memory_governance_store
            await _until(lambda: store.deletion("rejected", user_id="local").attempts == 1)

    asyncio.run(first_start())
    failed = _open(database).deletion("rejected", user_id="local")
    assert (failed.status, failed.attempts) == (DeletionStatus.FAILED, 1)
    assert hy.deletes == []

    hy.available = True
    _time_passes(database)

    async def second_start() -> None:
        app = _app_with_hy(tmp_path, monkeypatch, hy)
        async with app.router.lifespan_context(app):
            store = app.state.memory_governance_store
            await _until(
                lambda: (
                    store.deletion("rejected", user_id="local").status is DeletionStatus.COMPLETED
                )
            )

    asyncio.run(second_start())
    assert hy.deletes == ["rejected"]


class _BrokenHy(_Hy):
    """HY 失败的方式不是 HyMemoryBridgeError，比如取不到模型密钥。"""

    def __init__(self) -> None:
        super().__init__(available=False)
        self.calls = 0

    async def delete(self, memory_id: str) -> dict[str, object]:
        self.calls += 1
        if not self.available:
            raise RuntimeError("keychain locked")
        return await super().delete(memory_id)


def test_an_unexpected_hy_failure_is_backed_off_and_the_sync_survives_it(
    tmp_path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _legacy_library(data_dir)
    hy = _BrokenHy()

    async def scenario() -> None:
        app = _app_with_hy(tmp_path, monkeypatch, hy)
        async with app.router.lifespan_context(app):
            store = app.state.memory_governance_store
            await _until(lambda: store.deletion("rejected", user_id="local").attempts == 1)
            failed = store.deletion("rejected", user_id="local")
            assert failed.status is DeletionStatus.FAILED
            assert store.deletion_retry_at("rejected", user_id="local") is not None
            await asyncio.sleep(0.2)
            # Backed off: not hammered while the wait runs.
            assert hy.calls == 1
            assert not app.state.deletion_sync.done()

            hy.available = True
            _time_passes(data_dir / "one-memory.sqlite3")
            app.state.memory_processing_supervisor.wake_deletions()
            await _until(
                lambda: (
                    store.deletion("rejected", user_id="local").status is DeletionStatus.COMPLETED
                )
            )

    asyncio.run(scenario())
    assert hy.deletes == ["rejected"]


def test_a_round_that_blows_up_does_not_end_the_deletion_sync(tmp_path, monkeypatch) -> None:
    hy = _Hy(available=True)
    real = MemoryGovernanceStore.claim_deletions
    rounds: list[str] = []

    def flaky(self, **kwargs):
        rounds.append("round")
        if len(rounds) == 1:
            raise ValueError("unreadable row")
        return real(self, **kwargs)

    monkeypatch.setattr(MemoryGovernanceStore, "claim_deletions", flaky)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _legacy_library(data_dir)

    async def scenario() -> None:
        app = _app_with_hy(tmp_path, monkeypatch, hy)
        async with app.router.lifespan_context(app):
            await _until(lambda: len(rounds) == 1)
            await asyncio.sleep(0.05)
            assert not app.state.deletion_sync.done()
            app.state.memory_processing_supervisor.wake_deletions()
            store = app.state.memory_governance_store
            await _until(
                lambda: (
                    store.deletion("rejected", user_id="local").status is DeletionStatus.COMPLETED
                )
            )

    asyncio.run(scenario())
    assert hy.deletes == ["rejected"]


def test_the_deletion_sync_keeps_running_and_retries_without_a_restart(
    tmp_path, monkeypatch
) -> None:
    hy = _Hy(available=False)

    async def scenario() -> None:
        app = _app_with_hy(tmp_path, monkeypatch, hy)
        async with app.router.lifespan_context(app), _client(app) as client:
            record = _put(
                app.state.evidence_store,
                message_id="m1",
                role="user",
                written_by=WrittenBy.PERSON,
                content="要删的原话",
            )
            created = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "create-1",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "要删的记忆",
                        "scopes": ["all-apps"],
                        "evidence_ids": [record.evidence_id],
                    },
                },
            )
            memory_id = created.json()["memory_id"]
            deleted = await client.post(
                f"/api/v1/memories/{memory_id}/actions/delete",
                json={"request_id": "delete-1", "expected_revision": 1},
            )
            assert deleted.status_code == 200
            store = app.state.memory_governance_store
            assert store.deletion(memory_id, user_id="local").status is DeletionStatus.FAILED

            hy.available = True
            _time_passes(app.state.evidence_store.database_path)
            app.state.memory_processing_supervisor.wake_deletions()
            await _until(
                lambda: (
                    store.deletion(memory_id, user_id="local").status is DeletionStatus.COMPLETED
                )
            )
            assert not app.state.deletion_sync.done()
            assert hy.deletes == [memory_id]

    asyncio.run(scenario())


# ------------------------------------------------ 回归：在途抽取不得让删掉的记忆复活


class _HeldBridge(FakeBridge):
    """HY 调用停在半路，等测试做完别的事再返回。"""

    def __init__(self, outputs: tuple[HyMemoryOutput, ...]) -> None:
        super().__init__(outputs=outputs)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def ingest(self, request):
        self.entered.set()
        await self.release.wait()
        return await super().ingest(request)


@pytest.mark.parametrize("origin", [MemoryOrigin.EXTRACTED, MemoryOrigin.MANUAL])
def test_a_memory_deleted_while_hy_is_extracting_does_not_come_back(tmp_path, origin) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    record = _put(
        evidence,
        message_id="u1",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我住在杭州。",
    )
    doomed = as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="用户住在杭州。",
            scopes=("all-apps",),
            evidence_ids=(record.evidence_id,),
            origin=origin,
        ),
        request_id="seed-1",
    )
    bridge = _HeldBridge(
        (HyMemoryOutput(memory_id="hy-fresh-id", content=doomed.content, layer="L0_BASIC_INFO"),)
    )
    task = _task(tasks, profile, record)

    async def scenario() -> None:
        running = asyncio.create_task(_runner(tmp_path, stores, bridge).run(task.task_id))
        await bridge.entered.wait()
        as_person(governance).delete(
            doomed.memory_id,
            user_id="local",
            request_id="delete-1",
            expected_revision=doomed.revision,
        )
        bridge.release.set()
        await running

    asyncio.run(scenario())

    assert bridge.requests, "HY 必须真的被调用过，否则这条断言守的是空场景"
    alive = [m for m in governance.list(user_id="local") if m.status is MemoryStatus.CONFIRMED]
    assert [m.content for m in alive] == []
    finished = tasks.get(task.task_id)
    assert (finished.status, finished.last_error_code) == (
        "unknown",
        "hy_memory_evidence_changed",
    )


def _overrule_mid_call(stores, bridge: "_HeldBridge", doomed, run) -> None:
    governance = stores[3]

    async def scenario() -> None:
        running = asyncio.create_task(run())
        await bridge.entered.wait()
        as_person(governance).delete(
            doomed.memory_id,
            user_id="local",
            request_id=f"delete-{doomed.memory_id}",
            expected_revision=doomed.revision,
        )
        bridge.release.set()
        await running

    asyncio.run(scenario())
    assert bridge.requests, "HY 必须真的被调用过"


def _manual(governance, record, content: str, request_id: str):
    return as_person(governance).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content=content,
            scopes=("all-apps",),
            evidence_ids=(record.evidence_id,),
            origin=MemoryOrigin.MANUAL,
        ),
        request_id=request_id,
    )


def test_hy_naming_an_existing_memory_cannot_link_it_to_overruled_evidence(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    elsewhere = _put(
        evidence, message_id="u0", role="user", written_by=WrittenBy.PERSON, content="别处的原话"
    )
    record = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    standing = _manual(governance, elsewhere, "用户住在杭州。", "seed-standing")
    doomed = _manual(governance, record, "用户在杭州。", "seed-doomed")
    bridge = _HeldBridge(
        (
            HyMemoryOutput(
                memory_id=standing.memory_id,
                content=standing.content,
                layer="L0_BASIC_INFO",
                evidence_ids=(record.evidence_id,),
            ),
        )
    )
    task = _task(tasks, profile, record)

    _overrule_mid_call(
        stores, bridge, doomed, lambda: _runner(tmp_path, stores, bridge).run(task.task_id)
    )

    assert governance.get(standing.memory_id, user_id="local").evidence_ids == (
        elsewhere.evidence_id,
    )
    assert tasks.get(task.task_id).status == "unknown"
    assert tasks.get(task.task_id).last_error_code == "hy_memory_evidence_changed"


def test_hy_revising_a_known_memory_cannot_draw_on_overruled_evidence(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    supervisor = _supervisor(stores)
    with sqlite3.connect(tmp_path / "one-memory.sqlite3") as db:
        db.executescript(GRANT_SCHEMA)
        db.execute(
            "INSERT INTO source_grants VALUES ('local','cursor','/authorized','default',?,NULL)",
            (T0,),
        )
    first = _put(
        evidence, message_id="u1", role="user", written_by=WrittenBy.PERSON, content="我住在杭州。"
    )
    earlier = FakeBridge(
        outputs=(
            HyMemoryOutput(
                memory_id="hy-known", content="用户住在杭州。", layer="L2_FACT", owner="user"
            ),
        )
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = earlier
    task = supervisor._enqueue_chunk((first,), profile, freeze_inputs=True)
    asyncio.run(supervisor._create_runner().run(task.task_id))
    known = governance.get("hy-known", user_id="local")
    assert known is not None, tasks.get(task.task_id)
    doomed = _manual(governance, first, "用户在杭州。", "seed-doomed")

    second = _put(
        evidence, message_id="u2", role="user", written_by=WrittenBy.PERSON, content="下个月搬家。"
    )
    bridge = _HeldBridge(
        (
            HyMemoryOutput(
                memory_id="hy-known",
                content="用户住在杭州，下个月搬家。",
                layer="L2_FACT",
                owner="user",
                evidence_ids=(first.evidence_id,),
            ),
        )
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = bridge
    later = supervisor._enqueue_chunk((second,), profile, freeze_inputs=True)

    _overrule_mid_call(
        stores, bridge, doomed, lambda: supervisor._create_runner().run(later.task_id)
    )

    assert [m.hy_memory_id for m in bridge.requests[-1].source_context.known_memories] == [
        "hy-known"
    ]
    assert governance.get("hy-known", user_id="local").content == known.content
    assert tasks.get(later.task_id).status == "unknown"
    assert tasks.get(later.task_id).last_error_code == "hy_memory_evidence_changed"


def test_later_hy_revision_omits_stale_known_memory_without_invalidating_evidence(
    tmp_path,
) -> None:
    """A later model revision is context staleness, not source invalidation.

    Backlog preparation can freeze a rolling chunk while another queued turn
    legitimately advances a memory produced by an earlier chunk.  The older
    output snapshot must then be omitted from context, while its unchanged
    Evidence remains eligible for the task that has not reached HY yet.
    """
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    supervisor = _supervisor(stores)
    with sqlite3.connect(tmp_path / "one-memory.sqlite3") as db:
        db.executescript(GRANT_SCHEMA)
        db.execute(
            "INSERT INTO source_grants VALUES ('local','cursor','/authorized','default',?,NULL)",
            (T0,),
        )

    first = _put(
        evidence,
        message_id="stale-u1",
        role="user",
        written_by=WrittenBy.PERSON,
        content="我住在杭州。",
        conversation_id="rolling",
    )
    initial = FakeBridge(
        outputs=(
            HyMemoryOutput(
                memory_id="hy-known", content="用户住在杭州。", layer="L2_FACT", owner="user"
            ),
        )
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = initial
    first_task = supervisor._enqueue_chunk((first,), profile, freeze_inputs=True)
    assert asyncio.run(supervisor._create_runner().run(first_task.task_id)).status == "completed"

    second = _put(
        evidence,
        message_id="stale-u2",
        role="user",
        written_by=WrittenBy.PERSON,
        content="下个月搬家。",
        conversation_id="rolling",
    )
    waiting = supervisor._enqueue_chunk((first, second), profile, freeze_inputs=True)

    third = _put(
        evidence,
        message_id="stale-u3",
        role="user",
        written_by=WrittenBy.PERSON,
        content="已经搬到上海。",
        conversation_id="rolling",
    )
    evolve = FakeBridge(
        outputs=(
            HyMemoryOutput(
                memory_id="hy-known",
                content="用户住在上海。",
                layer="L2_FACT",
                owner="user",
            ),
        )
    )
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = evolve
    evolving = supervisor._enqueue_chunk((third,), profile, freeze_inputs=True)
    assert asyncio.run(supervisor._create_runner().run(evolving.task_id)).status == "completed"
    assert governance.get("hy-known", user_id="local").revision == 2

    final = FakeBridge(outputs=())
    supervisor._bridges[(profile.profile_id, profile.revision, None)] = final
    finished = asyncio.run(supervisor._create_runner().run(waiting.task_id))

    assert finished.status == "completed"
    with sqlite3.connect(tmp_path / "one-memory.sqlite3") as db:
        assert (
            db.execute(
                "SELECT hy_invocation_count FROM memory_tasks WHERE task_id=?",
                (waiting.task_id,),
            ).fetchone()[0]
            == 1
        )
    assert len(final.requests) == 1
    assert {record.evidence_id for record in final.requests[0].source_context.current} == {
        first.evidence_id,
        second.evidence_id,
    }
    assert final.requests[0].source_context.known_memories == ()


def test_hy_revising_a_coding_memory_cannot_draw_on_overruled_evidence(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, governance, _secrets, profile = stores
    record = _put(
        evidence,
        message_id="u1",
        role="user",
        written_by=WrittenBy.PERSON,
        content="测试统一用 pytest。",
    )
    revisable = _manual(governance, record, "项目测试用 pytest。", "seed-revisable")
    doomed = _manual(governance, record, "项目用 pytest。", "seed-doomed")
    bridge = _HeldBridge(
        (
            HyMemoryOutput(
                memory_id=revisable.memory_id,
                content="项目测试统一用 pytest。",
                layer=HY_WORKING_FACT_LAYER,
                evidence_ids=(record.evidence_id,),
            ),
        )
    )
    task = _task(tasks, profile, record)

    _overrule_mid_call(
        stores, bridge, doomed, lambda: _runner(tmp_path, stores, bridge).run(task.task_id)
    )

    assert governance.get(revisable.memory_id, user_id="local").content == revisable.content
    assert tasks.get(task.task_id).status == "unknown"
    assert tasks.get(task.task_id).last_error_code == "hy_memory_evidence_changed"


# ---------------------------------------------------------------- 回归：备份文件


class _BackupSpy:
    """Stands in for the source connection so a test sees the copy mid-write."""

    def __init__(self, connection: sqlite3.Connection, on_backup) -> None:
        self._connection = connection
        self._on_backup = on_backup

    def backup(self, target: sqlite3.Connection, *args, **kwargs) -> None:
        self._on_backup()
        self._connection.backup(target, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def _spy_on_backup(monkeypatch, on_backup) -> None:
    real_read = MainDatabase.read

    @contextmanager
    def read(self, *args, **kwargs):
        with real_read(self, *args, **kwargs) as connection:
            yield _BackupSpy(connection, on_backup)

    monkeypatch.setattr(MainDatabase, "read", read)


def _modes(directory: Path) -> dict[str, int]:
    return {path.name: stat.S_IMODE(path.lstat().st_mode) for path in directory.iterdir()}


def test_the_backup_is_owner_only_while_it_is_being_written(tmp_path, monkeypatch) -> None:
    database, _evidence = _legacy_library(tmp_path)
    seen: list[dict[str, int]] = []
    named: list[list[Path]] = []

    def look() -> None:
        seen.append(_modes(tmp_path / "backups"))
        named.append([path.stat().st_size for path in _backups(tmp_path)])

    _spy_on_backup(monkeypatch, look)

    _open(database)

    # The copy exists by the time bytes go in; its mode then is what matters.
    assert seen and all(seen), seen
    # Killed mid-copy, nothing under a backup's name may be left looking whole:
    # the name is held by an empty reservation until the finished copy replaces it.
    assert named == [[0]]
    assert {mode for modes in seen for mode in modes.values()} == {0o600}
    (backup,) = _backups(tmp_path)
    assert _modes(tmp_path / "backups") == {backup.name: 0o600}


def test_a_failed_backup_leaves_no_file_and_does_not_migrate(tmp_path, monkeypatch) -> None:
    database, _evidence = _legacy_library(tmp_path)
    before = _tables(database)
    schema = _schema(database)

    def fail() -> None:
        raise sqlite3.OperationalError("disk I/O error")

    _spy_on_backup(monkeypatch, fail)

    from one_memory.library_upgrade import LibraryUpgradeError

    with pytest.raises(LibraryUpgradeError, match="disk I/O error"):
        _open(database)

    assert list((tmp_path / "backups").iterdir()) == []
    assert _schema(database) == schema
    assert _tables(database) == before


def test_an_existing_backups_directory_is_tightened_to_owner_only(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    directory = tmp_path / "backups"
    directory.mkdir()
    directory.chmod(0o755)

    _open(database)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_a_symlinked_backups_directory_is_refused(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "backups").symlink_to(elsewhere, target_is_directory=True)
    before = _tables(database)
    schema = _schema(database)

    from one_memory.library_upgrade import LibraryUpgradeError

    with pytest.raises(LibraryUpgradeError, match="backups"):
        _open(database)

    assert list(elsewhere.iterdir()) == []
    assert _schema(database) == schema
    assert _tables(database) == before


def test_a_backup_never_replaces_a_file_already_under_its_name(tmp_path) -> None:
    database, _evidence = _legacy_library(tmp_path)
    target = tmp_path / "backups" / "pre-drop-candidate-taken.sqlite3"
    target.parent.mkdir(mode=0o700)
    target.write_bytes(b"an earlier backup")

    with pytest.raises(FileExistsError):
        main_database(database).back_up(target)

    assert target.read_bytes() == b"an earlier backup"
    assert _modes(tmp_path / "backups") == {target.name: stat.S_IMODE(target.stat().st_mode)}
