# -*- coding: utf-8 -*-
"""共享 pytest fixtures"""

import os
import shutil
import tempfile
import uuid

import pytest

from ._helpers import MockEmbedService


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="codingmem_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def coding_config(tmp_data_dir):
    """临时 chroma + sqlite，每次给独立 collection_name 避免进程内单例串味。"""
    from hy_memory.config import MemoryConfig

    cfg = MemoryConfig.from_env()
    cfg.history.db_path = os.path.join(tmp_data_dir, "history.db")
    cfg.coding.db_path = os.path.join(tmp_data_dir, "coding_memory.db")
    cfg.vector_store.provider = "chroma"
    cfg.vector_store.persist_directory = os.path.join(tmp_data_dir, "chroma")
    # 使用 uuid 后缀确保每个测试用独立 collection（chroma 客户端可能缓存单例）
    cfg.vector_store.collection_name = f"test_coding_{uuid.uuid4().hex[:8]}"
    cfg.vector_store.embedding_dims = 1536
    return cfg


@pytest.fixture
def mock_embed():
    return MockEmbedService()


@pytest.fixture
async def coding_store(coding_config, mock_embed):
    """已经 initialize 的 CodingMemoryStore"""
    from hy_memory.coding.store import CodingMemoryStore
    store = CodingMemoryStore(coding_config, embed_service=mock_embed)
    await store.initialize()
    yield store
    await store.close()
