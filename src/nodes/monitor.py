"""
监控节点：检测新工单
每次模拟巡检从 test_tickets_incremental.csv 随机读取工单，格式与 test_tickets.csv 一致。
"""

import os
import time
import random
from src.state import TicketState
from src.config import MonitorConfig
from src.services.database import get_database


def load_tickets_from_csv(csv_path: str, max_count: int = 50):
    """
    从 CSV 读取工单列表（表头：Ticket_ID, User_Message 等）。
    返回列表，每项为 dict：ticket_id, ticket_content, user_id, timestamp, urgency_level, category。
    """
    if not os.path.isfile(csv_path):
        return []
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        if "Ticket_ID" not in df.columns or "User_Message" not in df.columns:
            return []
        rows = []
        for _, row in df.iterrows():
            tid = str(row.get("Ticket_ID", "")).strip()
            if not tid:
                continue
            msg = str(row.get("User_Message", "")).strip()
            if not msg:
                continue
            rows.append({
                "ticket_id": tid,
                "ticket_content": msg,
                "user_id": f"ticket_{tid}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "urgency_level": None,
                "category": None,
            })
            if len(rows) >= max_count:
                break
        return rows
    except Exception:
        return []


def node_monitor(state: TicketState) -> TicketState:
    """
    节点 1: 监控新工单
    每次巡检从 test_tickets_incremental.csv 随机读取工单；若配置 USE_TICKETS_CSV 则也可从 test_tickets.csv 读取。
    仅当 ticket_id 不在 DB 且未在 processed_ids 中时才入库并进入后续节点。
    """
    db = get_database()
    processed_ids = set(state.get("processed_ids", []))
    new_tickets = []
    new_processed_ids = []

    # 优先使用增量工单文件（每次巡检从此文件随机抽取）
    inc_path = MonitorConfig.TICKETS_INCREMENTAL_CSV
    if not os.path.isabs(inc_path):
        inc_path = os.path.join(os.getcwd(), inc_path)

    main_path = MonitorConfig.TICKETS_CSV_PATH
    if not os.path.isabs(main_path):
        main_path = os.path.join(os.getcwd(), main_path)

    # 输入源：seed 模式强制使用指定 CSV；否则增量存在则用增量，否则用主 CSV
    if MonitorConfig.SEED_CSV:
        csv_path = os.path.join(os.getcwd(), MonitorConfig.SEED_CSV) if not os.path.isabs(MonitorConfig.SEED_CSV) else MonitorConfig.SEED_CSV
    else:
        csv_path = inc_path if os.path.isfile(inc_path) else main_path
    all_loaded = load_tickets_from_csv(csv_path, max_count=100)
    if not all_loaded:
        log_message = "⚠️ 工单输入源：未找到工单文件或文件为空"
        return {
            "incr_tickets": [],
            "processed_ids": [],
            "logs": [log_message],
        }

    # 随机打乱后依次取未处理工单，直到达到本批数量（seed 模式取全部）
    if not MonitorConfig.SEED_CSV:
        random.shuffle(all_loaded)
    need = len(all_loaded) if MonitorConfig.SEED_CSV else MonitorConfig.MIN_TICKETS_PER_BATCH
    for t in all_loaded:
        tid = t["ticket_id"]
        if db.exists(tid) or tid in processed_ids:
            continue
        db.add_ticket({
            "ticket_id": tid,
            "ticket_content": t["ticket_content"],
            "source": "test_tickets_incremental" if csv_path == inc_path else "test_tickets_csv",
            "timestamp": t["timestamp"],
            "risk_level": None,
            "urgency_level": t.get("urgency_level"),
            "category": t.get("category"),
            "status": "pending",
            "is_test": False,
        })
        new_tickets.append({
            "ticket_id": tid,
            "ticket_content": t["ticket_content"],
            "user_id": t["user_id"],
            "timestamp": t["timestamp"],
            "urgency_level": t.get("urgency_level"),
            "category": t.get("category"),
        })
        new_processed_ids.append(tid)
        if len(new_tickets) >= need:
            break

    if new_tickets:
        ticket_ids = [r["ticket_id"] for r in new_tickets]
        joined_ids = ", ".join(ticket_ids)
        log_message = f"📥 成功拉取 {len(new_tickets)} 条增量工单 | ID: {joined_ids} ✅ 已入库"
    else:
        log_message = "⚠️ 本次未拉取到新工单（可能已全部处理）"

    return {
        "incr_tickets": new_tickets,
        "processed_ids": new_processed_ids,
        "logs": [log_message],
    }
