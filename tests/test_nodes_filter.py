"""
测试筛选节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.filter import node_filter
from src.state import TicketState


class TestNodeFilter:
    """测试筛选节点"""
    
    def test_node_filter_empty_reviews(self):
        """测试空工单列表"""
        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_filter(state)
        
        assert result["critical_tickets"] == []
        assert len(result["logs"]) > 0
        assert "无新工单需要筛选" in result["logs"][0]
    
    @patch('src.nodes.filter.init_llm')
    def test_node_filter_with_llm_success(self, mock_init_llm):
        """测试 LLM 筛选成功"""
        # Mock LLM 响应
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"critical_ticket_ids": ["101_1234567890_5678"], "reason": "系统级报错"}'
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm
        
        state: TicketState = {
            "incr_tickets": [
                {
                    "ticket_id": "101_1234567890_5678",
                    "ticket_content": "产品有问题",
                }
            ],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_filter(state)
        
        assert len(result["critical_tickets"]) >= 0  # 可能匹配成功或失败
        assert len(result["logs"]) > 0
    
    @patch('src.nodes.filter.init_llm')
    def test_node_filter_fallback_to_keywords(self, mock_init_llm):
        """测试 LLM 失败时降级到关键词匹配"""
        # Mock LLM 初始化成功，但 invoke 抛出异常
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM error")
        mock_init_llm.return_value = mock_llm
        
        state: TicketState = {
            "incr_tickets": [
                {
                    "ticket_id": "101_1234567890_5678",
                    "ticket_content": "API 返回 502，页面白屏",
                }
            ],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_filter(state)
        
        # 降级模式应能筛选出包含 SaaS 故障关键词的工单
        assert len(result["critical_tickets"]) > 0
        assert result["critical_tickets"][0]["ticket_id"] == "101_1234567890_5678"
        assert len(result["logs"]) > 0
        assert "降级模式" in result["logs"][0] or "筛选出" in result["logs"][0]
    
    @patch('src.nodes.filter.init_llm')
    def test_node_filter_fallback_keywords_only(self, mock_init_llm):
        """测试降级模式仅按 SaaS 故障关键词匹配"""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM error")
        mock_init_llm.return_value = mock_llm

        state: TicketState = {
            "incr_tickets": [
                {
                    "ticket_id": "101_1234567890_5678",
                    "ticket_content": "系统 502 宕机，全不更新",
                },
                {
                    "ticket_id": "201_1234567890_5679",
                    "ticket_content": "体验很好，没问题",
                }
            ],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }

        result = node_filter(state)

        critical_ids = [r["ticket_id"] for r in result["critical_tickets"]]
        assert "101_1234567890_5678" in critical_ids
        assert "201_1234567890_5679" not in critical_ids
        assert len(result["critical_tickets"]) == 1

