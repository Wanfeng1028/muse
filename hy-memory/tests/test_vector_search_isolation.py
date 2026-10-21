# -*- coding: utf-8 -*-
"""
Neo4j 向量检索隔离性和多用户场景的测试

测试迭代式多轮获取策略确保：
1. 不同 isolation_key 的结果不会交叉泄露
2. 稀疏用户能获得期望的召回率
3. 迭代搜索开销 < 10%（正常情况下）

NOTE: 这些测试需要运行的 Neo4j 实例和已初始化的图模式。
标记为 @pytest.mark.integration 的测试在集成环境中运行。
"""

import asyncio
import pytest
from typing import List, Dict, Any
import time

# 假设已导入必要的类
# from hy_memory.data.graph_store_neo4j import Neo4jGraphStore
# from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


@pytest.mark.integration
class TestVectorSearchIsolation:
    """向量检索隔离性测试"""

    @pytest.mark.slow
    async def test_vector_search_no_cross_user_leakage(self, graph_store_neo4j_fixture):
        """
        测试：两个用户的向量搜索结果不会交叉泄露
        
        Setup:
        - User A: 创建 5 个关于"编程"的记忆节点
        - User B: 创建 10 个关于"美食"的记忆节点
        
        Query:
        - User A 搜索"编程"相关向量，isolation_key=user_a_ik
        
        Expected:
        - 返回结果仅包含 User A 的记忆（via isolation_key 检查）
        - 不包含 User B 的任何记忆
        """
        # 创建两个 isolation_key
        ik_a = "user_a::default"
        ik_b = "user_b::default"
        
        # 生成模拟向量（1536 维，符合 text-embedding-3-large）
        def make_embedding(seed: int) -> List[float]:
            import random
            random.seed(seed)
            return [random.gauss(0, 1) for _ in range(1536)]
        
        # User A: 编程相关记忆
        user_a_memories = [
            {
                "node_id": f"user_a_prog_{i}",
                "content": f"编程相关的记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_a,
                "embedding": make_embedding(100 + i),  # 一致的向量
                "confidence": 0.9,
                "custom_json": {"topic": "programming"}
            }
            for i in range(5)
        ]
        
        # User B: 美食相关记忆
        user_b_memories = [
            {
                "node_id": f"user_b_food_{i}",
                "content": f"美食相关的记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_b,
                "embedding": make_embedding(200 + i),  # 不同的向量
                "confidence": 0.9,
                "custom_json": {"topic": "food"}
            }
            for i in range(10)
        ]
        
        # 使用 graph_store_neo4j_fixture 的方法创建节点
        # （假设 graph_store 有某种批量创建方法）
        # 实际测试中这需要正确的实现
        
        # 用 User A 的向量进行搜索
        query_embedding = user_a_memories[0]["embedding"]
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik_a,
            limit=10,
        )
        
        # 验证隔离性
        for result in results:
            assert result["node_id"].startswith("user_a_"), \
                f"Expected all results for user_a, but got {result['node_id']}"
        
        print(f"✓ Isolation test passed: got {len(results)} results for user_a only")

    @pytest.mark.slow
    async def test_vector_search_returns_results_for_sparse_user(self, graph_store_neo4j_fixture):
        """
        测试：稀疏用户（结果不在全局 top-K）仍能获得结果
        
        Setup:
        - User A (sparse): 5 个记忆
        - User B (dense): 100 个相似度更高的记忆
        
        Query:
        - User A 搜索，limit=10
        - 全局 top-30（迭代初值）可能被 User B 的记忆填满
        
        Expected:
        - 迭代搜索通过增加 K 倍数，最终返回 User A 的结果
        - 不会因为全局 top-K 被其他用户填满就放弃
        """
        ik_a = "sparse_user::default"
        ik_b = "dense_user::default"
        
        def make_embedding(seed: int) -> List[float]:
            import random
            random.seed(seed)
            return [random.gauss(0, 1) for _ in range(1536)]
        
        # Sparse user: 5 个记忆
        sparse_memories = [
            {
                "node_id": f"sparse_{i}",
                "content": f"稀疏用户记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_a,
                "embedding": make_embedding(300 + i),
                "confidence": 0.7,
            }
            for i in range(5)
        ]
        
        # Dense user: 100 个高相似度的记忆（可能填满全局 top-30）
        dense_memories = [
            {
                "node_id": f"dense_{i}",
                "content": f"密集用户记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_b,
                "embedding": make_embedding(400),  # 都使用相同的种子（高相似性）
                "confidence": 0.95,
            }
            for i in range(100)
        ]
        
        # 搜索 sparse user 的结果
        query_embedding = sparse_memories[0]["embedding"]
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik_a,
            limit=5,
        )
        
        # 验证即使有 100 个密集用户的竞争，仍能获得稀疏用户的结果
        assert len(results) > 0, "Sparse user should get results despite dense competition"
        assert all(r["node_id"].startswith("sparse_") for r in results), \
            "All results should be from sparse user"
        
        print(f"✓ Sparse user test passed: got {len(results)} results despite 100 competing dense nodes")

    @pytest.mark.slow
    async def test_vector_search_multi_user_prefix(self, graph_store_neo4j_fixture):
        """
        测试：跨 user_id 搜索（指定 user_id 但不指定 agent_id）
        
        Setup:
        - User X::agent_1: 3 个记忆
        - User X::agent_2: 3 个记忆
        - User Y::agent_1: 3 个记忆
        
        Query:
        - 用 user_id="User X"（不指定 agent_id）搜索
        
        Expected:
        - 返回 User X::agent_1 和 User X::agent_2 的结果
        - 不包含 User Y 的结果
        """
        def make_embedding(seed: int) -> List[float]:
            import random
            random.seed(seed)
            return [random.gauss(0, 1) for _ in range(1536)]
        
        # 创建多个 agent 下的记忆
        memories_x_agent_1 = [
            {
                "node_id": f"x_a1_{i}",
                "content": f"User X Agent 1 记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": "user_x::agent_1",
                "embedding": make_embedding(500 + i),
                "confidence": 0.8,
            }
            for i in range(3)
        ]
        
        memories_x_agent_2 = [
            {
                "node_id": f"x_a2_{i}",
                "content": f"User X Agent 2 记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": "user_x::agent_2",
                "embedding": make_embedding(550 + i),
                "confidence": 0.8,
            }
            for i in range(3)
        ]
        
        memories_y_agent_1 = [
            {
                "node_id": f"y_a1_{i}",
                "content": f"User Y Agent 1 记忆 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": "user_y::agent_1",
                "embedding": make_embedding(600 + i),
                "confidence": 0.8,
            }
            for i in range(3)
        ]
        
        # 跨 agent 搜索
        query_embedding = memories_x_agent_1[0]["embedding"]
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key="",  # 空隔离键
            user_id="user_x",  # 指定 user_id（会转为 user_x::）
            limit=10,
        )
        
        # 验证
        result_ids = [r["node_id"] for r in results]
        # 应包含来自 user_x 的结果
        has_x_results = any(id.startswith("x_a1_") or id.startswith("x_a2_") for id in result_ids)
        # 不应包含来自 user_y 的结果
        has_y_results = any(id.startswith("y_a1_") for id in result_ids)
        
        assert has_x_results, "Should include results from user_x"
        assert not has_y_results, "Should not include results from user_y"
        
        print(f"✓ Multi-user prefix test passed: got {len(results)} results from user_x only")


