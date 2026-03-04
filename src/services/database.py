"""
数据库服务模块
封装 SQLite 数据库操作，实现数据持久化
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager


class DatabaseManager:
    """数据库管理器，封装所有 SQL 操作"""
    
    def __init__(self, db_path: str = "reviewops.db"):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径（默认：reviewops.db）
        """
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """
        获取数据库连接的上下文管理器
        自动处理连接的创建和关闭
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使查询结果可以通过列名访问
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """初始化数据库，创建表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建 reviews 表（B2B 工单语义：无 rating，用 urgency_level / category）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
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
            
            # 迁移逻辑：检查并添加缺失的列（兼容旧数据库）
            self._migrate_table(cursor, conn)
            
            # 创建索引以提高查询性能
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_review_id ON reviews(review_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON reviews(created_at)
            """)
            
            conn.commit()
    
    def _migrate_table(self, cursor, conn):
        """迁移表结构，添加缺失的列（兼容旧数据库）"""
        # 获取现有表的列名
        cursor.execute("PRAGMA table_info(reviews)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # 定义必需的列（B2B 工单：urgency_level/category，不再使用 rating）
        required_columns = {
            'content': ('TEXT', "DEFAULT ''"),
            'source': ('TEXT', "DEFAULT 'mock'"),
            'timestamp': ('TEXT', ''),
            'risk_level': ('TEXT', ''),
            'rag_result': ('TEXT', ''),
            'action_plan': ('TEXT', ''),
            'created_at': ('TIMESTAMP', 'DEFAULT CURRENT_TIMESTAMP'),
            'urgency_level': ('TEXT', ''),
            'category': ('TEXT', '')
        }
        
        # 添加缺失的列
        for column_name, (column_type, column_default) in required_columns.items():
            if column_name not in existing_columns:
                try:
                    # 构建 ALTER TABLE 语句
                    if column_default:
                        alter_sql = f"ALTER TABLE reviews ADD COLUMN {column_name} {column_type} {column_default}"
                    else:
                        alter_sql = f"ALTER TABLE reviews ADD COLUMN {column_name} {column_type}"
                    
                    cursor.execute(alter_sql)
                except sqlite3.OperationalError as e:
                    # 如果列已存在（并发情况），忽略错误
                    if "duplicate column name" not in str(e).lower() and "already exists" not in str(e).lower():
                        raise
        
        # 数据迁移：将 review_text 的数据复制到 content（如果存在旧列）
        if 'review_text' in existing_columns and 'content' in (existing_columns | set(required_columns.keys())):
            try:
                cursor.execute("UPDATE reviews SET content = COALESCE(review_text, '') WHERE content IS NULL OR content = ''")
                conn.commit()  # 确保迁移数据被提交
            except sqlite3.OperationalError:
                # 如果更新失败（例如列不存在），忽略
                pass
    
    def exists(self, review_id: str) -> bool:
        """
        检查 review_id 是否存在

        Args:
            review_id: 工单 ID
        
        Returns:
            bool: 如果存在返回 True，否则返回 False
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM reviews WHERE review_id = ?", (review_id,))
            return cursor.fetchone() is not None
    
    def add_review(self, data: Dict) -> Optional[int]:
        """
        插入新工单（使用 INSERT OR IGNORE 避免重复）
        
        Args:
            data: 工单数据字典：
                - review_id: 工单 ID（必需）
                - content: 工单内容（必需）
                - source: 数据来源（可选，默认 'mock'）
                - timestamp: 时间戳（可选）
                - risk_level: 风险等级（可选）
                - urgency_level: 紧急程度 P0/P1/P2（可选）
                - category: 工单类别（可选）
        
        Returns:
            Optional[int]: 新插入记录的 ID，如果已存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(reviews)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            review_id = data.get('review_id')
            content = data.get('content', '')
            source = data.get('source', 'mock')
            timestamp = data.get('timestamp')
            risk_level = data.get('risk_level')
            urgency_level = data.get('urgency_level')
            category = data.get('category')
            
            if 'urgency_level' in existing_columns and 'category' in existing_columns:
                if 'review_text' in existing_columns:
                    cursor.execute("""
                        INSERT OR IGNORE INTO reviews 
                        (review_id, review_text, content, source, timestamp, risk_level, urgency_level, category)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (review_id, content, content, source, timestamp, risk_level, urgency_level, category))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO reviews 
                        (review_id, content, source, timestamp, risk_level, urgency_level, category)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (review_id, content, source, timestamp, risk_level, urgency_level, category))
            else:
                rating = data.get('rating')
                if 'review_text' in existing_columns:
                    cursor.execute("""
                        INSERT OR IGNORE INTO reviews 
                        (review_id, review_text, content, source, rating, timestamp, risk_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (review_id, content, content, source, rating, timestamp, risk_level))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO reviews 
                        (review_id, content, source, timestamp, risk_level)
                        VALUES (?, ?, ?, ?, ?)
                    """, (review_id, content, source, timestamp, risk_level))
            
            # 如果插入成功，返回新记录的 ID
            if cursor.rowcount > 0:
                return cursor.lastrowid
            else:
                # 如果已存在，返回该记录的 ID
                cursor.execute("SELECT id FROM reviews WHERE review_id = ?", (review_id,))
                row = cursor.fetchone()
                return row['id'] if row else None
    
    def update_analysis(
        self,
        review_id: str,
        rag_result: Optional[Dict] = None,
        action_plan: Optional[Dict] = None,
        risk_level: Optional[str] = None,
        urgency_level: Optional[str] = None,
        category: Optional[str] = None
    ) -> bool:
        """
        更新分析结果（RAG、Action、风险等级、紧急程度、工单类别）
        
        Args:
            review_id: 工单 ID
            rag_result: RAG 分析结果字典（可选）
            action_plan: Action 计划字典（可选）
            risk_level: 风险等级（可选）
            urgency_level: 紧急程度 P0/P1/P2（可选）
            category: 工单类别（可选）
        
        Returns:
            bool: 更新是否成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(reviews)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            update_fields = []
            update_values = []
            
            if rag_result is not None:
                update_fields.append("rag_result = ?")
                update_values.append(json.dumps(rag_result, ensure_ascii=False))
            if action_plan is not None:
                update_fields.append("action_plan = ?")
                update_values.append(json.dumps(action_plan, ensure_ascii=False))
            if risk_level is not None:
                update_fields.append("risk_level = ?")
                update_values.append(risk_level)
            if urgency_level is not None and 'urgency_level' in existing_columns:
                update_fields.append("urgency_level = ?")
                update_values.append(urgency_level)
            if category is not None and 'category' in existing_columns:
                update_fields.append("category = ?")
                update_values.append(category)
            
            if not update_fields:
                return False
            
            update_values.append(review_id)
            sql = f"""
                UPDATE reviews 
                SET {', '.join(update_fields)}
                WHERE review_id = ?
            """
            cursor.execute(sql, update_values)
            return cursor.rowcount > 0
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """
        按 created_at 倒序查询历史记录
        
        Args:
            limit: 返回记录数限制（默认 20）
        
        Returns:
            List[Dict]: 历史记录列表，每个记录包含所有字段
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(reviews)")
            cols = [row[1] for row in cursor.fetchall()]
            sel = ["id", "review_id", "content", "source", "timestamp", "risk_level", "rag_result", "action_plan", "created_at"]
            if "urgency_level" in cols:
                sel.append("urgency_level")
            if "category" in cols:
                sel.append("category")
            cursor.execute(f"""
                SELECT {", ".join(sel)}
                FROM reviews
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                # 解析 JSON 字段
                if result.get('rag_result'):
                    try:
                        result['rag_result'] = json.loads(result['rag_result'])
                    except json.JSONDecodeError:
                        result['rag_result'] = None
                else:
                    result['rag_result'] = None
                
                if result.get('action_plan'):
                    try:
                        result['action_plan'] = json.loads(result['action_plan'])
                    except json.JSONDecodeError:
                        result['action_plan'] = None
                else:
                    result['action_plan'] = None
                
                results.append(result)
            
            return results

    def clear_all_reviews(self) -> int:
        """
        清空 reviews 表所有数据，将系统还原为未跑过巡检的状态。
        用于清除脏数据或重置环境。

        Returns:
            int: 被删除的行数
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM reviews")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM reviews")
            return count

    def get_all_reviews(self) -> List[Dict]:
        """
        获取所有工单及其分析结果（不区分时间，按创建时间倒序）

        Returns:
            List[Dict]: 工单列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(reviews)")
            cols = [row[1] for row in cursor.fetchall()]
            sel = ["id", "review_id", "content", "source", "timestamp", "risk_level", "rag_result", "action_plan", "created_at"]
            if "urgency_level" in cols:
                sel.append("urgency_level")
            if "category" in cols:
                sel.append("category")
            cursor.execute(f"""
                SELECT {", ".join(sel)}
                FROM reviews
                ORDER BY created_at DESC
            """)

            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                # 解析 JSON 字段
                if result.get('rag_result'):
                    try:
                        result['rag_result'] = json.loads(result['rag_result'])
                    except json.JSONDecodeError:
                        result['rag_result'] = None
                else:
                    result['rag_result'] = None

                if result.get('action_plan'):
                    try:
                        result['action_plan'] = json.loads(result['action_plan'])
                    except json.JSONDecodeError:
                        result['action_plan'] = None
                else:
                    result['action_plan'] = None

                results.append(result)

            return results
    
    def get_review_by_id(self, review_id: str) -> Optional[Dict]:
        """
        根据 review_id 获取单条工单

        Args:
            review_id: 工单 ID

        Returns:
            Optional[Dict]: 工单数据，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(reviews)")
            cols = [row[1] for row in cursor.fetchall()]
            sel = ["id", "review_id", "content", "source", "timestamp", "risk_level", "rag_result", "action_plan", "created_at"]
            if "urgency_level" in cols:
                sel.append("urgency_level")
            if "category" in cols:
                sel.append("category")
            cursor.execute(f"""
                SELECT {", ".join(sel)}
                FROM reviews
                WHERE review_id = ?
            """, (review_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            result = dict(row)
            # 解析 JSON 字段
            if result.get('rag_result'):
                try:
                    result['rag_result'] = json.loads(result['rag_result'])
                except json.JSONDecodeError:
                    result['rag_result'] = None
            else:
                result['rag_result'] = None
            
            if result.get('action_plan'):
                try:
                    result['action_plan'] = json.loads(result['action_plan'])
                except json.JSONDecodeError:
                    result['action_plan'] = None
            else:
                result['action_plan'] = None
            
            return result


# ==================== 全局数据库实例 ====================
_db_instance: Optional[DatabaseManager] = None


def get_database(db_path: str = "reviewops.db") -> DatabaseManager:
    """
    获取数据库管理器实例（单例模式）
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        DatabaseManager: 数据库管理器实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager(db_path)
    return _db_instance
