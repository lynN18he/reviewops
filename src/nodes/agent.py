"""
诊断路由节点：根据 RAG 归因结果将每条工单路由到 NEW_REGRESSION / USER_CONFIG_ERROR / KNOWN_ISSUE / UNKNOWN
"""

import json
import re
from src.state import TicketState, NEW_REGRESSION, USER_CONFIG_ERROR, KNOWN_ISSUE, UNKNOWN_ESCALATE
from src.utils import init_llm
from langchain_core.messages import HumanMessage


def _extract_jira_id(text: str) -> str:
    """从证据/结论中提取已有 Jira 编号，如 JIRA-1042"""
    if not text:
        return ""
    m = re.search(r"JIRA-\d+", text, re.IGNORECASE)
    return m.group(0) if m else ""


def agent_node(state: TicketState) -> TicketState:
    """
    诊断枢纽节点：根据归因结果对每条工单打上路由类型。
    输出 diagnosis_routes: [{ ticket_id, route_type, jira_id? }]，并清空 processed_route_types 以便后续条件边循环。
    """
    llm = init_llm()
    rag_results = state.get("rag_analysis_results", [])

    if not rag_results:
        return {
            "diagnosis_routes": [],
            "processed_route_types": [],
            "logs": ["⚠️ 诊断节点：无归因结果，跳过路由"],
        }

    routes = []
    for r in rag_results:
        ticket_id = r.get("ticket_id", "")
        conclusion = (r.get("conclusion") or "")
        reason = (r.get("reason") or "")
        evidence = (r.get("evidence") or "")

        # 规则优先：已知缺陷且能提取到 Jira 编号 -> KNOWN_ISSUE
        jira_id = _extract_jira_id(evidence + conclusion)
        if jira_id and ("已知" in conclusion or "已知缺陷" in conclusion or "JIRA-" in conclusion):
            routes.append({"ticket_id": ticket_id, "route_type": KNOWN_ISSUE, "jira_id": jira_id})
            continue

        # 规则：结论含用户/配置/Token/授权/SOP -> USER_CONFIG_ERROR
        if any(k in conclusion for k in ("用户", "配置", "Token", "授权", "SOP", "重新授权", "用户使用问题")):
            routes.append({"ticket_id": ticket_id, "route_type": USER_CONFIG_ERROR, "jira_id": ""})
            continue

        # 规则：结论含发版/回归/新版本/刚上线 -> NEW_REGRESSION
        if any(k in conclusion for k in ("发版", "回归", "新版本", "刚上线", "需进一步调查", "缺陷")):
            routes.append({"ticket_id": ticket_id, "route_type": NEW_REGRESSION, "jira_id": ""})
            continue

        # 规则：无法判断/需要人工 -> UNKNOWN_ESCALATE
        if any(k in conclusion for k in ("人工", "判断", "❓", "看不懂", "未找到")):
            routes.append({"ticket_id": ticket_id, "route_type": UNKNOWN_ESCALATE, "jira_id": ""})
            continue

        # 其余用 LLM 做一次路由判定，仅允许四枚举之一
        prompt = f"""根据以下 B2B 工单归因结果，判断应路由到哪一类。必须只返回下列四个英文枚举值之一，不要其他内容：
- USER_CONFIG_ERROR：用户配置错误（如 Token/配置问题）
- KNOWN_ISSUE：已知缺陷且已有 Jira
- NEW_REGRESSION：新 Bug 或发版故障，需提 P0 Jira
- UNKNOWN_ESCALATE：无法判断或资料不足，需转人工

工单ID: {ticket_id}
结论: {conclusion}
原因: {reason}
证据: {evidence[:300] if evidence else "无"}

只返回一个值：USER_CONFIG_ERROR、KNOWN_ISSUE、NEW_REGRESSION 或 UNKNOWN_ESCALATE。"""
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip().upper()
            if "NEW_REGRESSION" in raw:
                route_type = NEW_REGRESSION
            elif "USER_CONFIG" in raw:
                route_type = USER_CONFIG_ERROR
            elif "KNOWN_ISSUE" in raw:
                route_type = KNOWN_ISSUE
                jira_id = _extract_jira_id(evidence + conclusion)
                routes.append({"ticket_id": ticket_id, "route_type": route_type, "jira_id": jira_id})
                continue
            else:
                route_type = UNKNOWN_ESCALATE
            routes.append({"ticket_id": ticket_id, "route_type": route_type, "jira_id": ""})
        except Exception:
            routes.append({"ticket_id": ticket_id, "route_type": UNKNOWN_ESCALATE, "jira_id": ""})

    diagnosis_category = [r["route_type"] for r in routes]
    log = f"🔀 诊断节点：完成 {len(routes)} 条工单路由"
    return {
        "diagnosis_routes": routes,
        "diagnosis_category": diagnosis_category,
        "processed_route_types": [],
        "logs": [log],
    }
