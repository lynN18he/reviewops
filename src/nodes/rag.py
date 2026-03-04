"""
RAG 分析节点：基于工具调用（Tool Use）的归因分析
原 ChromaDB/向量检索逻辑已注释，改用轻量级 Mock Tools 进行 MVP 测试。
"""

import json
from src.state import ReviewState
from src.utils import init_llm
from src.tools import get_support_agent_tools, AGENT_SYSTEM_PROMPT
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# ==================== 已屏蔽的 ChromaDB/向量检索逻辑（保留供后续恢复）====================
# 初始化向量库（如果还没有初始化）
# vectorstore = None
# try:
#     from langchain_community.vectorstores import Chroma
#     from langchain_community.embeddings import DashScopeEmbeddings
#     from src.config import EmbeddingConfig, VectorStoreConfig
#
#     api_key = EmbeddingConfig.get_api_key()
#     if api_key:
#         embeddings = DashScopeEmbeddings(
#             model=EmbeddingConfig.MODEL,
#             dashscope_api_key=api_key
#         )
#         vectorstore = Chroma(
#             persist_directory=VectorStoreConfig.PERSIST_DIRECTORY,
#             embedding_function=embeddings
#         )
# except Exception as e:
#     log_message = f"⚠️ 向量库初始化失败: {str(e)[:50]}"
#
# 检索相关文档：
#     docs_with_scores = vectorstore.similarity_search_with_score(query, k=VectorStoreConfig.TOP_K)
#     relevant_docs = [doc for doc, distance in docs_with_scores if distance < VectorStoreConfig.DISTANCE_THRESHOLD]
#     context = "\n\n".join([doc.page_content[:VectorStoreConfig.MAX_CONTEXT_LENGTH] for doc in relevant_docs[:max_docs]])
# ==================== 以上为注释掉的 RAG 逻辑 ====================


def run_attribution_with_tools(llm, question: str, max_tool_rounds: int = 5):
    """
    供 Playground 等调用：基于工具调用的归因分析。
    返回 (conclusion, reason, evidence, tool_outputs: list[str])。
    若解析失败则 conclusion/reason/evidence 可能为 None 或占位文本。
    """
    return _run_agent_with_tools(llm, question, "", max_tool_rounds)


def _run_agent_with_tools(llm, review_text: str, review_id: str, max_tool_rounds: int = 5):
    """
    使用绑定了工具的 LLM 进行一轮归因分析：可多次调用工具，最终解析 JSON 结论。
    返回 (conclusion, reason, evidence, tool_outputs) 或 (None, None, None, []) 表示解析失败。
    """
    tools = get_support_agent_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)
    tool_outputs = []

    user_content = f"用户反馈：{review_text}\n\n请根据上述说明调用合适的工具获取排查线索后，输出最终 JSON（conclusion、reason、evidence）。"
    messages = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    answer = None

    for _ in range(max_tool_rounds):
        response = llm_with_tools.invoke(messages)
        answer = response.content if hasattr(response, "content") else str(response)

        if not getattr(response, "tool_calls", None):
            break

        # 必须追加模型返回的原始 response，否则 DashScope 会报 tool 消息必须紧跟带 tool_calls 的 assistant 消息
        messages.append(response)
        for tc in response.tool_calls:
            # 兼容 dict 或 ToolCall 对象，DashScope 要求 tool_call_id 与 assistant 消息中的 id 一致
            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            tool_fn = tool_map.get(name) if name else None
            if not tool_fn:
                messages.append(ToolMessage(content="未知工具", tool_call_id=tc_id))
                continue
            args = (tc.get("args") or {}) if isinstance(tc, dict) else (getattr(tc, "args", None) or {})
            if isinstance(args, dict) and "query" not in args:
                args["query"] = review_text
            try:
                tool_result = tool_fn.invoke(args)
            except Exception as e:
                tool_result = f"工具执行异常: {str(e)[:200]}"
            tool_outputs.append(str(tool_result))
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc_id))

    if not answer:
        return None, None, None, tool_outputs

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
        return (
            result.get("conclusion", "❓ 需要人工判断"),
            result.get("reason", ""),
            result.get("evidence", ""),
            tool_outputs,
        )
    except json.JSONDecodeError:
        return None, None, None, tool_outputs


def node_rag_analysis(state: ReviewState) -> ReviewState:
    """
    节点 3: RAG 归因分析
    使用 Mock Tools（search_known_issues / search_release_notes / search_api_docs_and_sop）替代向量检索。
    """
    llm = init_llm()
    critical_reviews = state.get("critical_reviews", [])

    if not critical_reviews:
        log_message = "⚠️ RAG 分析节点：无高危评论需要分析"
        return {
            "rag_analysis_results": [],
            "logs": [log_message],
        }

    rag_results = []

    for review in critical_reviews:
        review_text = review.get("review_text", "")
        review_id = review.get("review_id", "")

        try:
            conclusion, reason, evidence, _ = _run_agent_with_tools(llm, review_text, review_id)
            if conclusion is None:
                conclusion, reason, evidence = (
                    "❓ 需要人工判断",
                    "模型未返回有效 JSON",
                    "",
                )
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": conclusion,
                "reason": reason,
                "evidence": evidence or "",
            })
        except Exception as e:
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": "❓ 需要人工判断",
                "reason": f"RAG 分析失败: {str(e)[:100]}",
                "evidence": "",
            })

    log_message = f"📄 RAG 分析节点：完成 {len(rag_results)} 条评论的归因分析（已使用 Tool 调用）"
    return {
        "rag_analysis_results": rag_results,
        "logs": [log_message],
    }
