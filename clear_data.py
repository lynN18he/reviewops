#!/usr/bin/env python3
"""
清空所有工单数据，使系统回到「未执行过巡检」的状态。
会删除 reviewops.db 中 tickets 表的全部记录。
执行后请重启 Streamlit 应用（或刷新页面），以便 session_state 重新从空库加载。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.database import get_database


def main():
    db = get_database()  # 初始化时会 DROP TABLE reviews、清空 incidents（若存在）
    count = db.clear_all_tickets()
    print(f"已清空 {count} 条工单记录，数据库已回到未执行巡检的状态。")
    print("（启动时已删除废弃的 reviews 表并清空 incidents 表数据。）")
    print("请重启 Streamlit 应用（Ctrl+C 后重新运行 streamlit run app.py）以使页面状态同步。")


if __name__ == "__main__":
    main()
