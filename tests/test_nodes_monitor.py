"""
测试监控节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.monitor import node_monitor, load_tickets_from_csv
from src.state import ReviewState


def _fake_tickets(n=3):
    return [
        {
            "review_id": f"TIK-{100 + i}",
            "review_text": f"工单内容 {i}",
            "user_id": f"ticket_TIK-{100 + i}",
            "timestamp": "2026-03-04 12:00:00",
            "urgency_level": None,
            "category": None,
        }
        for i in range(n)
    ]


class TestNodeMonitor:
    """测试监控节点"""

    @patch("src.nodes.monitor.load_tickets_from_csv")
    @patch("src.nodes.monitor.get_database")
    def test_node_monitor_generates_tickets(self, mock_get_db, mock_load_csv):
        """测试从增量 CSV 随机读取并生成工单"""
        mock_load_csv.return_value = _fake_tickets(3)
        db = MagicMock()
        db.exists.return_value = False
        mock_get_db.return_value = db

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_monitor(state)

        assert "raw_reviews" in result
        assert "processed_ids" in result
        assert "logs" in result
        assert len(result["raw_reviews"]) >= 2
        assert len(result["processed_ids"]) == len(result["raw_reviews"])

    @patch("src.nodes.monitor.load_tickets_from_csv")
    @patch("src.nodes.monitor.get_database")
    def test_node_monitor_empty_csv_returns_empty(self, mock_get_db, mock_load_csv):
        """测试增量文件为空时返回无新工单"""
        mock_load_csv.return_value = []

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_monitor(state)

        assert result["raw_reviews"] == []
        assert result["processed_ids"] == []
        assert "未找到工单文件或文件为空" in result["logs"][0]

    @patch("src.nodes.monitor.load_tickets_from_csv")
    @patch("src.nodes.monitor.get_database")
    def test_node_monitor_idempotency(self, mock_get_db, mock_load_csv):
        """测试已处理 ID 不会重复入库"""
        mock_load_csv.return_value = _fake_tickets(3)
        db = MagicMock()
        db.exists.side_effect = lambda rid: rid == "TIK-100"
        mock_get_db.return_value = db

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": ["TIK-100"],
        }

        result = node_monitor(state)

        assert "TIK-100" not in result["processed_ids"] or len(result["raw_reviews"]) == 0

    @patch("src.nodes.monitor.load_tickets_from_csv")
    @patch("src.nodes.monitor.get_database")
    def test_node_monitor_logs_format(self, mock_get_db, mock_load_csv):
        """测试日志格式"""
        mock_load_csv.return_value = _fake_tickets(2)
        db = MagicMock()
        db.exists.return_value = False
        mock_get_db.return_value = db

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_monitor(state)

        assert len(result["logs"]) > 0
        log_message = result["logs"][0]
        assert "工单" in log_message

    @patch("src.nodes.monitor.load_tickets_from_csv")
    @patch("src.nodes.monitor.get_database")
    def test_node_monitor_ticket_structure(self, mock_get_db, mock_load_csv):
        """测试生成的工单结构"""
        mock_load_csv.return_value = _fake_tickets(2)
        db = MagicMock()
        db.exists.return_value = False
        mock_get_db.return_value = db

        state: ReviewState = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_monitor(state)

        if result["raw_reviews"]:
            ticket = result["raw_reviews"][0]
            assert "review_id" in ticket
            assert "user_id" in ticket
            assert "timestamp" in ticket
            assert "review_text" in ticket
            assert "urgency_level" in ticket or "category" in ticket
