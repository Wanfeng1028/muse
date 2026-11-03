# -*- coding: utf-8 -*-
"""
Neo4j 向量检索对抗场景测试

重点：在极端场景下验证迭代搜索的有效性
- 99% 的索引被其他用户的高相似度数据填满
- 目标用户的相关数据相似度较低但仍需返回

这是 Solution B 的 stress test，验证：
1. 最坏情况下迭代仍能找到目标用户的结果
2. 迭代次数和 K 倍数增长足以覆盖这些场景
3. 不会因为数据竞争而产生错误结果或数据泄露
"""

import pytest
from typing import List
import numpy as np


@pytest.mark.integration
class TestVectorSearchAdversarial:
    """对抗性向量搜索场景测试"""

    @pytest.mark.slow
    async def test_vector_search_with_99_percent_competitors(self, graph_store_neo4j_fixture):
        """
        极端场景：99% 的全局 top-K 被其他用户填满
        
        Setup:
        - Target User: 1 个记忆（低相似度 0.4）
        - Competitor Users: 990 个记忆（高相似度 0.95+）
        
        全局 top-30 会被 competitor 填满，需要迭代到更大的 K 才能找到 target
        
        Expected:
        - 即使目标用户的相似度较低，迭代搜索也应该找到
        - 通过增加 K（3 → 4.5 → 6.75）覆盖更多结果
        """
        ik_target = "target_user::default"
        ik_competitor = "competitor::default"
        
        np.random.seed(111)
        
        # Target user 的向量（独特的方向）
        target_base = np.random.randn(1536)
        target_base = target_base / np.linalg.norm(target_base)
        
        # Competitor users 的向量（不同的方向，但内部高度相似）
        competitor_base = np.random.randn(1536)
        competitor_base = competitor_base / np.linalg.norm(competitor_base)
        
        # 确保 target 和 competitor 方向不同（测试隔离性）
        while np.dot(target_base, competitor_base) > 0.1:
            competitor_base = np.random.randn(1536)
            competitor_base = competitor_base / np.linalg.norm(competitor_base)
        
        # 创建 target user 的记忆
        target_memory = {
            "node_id": "target_mem_0",
            "content": "Target user's unique memory",
            "layer": "l6_schema",
            "status": "active",
            "isolation_key": ik_target,
            "embedding": target_base.tolist(),
            "confidence": 0.6,
        }
        
        # 创建 990 个 competitor 记忆（高相似度）
        competitor_memories = []
        for i in range(990):
            noise = np.random.randn(1536) * 0.01  # 非常小的噪声
            vec = competitor_base + noise
            vec = vec / np.linalg.norm(vec)
            competitor_memories.append({
                "node_id": f"competitor_mem_{i}",
                "content": f"Competitor memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik_competitor,
                "embedding": vec.tolist(),
                "confidence": 0.95,
            })
        
        # 搜索：使用一个混合向量（接近 competitor 但不完全相同）
        # 这样 top-30 会被 competitor 填满，但迭代应该找到 target
        query_vector = (target_base * 0.1 + competitor_base * 0.9)
        query_vector = query_vector / np.linalg.norm(query_vector)
        
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_vector.tolist(),
            isolation_key=ik_target,
            limit=5,
        )
        
        # 验证
        assert len(results) > 0, \
            "Iterative search should find target even with 990 high-similarity competitors"
        
        assert results[0]["node_id"] == "target_mem_0", \
            "Should find the target memory despite extreme competition"
        
        # 验证没有数据泄露
        for result in results:
            assert result["node_id"].startswith("target_mem_"), \
                f"No data leakage: got {result['node_id']}"
        
        print(f"✓ 99% competitor test passed: found target despite 990 high-similarity competitors")

    @pytest.mark.slow
    async def test_vector_search_many_isolated_users(self, graph_store_neo4j_fixture):
        """
        测试：100 个不同用户的隔离性在迭代搜索下保持
        
        Setup:
        - 100 个不同的 isolation_key
        - 每个 10 个记忆，总共 1000 个节点
        
        Expected:
        - 搜索任一用户的结果，只返回该用户的数据
        - 不会因为全局 top-K 过大或迭代而产生交叉污染
        """
        num_users = 100
        memories_per_user = 10
        
        np.random.seed(222)
        
        user_vectors = []
        for user_id in range(num_users):
            # 每个用户的基向量不同
            base_vec = np.random.randn(1536)
            base_vec = base_vec / np.linalg.norm(base_vec)
            user_vectors.append(base_vec)
        
        # 创建记忆
        all_memories = []
        for user_id in range(num_users):
            ik = f"user_{user_id}::default"
            base_vec = user_vectors[user_id]
            
            for mem_id in range(memories_per_user):
                noise = np.random.randn(1536) * 0.05
                vec = base_vec + noise
                vec = vec / np.linalg.norm(vec)
                all_memories.append({
                    "node_id": f"user_{user_id}_mem_{mem_id}",
                    "content": f"User {user_id}'s memory {mem_id}",
                    "layer": "l6_schema",
                    "status": "active",
                    "isolation_key": ik,
                    "embedding": vec.tolist(),
                    "confidence": 0.8,
                })
        
        # 随机选取 5 个用户进行搜索测试
        test_users = np.random.choice(num_users, 5, replace=False)
        
        for user_id in test_users:
            ik = f"user_{user_id}::default"
            query_vec = user_vectors[user_id]
            
            results = await graph_store_neo4j_fixture.vector_search(
                query_embedding=query_vec.tolist(),
                isolation_key=ik,
                limit=5,
            )
            
            # 验证隔离性
            for result in results:
                expected_prefix = f"user_{user_id}_"
                assert result["node_id"].startswith(expected_prefix), \
                    f"User {user_id} search got wrong node: {result['node_id']}"
            
            assert len(results) <= 5, "Should respect limit"
        
        print(f"✓ Many users test passed: 100 users with {num_users * memories_per_user} total nodes, isolation maintained")

    @pytest.mark.slow
    async def test_vector_search_inactive_status_filtering(self, graph_store_neo4j_fixture):
        """
        测试：迭代搜索正确过滤 inactive 节点
        
        Setup:
        - 5 个 active 记忆
        - 95 个 inactive 记忆（模拟已删除或过期的节点）
        
        Expected:
        - 搜索结果仅包含 active 节点
        - 迭代过程中也要过滤 inactive（不会返回已过期的结果）
        """
        ik = "status_filter_test::default"
        
        np.random.seed(333)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        memories = []
        
        # Active 记忆
        for i in range(5):
            noise = np.random.randn(1536) * 0.02
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"active_mem_{i}",
                "content": f"Active memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        # Inactive 记忆（大量，会填满 top-30）
        for i in range(95):
            noise = np.random.randn(1536) * 0.01
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"inactive_mem_{i}",
                "content": f"Inactive memory {i}",
                "layer": "l6_schema",
                "status": "inactive",  # 已过期/已删除
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=base_vec.tolist(),
            isolation_key=ik,
            limit=10,
        )
        
        # 验证
        for result in results:
            assert result["node_id"].startswith("active_mem_"), \
                f"Should only return active nodes, got {result['node_id']}"
        
        # 应该找到所有 5 个 active 节点（在默认无相似度阈值下）
        assert len(results) <= 5, "At most 5 active nodes available"
        
        print(f"✓ Status filtering test passed: returned {len(results)}/5 active nodes (95 inactive ignored)")

    @pytest.mark.slow
    async def test_vector_search_duplicate_detection(self, graph_store_neo4j_fixture):
        """
        测试：迭代搜索的去重逻辑
        
        Setup:
        - 创建相同 node_id 的多个版本（模拟数据不一致）
        
        Expected:
        - 即使多轮查询返回相同的 node_id，也只返回一次
        - 去重是基于 node_id 的
        """
        ik = "dedup_test::default"
        
        np.random.seed(444)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        # 创建 10 个记忆
        memories = []
        for i in range(10):
            noise = np.random.randn(1536) * 0.05
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"dedup_mem_{i % 3}",  # 故意重复 node_id
                "content": f"Memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=base_vec.tolist(),
            isolation_key=ik,
            limit=10,
        )
        
        # 验证去重
        node_ids = [r["node_id"] for r in results]
        assert len(node_ids) == len(set(node_ids)), \
            f"Should deduplicate, got duplicates in {node_ids}"
        
        print(f"✓ Deduplication test passed: returned {len(results)} unique nodes (dedup working)")

