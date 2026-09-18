"""
测试 LangGraph 状态契约
"""

from src.state import (
    KNOWN_ISSUE,
    NEW_REGRESSION,
    UNKNOWN_ESCALATE,
    USER_CONFIG_ERROR,
    TicketState,
)


class TestTicketState:
    """测试当前工作流状态字段和路由枚举"""

    def test_ticket_state_accepts_current_graph_fields(self):
        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "diagnosis_routes": [],
            "diagnosis_category": [],
            "processed_route_types": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
            "monitor_next_batch_id": 1,
        }

        assert state["monitor_next_batch_id"] == 1
        assert state["logs"] == []

    def test_route_constants_are_the_supported_values(self):
        assert {
            NEW_REGRESSION,
            USER_CONFIG_ERROR,
            KNOWN_ISSUE,
            UNKNOWN_ESCALATE,
        } == {
            "NEW_REGRESSION",
            "USER_CONFIG_ERROR",
            "KNOWN_ISSUE",
            "UNKNOWN_ESCALATE",
        }
