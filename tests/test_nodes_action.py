"""
测试行动生成节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.action import node_action_gen
from src.state import ReviewState


class TestNodeActionGen:
    """测试行动生成节点"""
    
    def test_node_action_empty_rag_results(self):
        """测试空归因结果"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_action_gen(state)
        
        assert result["action_plans"] == []
        assert len(result["logs"]) > 0
        assert "无归因结果需要生成行动" in result["logs"][0]
    
    @patch('src.nodes.action.init_llm')
    def test_node_action_with_llm_success(self, mock_init_llm):
        """测试 LLM 生成行动成功"""
        # Mock LLM 响应
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''{
            "action_type": "Jira Ticket",
            "title": "修复 API 401 鉴权问题",
            "content": "用户反馈 create order API 返回 401，需排查 Token 与授权",
            "priority": "High"
        }'''
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm
        
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [
                {
                    "review_id": "TIK-054",
                    "review_text": "调用 create order API 一直返回 401",
                    "conclusion": "⚠️ 需进一步调查",
                    "reason": "需要检查",
                    "evidence": "无"
                }
            ],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_action_gen(state)
        
        assert len(result["action_plans"]) > 0
        action = result["action_plans"][0]
        assert action["review_id"] == "TIK-054"
        assert "action_type" in action
        assert "title" in action
        assert "content" in action
        assert "priority" in action
    
    @patch('src.nodes.action.init_llm')
    def test_node_action_json_parse_error(self, mock_init_llm):
        """测试 JSON 解析错误时使用默认值"""
        # Mock LLM 返回无效 JSON
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这不是有效的 JSON"
        mock_llm.invoke.return_value = mock_response
        mock_init_llm.return_value = mock_llm
        
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [
                {
                    "review_id": "TIK-055",
                    "review_text": "测试工单内容",
                    "conclusion": "测试结论",
                    "reason": "测试原因",
                    "evidence": "测试证据"
                }
            ],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }

        result = node_action_gen(state)

        assert len(result["action_plans"]) > 0
        action = result["action_plans"][0]
        assert action["review_id"] == "TIK-055"
        assert action["action_type"] == "Jira Ticket"  # 默认值
        assert action["priority"] == "Medium"  # 默认值

