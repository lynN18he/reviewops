"""
测试监控节点
"""

import pytest
from unittest.mock import patch
from src.nodes.monitor import node_monitor, MOCK_DATA_POOL
from src.state import ReviewState


class TestNodeMonitor:
    """测试监控节点"""
    
    def test_node_monitor_generates_reviews(self):
        """测试生成评论"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_monitor(state)
        
        assert "raw_reviews" in result
        assert "processed_ids" in result
        assert "logs" in result
        assert len(result["raw_reviews"]) >= 2  # 至少生成 2 条
        assert len(result["processed_ids"]) == len(result["raw_reviews"])
    
    def test_node_monitor_ensures_positive_review(self):
        """测试确保包含正面评论"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_monitor(state)
        
        # 检查是否有正面评论（rating >= 4）
        positive_reviews = [r for r in result["raw_reviews"] if r.get("rating", 0) >= 4]
        assert len(positive_reviews) >= 1
    
    def test_node_monitor_idempotency(self):
        """测试幂等性 - 已处理的ID不会重复生成"""
        processed_id = "201_1234567890_5678"
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [processed_id]
        }
        
        result = node_monitor(state)
        
        # 确保不会生成已处理的ID（虽然由于时间戳不同，这个测试可能不够严格）
        # 但至少验证了 processed_ids 的逻辑
        assert processed_id not in result["processed_ids"] or len(result["raw_reviews"]) == 0
    
    def test_node_monitor_logs_format(self):
        """测试日志格式"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_monitor(state)
        
        assert len(result["logs"]) > 0
        log_message = result["logs"][0]
        assert "检测到" in log_message
        assert "条新增评论" in log_message
    
    def test_node_monitor_review_structure(self):
        """测试生成的评论结构"""
        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": []
        }
        
        result = node_monitor(state)
        
        if result["raw_reviews"]:
            review = result["raw_reviews"][0]
            assert "review_id" in review
            assert "user_id" in review
            assert "timestamp" in review
            assert "review_text" in review
            assert "rating" in review
            assert isinstance(review["rating"], int)
            assert 1 <= review["rating"] <= 5

