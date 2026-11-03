# -*- coding: utf-8 -*-
"""
list_by_user 多值枚举（user_ids / agent_ids）与 only_latest 语义。

背景（R1 需求：CTX 需一次拉取多个 user 的记忆）：
- list_by_user 原本只接受单个 user_id / agent_id，多用户须串行 N 次调用。
- 新增 user_ids / agent_ids 多值参数，单值参数保留向后兼容。

only_latest 默认值是本次改动风险最高处，必须锁死：
- 默认 False（返回演化链全部版本）。clone 依赖此语义复制完整链，
  一旦默认改成 True，克隆会静默丢失全部历史版本。
- list API 路径（client._list_vdb_bucket）同样不传：该路径的过滤条件与改动前
  逐字一致（仅 status=ACTIVE），本次只加多值枚举，不得改变现网返回口径。

同理 status_filter 不传时不得兜底过滤 ACTIVE。
"""

import asyncio
import inspect
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


DIMS = 32


def _node(user_id, agent_id="a1", content="x", is_latest=True,
          status=MemoryStatus.ACTIVE, layer=MemoryLayer.L2_FACT):
    import random
    n = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id=user_id,
        agent_id=agent_id,
        session_id="s1",
        content=content,
        layer=layer,
        status=status,
        is_latest=is_latest,
    )
    vec = [random.gauss(0, 1) for _ in range(DIMS)]
    norm = sum(v * v for v in vec) ** 0.5
    n.embedding = [v / norm for v in vec]
    return n


@pytest.fixture
def faiss_store(tmp_path):
    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "faiss",
            "collection_name": "test_multi_value",
            "persist_directory": str(tmp_path / "faiss_data"),
            "embedding_dims": DIMS,
        },
    })
    from hy_memory.data.vector_store_faiss import FaissVectorStore
    vs = FaissVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestMultiValueEnumeration:
    def test_user_ids_returns_union(self, faiss_store):
        run(faiss_store.upsert_batch([
            _node("u1", content="a"),
            _node("u2", content="b"),
            _node("u3", content="c"),
        ]))

        both = run(faiss_store.list_by_user(user_ids=["u1", "u2"]))
        assert {n.user_id for n in both} == {"u1", "u2"}, "应只返回请求的两个 user"
        assert len(both) == 2

    def test_agent_ids_multi_value(self, faiss_store):
        run(faiss_store.upsert_batch([
            _node("u1", agent_id="g1"),
            _node("u1", agent_id="g2"),
            _node("u1", agent_id="g3"),
        ]))

        got = run(faiss_store.list_by_user(user_id="u1", agent_ids=["g1", "g3"]))
        assert {n.agent_id for n in got} == {"g1", "g3"}

    def test_single_value_still_works(self, faiss_store):
        """向后兼容：11 处生产调用点全部使用单值形式。"""
        run(faiss_store.upsert_batch([
            _node("u1", agent_id="g1"),
            _node("u2", agent_id="g1"),
        ]))

        got = run(faiss_store.list_by_user(user_id="u1", agent_id="g1"))
        assert len(got) == 1
        assert got[0].user_id == "u1"

    def test_user_ids_takes_precedence_over_user_id(self, faiss_store):
        run(faiss_store.upsert_batch([_node("u1"), _node("u2")]))

        got = run(faiss_store.list_by_user(user_id="u1", user_ids=["u2"]))
        assert {n.user_id for n in got} == {"u2"}

    def test_no_user_at_all_returns_empty_not_full_scan(self, faiss_store):
        """user_id 从必填位置参数变为可选后，两者皆空必须拒绝，不能退化成全表扫描。"""
        run(faiss_store.upsert_batch([_node("u1"), _node("u2")]))

        assert run(faiss_store.list_by_user()) == []
        assert run(faiss_store.list_by_user(user_ids=[])) == []


class TestOnlyLatestDefault:
    """clone 的生命线：默认必须返回演化链全部版本。"""

    def test_default_returns_history_versions(self, faiss_store):
        run(faiss_store.upsert_batch([
            _node("u1", content="v2 head", is_latest=True),
            _node("u1", content="v1 old", is_latest=False,
                  status=MemoryStatus.SUPERSEDED),
        ]))

        got = run(faiss_store.list_by_user(user_id="u1"))
        assert len(got) == 2, (
            "list_by_user 默认不得过滤 is_latest——clone 依赖它复制完整演化链，"
            "默认值改成 True 会导致克隆静默丢失历史版本"
        )
        assert {n.content for n in got} == {"v2 head", "v1 old"}

    def test_default_returns_all_statuses(self, faiss_store):
        """不传 status_filter 时不得兜底过滤 ACTIVE（clone 同样依赖）。"""
        run(faiss_store.upsert_batch([
            _node("u1", content="active", status=MemoryStatus.ACTIVE),
            _node("u1", content="superseded", is_latest=False,
                  status=MemoryStatus.SUPERSEDED),
            _node("u1", content="shadow", is_latest=False,
                  status=MemoryStatus.SHADOW),
        ]))

        got = run(faiss_store.list_by_user(user_id="u1"))
        assert len(got) == 3
        assert {n.content for n in got} == {"active", "superseded", "shadow"}

    def test_only_latest_true_filters_dirty_data(self, faiss_store):
        """显式传 True 时该过滤须真的生效（当前无调用方，为后续启用留的能力）。

        构造 status=ACTIVE 但 is_latest=False 的脏数据：正常写入不会产生
        （writer 两字段成对写），故只有脏数据能验证该过滤真的接上了——
        若仅靠 status 过滤，这条会漏出去。
        """
        run(faiss_store.upsert_batch([
            _node("u1", content="head", is_latest=True),
            _node("u1", content="dirty", is_latest=False,
                  status=MemoryStatus.ACTIVE),
        ]))

        got = run(faiss_store.list_by_user(
            user_id="u1", status_filter=[MemoryStatus.ACTIVE], only_latest=True,
        ))
        assert [n.content for n in got] == ["head"]


