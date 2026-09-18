"""
配置管理模块
集中管理所有配置参数，便于后续低代码/配置化改造
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 仓库根目录（src 的上一级），用于固定 chroma_db 路径，避免依赖进程 cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_vector_db_path() -> str:
    """
    向量库持久化目录：默认 <repo>/chroma_db，与当前工作目录无关。
    VECTOR_DB_PATH 若为相对路径，则相对仓库根解析。
    """
    raw = (os.getenv("VECTOR_DB_PATH") or "").strip()
    if not raw:
        return str((_REPO_ROOT / "chroma_db").resolve())
    p = Path(raw)
    if p.is_absolute():
        return str(p.resolve())
    return str((_REPO_ROOT / p).resolve())


def resolve_repo_relative_path(path: str) -> str:
    """
    将配置中的相对路径解析为绝对路径（相对仓库根目录）。
    避免 Streamlit / 脚本从非仓库根 cwd 启动时找不到 CSV、向量库旁文件等。
    """
    raw = (path or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    if p.is_absolute():
        return str(p.resolve())
    return str((_REPO_ROOT / p).resolve())


class LLMConfig:
    """LLM 配置"""
    # 模型配置
    MODEL: str = os.getenv("LLM_MODEL", "qwen3.7-max-2026-05-17")
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
    PERSIST_DIRECTORY: str = _resolve_vector_db_path()
    TOOL_TOP_K: int = min(2, max(1, int(os.getenv("RAG_TOOL_TOP_K", "1"))))
    SCORE_THRESHOLD: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.25"))
    CHROMA_FETCH_K: int = int(os.getenv("RAG_CHROMA_FETCH_K", "24"))


class FilterConfig:
    """筛选节点配置（B2B 电商/物流 SaaS 工单）"""
    # 降级模式关键词（SaaS 故障相关）
    KEYWORDS: list = [
        "502", "504", "白屏", "宕机", "全不更新", "无法登陆",
        "无法登录", "登录失败", "同步失败", "订单同步", "大面积", "业务停摆",
        "资损", "理赔", "403", "401", "鉴权失效", "数据库超时",
    ]


class MonitorConfig:
    """监控节点配置"""
    MIN_TICKETS_PER_BATCH: int = int(os.getenv("MONITOR_MIN_TICKETS", "7"))  # 非增量回退模式每批读取工单数
    TICKETS_CSV_PATH: str = os.getenv("MONITOR_TICKETS_CSV_PATH", "cold_start_tickets.csv")
    TICKETS_INCREMENTAL_CSV: str = os.getenv("MONITOR_TICKETS_INCREMENTAL_CSV", "incremental_tickets.csv")
    SEED_CSV: str = os.getenv("MONITOR_SEED_CSV", "")  # 非空时 seed_db 强制使用此 CSV 路径


# ==================== 配置导出 ====================
__all__ = [
    "LLMConfig",
    "EmbeddingConfig",
    "VectorStoreConfig",
    "FilterConfig",
    "MonitorConfig",
    "resolve_repo_relative_path",
]

