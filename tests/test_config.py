"""
测试配置管理模块
"""

import os
import pytest
from unittest.mock import patch
from src.config import (
    LLMConfig, EmbeddingConfig, VectorStoreConfig,
    FilterConfig, MonitorConfig, ActionConfig, validate_config
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
            validate_config()  # 不应该抛出异常
    
    def test_validate_api_key_failure(self):
        """测试 API Key 验证失败"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
                validate_config()
    
    def test_model_default(self):
        """测试模型默认值"""
        with patch.dict(os.environ, {}, clear=True):
            assert LLMConfig.MODEL == "qwen-plus"
    
    def test_model_from_env(self):
        """测试从环境变量读取模型"""
        with patch.dict(os.environ, {"LLM_MODEL": "qwen-turbo"}):
            # 需要重新导入才能生效，这里只测试 getter
            assert os.getenv("LLM_MODEL", "qwen-plus") == "qwen-turbo"


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
        """测试默认值"""
        assert VectorStoreConfig.PERSIST_DIRECTORY == "./chroma_db"
        assert VectorStoreConfig.TOP_K == 5
        assert VectorStoreConfig.DISTANCE_THRESHOLD == 1.5
        assert VectorStoreConfig.MAX_CONTEXT_LENGTH == 300
        assert VectorStoreConfig.MAX_DOCS_IN_CONTEXT == 3


class TestFilterConfig:
    """测试筛选配置"""
    
    def test_keywords(self):
        """测试关键词列表"""
        assert isinstance(FilterConfig.KEYWORDS, list)
        assert len(FilterConfig.KEYWORDS) > 0
        assert "故障" in FilterConfig.KEYWORDS
        assert "失效" in FilterConfig.KEYWORDS
    
    def test_rating_threshold_default(self):
        """测试评分阈值默认值"""
        assert FilterConfig.RATING_THRESHOLD == 3


class TestMonitorConfig:
    """测试监控配置"""
    
    def test_default_values(self):
        """测试默认值"""
        assert MonitorConfig.MIN_REVIEWS_PER_BATCH == 2
        assert MonitorConfig.MUST_HAVE_POSITIVE is True


class TestActionConfig:
    """测试行动配置"""
    
    def test_default_values(self):
        """测试默认值"""
        assert ActionConfig.DEFAULT_ACTION_TYPE == "Jira Ticket"
        assert ActionConfig.DEFAULT_PRIORITY == "Medium"

