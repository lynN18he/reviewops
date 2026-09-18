#!/usr/bin/env python3
"""
清空工单数据。

默认（推荐）：仅删除增量巡检单（INC-* / source=incremental_tickets_csv），
保留冷启动 CS-* 及其已写入的 RAG/行动基线。

--all：删除 tickets 表全部记录（与 seed 前全量清空一致）。

执行后请重启 Streamlit（或刷新），以便 session_state 与 DB 一致。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.database import get_database


def main():
    parser = argparse.ArgumentParser(description="清空 ReviewOps 工单表")
    parser.add_argument(
        "--all",
        action="store_true",
        help="清空全部工单（含冷启动基线）",
    )
    args = parser.parse_args()

    db = get_database()
    if args.all:
        count = db.clear_all_tickets()
        print(f"已清空全部 {count} 条工单记录。")
    else:
        count = db.clear_incremental_tickets()
        print(f"已删除增量工单 {count} 条；冷启动（CS-* 等）及已分析结果已保留。")
    print("请重启 Streamlit 应用以使页面状态同步。")


if __name__ == "__main__":
    main()
