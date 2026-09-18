"""
测试动作节点：generate_email_node / generate_jira_node / escalate_human_node
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.action import generate_email_node, generate_jira_node, escalate_human_node
from src.state import TicketState, NEW_REGRESSION, USER_CONFIG_ERROR, KNOWN_ISSUE, UNKNOWN_ESCALATE


def _base_state():
    return {
        "incr_tickets": [],
        "critical_tickets": [],
        "rag_analysis_results": [],
        "diagnosis_routes": [],
        "processed_route_types": [],
        "action_plans": [],
        "logs": [],
        "processed_ids": [],
    }


class TestGenerateEmailNode:
    """测试邮件节点"""

    def test_empty_routes(self):
        state: TicketState = {**_base_state(), "diagnosis_routes": []}
        out = generate_email_node(state)
        assert "无 USER_CONFIG_ERROR/KNOWN_ISSUE" in out["logs"][0]

    @patch("src.nodes.action.get_database")
    @patch("src.nodes.action.init_llm")
    def test_known_issue_email_template(self, mock_init_llm, mock_get_db):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="这是平台已知问题（工单 JIRA-1042），研发正在抢修中。请使用临时方案：...")
        mock_init_llm.return_value = mock_llm
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        state: TicketState = {
            **_base_state(),
            "diagnosis_routes": [{"ticket_id": "TIK-1", "route_type": KNOWN_ISSUE, "jira_id": "JIRA-1042"}],
            "rag_analysis_results": [{"ticket_id": "TIK-1", "ticket_content": "阿拉伯语地址乱码", "conclusion": "已知缺陷", "reason": "", "evidence": "JIRA-1042"}],
        }
        out = generate_email_node(state)
        assert len(out["action_plans"]) >= 1
        assert out["action_plans"][0]["action_type"] == "Email Draft"
        assert "email" in out["processed_route_types"]


class TestGenerateJiraNode:
    """测试 Jira 节点"""

    def test_empty_regression(self):
        state: TicketState = {**_base_state(), "diagnosis_routes": []}
        out = generate_jira_node(state)
        assert "无 NEW_REGRESSION" in out["logs"][0]

    @patch("src.nodes.action.get_database")
    @patch("src.nodes.action.init_llm")
    def test_jira_node_output(self, mock_init_llm, mock_get_db):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='{"title": "P0 回归", "content": "描述", "priority": "High"}')
        mock_init_llm.return_value = mock_llm
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        state: TicketState = {
            **_base_state(),
            "diagnosis_routes": [{"ticket_id": "TIK-2", "route_type": NEW_REGRESSION, "jira_id": ""}],
            "rag_analysis_results": [{"ticket_id": "TIK-2", "ticket_content": "发版后白屏", "conclusion": "缺陷", "reason": "", "evidence": ""}],
        }
        out = generate_jira_node(state)
        assert len(out["action_plans"]) >= 1
        assert out["action_plans"][0]["action_type"] == "Jira Ticket"
        assert out["action_plans"][0]["priority"] == "High"


class TestEscalateHumanNode:
    """测试人工升级节点"""

    def test_empty_unknown(self):
        state: TicketState = {**_base_state(), "diagnosis_routes": []}
        out = escalate_human_node(state)
        assert "无 UNKNOWN_ESCALATE" in out["logs"][0]

    @patch("src.nodes.action.get_database")
    def test_escalate_output(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        state: TicketState = {
            **_base_state(),
            "diagnosis_routes": [{"ticket_id": "TIK-3", "route_type": UNKNOWN_ESCALATE, "jira_id": ""}],
            "rag_analysis_results": [{"ticket_id": "TIK-3", "ticket_content": "看不懂报错", "conclusion": "❓ 需要人工", "reason": "", "evidence": ""}],
        }
        out = escalate_human_node(state)
        assert len(out["action_plans"]) >= 1
        assert out["action_plans"][0]["action_type"] == "Escalate"
        assert "escalate" in out["processed_route_types"]
