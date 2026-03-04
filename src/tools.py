"""
Agent 工具定义：B2B 电商履约与物流 SaaS 技术支持场景
使用硬编码 Mock 返回值，替代 ChromaDB RAG 进行 MVP 测试。
"""

from langchain_core.tools import tool


# ==================== Mock Tools（硬编码返回值）====================

@tool
def search_known_issues(query: str) -> str:
    """用于检索产研团队内部的已知缺陷库和历史 Jira 工单。当用户描述的故障没有明显的 API 错误码，且带有「又来了、一直这样、老毛病」等特定边缘场景或规律性问题时调用。"""
    return "已知缺陷 JIRA-1042：带有阿拉伯语地址的 Shopify 订单同步时，特定字符会导致解析超时。目前仍在排期修复中。"


@tool
def search_release_notes(query: str) -> str:
    """用于检索系统最近的发版记录和底层服务变更日志。当用户明确表示「昨天还好好的，今天突然不行了」、「更新之后白屏/断流」等强时间突变特征时调用。"""
    return "发版记录 2026-03-02：重构了 USPS 物流轨迹抓取爬虫模块，增加了一层限流校验。"


@tool
def search_api_docs_and_sop(query: str) -> str:
    """用于检索 API 接口文档和客服标准排查 SOP。当用户反馈中包含具体错误码（如 401, 403, Auth-9002）、HMAC 验签失败、或者不懂如何配置 Webhook 和授权时调用。"""
    return "SOP 排查手册：遇到 HMAC validation failed 或 401 错误，通常是商家在 Shopify 后台重置了 API Token 但未在我们的系统更新。请引导商家重新授权。"


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
{"conclusion": "✅ 产品已知局限" | "⚠️ 需进一步调查" | "❓ 用户使用问题", "reason": "分析原因", "evidence": "从工具或知识中提取的证据片段"}"""
