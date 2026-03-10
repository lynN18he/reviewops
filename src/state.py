"""
ReviewOps 状态定义（B2B 工单分诊）
"""

from typing import TypedDict, List

# 诊断路由类型（agent_node 仅输出以下四类，用于条件边强拦截）
NEW_REGRESSION = "NEW_REGRESSION"           # 新 Bug/发版故障 -> P0 Jira
USER_CONFIG_ERROR = "USER_CONFIG_ERROR"     # 用户配置错误 -> 邮件+SOP
KNOWN_ISSUE = "KNOWN_ISSUE"                # 已知缺陷（已有 Jira）-> 邮件+原 Jira+Workaround
UNKNOWN_ESCALATE = "UNKNOWN_ESCALATE"       # 未知需人工 -> 转 L2 人工
# 兼容旧键
UNKNOWN = UNKNOWN_ESCALATE


class TicketState(TypedDict):
    """工作流状态（B2B 工单分诊）"""
    incr_tickets: List[dict]
    critical_tickets: List[dict]
    rag_analysis_results: List[dict]
    diagnosis_routes: List[dict]   # [{ ticket_id, route_type, jira_id? }, route_type 为上述四枚举之一
    diagnosis_category: List[str]  # 与 diagnosis_routes 一一对应的枚举列表，便于统计与路由
    processed_route_types: List[str]
    action_plans: List[dict]
    logs: List[str]
    processed_ids: List[str]


def reducer(state: TicketState, update: TicketState) -> TicketState:
    """合并状态更新"""
    merged = state.copy()

    if "logs" in update:
        merged["logs"] = state.get("logs", []) + update.get("logs", [])
    if "incr_tickets" in update:
        merged["incr_tickets"] = update.get("incr_tickets", [])
    if "critical_tickets" in update:
        merged["critical_tickets"] = update.get("critical_tickets", [])
    if "rag_analysis_results" in update:
        merged["rag_analysis_results"] = update.get("rag_analysis_results", [])
    if "diagnosis_routes" in update:
        merged["diagnosis_routes"] = update.get("diagnosis_routes", [])
    if "diagnosis_category" in update:
        merged["diagnosis_category"] = update.get("diagnosis_category", [])
    if "processed_route_types" in update:
        merged["processed_route_types"] = state.get("processed_route_types", []) + update.get("processed_route_types", [])
    if "action_plans" in update:
        merged["action_plans"] = state.get("action_plans", []) + update.get("action_plans", [])
    if "processed_ids" in update:
        existing_ids = set(state.get("processed_ids", []))
        new_ids = set(update.get("processed_ids", []))
        merged["processed_ids"] = list(existing_ids | new_ids)

    return merged