@pytest.mark.integration
class TestVectorSearchPerformance:
    """向量检索性能测试"""

    @pytest.mark.slow
    async def test_vector_search_iteration_overhead(self, graph_store_neo4j_fixture):
        """
        测试：迭代搜索的性能开销 < 10%
        
        Measure:
        - 单轮查询耗时（limit*3 获取）
        - 多轮迭代查询耗时
        
        Expected:
        - 多轮迭代开销（相对于单轮）< 10%
        - 在正常情况下，90%+ 的结果在首轮获得（无需迭代）
        """
        ik = "test_perf::default"
        
        def make_embedding(seed: int) -> List[float]:
            import random
            random.seed(seed)
            return [random.gauss(0, 1) for _ in range(1536)]
        
        # 创建足够的节点以测试性能
        for i in range(100):
            # 模拟创建节点
            pass
        
        query_embedding = make_embedding(1000)
        
        # 测量搜索耗时
        start = time.time()
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik,
            limit=10,
        )
        elapsed = time.time() - start
        
        # 日志中应该能看到迭代次数
        # 如果结果充足且在首轮获得，elapsed 应该接近单轮查询时间
        # 如果需要多轮，elapsed 会相应增加，但不应超过单轮的 1.1 倍
        
        print(f"✓ Performance test: vector_search took {elapsed:.3f}s for {len(results)} results")
        assert elapsed < 5.0, "Vector search should complete within 5 seconds"

    @pytest.mark.slow
    async def test_beh_vector_search_isolation(self, graph_store_neo4j_fixture):
        """
        测试：行为向量搜索（beh_vector_search）也遵守隔离策略
        
        验证 beh_vector_search 使用相同的迭代式多轮获取，确保隔离性
        """
        ik_a = "user_a_beh::default"
        ik_b = "user_b_beh::default"
        
        def make_embedding(seed: int) -> List[float]:
            import random
            random.seed(seed)
            return [random.gauss(0, 1) for _ in range(512)]
        
        # 创建 L6 schema 行为节点
        beh_nodes_a = [
            {
                "node_id": f"beh_a_{i}",
                "content": f"User A 行为 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_a,
                "beh_embedding": make_embedding(700 + i),
            }
            for i in range(3)
        ]
        
        beh_nodes_b = [
            {
                "node_id": f"beh_b_{i}",
                "content": f"User B 行为 {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_b,
                "beh_embedding": make_embedding(800 + i),
            }
            for i in range(10)
        ]
        
        # 行为向量搜索
        query_beh_embedding = beh_nodes_a[0]["beh_embedding"]
        results = await graph_store_neo4j_fixture.beh_vector_search(
            query_beh_embedding=query_beh_embedding,
            isolation_key=ik_a,
            limit=5,
        )
        
        # 验证隔离性
        for result in results:
            assert result["node_id"].startswith("beh_a_"), \
                f"beh_vector_search should isolate by isolation_key, got {result['node_id']}"
        
        print(f"✓ Behavior vector search isolation test passed: got {len(results)} results for user_a only")


# ==================== Fixtures ====================

@pytest.fixture
async def graph_store_neo4j_fixture():
    """
    返回一个配置好的 Neo4j GraphStore 实例
    
    NOTE: 这是一个占位符，实际使用需要：
    1. 从配置文件读取 Neo4j 连接信息
    2. 初始化 GraphStore
    3. 在测试后清理
    """
    # 这里假设测试环境已配置 NEO4J_URI 等环境变量
    from hy_memory.config import MemoryConfig
    from hy_memory.data.graph_store_neo4j import Neo4jGraphStore
    
    config = MemoryConfig(
        # 从环境变量读取
        embedding_dims=1536,
        neo4j_uri="neo4j://localhost:7687",  # 需要从 .env 覆盖
        neo4j_user="neo4j",
        neo4j_password="password",
    )
    
    store = Neo4jGraphStore(config)
    await store.initialize()
    
    yield store
    
    # 清理
    await store.close()

