"""
三个动作节点：generate_email_node / generate_jira_node / escalate_human_node
根据 diagnosis_routes 过滤工单并生成对应行动，写 DB 并追加 action_plans、processed_route_types。
"""

import json
from src.state import (
    TicketState,
    NEW_REGRESSION,
    USER_CONFIG_ERROR,
    KNOWN_ISSUE,
    UNKNOWN_ESCALATE,
)
from src.utils import init_llm
from src.services.database import get_database
from langchain_core.messages import HumanMessage


def _route_types_for_email():
    return {USER_CONFIG_ERROR, KNOWN_ISSUE}


def _tickets_by_route(state: TicketState, route_type: str):
    """返回本节点要处理的 diagnosis_routes 子集及对应 rag 结果"""
    routes = state.get("diagnosis_routes", [])
    rag_by_id = {r.get("ticket_id"): r for r in state.get("rag_analysis_results", [])}
    out = []
    for r in routes:
        if r.get("route_type") == route_type:
            out.append((r, rag_by_id.get(r.get("ticket_id"))))
    return out


def _update_db_for_plans(ticket_id: str, rag_result: dict, action_plan: dict, category: str):
    db = get_database()
    priority = action_plan.get("priority", "Medium")
    risk_level = "high" if priority == "High" else "medium" if priority == "Medium" else "low"
    urgency_level = {"High": "P0", "Medium": "P1", "Low": "P2"}.get(priority, "P2")
    db.update_analysis(
        ticket_id=ticket_id,
        rag_result=rag_result,
        action_plan=action_plan,
        risk_level=risk_level,
        urgency_level=urgency_level,
        category=category,
    )


def generate_email_node(state: TicketState) -> TicketState:
    """
    处理 USER_CONFIG_ERROR 与 KNOWN_ISSUE：生成邮件。
    KNOWN_ISSUE 时邮件模板需包含「这是平台已知问题（附带原 Jira 编号），研发正在抢修中」。
    """
    llm = init_llm()
    routes = state.get("diagnosis_routes", [])
    rag_by_id = {r.get("ticket_id"): r for r in state.get("rag_analysis_results", [])}
    to_process = [(r, rag_by_id.get(r.get("ticket_id"))) for r in routes if r.get("route_type") in _route_types_for_email()]

    if not to_process:
        return {"logs": ["📧 邮件节点：无 USER_CONFIG_ERROR/KNOWN_ISSUE 工单"]}

    action_plans = []
    for route, rag in to_process:
        if not rag:
            continue
        ticket_id = route.get("ticket_id", "")
        ticket_content = rag.get("ticket_content", "")
        conclusion = rag.get("conclusion", "")
        reason = rag.get("reason", "")
        evidence = rag.get("evidence", "")
        is_known = route.get("route_type") == KNOWN_ISSUE
        jira_id = route.get("jira_id", "")

        if is_known and jira_id:
            prompt = f"""请为以下「已知缺陷」工单生成一封给客户的邮件（纯正文，不要 JSON）。
要求：必须包含「这是平台已知问题，对应工单编号 {jira_id}，研发正在抢修中」的语义，并给出临时替代方案（Workaround）。

用户反馈：{ticket_content}
归因结论：{conclusion}
原因：{reason}
证据：{evidence}

请直接输出邮件正文（可分段），不要其他说明。"""
        else:
            prompt = f"""请为以下「客户配置/Token 问题」工单生成一封带 SOP 步骤的邮件（纯正文）。
要求：引导客户按 SOP 重新配置/授权，不要升级研发。

用户反馈：{ticket_content}
归因结论：{conclusion}
原因：{reason}

请直接输出邮件正文（可分段），不要其他说明。"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            content = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        except Exception:
            content = f"用户反馈：{ticket_content}\n归因：{conclusion}\n请按 SOP 重新配置或联系支持。"
            if is_known and jira_id:
                content = f"这是平台已知问题（工单编号 {jira_id}），研发正在抢修中。\n\n{content}"

        if is_known and jira_id and "已知问题" not in content and "抢修" not in content:
            content = f"这是平台已知问题（对应工单编号：{jira_id}），研发正在抢修中。\n\n{content}"

        plan = {
            "ticket_id": ticket_id,
            "action_type": "Email Draft",
            "title": f"客户邮件-{ticket_id}" + ("（已知问题+临时方案）" if is_known else "（SOP 引导）"),
            "content": content,
            "priority": "Low" if is_known else "Medium",
        }
        action_plans.append(plan)
        _update_db_for_plans(ticket_id, rag, plan, "技术支援")

    existing_plans = state.get("action_plans", [])
    existing_route_types = state.get("processed_route_types", [])
    return {
        "action_plans": existing_plans + action_plans,
        "processed_route_types": existing_route_types + ["email"],
        "logs": [f"📧 邮件节点：已生成 {len(action_plans)} 封邮件"],
    }


def generate_jira_node(state: TicketState) -> TicketState:
    """处理 NEW_REGRESSION：生成 P0 Jira 提给研发。"""
    to_process = _tickets_by_route(state, NEW_REGRESSION)
    if not to_process:
        return {"logs": ["🐞 Jira 节点：无 NEW_REGRESSION 工单"]}

    llm = init_llm()
    action_plans = []
    for route, rag in to_process:
        if not rag:
            continue
        ticket_id = route.get("ticket_id", "")
        ticket_content = rag.get("ticket_content", "")
        conclusion = rag.get("conclusion", "")
        reason = rag.get("reason", "")
        evidence = rag.get("evidence", "")

        prompt = f"""请为以下「新发版导致的 Bug」生成一条 P0 Jira 工单（只返回 JSON，不要其他说明）。

