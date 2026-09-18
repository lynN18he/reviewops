"""
测试工作流运行状态的 SQLite 持久化。
"""

from src.services.database import DatabaseManager


def test_workflow_meta_persists_monitor_cursor_and_last_run_time(tmp_path):
    db = DatabaseManager(str(tmp_path / "workflow.db"))

    assert db.get_monitor_next_batch_id(default=1) == 1
    assert db.get_last_run_time() is None

    db.set_monitor_next_batch_id(4)
    db.set_last_run_time("2026-09-17 16:30:00")

    reopened = DatabaseManager(str(tmp_path / "workflow.db"))
    assert reopened.get_monitor_next_batch_id(default=1) == 4
    assert reopened.get_last_run_time() == "2026-09-17 16:30:00"


def test_workflow_run_history_round_trips_as_recent_first(tmp_path):
    db = DatabaseManager(str(tmp_path / "workflow.db"))
    first = {
        "batch_id": "2026-09-17 16:30:00",
        "total_count": 5,
        "safe_count": 3,
        "scanned_ids": "INC-001, INC-002",
        "high_risk_tickets": [
            {
                "ticket_id": "INC-001",
                "category": "系统缺陷",
                "summary": "订单同步失败",
                "action": "**[已推送 P0 Jira]**",
            }
        ],
    }
    second = {
        "batch_id": "2026-09-17 16:40:00",
        "total_count": 2,
        "safe_count": 2,
        "scanned_ids": "INC-006, INC-007",
        "high_risk_tickets": [],
    }

    db.save_workflow_run(first)
    db.save_workflow_run(second)

    runs = db.get_workflow_runs(limit=10)
    assert [r["batch_id"] for r in runs] == [
        "2026-09-17 16:40:00",
        "2026-09-17 16:30:00",
    ]
    assert runs[1]["high_risk_tickets"][0]["ticket_id"] == "INC-001"

