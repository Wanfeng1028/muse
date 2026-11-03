"""
Agent Memory - 模型测试

测试数据模型的正确性
运行方式：
    pytest tests/test_models.py -v
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from hy_memory.models import (
    # 枚举
    MemoryLayer,
    MemoryInputType,
    AgentProcessMode,
    TaskStatus,
    DeleteScope,
    # 数据类
    QAPair,
    AddRequest,
    AddResponse,
    AsyncAddResponse,
    RecallRequest,
    RecallResponse,
    UpdateRequest,
    DeleteRequest,
    BatchDeleteRequest,
    MemoryEntry,
    MemoryMetadata,
)


# ==================== 枚举测试 ====================

class TestEnums:
    """枚举测试"""
    
    def test_memory_layer_values(self):
        """测试记忆层枚举值 (V3 七层模型 + V1/V2 兼容别名)"""
        # V3 原始层
        assert MemoryLayer.L4_IDENTITY.value == "l4_identity"
        assert MemoryLayer.L2_FACT.value == "l2_fact"
        assert MemoryLayer.L3_SUMMARY.value == "l3_summary"
        assert MemoryLayer.L5_KNOWLEDGE.value == "l5_knowledge"
        assert MemoryLayer.L6_SCHEMA.value == "l6_schema"
        assert MemoryLayer.L1_RAW.value == "l1_raw"
        # V2 兼容别名（旧枚举名指向新值）
        assert MemoryLayer.L6_IDENTITY.value == "l4_identity"
        assert MemoryLayer.L4_KNOWLEDGE.value == "l5_knowledge"
        assert MemoryLayer.L5_SCHEMA.value == "l6_schema"
        # V1 兼容别名（值与 V3 对应层相同）
        assert MemoryLayer.PROFILE.value == "l4_identity"
        assert MemoryLayer.DIALOGUE.value == "l2_fact"
        assert MemoryLayer.SUMMARY.value == "l3_summary"
        assert MemoryLayer.KNOWLEDGE.value == "l5_knowledge"
        assert MemoryLayer.RAW.value == "l1_raw"
    
    def test_memory_layer_from_string(self):
        """测试从字符串创建记忆层"""
        assert MemoryLayer.from_string("profile") == MemoryLayer.L4_IDENTITY
        assert MemoryLayer.from_string("PROFILE") == MemoryLayer.L4_IDENTITY
        assert MemoryLayer.from_string("Profile") == MemoryLayer.L4_IDENTITY
        # V2 旧值兼容
        assert MemoryLayer.from_string("l6_identity") == MemoryLayer.L4_IDENTITY
        assert MemoryLayer.from_string("l5_schema") == MemoryLayer.L6_SCHEMA
        assert MemoryLayer.from_string("l4_knowledge") == MemoryLayer.L5_KNOWLEDGE
        assert MemoryLayer.from_string("l1_raw") == MemoryLayer.L1_RAW
    
    def test_memory_layer_invalid_string(self):
        """测试无效字符串创建记忆层"""
        with pytest.raises(ValueError):
            MemoryLayer.from_string("invalid_layer")
    
    def test_memory_input_type_values(self):
        """测试输入类型枚举值"""
        assert MemoryInputType.TEXT.value == "text"
        assert MemoryInputType.QA.value == "qa"
        assert MemoryInputType.DIALOGUE.value == "dialogue"
    
    def test_agent_process_mode_values(self):
        """测试 Agent 处理模式枚举值"""
        assert AgentProcessMode.DISABLED.value == "disabled"
        assert AgentProcessMode.FULL.value == "full"
    
    def test_task_status_values(self):
        """测试任务状态枚举值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
    
    def test_delete_scope_values(self):
        """测试删除范围枚举值"""
        assert DeleteScope.MEMORY.value == "memory"
        assert DeleteScope.SCENE.value == "scene"
        assert DeleteScope.USER.value == "user"
        assert DeleteScope.APP.value == "app"


# ==================== QAPair 测试 ====================

