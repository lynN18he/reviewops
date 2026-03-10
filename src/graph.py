"""
工作流图构建模块
Monitor -> Filter -> RAG -> Agent(诊断路由) -> [Email | Jira | Escalate] -> NextRoute -> (循环或 END)
"""

from typing import Literal
from langgraph.graph import StateGraph, END

from src.state import (
    TicketState,
    NEW_REGRESSION,
    USER_CONFIG_ERROR,
    KNOWN_ISSUE,
    UNKNOWN_ESCALATE,
)
from src.nodes.monitor import node_monitor
from src.nodes.filter import node_filter
from src.nodes.rag import node_rag_analysis
from src.nodes.agent import agent_node
from src.nodes.action import (
    generate_email_node,
    generate_jira_node,
    escalate_human_node,
    next_route_node,
)


def should_continue_analysis(state: TicketState) -> Literal["rag_analysis", "end"]:
    """filter 后是否继续 RAG 分析"""
    critical_tickets = state.get("critical_tickets", [])
    if len(critical_tickets) > 0:
        return "rag_analysis"
    return "end"


def route_after_diagnosis(
    state: TicketState,
) -> Literal["generate_email", "generate_jira", "escalate_human", "end"]:
    """
    强拦截条件路由（仅允许四类诊断枚举）：
    - USER_CONFIG_ERROR 或 KNOWN_ISSUE -> generate_email_node
    - 仅当 NEW_REGRESSION -> generate_jira_node
    - 其他（含 UNKNOWN_ESCALATE）-> escalate_human_node
    """
    routes = state.get("diagnosis_routes", [])
    processed = set(state.get("processed_route_types", []))

    has_escalate = any(
        r.get("route_type") == UNKNOWN_ESCALATE or r.get("route_type") not in (USER_CONFIG_ERROR, KNOWN_ISSUE, NEW_REGRESSION)
        for r in routes
    )
    has_regression = any(r.get("route_type") == NEW_REGRESSION for r in routes)
    has_email = any(
        r.get("route_type") in (USER_CONFIG_ERROR, KNOWN_ISSUE) for r in routes
    )

    if has_escalate and "escalate" not in processed:
        return "escalate_human"
    if has_regression and "jira" not in processed:
        return "generate_jira"
    if has_email and "email" not in processed:
        return "generate_email"
    return "end"


def build_graph():
    """构建 LangGraph 工作流"""
    workflow = StateGraph(TicketState)

    workflow.add_node("monitor", node_monitor)
    workflow.add_node("filter", node_filter)
    workflow.add_node("rag_analysis", node_rag_analysis)
    workflow.add_node("agent_node", agent_node)
    workflow.add_node("generate_email_node", generate_email_node)
    workflow.add_node("generate_jira_node", generate_jira_node)
    workflow.add_node("escalate_human_node", escalate_human_node)
    workflow.add_node("next_route", next_route_node)

    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "filter")
    workflow.add_conditional_edges(
        "filter",
        should_continue_analysis,
        {"rag_analysis": "rag_analysis", "end": END},
    )
    workflow.add_edge("rag_analysis", "agent_node")

    workflow.add_conditional_edges(
        "agent_node",
        route_after_diagnosis,
        {
            "generate_email": "generate_email_node",
            "generate_jira": "generate_jira_node",
            "escalate_human": "escalate_human_node",
            "end": END,
        },
    )

    workflow.add_edge("generate_email_node", "next_route")
    workflow.add_edge("generate_jira_node", "next_route")
    workflow.add_edge("escalate_human_node", "next_route")

    workflow.add_conditional_edges(
        "next_route",
        route_after_diagnosis,
        {
            "generate_email": "generate_email_node",
            "generate_jira": "generate_jira_node",
            "escalate_human": "escalate_human_node",
            "end": END,
        },
    )

    graph_app = workflow.compile()
    return graph_app


graph_app = build_graph()
