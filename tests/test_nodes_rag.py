"""
测试 RAG 分析节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.rag import node_rag_analysis
from src.state import ReviewState


class TestNodeRagAnalysis:
    """测试 RAG 分析节点（工单归因）"""

    def test_node_rag_empty_critical_tickets(self):
        """测试空高危工单列表"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert result["rag_analysis_results"] == []
        assert len(result["logs"]) > 0
        assert "无高危工单需要分析" in result["logs"][0]

    @patch("src.nodes.rag.init_llm")
    def test_node_rag_with_llm_success(self, mock_init_llm):
        """测试 LLM 归因分析成功"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """{
            "review_id": "TIK-054",
            "conclusion": "✅ 配置问题，建议按 SOP 重新授权",
            "reason": "知识库/SOP 中有说明",
            "evidence": "相关证据"
        }"""
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [
                {
                    "review_id": "TIK-054",
                    "review_text": "调用 create order API 一直返回 401 Unauthorized",
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["review_id"] == "TIK-054"
        assert "conclusion" in rag_result
        assert "reason" in rag_result
        assert "evidence" in rag_result

    @patch("src.nodes.rag.init_llm")
    def test_node_rag_json_parse_error(self, mock_init_llm):
        """测试 JSON 解析错误处理"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这不是有效的 JSON"
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [
                {
                    "review_id": "TIK-055",
                    "review_text": "批量查询接口报 429",
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["conclusion"] == "❓ 需要人工判断"
        assert "JSON 解析失败" in rag_result["reason"] or "RAG 分析失败" in rag_result["reason"]
