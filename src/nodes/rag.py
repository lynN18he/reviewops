"""
RAG 分析节点：基于工具调用（Tool Use）的归因分析
通过 search_known_issues / search_release_notes / search_api_docs_and_sop 对 ChromaDB 做向量检索，获取归因依据。
"""

import json
import re

from src.state import TicketState
from src.utils import init_llm
from src.tools import (
    AGENT_SYSTEM_PROMPT,
    CHROMA_TOP_K,
    _search_chroma,
    get_support_agent_tools,
)
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# 拒绝回答 / 低相关：与 tools.py Prompt、agent 路由一致，供跨模块判断
REFUSAL_EVIDENCE_CORE = "当前知识库或历史记录中未检索到相关高匹配度依据，需人工介入排查。"
REFUSAL_CONCLUSION_TEXT = "⚠️ 需人工介入（知识库无高匹配依据）"
REFUSAL_REASON_TEMPLATE = "检索内容与用户问题相关性不足或知识库无匹配片段，拒绝强行关联。"


def _user_facing_rag_failure(exc: BaseException) -> tuple:
    """
    LLM/RAG 调用失败时写入工单的结果（禁止把 HTTPSConnectionPool、URL 等暴露给业务界面）。
    返回 (conclusion, reason, evidence)；evidence 含 REFUSAL 核心句时与 agent 转人工逻辑一致。
    """
    text = str(exc) or ""
    raw = text.lower()

    # DashScope 额度 / 免费档（须在泛化 403「鉴权」之前判断）
    if any(
        x in raw
        for x in (
            "allocationquota",
            "freetieronly",
            "free tier",
            "exhausted",
            "use free tier only",
        )
    ):
        return (
            "⚠️ 智能分析暂不可用（模型额度）",
            "DashScope 返回额度相关错误（常见：免费额度用尽，或控制台开启了「仅使用免费额度」）。"
            "请在阿里云百炼关闭该限制、开通按量付费或更换模型后重试。",
            f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统状态]",
        )

    # LangChain Tongyi 用 HTTPError 包装 DashScope 响应时的兼容坑
    if isinstance(exc, KeyError) and getattr(exc, "args", None) == ("request",):
        return (
            "⚠️ 智能分析暂不可用（API 错误未正确展示）",
            "底层库在展示 DashScope 报错时触发了 KeyError: 'request'，真实原因被掩盖。"
            "请升级 langchain-community / dashscope，并检查百炼控制台中的调用失败原因与额度。",
            f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统状态]",
        )

    net_hints = (
        "connection",
        "timeout",
        "max retries",
        ":443",
        "network",
        "ssl",
        "resolve",
        "unreachable",
        "refused",
        "remote",
        "urllib",
        "httperror",
        "chunked",
        "httpsconnectionpool",
    )
    auth_hints = ("401", "403", "api key", "invalid_api", "unauthorized", "鉴权", "invalid key")
    # 未配置 Key 的 ValueError 里也会出现 dashscope 字样，必须先于网络类判断
    if any(h in raw for h in auth_hints) or ("未设置" in raw and "key" in raw):
        return (
            "⚠️ 智能分析暂不可用（鉴权失败）",
            "模型 API 鉴权失败或未配置，请检查 DASHSCOPE_API_KEY 等配置后重试。",
            f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统状态]",
        )
    if any(h in raw for h in net_hints) or "dashscope.aliyuncs.com" in raw:
        return (
            "⚠️ 智能分析暂不可用（网络或服务波动）",
            "无法连接归因服务或请求超时。请稍后重试巡检；若持续出现请检查网络与 API 配置。",
            f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统状态]",
        )
    return (
        "❓ 需要人工判断",
        "自动归因未完成，请结合工单原文由人工处理。",
        f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统状态]",
    )


def run_attribution_with_tools(llm, question: str, max_tool_rounds: int = 5):
    """
    供 Playground 等调用：基于工具调用的归因分析。
    返回 (conclusion, reason, evidence, tool_outputs, knowledge_relevant)。
    """
    return _run_agent_with_tools(llm, question, max_tool_rounds)


