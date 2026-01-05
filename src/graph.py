"""
工作流图构建模块
"""

from typing import Literal
from langgraph.graph import StateGraph, END

from src.state import ReviewState, reducer
from src.nodes.monitor import node_monitor
from src.nodes.filter import node_filter
from src.nodes.rag import node_rag_analysis
from src.nodes.action import node_action_gen


def should_continue_analysis(state: ReviewState) -> Literal["rag_analysis", "end"]:
    """判断是否继续 RAG 分析"""
    critical_reviews = state.get("critical_reviews", [])
    if len(critical_reviews) > 0:
        return "rag_analysis"
    return "end"


def build_graph():
    """构建 LangGraph 工作流"""
    # 创建状态图，指定 reducer
    from operator import add
    workflow = StateGraph(ReviewState)
    
    # 添加节点
    workflow.add_node("monitor", node_monitor)
    workflow.add_node("filter", node_filter)
    workflow.add_node("rag_analysis", node_rag_analysis)
    workflow.add_node("action_gen", node_action_gen)
    
    # 设置入口点
    workflow.set_entry_point("monitor")
    
    # 添加边
    workflow.add_edge("monitor", "filter")
    
    # 条件路由：filter 后判断是否继续
    workflow.add_conditional_edges(
        "filter",
        should_continue_analysis,
        {
            "rag_analysis": "rag_analysis",
            "end": END
        }
    )
    
    workflow.add_edge("rag_analysis", "action_gen")
    workflow.add_edge("action_gen", END)
    
    # 编译图
    graph_app = workflow.compile()
    
    return graph_app


# ==================== 导出 ====================
# 创建全局图实例
graph_app = build_graph()

