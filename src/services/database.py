"""
数据库服务模块
封装 SQLite 数据库操作，工单表 tickets（ticket_id, ticket_content）
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager
from pathlib import Path

from src.config import resolve_repo_relative_path

_TABLE = "tickets"
_WORKFLOW_META_TABLE = "workflow_meta"
_WORKFLOW_RUNS_TABLE = "workflow_runs"
COLD_START_CSV = "cold_start_tickets.csv"
_COLD_START_CSV = COLD_START_CSV  # 兼容旧引用


def _golden_ticket_bucket(status: Optional[str], action_plan_raw) -> Optional[str]:
    """
    黄金三指标互斥分桶：'jira' | 'escalate' | 'resolved' | None。
    优先级：Jira 缺陷单 > 疑难转 L2 > 筛选拦截 > 邮件草稿闭环。
    """
    st = (status or "").strip()
    action_type = ""
    if action_plan_raw:
        try:
            ap = (
                json.loads(action_plan_raw)
                if isinstance(action_plan_raw, str)
                else action_plan_raw
            )
            if isinstance(ap, dict):
                action_type = (ap.get("action_type") or "").strip()
        except (json.JSONDecodeError, TypeError):
            pass
    if action_type == "Jira Ticket":
        return "jira"
    if action_type == "Escalate":
        return "escalate"
    if st == "intercepted":
        return "resolved"
    if action_type == "Email Draft":
        return "resolved"
    return None


class DatabaseManager:
    """数据库管理器，封装所有 SQL 操作"""

    def __init__(self, db_path: str = "reviewops.db"):
        self.db_path = db_path
        self._init_database()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL UNIQUE,
                    ticket_content TEXT NOT NULL,
                    source TEXT DEFAULT 'mock',
                    timestamp TEXT,
                    risk_level TEXT,
                    rag_result TEXT,
                    action_plan TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    urgency_level TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'pending',
                    is_test INTEGER DEFAULT 0,
                    analyzed_at TIMESTAMP
                )
            """)
            # Migration: add new columns if table exists from older schema
            for col_def in [
                ("status", "TEXT DEFAULT 'pending'"),
                ("is_test", "INTEGER DEFAULT 0"),
                ("analyzed_at", "TIMESTAMP"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {col_def[0]} {col_def[1]}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_ticket_id ON {_TABLE}(ticket_id)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_created_at ON {_TABLE}(created_at)")
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {_WORKFLOW_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {_WORKFLOW_RUNS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL UNIQUE,
                    total_count INTEGER DEFAULT 0,
                    safe_count INTEGER DEFAULT 0,
                    scanned_ids TEXT,
                    high_risk_tickets TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at ON {_WORKFLOW_RUNS_TABLE}(created_at)"
            )
            # 清理早期原型遗留表，避免旧数据影响当前 tickets 单表口径。
            cursor.execute("DROP TABLE IF EXISTS reviews")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM incidents")
            conn.commit()

    def exists(self, ticket_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT 1 FROM {_TABLE} WHERE ticket_id = ?", (ticket_id,))
            return cursor.fetchone() is not None

    def is_pending_needs_analysis(self, ticket_id: str) -> bool:
        """status=pending 且尚无有效 RAG 结论：可再次进入 monitor→filter 流水线。"""
        row = self.get_ticket_by_id(ticket_id)
        if not row:
            return False
        if (row.get("status") or "").strip() != "pending":
            return False
        rr = row.get("rag_result")
        if rr is None:
            return True
        if isinstance(rr, dict):
            return not (str(rr.get("conclusion") or "").strip())
        return True

    def get_workflow_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT value FROM {_WORKFLOW_META_TABLE} WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_workflow_meta(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO {_WORKFLOW_META_TABLE} (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def get_monitor_next_batch_id(self, default: int = 1) -> int:
        raw = self.get_workflow_meta("monitor_next_batch_id")
        try:
            return int(raw) if raw is not None else int(default)
        except (TypeError, ValueError):
            return int(default)

    def set_monitor_next_batch_id(self, batch_id: int) -> None:
        self.set_workflow_meta("monitor_next_batch_id", str(int(batch_id)))

    def get_last_run_time(self) -> Optional[str]:
        return self.get_workflow_meta("last_run_time")

    def set_last_run_time(self, run_time: str) -> None:
        self.set_workflow_meta("last_run_time", str(run_time))

    def save_workflow_run(self, batch_record: Dict) -> Optional[int]:
        batch_id = str(batch_record.get("batch_id") or "").strip()
        if not batch_id:
            return None
        high_risk_tickets = batch_record.get("high_risk_tickets") or []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO {_WORKFLOW_RUNS_TABLE}
                    (batch_id, total_count, safe_count, scanned_ids, high_risk_tickets, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    total_count = excluded.total_count,
                    safe_count = excluded.safe_count,
                    scanned_ids = excluded.scanned_ids,
                    high_risk_tickets = excluded.high_risk_tickets,
                    created_at = excluded.created_at
                """,
                (
                    batch_id,
                    int(batch_record.get("total_count") or 0),
                    int(batch_record.get("safe_count") or 0),
                    str(batch_record.get("scanned_ids") or ""),
                    json.dumps(high_risk_tickets, ensure_ascii=False),
                    batch_id,
                ),
            )
            cursor.execute(
                f"SELECT id FROM {_WORKFLOW_RUNS_TABLE} WHERE batch_id = ?",
                (batch_id,),
            )
            row = cursor.fetchone()
            return row["id"] if row else None

    def get_workflow_runs(self, limit: int = 20) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT batch_id, total_count, safe_count, scanned_ids, high_risk_tickets, created_at
                FROM {_WORKFLOW_RUNS_TABLE}
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        results: List[Dict] = []
        for row in rows:
            item = dict(row)
            try:
                item["high_risk_tickets"] = json.loads(item.get("high_risk_tickets") or "[]")
            except (json.JSONDecodeError, TypeError):
                item["high_risk_tickets"] = []
            results.append(item)
        return results

    def add_ticket(self, data: Dict) -> Optional[int]:
        ticket_id = data.get("ticket_id")
        ticket_content = data.get("ticket_content", data.get("content", ""))
        source = data.get("source", "mock")
        timestamp = data.get("timestamp")
        risk_level = data.get("risk_level")
        urgency_level = data.get("urgency_level")
        category = data.get("category")
        status = data.get("status", "pending")
        is_test = 1 if data.get("is_test", False) else 0
        analyzed_at = data.get("analyzed_at")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT OR IGNORE INTO {_TABLE}
                (ticket_id, ticket_content, source, timestamp, risk_level, urgency_level, category, status, is_test, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticket_id, ticket_content, source, timestamp, risk_level, urgency_level, category, status, is_test, analyzed_at))
            if cursor.rowcount > 0:
                return cursor.lastrowid
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE ticket_id = ?", (ticket_id,))
            row = cursor.fetchone()
            return row["id"] if row else None

    def update_analysis(
        self,
        ticket_id: str,
        rag_result: Optional[Dict] = None,
        action_plan: Optional[Dict] = None,
        risk_level: Optional[str] = None,
        urgency_level: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """
        更新工单分析结果。当写入 rag_result 且 action_plan 时，自动将 status 置为 'analyzed'，
        以便巡检出的高危工单能出现在「全局待办」中。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            update_fields, update_values = [], []
            if rag_result is not None:
                update_fields.append("rag_result = ?")
                update_values.append(json.dumps(rag_result, ensure_ascii=False))
            if action_plan is not None:
                update_fields.append("action_plan = ?")
                update_values.append(json.dumps(action_plan, ensure_ascii=False))
            if risk_level is not None:
                update_fields.append("risk_level = ?")
                update_values.append(risk_level)
            if urgency_level is not None:
                update_fields.append("urgency_level = ?")
                update_values.append(urgency_level)
            if category is not None:
                update_fields.append("category = ?")
                update_values.append(category)
            if not update_fields:
                return False
            # 关键：当有 rag_result 和 action_plan 时，同步 status='analyzed'，使工单进入全局待办
            if rag_result is not None and action_plan is not None:
                update_fields.append("status = ?")
                update_values.append("analyzed")
                update_fields.append("analyzed_at = ?")
                update_values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            update_values.append(ticket_id)
            cursor.execute(
                f"UPDATE {_TABLE} SET {', '.join(update_fields)} WHERE ticket_id = ?",
                update_values,
            )
            return cursor.rowcount > 0

    def get_briefing_tickets_24h(self, limit: int = 100) -> List[Dict]:
        """
        晨报专用：过去 24 小时内 analyzed/resolved 的工单，LIMIT 防止 Token 超载。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category, analyzed_at
                FROM {_TABLE}
                WHERE status IN ('analyzed', 'resolved') AND (is_test = 0 OR is_test IS NULL)
                  AND COALESCE(analyzed_at, created_at) >= datetime('now', 'localtime', '-1 day')
                ORDER BY COALESCE(analyzed_at, created_at) DESC, created_at DESC
                LIMIT ?
            """, (limit,))
            return self._rows_to_dicts(cursor.fetchall())

    def get_briefing_stats_24h(self) -> tuple:
        """
        晨报专用：过去 24 小时内已分析/已闭环工单数与「AI 智能闭环」占比（同黄金指标分桶）。
        返回 (total_count, ai_resolution_rate)。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT status, action_plan
                FROM {_TABLE}
                WHERE status IN ('analyzed', 'resolved') AND (is_test = 0 OR is_test IS NULL)
                  AND COALESCE(analyzed_at, created_at) >= datetime('now', 'localtime', '-1 day')
            """)
            rows = cursor.fetchall()
        if not rows:
            return 0, 0.0
        resolved_n = 0
        for row in rows:
            b = _golden_ticket_bucket(row["status"], row["action_plan"])
            if b == "resolved":
                resolved_n += 1
        total = len(rows)
        rate = round((resolved_n / total) * 100, 1) if total else 0.0
        return total, rate

    def get_pending_tickets(self, limit: int = 100) -> List[Dict]:
        """
        待处理异常：status='analyzed' 且 is_test=False，且 action_type IN ('Jira Ticket','Email Draft')。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category, analyzed_at
                FROM {_TABLE}
                WHERE status = 'analyzed' AND (is_test = 0 OR is_test IS NULL)
                ORDER BY COALESCE(analyzed_at, created_at) DESC
                LIMIT ?
            """, (limit,))
            rows = self._rows_to_dicts(cursor.fetchall())
        # Python 层过滤：只保留 Jira/Email 类 action
        def _needs_action(r):
            ap = r.get("action_plan")
            if not ap or not isinstance(ap, dict):
                return False
            at = (ap.get("action_type") or "").strip()
            return at in ("Jira Ticket", "Email Draft")
        return [r for r in rows if _needs_action(r)]

    def get_escalate_queue_tickets(self, limit: int = 100) -> List[Dict]:
        """
        转 L2 / AI 拒答队列：status='analyzed' 且 action_type='Escalate'。
        与 get_pending_tickets（仅 Email/Jira）互补，用于解释「总数 ≠ 待办条数」。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category, analyzed_at
                FROM {_TABLE}
                WHERE status = 'analyzed' AND (is_test = 0 OR is_test IS NULL)
                ORDER BY COALESCE(analyzed_at, created_at) DESC
                LIMIT ?
            """, (limit,))
            rows = self._rows_to_dicts(cursor.fetchall())

        def _is_escalate(r):
            ap = r.get("action_plan")
            if not ap or not isinstance(ap, dict):
                return False
            return (ap.get("action_type") or "").strip() == "Escalate"

        return [r for r in rows if _is_escalate(r)]

    def get_inbox_visibility_summary(self) -> Dict[str, int]:
        """
        解释大盘「工单总数」与「全局待办」差异用的计数（仅统计，不拉全文）。
        键：db_total, analyzed_inbox, analyzed_escalate, analyzed_other, pending, intercepted, resolved
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            db_total = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT status, COUNT(*) AS c FROM {_TABLE} GROUP BY status"
            )
            status_rows = {row["status"] or "": row["c"] for row in cursor.fetchall()}
            cursor.execute(f"""
                SELECT rag_result, action_plan, status FROM {_TABLE}
                WHERE status = 'analyzed' AND (is_test = 0 OR is_test IS NULL)
            """)
            analyzed = cursor.fetchall()

        pending = int(status_rows.get("pending", 0) or 0)
        intercepted = int(status_rows.get("intercepted", 0) or 0)
        resolved = int(status_rows.get("resolved", 0) or 0)

        inbox = escalate = other = 0
        for row in analyzed:
            ap_raw = row["action_plan"]
            action_type = ""
            if ap_raw:
                try:
                    ap = json.loads(ap_raw) if isinstance(ap_raw, str) else ap_raw
                    action_type = (ap.get("action_type") or "").strip()
                except (json.JSONDecodeError, TypeError):
                    pass
            if action_type in ("Jira Ticket", "Email Draft"):
                inbox += 1
            elif action_type == "Escalate":
                escalate += 1
            else:
                other += 1

        return {
            "db_total": db_total,
            "analyzed_inbox": inbox,
            "analyzed_escalate": escalate,
            "analyzed_other": other,
            "pending": pending,
            "intercepted": intercepted,
            "resolved": resolved,
        }

    def get_resolved_tickets(self, limit: int = 100) -> List[Dict]:
        """
        今日已闭环：status='resolved' 且 is_test=False。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category, analyzed_at
                FROM {_TABLE}
                WHERE status = 'resolved' AND (is_test = 0 OR is_test IS NULL)
                ORDER BY COALESCE(analyzed_at, created_at) DESC
                LIMIT ?
            """, (limit,))
            return self._rows_to_dicts(cursor.fetchall())

    def resolve_ticket(self, ticket_id: str) -> bool:
        """标记工单为已处理：UPDATE tickets SET status='resolved' WHERE ticket_id=?"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE {_TABLE} SET status = 'resolved' WHERE ticket_id = ?", (ticket_id,))
            return cursor.rowcount > 0

    def mark_tickets_intercepted(self, ticket_ids: List[str]) -> int:
        """
        将指定工单（且当前 status='pending'）更新为 intercepted。
        用于 Filter 节点过滤掉低危工单后的状态闭环。
        """
        if not ticket_ids:
            return 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(ticket_ids))
            cursor.execute(
                f"UPDATE {_TABLE} SET status = 'intercepted' WHERE ticket_id IN ({placeholders}) AND status = 'pending'",
                ticket_ids,
            )
            return cursor.rowcount

    def get_dashboard_metrics(self) -> tuple:
        """
        黄金三指标（互斥分桶）。
        第一张卡片口径：total_tickets = 库内累计条数（含 pending）。
        后三率分母：已完成 AI 分析 / 已流出待分析队列的工单数（status != 'pending'），不含积压。
        返回 (total_tickets, ai_resolution_rate, human_escalation_rate, bug_ident_rate,
        processed_tickets_count, resolved_bucket_count, escalated_count, jira_count)。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            total_tickets = cursor.fetchone()[0]
            if total_tickets == 0:
                return 0, 0.0, 0.0, 0.0, 0, 0, 0, 0

            cursor.execute(f"SELECT status, action_plan FROM {_TABLE}")
            rows = cursor.fetchall()

        resolved_count = 0
        escalated_count = 0
        jira_count = 0
        for row in rows:
            st = (row["status"] or "").strip()
            if st == "pending" or st == "":
                continue
            b = _golden_ticket_bucket(row["status"], row["action_plan"])
            if b == "jira":
                jira_count += 1
            elif b == "escalate":
                escalated_count += 1
            elif b == "resolved":
                resolved_count += 1

        processed = sum(
            1
            for row in rows
            if (row["status"] or "").strip() not in ("", "pending")
        )
        if processed == 0:
            return total_tickets, 0.0, 0.0, 0.0, 0, 0, 0, 0

        ai_resolution_rate = round((resolved_count / processed) * 100, 1)
        human_escalation_rate = round((escalated_count / processed) * 100, 1)
        bug_ident_rate = round((jira_count / processed) * 100, 1)
        return (
            total_tickets,
            ai_resolution_rate,
            human_escalation_rate,
            bug_ident_rate,
            processed,
            resolved_count,
            escalated_count,
            jira_count,
        )

    def get_briefing_library_breakdown(self) -> Dict[str, int]:
        """
        晨报用全库条数分解（与黄金分桶、大盘三率一致）。
        返回 total, processed（非 pending）, n_pending, n_jira, n_escalate, n_ai_closure,
        n_intercepted, n_email_closure。
        分桶计数仅统计 processed 行，与 get_dashboard_metrics 分母一致。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            total = int(cursor.fetchone()[0] or 0)
            if total == 0:
                return {
                    "total": 0,
                    "processed": 0,
                    "n_pending": 0,
                    "n_jira": 0,
                    "n_escalate": 0,
                    "n_ai_closure": 0,
                    "n_intercepted": 0,
                    "n_email_closure": 0,
                }
            cursor.execute(f"SELECT status, action_plan FROM {_TABLE}")
            rows = cursor.fetchall()

        n_jira = n_escalate = n_ai_closure = n_intercepted = n_email_closure = n_pending = 0
        for row in rows:
            st = (row["status"] or "").strip()
            if st == "pending" or st == "":
                n_pending += 1
                continue
            if st == "intercepted":
                n_intercepted += 1
            b = _golden_ticket_bucket(row["status"], row["action_plan"])
            if b == "jira":
                n_jira += 1
            elif b == "escalate":
                n_escalate += 1
            elif b == "resolved":
                n_ai_closure += 1
                if st != "intercepted":
                    n_email_closure += 1

        processed = total - n_pending
        return {
            "total": total,
            "processed": processed,
            "n_pending": n_pending,
            "n_jira": n_jira,
            "n_escalate": n_escalate,
            "n_ai_closure": n_ai_closure,
            "n_intercepted": n_intercepted,
            "n_email_closure": n_email_closure,
        }

    def get_intercepted_count_24h(self) -> int:
        """近 24 小时内写入且 status=intercepted 的工单数（与晨报时间窗对齐）。"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT COUNT(*) FROM {_TABLE}
                WHERE status = 'intercepted'
                  AND (is_test = 0 OR is_test IS NULL)
                  AND datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', 'localtime', '-1 day')
            """)
            return int(cursor.fetchone()[0] or 0)

    def clear_all_tickets(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            count = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM {_TABLE}")
            return count

    def clear_incremental_tickets(self) -> int:
        """
        仅删除增量巡检入库的工单（保留冷启动 CS-* 及 seed 基线）。
        以 source=incremental_tickets_csv 为准，并以 INC- 前缀兜底。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {_TABLE} WHERE source = ? OR ticket_id LIKE ?",
                ("incremental_tickets_csv", "INC-%"),
            )
            return int(cursor.rowcount or 0)

    def get_all_tickets(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category
                FROM {_TABLE}
                ORDER BY created_at DESC
            """)
            return self._rows_to_dicts(cursor.fetchall())

    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category
                FROM {_TABLE}
                WHERE ticket_id = ?
            """, (ticket_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._rows_to_dicts([row])[0]

    def _rows_to_dicts(self, rows) -> List[Dict]:
        results = []
        for row in rows:
            result = dict(row)
            for key in ("rag_result", "action_plan"):
                val = result.get(key)
                if val:
                    try:
                        result[key] = json.loads(val)
                    except json.JSONDecodeError:
                        result[key] = None
                else:
                    result[key] = None
            results.append(result)
        return results

    def cold_start_ingest_tickets(self, csv_path: Optional[str] = None) -> int:
        """
        冷启动摄入：当 DB 为空时，读取 cold_start_tickets.csv（或指定路径）并批量插入原始工单。
        仅插入 ticket_id, ticket_content, source, timestamp 等原始字段。
        status='pending'，rag_result/action_plan 均为空，等待工作流真实分析。
        返回插入条数。
        """
        raw = (csv_path or COLD_START_CSV).strip() or COLD_START_CSV
        if os.path.isabs(raw):
            csv_path = str(Path(raw).resolve())
        else:
            csv_path = resolve_repo_relative_path(raw) or raw
        if not os.path.isfile(csv_path):
            return 0
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, encoding="utf-8")
        except Exception:
            return 0
        if df.empty or "Ticket_ID" not in df.columns or "User_Message" not in df.columns:
            return 0

        existing = self.get_all_tickets()
        if existing:
            return 0

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0

        for _, row in df.iterrows():
            tid = str(row.get("Ticket_ID", "")).strip()
            if not tid:
                continue
            msg = str(row.get("User_Message", "")).strip()
            if not msg:
                continue

            row_id = self.add_ticket({
                "ticket_id": tid,
                "ticket_content": msg,
                "source": "stock_init",
                "timestamp": created_at,
                "status": "pending",
                "is_test": False,
                "analyzed_at": None,
            })
            if row_id is not None:
                inserted += 1

        return inserted


_db_instance: Optional[DatabaseManager] = None


def get_database(db_path: str = "reviewops.db") -> DatabaseManager:
    """
    单例 DB。默认路径相对仓库根解析，与 CSV / Chroma 一致，避免 cwd 不同导致「清库无效、扫描 0 条」。
    """
    global _db_instance
    if _db_instance is None:
        raw = (db_path or "reviewops.db").strip() or "reviewops.db"
        if os.path.isabs(raw):
            resolved = str(Path(raw).resolve())
        else:
            r = resolve_repo_relative_path(raw)
            resolved = r if r else raw
        _db_instance = DatabaseManager(resolved)
    return _db_instance
