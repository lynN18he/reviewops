"""
监控节点：检测新工单
每次模拟巡检从 test_tickets_incremental.csv 随机读取工单，格式与 test_tickets.csv 一致。
"""

import os
import time
import random
from src.state import ReviewState
from src.config import MonitorConfig
from src.services.database import get_database


def load_tickets_from_csv(csv_path: str, max_count: int = 50):
    """
    从 CSV 读取工单列表（表头：Ticket_ID, User_Message 等）。
    返回列表，每项为 dict：review_id, review_text, user_id, timestamp, urgency_level, category。
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
                "review_id": tid,
                "review_text": msg,
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


def node_monitor(state: ReviewState) -> ReviewState:
    """
    节点 1: 监控新工单
    每次巡检从 test_tickets_incremental.csv 随机读取工单；若配置 USE_TICKETS_CSV 则也可从 test_tickets.csv 读取。
    仅当 review_id 不在 DB 且未在 processed_ids 中时才入库并进入后续节点。
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

    # 输入源：增量文件存在则从中随机读取；否则从主 CSV 读取（与原有逻辑一致）
    csv_path = inc_path if os.path.isfile(inc_path) else main_path
    all_loaded = load_tickets_from_csv(csv_path, max_count=100)
    if not all_loaded:
        log_message = "⚠️ 工单输入源：未找到工单文件或文件为空"
        return {
            "raw_reviews": [],
            "processed_ids": [],
            "logs": [log_message],
        }

    # 随机打乱后依次取未处理工单，直到达到本批数量
    random.shuffle(all_loaded)
    need = MonitorConfig.MIN_TICKETS_PER_BATCH
    for t in all_loaded:
        rid = t["review_id"]
        if db.exists(rid) or rid in processed_ids:
            continue
        review_data = {
            "review_id": rid,
            "content": t["review_text"],
            "source": "test_tickets_incremental" if csv_path == inc_path else "test_tickets_csv",
            "timestamp": t["timestamp"],
            "risk_level": None,
            "urgency_level": t.get("urgency_level"),
            "category": t.get("category"),
        }
        db.add_review(review_data)
        new_tickets.append({
            "review_id": rid,
            "user_id": t["user_id"],
            "timestamp": t["timestamp"],
            "review_text": t["review_text"],
            "urgency_level": t.get("urgency_level"),
            "category": t.get("category"),
        })
        new_processed_ids.append(rid)
        if len(new_tickets) >= need:
            break

    log_message = f"📅 工单输入源：{csv_path} | 本次新增 {len(new_tickets)} 条工单"
    if new_tickets:
        log_message += f" | ID: {[r['review_id'] for r in new_tickets]} | ✅ 已入库"

    return {
        "raw_reviews": new_tickets,
        "processed_ids": new_processed_ids,
        "logs": [log_message],
    }
