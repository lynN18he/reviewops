"""
数据库服务模块
封装 SQLite 数据库操作，工单表 tickets（ticket_id, ticket_content）
"""

import sqlite3
import json
from typing import List, Dict, Optional
from contextlib import contextmanager

_TABLE = "tickets"


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
                    category TEXT
                )
            """)
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_ticket_id ON {_TABLE}(ticket_id)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_created_at ON {_TABLE}(created_at)")
            # 删除已废弃的 reviews 表，避免与 tickets 并存
            cursor.execute("DROP TABLE IF EXISTS reviews")
            # 若存在 incidents 表则清空其数据
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM incidents")
            conn.commit()

    def exists(self, ticket_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT 1 FROM {_TABLE} WHERE ticket_id = ?", (ticket_id,))
            return cursor.fetchone() is not None

    def add_ticket(self, data: Dict) -> Optional[int]:
        ticket_id = data.get("ticket_id")
        ticket_content = data.get("ticket_content", data.get("content", ""))
        source = data.get("source", "mock")
        timestamp = data.get("timestamp")
        risk_level = data.get("risk_level")
        urgency_level = data.get("urgency_level")
        category = data.get("category")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT OR IGNORE INTO {_TABLE}
                (ticket_id, ticket_content, source, timestamp, risk_level, urgency_level, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticket_id, ticket_content, source, timestamp, risk_level, urgency_level, category))
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
            update_values.append(ticket_id)
            cursor.execute(
                f"UPDATE {_TABLE} SET {', '.join(update_fields)} WHERE ticket_id = ?",
                update_values,
            )
            return cursor.rowcount > 0

    def get_history(self, limit: int = 20) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ticket_id, ticket_content, source, timestamp, risk_level, rag_result, action_plan, created_at, urgency_level, category
                FROM {_TABLE}
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return self._rows_to_dicts(cursor.fetchall())

    def get_dashboard_metrics(self) -> tuple:
        """
        基于 tickets 表统计看板指标（实时）。
        返回 (total_tickets, deflected_count, escalated_count, deflection_rate, escalation_rate)。
        - total_tickets: 工单总数
        - deflected_count: 未转研发（Email Draft / Escalate 或 category 技术支援）
        - escalated_count: 转研发（Jira Ticket 或 category 研发升级）
        - deflection_rate / escalation_rate: 百分比，总数为 0 时为 0.0。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            total_tickets = cursor.fetchone()[0]
            if total_tickets == 0:
                return 0, 0, 0, 0.0, 0.0

            cursor.execute(f"SELECT action_plan, category FROM {_TABLE}")
            rows = cursor.fetchall()
        deflected_count = 0
        escalated_count = 0
        for row in rows:
            ap_raw = row["action_plan"]
            category = (row["category"] or "").strip() if row["category"] is not None else ""
            action_type = ""
            if ap_raw:
                try:
                    ap = json.loads(ap_raw) if isinstance(ap_raw, str) else ap_raw
                    action_type = (ap.get("action_type") or "").strip()
                except (json.JSONDecodeError, TypeError):
                    if "Jira" in str(ap_raw) or "jira" in str(ap_raw).lower():
                        action_type = "Jira Ticket"
                    elif "Email" in str(ap_raw) or "邮件" in str(ap_raw):
                        action_type = "Email Draft"
            if action_type == "Jira Ticket" or category == "研发升级":
                escalated_count += 1
            elif action_type in ("Email Draft", "Escalate") or category == "技术支援":
                deflected_count += 1
            elif action_type and action_type != "Jira Ticket":
                deflected_count += 1
        deflection_rate = round((deflected_count / total_tickets) * 100, 1) if total_tickets else 0.0
        escalation_rate = round((escalated_count / total_tickets) * 100, 1) if total_tickets else 0.0
        return total_tickets, deflected_count, escalated_count, deflection_rate, escalation_rate

    def clear_all_tickets(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            count = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM {_TABLE}")
            return count

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


_db_instance: Optional[DatabaseManager] = None


def get_database(db_path: str = "reviewops.db") -> DatabaseManager:
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager(db_path)
    return _db_instance
