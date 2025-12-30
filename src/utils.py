"""
工具函数模块
"""

from langchain_community.chat_models import ChatTongyi
from src.config import LLMConfig


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

