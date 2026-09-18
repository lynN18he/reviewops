"""
Pytest 配置和共享 fixtures
"""

import pytest
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_env_vars():
    """自动 mock 环境变量，避免测试时依赖真实 API Key"""
    with patch.dict(os.environ, {
        "DASHSCOPE_API_KEY": "test-api-key-for-testing",
        "LLM_MODEL": "qwen3.7-max-2026-05-17",
        "LLM_TEMPERATURE": "0",
        "EMBEDDING_MODEL": "text-embedding-v3",
        "VECTOR_DB_PATH": "./test_chroma_db",
        "RAG_TOOL_TOP_K": "1",
        "RAG_SCORE_THRESHOLD": "0.25",
        "RAG_CHROMA_FETCH_K": "24",
        "MONITOR_MIN_TICKETS": "2",
        "MONITOR_TICKETS_INCREMENTAL_CSV": "incremental_tickets.csv",
    }, clear=False):
        yield