def _parse_knowledge_relevant(raw) -> bool:
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes")
    return bool(raw)


def _all_tool_outputs_miss_kb(tool_outputs: list) -> bool:
    """本次所有工具返回均为「未检索到相关文档」时视为无可用知识。"""
    if not tool_outputs:
        return False
    return all(str(t).strip() == "未检索到相关文档" for t in tool_outputs)


def _apply_refusal_fields() -> tuple:
    """统一拒绝回答时的 conclusion / reason / evidence。"""
    evidence = f"{REFUSAL_EVIDENCE_CORE}\n来源索引: [系统经验库]"
    return REFUSAL_CONCLUSION_TEXT, REFUSAL_REASON_TEMPLATE, evidence


def _enforce_sop_vs_product_bug_conclusion(conclusion: str, evidence: str) -> str:
    """
    确定性纠偏：证据来自 SOP 时禁止「产品已知局限」类结论（与 Prompt 铁律一致，防模型偶发违背）。
    """
    if not conclusion or not evidence:
        return conclusion
    if "产品已知" not in conclusion and "已知局限" not in conclusion:
        return conclusion
    if re.search(r"\[METADATA_SOURCE:\s*SOP-\d+\]", evidence, re.IGNORECASE):
        return "❓ 配置错误/常规问题（依据 SOP，客户侧配置或验签与文档要求不一致，非平台缺陷）"
    return conclusion


def _tool_call_id(tc) -> str:
    return tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "") or ""


def _tool_call_name(tc):
    return tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)


