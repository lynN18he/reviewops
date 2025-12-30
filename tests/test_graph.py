"""
测试工作流图构建
"""

import pytest
from src.graph import should_continue_analysis, build_graph
from src.state import ReviewState


class TestShouldContinueAnalysis:
    """测试条件路由函数"""
    
    def test_should_continue_with_critical_reviews(self):
        """测试有高危评论时继续分析"""
        state: ReviewState = {
            "critical_reviews": [{"id": 1}],
            "raw_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        result = should_continue_analysis(state)
        assert result == "rag_analysis"
    
    def test_should_end_without_critical_reviews(self):
        """测试没有高危评论时结束"""
        state: ReviewState = {
            "critical_reviews": [],
            "raw_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        result = should_continue_analysis(state)
        assert result == "end"
    
    def test_should_end_with_empty_state(self):
        """测试空状态时结束"""
        state: ReviewState = {}
        result = should_continue_analysis(state)
        assert result == "end"


class TestBuildGraph:
    """测试图构建"""
    
    def test_build_graph_returns_compiled_graph(self):
        """测试构建图返回编译后的图"""
        graph = build_graph()
        assert graph is not None
        # 验证图有必要的属性或方法
        assert hasattr(graph, "invoke") or hasattr(graph, "stream")

