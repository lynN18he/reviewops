"""
ReviewOps 状态定义（B2B 工单分诊）
"""

from typing import TypedDict, List, NotRequired

# 诊断路由类型（agent_node 仅输出以下四类，用于条件边强拦截）
NEW_REGRESSION = "NEW_REGRESSION"           # 新 Bug/发版故障 -> P0 Jira
USER_CONFIG_ERROR = "USER_CONFIG_ERROR"     # 用户配置错误 -> 邮件+SOP
KNOWN_ISSUE = "KNOWN_ISSUE"                # 已知缺陷（已有 Jira）-> 邮件+原 Jira+Workaround
UNKNOWN_ESCALATE = "UNKNOWN_ESCALATE"       # 未知需人工 -> 转 L2 人工


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
    monitor_next_batch_id: NotRequired[int]
