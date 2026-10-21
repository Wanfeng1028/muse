"""L0 基础画像层的 client_meta 透传。

线上实测发现：一次写入产出的多条记忆里，l2_fact 能带回 meta，
l0_basic_info 拿不到——画像走独立的 upsert 路径，透传时漏了。
这组测试锁住修复后的行为。
"""
import asyncio

from hy_memory.agent.tools.basic_profile import upsert_basic_profile
from hy_memory.models.memory import MemoryLayer, MemoryStatus


class FakeVectorStore:
    def __init__(self, nodes=None):
        self.nodes = list(nodes or [])
        self.upserted = []
        self.payload_updates = []

    async def list_by_user(self, **kwargs):
        return list(self.nodes)

    async def get_by_id(self, node_id):
        return next((n for n in self.nodes if n.node_id == node_id), None)

    async def upsert(self, node):
        self.upserted.append(node)
        self.nodes.append(node)

    async def update_payload(self, node_id, updates):
        self.payload_updates.append((node_id, updates))


class FakeEmbedService:
    async def embed_queued(self, text):
        return [0.1] * 8


FIELDS = ["name", "age", "location"]


def upsert(store, kv, meta=None, user="u1"):
    return asyncio.run(
        upsert_basic_profile(
            user_id=user,
            kv=kv,
            vector_store=store,
            embed_service=FakeEmbedService(),
            allowed_fields=FIELDS,
            client_meta=meta,
        )
    )


class TestBasicProfileClientMeta:
    def test_meta_attached_to_new_node(self):
        store = FakeVectorStore()
        meta = {"source": "codebuddy", "trace_id": "t-1"}

        r = upsert(store, {"name": "张伟"}, meta=meta)

        assert r.success and r.changed
        assert len(store.upserted) == 1
        node = store.upserted[0]
        assert node.layer == MemoryLayer.L0_BASIC_INFO
        assert node.custom["meta"] == [meta]

    def test_basic_info_kv_still_stored_alongside_meta(self):
        """meta 不能挤掉原有的 basic_info_kv——后者是画像装配的依据。"""
        store = FakeVectorStore()

        upsert(store, {"name": "张伟", "age": 35}, meta={"k": "v"})

        custom = store.upserted[0].custom
        assert custom["basic_info_kv"] == {"name": "张伟", "age": 35}
        assert custom["meta"] == [{"k": "v"}]

    def test_no_meta_key_when_not_provided(self):
        """不传 meta 时不应凭空造出该键，否则旧数据形态被改。"""
        store = FakeVectorStore()

        upsert(store, {"name": "张伟"})

        assert "meta" not in store.upserted[0].custom

    def test_empty_meta_treated_as_absent(self):
        store = FakeVectorStore()

        upsert(store, {"name": "张伟"}, meta={})

        assert "meta" not in store.upserted[0].custom

    def test_meta_is_copied_not_referenced(self):
        """存进去后调用方再改自己的 dict，不应影响已落库的内容。"""
        store = FakeVectorStore()
        meta = {"source": "a"}

        upsert(store, {"name": "张伟"}, meta=meta)
        meta["source"] = "mutated"

        assert store.upserted[0].custom["meta"] == [{"source": "a"}]

    def test_new_version_carries_only_current_meta(self):
        """L0 每次变更新建节点、旧节点转 SUPERSEDED，与 SUPERSEDE 同构：
        新节点只带本次 meta，不继承旧链，避免长链上无限累积。"""
        store = FakeVectorStore()

        upsert(store, {"name": "张伟"}, meta={"round": 1})
        upsert(store, {"name": "张伟", "age": 35}, meta={"round": 2})

        assert len(store.upserted) == 2
        assert store.upserted[1].custom["meta"] == [{"round": 2}]

        # 旧节点被标记取代，其 meta 原样留在链上
        assert store.payload_updates
        old_id, updates = store.payload_updates[-1]
        assert old_id == store.upserted[0].node_id
        assert updates["status"] == MemoryStatus.SUPERSEDED.value
        assert store.upserted[0].custom["meta"] == [{"round": 1}]

    def test_no_diff_writes_nothing_even_with_meta(self):
        """内容无变化时本就不落新版本，带了 meta 也不应因此凭空建节点。"""
        store = FakeVectorStore()

        upsert(store, {"name": "张伟"}, meta={"round": 1})
        r = upsert(store, {"name": "张伟"}, meta={"round": 2})

        assert r.success and not r.changed
        assert len(store.upserted) == 1
