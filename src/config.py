"""
配置管理模块
集中管理所有配置参数，便于后续低代码/配置化改造
"""

import os
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class LLMConfig:
    """LLM 配置"""
    # 模型配置
    MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")
    TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    
    # API Key（从环境变量读取）
    @staticmethod
    def get_api_key() -> Optional[str]:
        """获取 DashScope API Key"""
        return os.getenv("DASHSCOPE_API_KEY")
    
    @staticmethod
    def validate_api_key() -> None:
        """验证 API Key 是否存在"""
        api_key = LLMConfig.get_api_key()
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置，请在 .env 文件中配置")


class EmbeddingConfig:
    """Embedding 配置"""
    MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    
    @staticmethod
    def get_api_key() -> Optional[str]:
        """获取 DashScope API Key（与 LLM 共用）"""
        return LLMConfig.get_api_key()


class VectorStoreConfig:
    """向量数据库配置"""
    PERSIST_DIRECTORY: str = os.getenv("VECTOR_DB_PATH", "./chroma_db")
    
    # RAG 检索参数
    TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))  # 检索文档数量
    DISTANCE_THRESHOLD: float = float(os.getenv("RAG_DISTANCE_THRESHOLD", "1.5"))  # 距离阈值
    MAX_CONTEXT_LENGTH: int = int(os.getenv("RAG_MAX_CONTEXT_LENGTH", "300"))  # 每个文档的最大长度
    MAX_DOCS_IN_CONTEXT: int = int(os.getenv("RAG_MAX_DOCS_IN_CONTEXT", "3"))  # 上下文中的最大文档数


class FilterConfig:
    """筛选节点配置"""
    # 降级模式关键词列表
    KEYWORDS: list = [
        "故障", "失效", "问题", "坏", "不工作", "安全", "危险", 
        "质量", "避障", "抖动", "不稳定", "撞", "差点", "虚标", "欺骗"
    ]
    
    # 评分阈值
    RATING_THRESHOLD: int = int(os.getenv("FILTER_RATING_THRESHOLD", "3"))  # 低于此评分为高危


class MonitorConfig:
    """监控节点配置"""
    # Mock 数据生成配置
    MIN_REVIEWS_PER_BATCH: int = int(os.getenv("MONITOR_MIN_REVIEWS", "2"))  # 每批最少评论数
    MUST_HAVE_POSITIVE: bool = os.getenv("MONITOR_MUST_HAVE_POSITIVE", "true").lower() == "true"  # 是否必须包含正面评论


class ActionConfig:
    """行动生成配置"""
    # 默认行动类型
    DEFAULT_ACTION_TYPE: str = os.getenv("ACTION_DEFAULT_TYPE", "Jira Ticket")
    DEFAULT_PRIORITY: str = os.getenv("ACTION_DEFAULT_PRIORITY", "Medium")


# ==================== 配置验证 ====================
def validate_config():
    """验证所有必需的配置"""
    LLMConfig.validate_api_key()


# ==================== 配置导出 ====================
__all__ = [
    "LLMConfig",
    "EmbeddingConfig",
    "VectorStoreConfig",
    "FilterConfig",
    "MonitorConfig",
    "ActionConfig",
    "validate_config"
]

