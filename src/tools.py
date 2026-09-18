"""
Agent 工具定义：B2B 电商履约与物流 SaaS 技术支持场景
三个工具均对接 ChromaDB（需先运行 injest.py）。检索使用 LangChain 原生
similarity_score_threshold Retriever；见环境变量 RAG_SCORE_THRESHOLD。
"""

from langchain_core.tools import tool

from src.config import VectorStoreConfig

# 检索返回条数：默认 1，环境变量最多建议不超过 2
CHROMA_TOP_K = VectorStoreConfig.TOOL_TOP_K
RAG_SCORE_THRESHOLD = VectorStoreConfig.SCORE_THRESHOLD
# similarity_score_threshold 模式下，k 为从向量库拉取的候选条数；过小会导致阈值过滤后常为空
RAG_CHROMA_FETCH_K = VectorStoreConfig.CHROMA_FETCH_K

_DOC_TYPE_FILTERS = {
    "jira_ticket": {"doc_type": "jira_ticket"},
    "release_note": {"doc_type": "release_note"},
    "SOP": {"doc_type": "SOP"},
}


def _get_vectorstore():
    """从 ./chroma_db 加载 Chroma 向量库，用于工具内检索。"""
    from src.config import EmbeddingConfig
    api_key = EmbeddingConfig.get_api_key()
    if not api_key:
        return None
    try:
        from langchain_community.embeddings import DashScopeEmbeddings
        from langchain_community.vectorstores import Chroma

        embeddings = DashScopeEmbeddings(
            model=EmbeddingConfig.MODEL,
            dashscope_api_key=api_key,
        )
        return Chroma(
            persist_directory=VectorStoreConfig.PERSIST_DIRECTORY,
            embedding_function=embeddings,
        )
    except Exception:
        return None


def _metadata_source_label(meta: dict) -> str:
    """从向量库 metadata 取展示用来源名：SOP doc_id / Jira jira_id / 否则 Title / 兜底。"""
    if not meta:
        return "系统知识库"
    m = {k: (v if v is not None else "") for k, v in meta.items()}
    doc_id = (m.get("doc_id") or "").strip()
    if doc_id:
        return doc_id
    jira_id = (m.get("jira_id") or "").strip()
    if jira_id:
        return jira_id
    title = (m.get("Title") or "").strip()
    if title:
        return title
    return "系统知识库"


def _format_retrieved_docs(docs) -> str:
    """将检索到的 Document 拼接为带 [METADATA_SOURCE: XXX] 的文本，供 LLM 严格溯源。"""
    formatted_results = []
    for doc in docs:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        meta = getattr(doc, "metadata", None) or {}
        source_name = _metadata_source_label(meta)
        chunk_text = f"{text}\n[METADATA_SOURCE: {source_name}]"
        formatted_results.append(chunk_text)
    if not formatted_results:
        return "未检索到相关文档"
    return "\n\n---\n\n".join(formatted_results)


def _search_chroma(query: str, k: int = CHROMA_TOP_K, *, doc_type: str | None = None) -> str:
    """
    使用 LangChain Retriever（similarity_score_threshold）；候选池用较大 fetch_k，
    再截断为 k 条，避免 k=1 时阈值过滤后无结果。
    """
    vs = _get_vectorstore()
    if not vs:
        return "未检索到相关文档"
    fetch_k = max(RAG_CHROMA_FETCH_K, k, 4)
    metadata_filter = _DOC_TYPE_FILTERS.get(doc_type) if doc_type else None
    search_kwargs = {
        "score_threshold": RAG_SCORE_THRESHOLD,
        "k": fetch_k,
    }
    if metadata_filter:
        search_kwargs["filter"] = metadata_filter
    try:
        retriever = vs.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs=search_kwargs,
        )
        docs = retriever.invoke(query)[:k]
        if not docs:
            docs = (
                vs.similarity_search(query, k=fetch_k, filter=metadata_filter)[:k]
                if metadata_filter
                else vs.similarity_search(query, k=fetch_k)[:k]
            )
        if not docs:
            return "未检索到相关文档"
        return _format_retrieved_docs(docs)
    except Exception:
        try:
            docs = (
                vs.similarity_search(query, k=fetch_k, filter=metadata_filter)[:k]
                if metadata_filter
                else vs.similarity_search(query, k=fetch_k)[:k]
            )
            return _format_retrieved_docs(docs) if docs else "未检索到相关文档"
        except Exception:
            return "未检索到相关文档"


# ==================== ChromaDB 检索工具 ====================

@tool
def search_known_issues(query: str) -> str:
    """用于检索产研团队内部的已知缺陷库和历史 Jira 工单。当用户描述的故障没有明显的 API 错误码，且带有「又来了、一直这样、老毛病」等特定边缘场景或规律性问题时调用。"""
    return _search_chroma(query, doc_type="jira_ticket")


@tool
def search_release_notes(query: str) -> str:
    """用于检索系统最近的发版记录和底层服务变更日志。当用户明确表示「昨天还好好的，今天突然不行了」、「更新之后白屏/断流」等强时间突变特征时调用。"""
    return _search_chroma(query, doc_type="release_note")


@tool
def search_api_docs_and_sop(query: str) -> str:
    """用于检索 API 接口文档和客服标准排查 SOP。当用户反馈中包含具体错误码（如 401, 403, Auth-9002）、HMAC 验签失败、或者不懂如何配置 Webhook 和授权时调用。"""
    return _search_chroma(query, doc_type="SOP")


# ==================== 工具列表（供 Agent bind_tools 使用）====================

