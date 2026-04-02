"""
工具函数模块
"""

from src.tongyi_check_response_patch import apply_patch

apply_patch()

from langchain_community.chat_models import ChatTongyi
from src.config import LLMConfig

# 展示层脱敏：历史 DB 中可能存有 requests/urllib3 异常原文
_SERVICE_ERROR_MARKERS = (
    "httpsconnectionpool",
    "connectionerror",
    "max retries exceeded",
    "dashscope.aliyuncs.com",
    "urllib3",
    "remotedisconnected",
    "sslerror",
    "name or service not known",
    "newconnectionerror",
)


def sanitize_stored_rag_text_for_ui(text: str) -> str:
    """
    将已落库的 RAG reason/evidence 中的底层网络/连接异常替换为业务可读说明（不改 DB，仅展示用）。
    """
    if not text or not isinstance(text, str):
        return text or ""
    low = text.lower()
    if any(m in low for m in _SERVICE_ERROR_MARKERS):
        return (
            "归因服务暂时无法连接或响应超时（网络或 API 波动）。"
            "请稍后重试巡检，或由 L2 根据「原始问题」人工处理。"
        )
    return text


def init_llm():
    """初始化 LLM"""
    api_key = LLMConfig.get_api_key()
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置，请在 .env 文件中配置")
    
    return ChatTongyi(
        model=LLMConfig.MODEL,
        temperature=LLMConfig.TEMPERATURE,
        dashscope_api_key=api_key
    )

