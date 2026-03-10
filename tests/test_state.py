"""
测试状态定义和 reducer
"""

import pytest
from src.state import TicketState, reducer


class TestReducer:
    """测试 reducer 函数"""

    def test_reducer_merge_logs(self):
        """测试日志合并"""
        state = {"logs": ["log1"], "incr_tickets": []}
        update = {"logs": ["log2", "log3"]}
        result = reducer(state, update)
        assert result["logs"] == ["log1", "log2", "log3"]

    def test_reducer_replace_incr_tickets(self):
        """测试 incr_tickets 替换（不追加）"""
        state = {"incr_tickets": [{"id": 1}]}
        update = {"incr_tickets": [{"id": 2}, {"id": 3}]}
        result = reducer(state, update)
        assert result["incr_tickets"] == [{"id": 2}, {"id": 3}]
        assert len(result["incr_tickets"]) == 2

    def test_reducer_merge_processed_ids(self):
        """测试 processed_ids 去重合并"""
        state = {"processed_ids": ["id1", "id2"]}
        update = {"processed_ids": ["id2", "id3"]}
        result = reducer(state, update)
        assert set(result["processed_ids"]) == {"id1", "id2", "id3"}
        assert len(result["processed_ids"]) == 3

    def test_reducer_empty_state(self):
        """测试空状态更新"""
        state = {}
        update = {
            "incr_tickets": [{"id": 1}],
            "logs": ["log1"],
            "processed_ids": ["id1"]
        }
        result = reducer(state, update)
        assert result["incr_tickets"] == [{"id": 1}]
        assert result["logs"] == ["log1"]
        assert result["processed_ids"] == ["id1"]

    def test_reducer_empty_update(self):
        """测试空更新"""
        state = {"logs": ["log1"], "incr_tickets": [{"id": 1}]}
        update = {}
        result = reducer(state, update)
        assert result["logs"] == ["log1"]
        assert result["incr_tickets"] == [{"id": 1}]
