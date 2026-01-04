"""
ReviewOps 状态定义
"""

from typing import TypedDict, List


class ReviewState(TypedDict):
    """工作流状态"""
    raw_reviews: List[dict]  # 新评论
    critical_reviews: List[dict]  # 筛选后的高危评论
    rag_analysis_results: List[dict]  # 归因结果
    action_plans: List[dict]  # 行动建议
    logs: List[str]  # 日志（使用 operator.add 追加）
    processed_ids: List[str]  # 已处理的评论ID集合（用于幂等性去重）


def reducer(state: ReviewState, update: ReviewState) -> ReviewState:
    """合并状态更新"""
    # 对于列表类型，使用 operator.add 追加
    # 对于其他类型，直接覆盖
    merged = state.copy()
    
    # 合并列表（追加）
    if "logs" in update:
        merged["logs"] = state.get("logs", []) + update.get("logs", [])
    if "raw_reviews" in update:
        merged["raw_reviews"] = update.get("raw_reviews", [])
    if "critical_reviews" in update:
        merged["critical_reviews"] = update.get("critical_reviews", [])
    if "rag_analysis_results" in update:
        merged["rag_analysis_results"] = update.get("rag_analysis_results", [])
    if "action_plans" in update:
        merged["action_plans"] = update.get("action_plans", [])
    if "processed_ids" in update:
        # 合并已处理ID集合（去重）
        existing_ids = set(state.get("processed_ids", []))
        new_ids = set(update.get("processed_ids", []))
        merged["processed_ids"] = list(existing_ids | new_ids)
    
    return merged

