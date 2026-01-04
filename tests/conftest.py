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
        "LLM_MODEL": "qwen-plus",
        "LLM_TEMPERATURE": "0",
        "EMBEDDING_MODEL": "text-embedding-v3",
        "VECTOR_DB_PATH": "./test_chroma_db",
        "RAG_TOP_K": "5",
        "RAG_DISTANCE_THRESHOLD": "1.5",
        "RAG_MAX_CONTEXT_LENGTH": "300",
        "RAG_MAX_DOCS_IN_CONTEXT": "3",
        "FILTER_RATING_THRESHOLD": "3",
        "MONITOR_MIN_REVIEWS": "2",
        "MONITOR_MUST_HAVE_POSITIVE": "true",
        "ACTION_DEFAULT_TYPE": "Jira Ticket",
        "ACTION_DEFAULT_PRIORITY": "Medium"
    }, clear=False):
        yield