class TestListVdbBucketWiring:
    """client 的 list 路径：多值是否真的透传到了后端。"""

    def _client_with(self, store):
        from hy_memory.client import HyMemoryClient
        c = HyMemoryClient.__new__(HyMemoryClient)
        c._vector_store = store
        return c

    def test_multi_user_bucket_merges_and_filters(self, faiss_store):
        run(faiss_store.upsert_batch([
            _node("u1", content="u1 head"),
            _node("u2", content="u2 head"),
            _node("u3", content="u3 head"),
            # 历史版本：status 已是 SUPERSEDED，list 不应展示
            _node("u1", content="u1 old", is_latest=False,
                  status=MemoryStatus.SUPERSEDED),
            # L1_RAW：list 一律排除
            _node("u1", content="raw", layer=MemoryLayer.L1_RAW),
        ]))

        got = run(self._client_with(faiss_store)._list_vdb_bucket(
            user_id="", agent_id=None, user_ids=["u1", "u2"],
            agent_ids=None, limit=100, offset=0, order="desc",
        ))

        contents = {m["content"] for m in got["memories"]}
        assert contents == {"u1 head", "u2 head"}, f"实际返回 {contents}"
        assert got["total"] == 2

    def test_filter_semantics_unchanged_from_before(self, faiss_store):
        """list 的过滤口径必须与改动前逐字一致：只看 status，不看 is_latest。

        status=ACTIVE 但 is_latest=False 的脏数据改动前会返回，现在也必须返回。
        额外叠加 only_latest 会拦掉它——那是在改现网已有接口的返回口径，
        本次明确不做（该修复若要做，须单独评估并让研发验证条数变化）。
        """
        run(faiss_store.upsert_batch([
            _node("u1", content="head"),
            _node("u1", content="dirty", is_latest=False,
                  status=MemoryStatus.ACTIVE),
        ]))

        got = run(self._client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
        ))

        assert {m["content"] for m in got["memories"]} == {"head", "dirty"}

    def test_each_item_carries_user_id_for_attribution(self, faiss_store):
        """R1 验收：多用户混合返回后，每条记忆必须可追溯归属。"""
        run(faiss_store.upsert_batch([
            _node("u1", content="a"), _node("u2", content="b"),
        ]))

        got = run(self._client_with(faiss_store)._list_vdb_bucket(
            user_id="", agent_id=None, user_ids=["u1", "u2"],
            agent_ids=None, limit=100, offset=0, order="desc",
        ))

        by_content = {m["content"]: m for m in got["memories"]}
        assert by_content["a"]["user_id"] == "u1"
        assert by_content["b"]["user_id"] == "u2"

    def test_pagination_applies_after_merge(self, faiss_store):
        run(faiss_store.upsert_batch(
            [_node("u1", content=f"u1-{i}") for i in range(3)]
            + [_node("u2", content=f"u2-{i}") for i in range(3)]
        ))

        c = self._client_with(faiss_store)
        page = run(c._list_vdb_bucket(
            user_id="", agent_id=None, user_ids=["u1", "u2"],
            agent_ids=None, limit=4, offset=0, order="desc",
        ))
        assert page["total"] == 6, "total 是合并后的总数"
        assert len(page["memories"]) == 4

        rest = run(c._list_vdb_bucket(
            user_id="", agent_id=None, user_ids=["u1", "u2"],
            agent_ids=None, limit=4, offset=4, order="desc",
        ))
        assert len(rest["memories"]) == 2

    def test_single_user_path_unchanged(self, faiss_store):
        """既有单值调用必须逐字段不变（R1 验收标准）。"""
        run(faiss_store.upsert_batch([_node("u1", content="a"), _node("u2", content="b")]))

        got = run(self._client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
        ))
        assert [m["content"] for m in got["memories"]] == ["a"]


class TestAllBackendSignatures:
    """三个后端 + 基类签名必须齐平，否则换 provider 就炸。"""

    def _list_by_user_of(self, module_name, class_name):
        import importlib
        mod = importlib.import_module(f"hy_memory.data.{module_name}")
        return getattr(getattr(mod, class_name), "list_by_user")

    @pytest.mark.parametrize("module_name,class_name", [
        ("vector_store_base", "VectorStoreBase"),
        ("vector_store_qdrant", "QdrantVectorStore"),
        ("vector_store_chroma", "ChromaVectorStore"),
        ("vector_store_faiss", "FaissVectorStore"),
    ])
    def test_signature_has_multi_value_params(self, module_name, class_name):
        params = inspect.signature(
            self._list_by_user_of(module_name, class_name)
        ).parameters

        for name in ("user_ids", "agent_ids", "only_latest", "with_vectors"):
            assert name in params, f"{class_name}.list_by_user 缺少 {name}"

        assert params["only_latest"].default is False, (
            f"{class_name}.list_by_user 的 only_latest 默认值必须是 False"
        )
        assert params["with_vectors"].default is True, (
            f"{class_name}.list_by_user 的 with_vectors 默认值必须是 True，避免影响既有调用方"
        )
        assert params["user_id"].default is None, (
            f"{class_name}.list_by_user 的 user_id 应可选（由 user_ids 替代）"
        )
