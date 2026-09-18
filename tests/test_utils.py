"""
测试工具函数模块
"""

import pytest
from unittest.mock import patch, MagicMock
from src.utils import init_llm, normalize_expected_ground_truth_id
from src.config import LLMConfig


class TestInitLLM:
    """测试 LLM 初始化"""
    
    @patch('src.utils.ChatTongyi')
    @patch('src.utils.LLMConfig')
    def test_init_llm_success(self, mock_config, mock_chat_tongyi):
        """测试成功初始化 LLM"""
        mock_config.get_api_key.return_value = "test-api-key"
        mock_config.MODEL = "qwen3.7-max-2026-05-17"
        mock_config.TEMPERATURE = 0
        mock_llm = MagicMock()
        mock_chat_tongyi.return_value = mock_llm
        
        result = init_llm()
        
        mock_chat_tongyi.assert_called_once_with(
            model="qwen3.7-max-2026-05-17",
            temperature=0,
            dashscope_api_key="test-api-key"
        )
        assert result == mock_llm
    
    @patch('src.utils.LLMConfig')
    def test_init_llm_no_api_key(self, mock_config):
        """测试 API Key 不存在时抛出异常"""
        mock_config.get_api_key.return_value = None
        
        with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
            init_llm()


class TestNormalizeExpectedGroundTruthId:
    def test_real_id_preserved(self):
        assert normalize_expected_ground_truth_id("SOP-012") == "SOP-012"

    def test_none_placeholder_empty(self):
        assert normalize_expected_ground_truth_id("NONE") == ""
        assert normalize_expected_ground_truth_id("none") == ""

    def test_null_na_dash_empty(self):
        assert normalize_expected_ground_truth_id("N/A") == ""
        assert normalize_expected_ground_truth_id("NULL") == ""
        assert normalize_expected_ground_truth_id("-") == ""

    def test_none_and_nan(self):
        assert normalize_expected_ground_truth_id(None) == ""
        assert normalize_expected_ground_truth_id("nan") == ""
        assert normalize_expected_ground_truth_id("") == ""

