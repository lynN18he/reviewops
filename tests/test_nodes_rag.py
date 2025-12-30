"""
测试 RAG 分析节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.rag import node_rag_analysis
from src.state import ReviewState


class TestNodeRagAnalysis:
    """测试 RAG 分析节点"""
    
    def test_node_rag_empty_critical_reviews(self):
        """测试空高危评论列表"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_rag_analysis(state)
        
        assert result["rag_analysis_results"] == []
        assert len(result["logs"]) > 0
        assert "无高危评论需要分析" in result["logs"][0]
    
    @patch('src.nodes.rag.init_llm')
    def test_node_rag_with_llm_success(self, mock_init_llm):
        """测试 LLM RAG 分析成功"""
        # Mock LLM 响应
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''{
            "review_id": "101_1234567890_5678",
            "conclusion": "✅ 产品已知局限",
            "reason": "说明书中有说明",
            "evidence": "相关证据"
        }'''
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm
        
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [
                {
                    "review_id": "101_1234567890_5678",
                    "review_text": "避障功能失效",
                    "rating": 2
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_rag_analysis(state)
        
        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["review_id"] == "101_1234567890_5678"
        assert "conclusion" in rag_result
        assert "reason" in rag_result
        assert "evidence" in rag_result
    
    @patch('src.nodes.rag.init_llm')
    def test_node_rag_json_parse_error(self, mock_init_llm):
        """测试 JSON 解析错误处理"""
        # Mock LLM 返回无效 JSON
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这不是有效的 JSON"
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm
        
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [
                {
                    "review_id": "101_1234567890_5678",
                    "review_text": "测试评论",
                    "rating": 1
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_rag_analysis(state)
        
        # 应该返回错误处理的结果
        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["conclusion"] == "❓ 需要人工判断"
        assert "JSON 解析失败" in rag_result["reason"] or "RAG 分析失败" in rag_result["reason"]