用户反馈：{ticket_content}
归因结论：{conclusion}
原因：{reason}
证据：{evidence}

JSON 格式：
{{ "title": "P0 标题", "content": "详细描述（含复现步骤与影响）", "priority": "High" }}
"""
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            for prefix in ("```json", "```"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):].strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
            if "{" in raw and "}" in raw:
                raw = raw[raw.index("{"): raw.rindex("}") + 1]
            result = json.loads(raw)
            title = result.get("title", f"P0-{ticket_id}")
            content = result.get("content", ticket_content)
        except Exception:
            title = f"P0 新发版回归-{ticket_id}"
            content = f"用户反馈：{ticket_content}\n归因：{conclusion}"

        plan = {
            "ticket_id": ticket_id,
            "action_type": "Jira Ticket",
            "title": title,
            "content": content,
            "priority": "High",
        }
        action_plans.append(plan)
        _update_db_for_plans(ticket_id, rag, plan, "研发升级")

    existing_plans = state.get("action_plans", [])
    existing_route_types = state.get("processed_route_types", [])
    return {
        "action_plans": existing_plans + action_plans,
        "processed_route_types": existing_route_types + ["jira"],
        "logs": [f"🐞 Jira 节点：已生成 {len(action_plans)} 条 P0 Jira"],
    }


def escalate_human_node(state: TicketState) -> TicketState:
    """UNKNOWN_ESCALATE：不强行生成结论，仅打日志并写入「转交人工」类 action_plan 便于看板展示。"""
    to_process = _tickets_by_route(state, UNKNOWN_ESCALATE)
    if not to_process:
        return {"logs": ["👤 人工升级节点：无 UNKNOWN_ESCALATE 工单"]}

    rag_by_id = {r.get("ticket_id"): r for r in state.get("rag_analysis_results", [])}
    action_plans = []
    for route, rag in to_process:
        if not rag:
            continue
        ticket_id = route.get("ticket_id", "")
        rag = rag_by_id.get(ticket_id) or {}
        plan = {
            "ticket_id": ticket_id,
            "action_type": "Escalate",
            "title": f"转交 L2 人工-{ticket_id}",
            "content": "Agent 无法从知识库与报错中做出明确诊断，已转交 L2 技术支持人工处理。",
            "priority": "High",
        }
        action_plans.append(plan)
        _update_db_for_plans(ticket_id, rag, plan, "技术支援")

    existing_plans = state.get("action_plans", [])
    existing_route_types = state.get("processed_route_types", [])
    return {
        "action_plans": existing_plans + action_plans,
        "processed_route_types": existing_route_types + ["escalate"],
        "logs": [f"👤 人工升级节点：已转交 {len(action_plans)} 条工单给 L2 人工"],
    }


def next_route_node(state: TicketState) -> TicketState:
    """空节点，仅用于挂载条件边，不修改 state。"""
    return {}
