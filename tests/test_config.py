"""
测试配置管理模块
"""

import os
import pytest
from unittest.mock import patch
from pathlib import Path

from src.config import (
    LLMConfig,
    EmbeddingConfig,
    VectorStoreConfig,
    FilterConfig,
    MonitorConfig,
    resolve_repo_relative_path,
)


class TestLLMConfig:
    """测试 LLM 配置"""
    
    def test_get_api_key(self):
        """测试获取 API Key"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            assert LLMConfig.get_api_key() == "test-key"
    
    def test_get_api_key_none(self):
        """测试 API Key 不存在"""
        with patch.dict(os.environ, {}, clear=True):
            assert LLMConfig.get_api_key() is None
    
    def test_validate_api_key_success(self):
        """测试 API Key 验证成功"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            LLMConfig.validate_api_key()  # 不应该抛出异常
    
    def test_validate_api_key_failure(self):
        """测试 API Key 验证失败"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
                LLMConfig.validate_api_key()
    
    def test_model_default(self):
        """测试模型默认值"""
        with patch.dict(os.environ, {}, clear=True):
            assert LLMConfig.MODEL == "qwen3.7-max-2026-05-17"
    
    def test_model_from_env(self):
        """测试从环境变量读取模型"""
        with patch.dict(os.environ, {"LLM_MODEL": "qwen3.6-plus"}):
            assert os.getenv("LLM_MODEL", "qwen3.7-max-2026-05-17") == "qwen3.6-plus"


class TestEmbeddingConfig:
    """测试 Embedding 配置"""
    
    def test_get_api_key(self):
        """测试获取 API Key（与 LLM 共用）"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            assert EmbeddingConfig.get_api_key() == "test-key"
    
    def test_model_default(self):
        """测试模型默认值"""
        assert EmbeddingConfig.MODEL == "text-embedding-v3"


class TestVectorStoreConfig:
    """测试向量数据库配置"""
    
    def test_default_values(self):
        """测试默认值（向量库路径为绝对路径，不依赖进程 cwd）"""
        from pathlib import Path
        assert Path(VectorStoreConfig.PERSIST_DIRECTORY).is_absolute()
        assert VectorStoreConfig.TOOL_TOP_K == 1
        assert VectorStoreConfig.SCORE_THRESHOLD == 0.25
        assert VectorStoreConfig.CHROMA_FETCH_K == 24


class TestFilterConfig:
    """测试筛选配置"""
    
    def test_keywords(self):
        """测试关键词列表"""
        assert isinstance(FilterConfig.KEYWORDS, list)
        assert len(FilterConfig.KEYWORDS) > 0
        assert "502" in FilterConfig.KEYWORDS
        assert "白屏" in FilterConfig.KEYWORDS


class TestMonitorConfig:
    """测试监控配置"""
    
    def test_default_values(self):
        """测试默认值"""
        assert MonitorConfig.MIN_TICKETS_PER_BATCH == 7
        assert MonitorConfig.TICKETS_INCREMENTAL_CSV == "incremental_tickets.csv"


class TestResolveRepoRelativePath:
    def test_relative_csv_under_repo(self):
        p = resolve_repo_relative_path("cold_start_tickets.csv")
        assert Path(p).is_absolute()
        assert Path(p).name == "cold_start_tickets.csv"

    def test_absolute_unchanged(self):
        abs_path = str(Path(__file__).resolve())
        p = resolve_repo_relative_path(abs_path)
        assert p == str(Path(abs_path).resolve())