def _tool_call_args(tc) -> dict:
    raw = (tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _normalize_msg_content(content) -> str:
    """ChatTongyi 等模型可能返回 str 或 content block 列表，统一成可解析的字符串。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts).strip()
    return str(content).strip()


def _run_agent_with_tools(llm, ticket_content: str, max_tool_rounds: int = 5):
    """
    工具闭环：bind_tools 的 LLM 负责多轮 tool_calls；结束后用**未绑定工具**的 llm.invoke
    强制产出 JSON，避免首轮仅 tool_calls、content 为空时误走 JSON 解析失败。
    返回 (conclusion, reason, evidence, tool_outputs, knowledge_relevant)；
    解析失败时为 (None, None, None, tool_outputs, False)。
    """
    tools = get_support_agent_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)
    tool_outputs = []

    user_content = (
        f"用户反馈：{ticket_content}\n\n"
        "你必须先调用至少一个检索工具：search_api_docs_and_sop、search_known_issues、"
        "search_release_notes 之一（可多次），再根据检索结果输出最终 JSON（含 knowledge_relevant、conclusion、reason、evidence）。"
        "禁止在未调用工具的情况下直接猜测或拒答。"
    )
    messages: list = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    for _ in range(max_tool_rounds):
        try:
            ai_msg = llm_with_tools.invoke(messages)
        except Exception as e:
            c, r, ev = _user_facing_rag_failure(e)
            return c, r, ev, tool_outputs, False

        messages.append(ai_msg)
        tcalls = getattr(ai_msg, "tool_calls", None) or []

        if not tcalls:
            break

        for tc in tcalls:
            tc_id = _tool_call_id(tc)
            name = _tool_call_name(tc)
            tool_fn = tool_map.get(name) if name else None
            if not tool_fn:
                messages.append(ToolMessage(content="未知工具", tool_call_id=tc_id))
                continue
            args = _tool_call_args(tc)
            if "query" not in args:
                args["query"] = ticket_content
            try:
                tool_result = tool_fn.invoke(args)
            except Exception as e:
                _c, _r, _ = _user_facing_rag_failure(e)
                tool_result = _r if any(
                    x in str(e).lower()
                    for x in ("connection", "timeout", "ssl", "dashscope", "resolve", "443")
                ) else f"工具执行异常，请稍后重试。（{type(e).__name__}）"
            tool_outputs.append(str(tool_result))
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc_id))

    # 模型未调工具时仍用工单原文检索一次，避免无上下文却直接拒答。
    if not tool_outputs:
        try:
            broad = _search_chroma(ticket_content, k=CHROMA_TOP_K)
        except Exception:
            broad = "未检索到相关文档"
        tool_outputs.append(broad)
        messages.append(
            HumanMessage(
                content=(
                    "【系统自动兜底检索】尚未执行任何检索工具，已用工单原文完成向量检索。"
                    "请**仅依据**下列片段与系统规则重新判断并输出 JSON（含 METADATA_SOURCE 溯源），"
                    "若片段与客诉相关则不得再直接拒答。\n\n" + broad
                )
            )
        )

    final_hint = HumanMessage(
        content=(
            "请根据系统规则与上文工具检索结果，**不要调用任何工具**，仅输出一段 JSON，"
            '格式：{"knowledge_relevant": true或false, "conclusion": "字符串", '
            '"reason": "字符串", "evidence": "字符串"}'
        )
    )

    try:
        final_msg = llm.invoke(messages + [final_hint])
        answer = _normalize_msg_content(getattr(final_msg, "content", None))
    except Exception as e:
        c, r, ev = _user_facing_rag_failure(e)
        return c, r, ev, tool_outputs, False

    if not answer:
        return None, None, None, tool_outputs, False

    json_str = answer.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    elif json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()
    if "{" in json_str and "}" in json_str:
        start_idx = json_str.find("{")
        end_idx = json_str.rfind("}") + 1
        json_str = json_str[start_idx:end_idx]
    try:
        result = json.loads(json_str)
        kr = _parse_knowledge_relevant(result.get("knowledge_relevant", True))
        conclusion = result.get("conclusion", "❓ 需要人工判断")
        reason = result.get("reason", "")
        evidence = result.get("evidence", "")

        # 硬性规则：所有工具均未命中知识库 → 拒绝强行关联
        if _all_tool_outputs_miss_kb(tool_outputs):
            kr = False

        if not kr:
            conclusion, reason, evidence = _apply_refusal_fields()
        else:
            conclusion = _enforce_sop_vs_product_bug_conclusion(conclusion, evidence)

        return (conclusion, reason, evidence, tool_outputs, kr)
    except json.JSONDecodeError:
        return None, None, None, tool_outputs, False


def node_rag_analysis(state: TicketState) -> TicketState:
    """
    节点 3: RAG 归因分析
    使用工具（search_known_issues / search_release_notes / search_api_docs_and_sop）对 ChromaDB 做向量检索，获取归因依据。
    """
    llm = init_llm()
    critical_tickets = state.get("critical_tickets", [])

    if not critical_tickets:
        log_message = "⚠️ RAG 分析节点：无高危工单需要分析"
        return {
            "rag_analysis_results": [],
            "logs": [log_message],
        }

    rag_results = []

    for ticket in critical_tickets:
        ticket_content = ticket.get("ticket_content", "")
        ticket_id = ticket.get("ticket_id", "")

        try:
            conclusion, reason, evidence, _, knowledge_relevant = _run_agent_with_tools(
                llm, ticket_content
            )
            if conclusion is None:
                conclusion, reason, evidence = (
                    "❓ 需要人工判断",
                    "模型未返回有效 JSON",
                    "",
                )
                knowledge_relevant = False
            rag_results.append({
                "ticket_id": ticket_id,
                "ticket_content": ticket_content,
                "conclusion": conclusion,
                "reason": reason,
                "evidence": evidence or "",
                "knowledge_relevant": knowledge_relevant,
            })
        except Exception as e:
            conclusion, reason, evidence = _user_facing_rag_failure(e)
            rag_results.append({
                "ticket_id": ticket_id,
                "ticket_content": ticket_content,
                "conclusion": conclusion,
                "reason": reason,
                "evidence": evidence,
                "knowledge_relevant": False,
            })

    log_message = f"📄 RAG 分析节点：完成 {len(rag_results)} 条工单的归因分析"
    return {
        "rag_analysis_results": rag_results,
        "logs": [log_message],
    }