class TestQAPair:
    """QAPair 测试"""
    
    def test_qa_pair_creation(self):
        """测试创建 QAPair"""
        qa = QAPair(
            question="你叫什么名字？",
            answer="我叫小明"
        )
        
        assert qa.question == "你叫什么名字？"
        assert qa.answer == "我叫小明"
    
    def test_qa_pair_to_dict(self):
        """测试 QAPair 转字典"""
        qa = QAPair(question="Q1", answer="A1")
        d = qa.to_dict()
        
        assert d == {"question": "Q1", "answer": "A1"}
    
    def test_qa_pair_from_dict(self):
        """测试从字典创建 QAPair"""
        d = {"question": "Q1", "answer": "A1"}
        qa = QAPair.from_dict(d)
        
        assert qa.question == "Q1"
        assert qa.answer == "A1"
    
    def test_qa_pair_to_content(self):
        """测试 QAPair 转内容字符串"""
        qa = QAPair(question="你好吗？", answer="我很好")
        content = qa.to_content()
        
        assert "Q:" in content
        assert "A:" in content
        assert "你好吗？" in content
        assert "我很好" in content


# ==================== AddRequest 测试 ====================

class TestAddRequest:
    """AddRequest 测试"""
    
    def test_add_request_text_basic(self):
        """测试基本文本请求"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="测试内容"
        )

        assert request.uid == "user1"
        assert request.agent_id == "scene1"
        assert request.content == "测试内容"
        assert request.input_type == MemoryInputType.TEXT
    
    def test_add_request_qa(self):
        """测试 QA 请求"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            input_type=MemoryInputType.QA,
            qa_pair=QAPair(question="Q", answer="A")
        )
        
        assert request.input_type == MemoryInputType.QA
        assert request.qa_pair is not None
    
    def test_add_request_get_content_text(self):
        """测试获取文本内容"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="文本内容"
        )
        
        assert request.get_content() == "文本内容"
    
    def test_add_request_get_content_qa(self):
        """测试获取 QA 内容"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            input_type=MemoryInputType.QA,
            qa_pair=QAPair(question="问题", answer="答案")
        )
        
        content = request.get_content()
        assert "问题" in content
        assert "答案" in content
    
    def test_add_request_validates_text_content(self):
        """测试验证文本内容"""
        with pytest.raises(ValueError):
            AddRequest(
                uid="user1",
                agent_id="scene1",
                input_type=MemoryInputType.TEXT,
                content=None  # 文本类型必须有 content
            )
    
    def test_add_request_validates_qa_pair(self):
        """测试验证 QA 对"""
        with pytest.raises(ValueError):
            AddRequest(
                uid="user1",
                agent_id="scene1",
                input_type=MemoryInputType.QA,
                qa_pair=None  # QA 类型必须有 qa_pair
            )
    
    def test_add_request_layer_normalization(self):
        """测试层名称规范化"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="内容",
            layer="profile"  # 字符串形式
        )
        
        assert request.layer == MemoryLayer.PROFILE
    
    def test_add_request_agent_mode_normalization(self):
        """测试 agent 模式规范化"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="内容",
            agent_mode="full"  # 字符串形式
        )

        assert request.agent_mode == AgentProcessMode.FULL
    
    def test_add_request_auto_extract_compatibility(self):
        """测试 auto_extract 兼容性"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="内容",
            auto_extract=True  # 旧参数
        )
        
        # auto_extract=True 应该等同于 agent_mode=full
        assert request.agent_mode == AgentProcessMode.FULL
    
    def test_add_request_to_dict(self):
        """测试转字典"""
        request = AddRequest(
            uid="user1",
            agent_id="scene1",
            content="内容",
            importance=0.8,
            tags=["tag1", "tag2"]
        )

        d = request.to_dict()

        assert d["uid"] == "user1"
        assert d["importance"] == 0.8
        assert d["tags"] == ["tag1", "tag2"]


# ==================== AddResponse 测试 ====================

class TestAddResponse:
    """AddResponse 测试"""
    
    def test_add_response_success(self):
        """测试成功响应"""
        response = AddResponse(
            success=True,
            memory_id="mem_123",
            layer=MemoryLayer.PROFILE,
            message="Added successfully"
        )
        
        assert response.success is True
        assert response.memory_id == "mem_123"
        assert response.layer == MemoryLayer.PROFILE
    
    def test_add_response_with_extracted_ids(self):
        """测试带提取 ID 的响应"""
        response = AddResponse(
            success=True,
            memory_id="mem_123",
            extracted_ids=["ext_1", "ext_2"],
            abstract_key_ids=["key_1", "key_2"]
        )
        
        assert len(response.extracted_ids) == 2
        assert len(response.abstract_key_ids) == 2
    
    def test_add_response_to_dict(self):
        """测试转字典"""
        response = AddResponse(
            success=True,
            memory_id="mem_123",
            layer=MemoryLayer.KNOWLEDGE
        )
        
        d = response.to_dict()
        
        assert d["success"] is True
        assert d["memory_id"] == "mem_123"
        assert d["layer"] == "l5_knowledge"


# ==================== AsyncAddResponse 测试 ====================

class TestAsyncAddResponse:
    """AsyncAddResponse 测试"""
    
    def test_async_response(self):
        """测试异步响应"""
        response = AsyncAddResponse(
            success=True,
            task_id="task_123",
            status=TaskStatus.PENDING,
            estimated_time=30
        )
        
        assert response.success is True
        assert response.task_id == "task_123"
        assert response.status == TaskStatus.PENDING
        assert response.estimated_time == 30
    
    def test_async_response_to_dict(self):
        """测试转字典"""
        response = AsyncAddResponse(
            success=True,
            task_id="task_123",
            status=TaskStatus.PROCESSING
        )
        
        d = response.to_dict()
        
        assert d["task_id"] == "task_123"
        assert d["status"] == "processing"


# ==================== RecallRequest 测试 ====================

class TestRecallRequest:
    """RecallRequest 测试"""
    
    def test_recall_request_basic(self):
        """测试基本召回请求"""
        request = RecallRequest(
            query="用户偏好",
            uid="user1"
        )
        
        assert request.query == "用户偏好"
        assert request.limit == 10  # 默认值
    
    def test_recall_request_with_filters(self):
        """测试带过滤条件的召回请求"""
        request = RecallRequest(
            query="电影",
            uid="user1",
            layers=[MemoryLayer.PROFILE, MemoryLayer.KNOWLEDGE],
            tags=["兴趣"],
            min_importance=0.5
        )
        
        assert len(request.layers) == 2
        assert "兴趣" in request.tags
        assert request.min_importance == 0.5
    
    def test_recall_request_weights(self):
        """测试权重参数"""
        request = RecallRequest(
            query="test",
            uid="user1",
            semantic_weight=0.6,
            recency_weight=0.2,
            importance_weight=0.15,
            access_weight=0.05
        )
        
        # 权重之和应该接近 1
        total = (request.semantic_weight + request.recency_weight + 
                 request.importance_weight + request.access_weight)
        assert abs(total - 1.0) < 0.01


# ==================== MemoryEntry 测试 ====================

class TestMemoryEntry:
    """MemoryEntry 测试 (V2: MemoryEntry 是 MemoryNode 的别名，字段扁平化)"""
    
    def test_memory_entry_creation(self):
        """测试创建 MemoryEntry"""
        entry = MemoryEntry(
            content="测试内容",
            user_id="user1",
            agent_id="scene1",
            layer=MemoryLayer.PROFILE,
        )
        
        assert entry.content == "测试内容"
        assert entry.layer == MemoryLayer.L4_IDENTITY  # PROFILE 是 L4_IDENTITY 的别名
    
    def test_memory_entry_build_isolation_key(self):
        """测试构建隔离键（两级: user_id + agent_id）"""
        key = MemoryEntry.build_isolation_key("user1", "scene1")

        assert "user1" in key
        assert "scene1" in key
    
    def test_memory_entry_to_dict(self):
        """测试转字典"""
        entry = MemoryEntry(
            content="内容",
            user_id="user1",
            agent_id="scene1",
            layer=MemoryLayer.DIALOGUE,
        )

        d = entry.to_dict()

        assert d["content"] == "内容"
        assert d["layer"] == "l2_fact"  # DIALOGUE -> l2_fact
        assert d["user_id"] == "user1"


# ==================== BatchDeleteRequest 测试 ====================

class TestBatchDeleteRequest:
    """BatchDeleteRequest 测试"""
    
    def test_batch_delete_by_ids(self):
        """测试按 ID 批量删除"""
        request = BatchDeleteRequest(
            scope=DeleteScope.MEMORY,
            memory_ids=["id1", "id2", "id3"]
        )
        
        assert request.scope == DeleteScope.MEMORY
        assert len(request.memory_ids) == 3
    
    def test_batch_delete_by_scene(self):
        """测试按场景批量删除"""
        request = BatchDeleteRequest(
            scope=DeleteScope.SCENE,
            uid="user1",
            agent_id="scene1"
        )
        
        assert request.scope == DeleteScope.SCENE
        assert request.uid == "user1"
        assert request.agent_id == "scene1"
    
    def test_batch_delete_dangerous_requires_confirm(self):
        """测试危险操作需要确认"""
        request = BatchDeleteRequest(
            scope=DeleteScope.USER,
            uid="user1",
            confirm=True
        )
        
        assert request.confirm is True


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
