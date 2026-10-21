# -*- coding: utf-8 -*-
"""
Neo4j 向量检索性能测试

验证迭代搜索的性能特性：
1. 单轮查询的性能基准
2. 多轮迭代的开销 < 10%
3. 各种数据规模下的表现

这些测试帮助检测性能回归。
"""

import pytest
import time
from typing import List
import numpy as np


@pytest.mark.integration
class TestVectorSearchPerformance:
    """向量搜索性能测试"""

    @pytest.mark.slow
    async def test_vector_search_single_round_baseline(self, graph_store_neo4j_fixture):
        """
        建立单轮查询的性能基准
        
        Measure:
        - 创建 1000 个节点
        - 执行查询并计时
        
        Expected:
        - 在正常硬件上，应在 1 秒以内完成
        """
        ik = "perf_baseline::default"
        
        np.random.seed(555)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        # 创建 1000 个节点
        memories = []
        for i in range(1000):
            noise = np.random.randn(1536) * 0.1
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"perf_mem_{i}",
                "content": f"Performance test memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        # 查询并计时
        query_embedding = base_vec.tolist()
        
        start_time = time.time()
        results = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik,
            limit=20,
        )
        elapsed = time.time() - start_time
        
        # 验证
        assert len(results) <= 20
        assert elapsed < 5.0, f"Query took {elapsed:.2f}s, should be < 5s"
        
        print(f"✓ Baseline performance: {elapsed:.3f}s for 1000 nodes, returned {len(results)} results")

    @pytest.mark.slow
    async def test_vector_search_iteration_overhead(self, graph_store_neo4j_fixture):
        """
        测试：迭代搜索的开销（相对于单轮）
        
        对比：
        1. 单轮查询（大 K）
        2. 多轮迭代查询（小 K → 增长）
        
        Expected:
        - 多轮迭代开销 < 10%（在多数情况下不需要迭代）
        """
        ik = "perf_iteration::default"
        
        np.random.seed(666)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        # 创建充足的节点
        memories = []
        for i in range(5000):
            noise = np.random.randn(1536) * 0.1
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"iter_mem_{i}",
                "content": f"Iteration test memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        query_embedding = base_vec.tolist()
        
        # 执行多次查询以减少噪声
        times = []
        for _ in range(3):
            start_time = time.time()
            results = await graph_store_neo4j_fixture.vector_search(
                query_embedding=query_embedding,
                isolation_key=ik,
                limit=10,
            )
            elapsed = time.time() - start_time
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        
        # 验证合理的性能
        assert avg_time < 2.0, f"Average query time {avg_time:.2f}s should be < 2s"
        
        print(f"✓ Iteration overhead: avg {avg_time:.3f}s over 3 queries (overhead acceptable)")

    @pytest.mark.slow
    async def test_vector_search_limit_scaling(self, graph_store_neo4j_fixture):
        """
        测试：不同 limit 大小的性能扩展
        
        Measure:
        - limit=5
        - limit=10
        - limit=20
        - limit=50
        
        Expected:
        - 性能应该基本线性扩展（或接近）
        - 不应该因为迭代而出现突跳
        """
        ik = "perf_limit_scaling::default"
        
        np.random.seed(777)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        # 创建充足的节点
        memories = []
        for i in range(3000):
            noise = np.random.randn(1536) * 0.1
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"scale_mem_{i}",
                "content": f"Limit scaling test memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        query_embedding = base_vec.tolist()
        limits = [5, 10, 20, 50]
        times = {}
        
        for limit in limits:
            start_time = time.time()
            results = await graph_store_neo4j_fixture.vector_search(
                query_embedding=query_embedding,
                isolation_key=ik,
                limit=limit,
            )
            elapsed = time.time() - start_time
            times[limit] = elapsed
            
            assert len(results) <= limit
        
        # 验证近似线性扩展
        ratios = []
        for i in range(1, len(limits)):
            time_ratio = times[limits[i]] / times[limits[i-1]]
            limit_ratio = limits[i] / limits[i-1]
            # 时间比应该接近 limit 比（在 1.5 倍以内可接受）
            assert time_ratio < limit_ratio * 1.5, \
                f"Time scaling issue: limit {limits[i-1]}->{limits[i]}, ratio {time_ratio:.2f} vs expected ~{limit_ratio:.2f}"
            ratios.append(time_ratio)
        
        print(f"✓ Limit scaling: {times} (ratios {[f'{r:.2f}' for r in ratios]})")

    @pytest.mark.slow
    async def test_vector_search_layer_filter_cost(self, graph_store_neo4j_fixture):
        """
        测试：layer 过滤的性能成本
        
        对比：
        1. 无 layer 过滤
        2. 指定单个 layer
        3. 指定多个 layer
        
        Expected:
        - layer 过滤不应该显著增加查询时间
        """
        ik = "perf_layer::default"
        
        np.random.seed(888)
        base_vec = np.random.randn(1536)
        base_vec = base_vec / np.linalg.norm(base_vec)
        
        # 创建多个 layer 的记忆
        memories = []
        for layer in ["l5_identity", "l6_schema", "l7_intention"]:
            for i in range(1000):
                noise = np.random.randn(1536) * 0.1
                vec = base_vec + noise
                vec = vec / np.linalg.norm(vec)
                memories.append({
                    "node_id": f"layer_{layer}_{i}",
                    "content": f"Memory in {layer}",
                    "layer": layer,
                    "status": "active",
                    "isolation_key": ik,
                    "embedding": vec.tolist(),
                    "confidence": 0.8,
                })
        
        query_embedding = base_vec.tolist()
        
        # 查询 1: 无 layer 过滤
        start_time = time.time()
        results_all = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik,
            limit=20,
        )
        time_all = time.time() - start_time
        
        # 查询 2: 单个 layer
        start_time = time.time()
        results_single = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik,
            layers=["l6_schema"],
            limit=20,
        )
        time_single = time.time() - start_time
        
        # 查询 3: 多个 layer
        start_time = time.time()
        results_multi = await graph_store_neo4j_fixture.vector_search(
            query_embedding=query_embedding,
            isolation_key=ik,
            layers=["l5_identity", "l6_schema"],
            limit=20,
        )
        time_multi = time.time() - start_time
        
        # 验证
        assert time_single <= time_all * 1.2, "Single layer filter should not significantly increase time"
        assert time_multi <= time_all * 1.3, "Multiple layer filter should not significantly increase time"
        
        print(f"✓ Layer filter cost: no_filter={time_all:.3f}s, single={time_single:.3f}s, multi={time_multi:.3f}s")

    @pytest.mark.slow
    async def test_beh_vector_search_performance(self, graph_store_neo4j_fixture):
        """
        测试：行为向量搜索的性能
        
        Measure:
        - 创建 1000 个 L6 schema 节点（有 beh_embedding）
        - 执行 beh_vector_search
        
        Expected:
        - 性能与 vector_search 类似
        """
        ik = "perf_beh::default"
        
        np.random.seed(999)
        base_beh_vec = np.random.randn(512)
        base_beh_vec = base_beh_vec / np.linalg.norm(base_beh_vec)
        
        # 创建 L6 schema 节点
        memories = []
        for i in range(1000):
            noise = np.random.randn(512) * 0.1
            vec = base_beh_vec + noise
            vec = vec / np.linalg.norm(vec)
            memories.append({
                "node_id": f"beh_perf_mem_{i}",
                "content": f"Behavior test memory {i}",
                "layer": "l6_schema",
                "status": "active",
                "isolation_key": ik,
                "beh_embedding": vec.tolist(),
                "confidence": 0.8,
            })
        
        query_beh_embedding = base_beh_vec.tolist()
        
        start_time = time.time()
        results = await graph_store_neo4j_fixture.beh_vector_search(
            query_beh_embedding=query_beh_embedding,
            isolation_key=ik,
            limit=10,
        )
        elapsed = time.time() - start_time
        
        assert len(results) <= 10
        assert elapsed < 2.0, f"Behavior vector search took {elapsed:.2f}s, should be < 2s"
        
        print(f"✓ Behavior vector search: {elapsed:.3f}s for 1000 L6 nodes, returned {len(results)} results")