SUPPORT_AGENT_TOOLS = [
    search_known_issues,
    search_release_notes,
    search_api_docs_and_sop,
]


def get_support_agent_tools():
    """返回 L2 技术支持智能体可用的工具列表。"""
    return SUPPORT_AGENT_TOOLS


# ==================== Agent 系统提示词 ====================

AGENT_SYSTEM_PROMPT = """你现在是头部 B2B 电商与物流 SaaS 公司的 L2 级高级技术支持智能体。你的任务是分析商家的客诉，准确判断并调用最合适的工具（发版记录、已知缺陷或 API SOP）来寻找排查线索，并输出归因建议。

可用工具说明：
- search_known_issues：当客诉带有「又来了、一直这样、老毛病」等边缘/规律性问题、且无明确 API 错误码时使用。
- search_release_notes：当客诉带有「昨天还好好的，今天突然不行了」「更新之后白屏/断流」等强时间突变特征时使用。
- search_api_docs_and_sop：当客诉包含具体错误码（401、403、HMAC 验签失败等）或 Webhook/授权配置问题时使用。

请先根据用户反馈内容决定是否调用工具及调用哪个工具，再根据工具返回内容给出归因结论。最终你必须用以下 JSON 格式回复（只输出这一段 JSON，不要其他说明）：
{"knowledge_relevant": true 或 false, "conclusion": "字符串", "reason": "字符串", "evidence": "字符串"}

字段说明：
- knowledge_relevant：Context 是否在业务上与用户问题**有可用的关联**（见下方「相关性判定纪律」）。不要为了「绝对严谨」而轻易标 false。
- conclusion：当 knowledge_relevant 为 true 时，**须遵守下文「归因推导铁律」**：SOP/发版类依据 → 须为「配置错误/常规问题」「❓ 用户使用问题」等；**仅** JIRA 缺陷库依据 → 才可「✅ 产品已知局限」。还可为「⚠️ 需进一步调查」等；当为 false 时，必须为「⚠️ 需人工介入（知识库无高匹配依据）」。
- reason：简要说明；当 knowledge_relevant 为 false 时，说明为何完全无法使用检索内容。
- evidence：见下文溯源与拒绝规则。

【相关性判定纪律】
请评估 Context 与用户提问的关联度。**若 Context 能提供哪怕部分相关的业务概念、排查方向或规则，请尽量提取并正常输出分析**，设 knowledge_relevant 为 true，并严格基于原文引用 METADATA_SOURCE。
**仅当**两者【毫无任何业务交集】（例如问系统 Bug 却匹配到了完全无关的行政通知、或与物流/鉴权/订单完全无关的片段）时，才允许设 knowledge_relevant 为 false。
仍禁止编造：未出现在 Context 中的具体步骤、参数、JIRA 编号不得捏造；但允许在有关联时做合理归纳。

当 knowledge_relevant 为 false 时（仅限「毫无业务交集」或下方第 4 条硬性无检索）：
   - conclusion 必须为：「⚠️ 需人工介入（知识库无高匹配依据）」
   - evidence 必须为（可一字不改）：「当前知识库或历史记录中未检索到相关高匹配度依据，需人工介入排查。」并在下一行输出：「来源索引: [系统经验库]」
   - reason 简要说明为何无法建立任何业务关联。

4. **硬性规则**：当工具返回仅为「未检索到相关文档」或无任何带 [METADATA_SOURCE: …] 的片段时，必须设 knowledge_relevant 为 false，并按上条填写 conclusion / evidence / reason。

【归因推导铁律 — 依据类型绑定结论（违反视为严重错误）】
你必须根据**本次实际引用到的检索片段**及其 [METADATA_SOURCE: …] 决定 conclusion，禁止结论与依据类型冲突：
1. 若你依据的片段来源为 **[SOP-xxx]**（METADATA_SOURCE 以 SOP- 开头）或 **发版记录 / Release**（含版本号、变更说明类来源，或你调用的是 search_release_notes 且命中有效片段）：归因必须是 **「配置错误/常规问题」或「用户使用问题」或等价表述**（须体现客户侧配置/用法/变更适配，而非平台缺陷）。**绝不允许**输出「✅ 产品已知局限」或把此类情况甩锅为系统 Bug。
2. **仅当**你依据的片段来自 **明确的已知缺陷库 [JIRA-xxx]**（METADATA_SOURCE 为 JIRA- 数字编号，且内容描述的是已登记缺陷）时，才允许在 conclusion 中使用 **「✅ 产品已知局限」** 或「已知缺陷」类表述。
3. 若同时调用了多个工具，**以与客诉最直接相关的那一次检索结果为准**；检索结果通常只有 **一条 chunk**，evidence 中**只围绕这一条**展开，**禁止**把多个无关 JIRA 或 SOP 段落缝合成一段「依据大全」。
4. 作为主缺陷依据的 **JIRA 编号在 evidence 中至多出现一个是「主依据」**；禁止罗列多个 JIRA 充当同一问题的并列根因（检索已限制为单条 chunk，你也不得脑补补充其它 JIRA）。

关于 knowledge_relevant 为 true 时 evidence 的溯源要求：
1. 严格基于检索内容，不得编造不存在的 JIRA 或文档名。
2. 每一段带「[METADATA_SOURCE: XXX]」的检索结果，须在 evidence 末尾按出现顺序逐字输出「来源索引: [XXX]」，XXX 与 METADATA_SOURCE 中完全一致（通常仅一条）。
3. 若误将 knowledge_relevant 标为 true 但并无有效 METADATA_SOURCE，视为严重错误；应避免。"""
