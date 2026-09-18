"""
监控节点：检测新工单
增量模式按 incremental_tickets.csv 的 Batch_ID 顺序逐批拉取（不随机）；冷启动数据见 cold_start_tickets.csv。
"""

import os
import time
from typing import Any, Dict, List, Optional

from src.state import TicketState
from src.config import MonitorConfig, resolve_repo_relative_path
from src.services.database import get_database
from src.utils import normalize_expected_ground_truth_id


def _ticket_dict_from_row(row: Any) -> Optional[Dict]:
    """从 CSV 行构造工单 dict（兼容 pandas Series / dict）。"""
    get = row.get if hasattr(row, "get") else lambda k, d=None: row[k] if k in row else d
    tid = str(get("Ticket_ID", "") or "").strip()
    if not tid:
        return None
    msg = str(get("User_Message", "") or "").strip()
    if not msg:
        return None
    out: Dict = {
        "ticket_id": tid,
        "ticket_content": msg,
        "user_id": f"ticket_{tid}",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "urgency_level": None,
        "category": None,
    }
    gt = normalize_expected_ground_truth_id(get("Expected_Ground_Truth_ID", None))
    if gt:
        out["expected_ground_truth_id"] = gt
    tc = get("True_Category", None)
    if tc is not None and str(tc).strip() and str(tc).strip().lower() != "nan":
        out["true_category"] = str(tc).strip()
    et = get("Expected_Tool", None)
    if et is not None and str(et).strip() and str(et).strip().lower() != "nan":
        out["expected_tool"] = str(et).strip()
    return out


def _max_batch_id_from_csv(csv_path: str) -> int:
    if not os.path.isfile(csv_path):
        return 1
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if "Batch_ID" not in df.columns:
            return 1
        m = pd.to_numeric(df["Batch_ID"], errors="coerce").max()
        return int(m) if m == m and m is not None else 1
    except Exception:
        return 1


def load_incremental_batch(csv_path: str, batch_id: int) -> List[dict]:
    """
    读取增量 CSV 中指定 Batch_ID 的全部工单（行顺序与文件一致，不随机）。
    若无 Batch_ID 列则退化为整表仅 batch_id==1 时返回全部行。
    """
    if not os.path.isfile(csv_path):
        return []
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if "Ticket_ID" not in df.columns or "User_Message" not in df.columns:
            return []
        if "Batch_ID" not in df.columns:
            if int(batch_id) != 1:
                return []
            rows = []
            for _, row in df.iterrows():
                t = _ticket_dict_from_row(row)
                if t:
                    rows.append(t)
            return rows
        bids = pd.to_numeric(df["Batch_ID"], errors="coerce")
        sub = df[bids == int(batch_id)]
        rows = []
        for _, row in sub.iterrows():
            t = _ticket_dict_from_row(row)
            if t:
                rows.append(t)
        return rows
    except Exception:
        return []


def load_tickets_from_csv(csv_path: str, max_count: int = 50) -> List[dict]:
    """
    从 CSV 读取工单列表（表头：Ticket_ID, User_Message；可选 Batch_ID, Expected_Ground_Truth_ID 等）。
    用于 SEED 模式或非增量主文件；按文件行序，至多 max_count 条。
    """
    if not os.path.isfile(csv_path):
        return []
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if "Ticket_ID" not in df.columns or "User_Message" not in df.columns:
            return []
        rows: List[dict] = []
        for _, row in df.iterrows():
            t = _ticket_dict_from_row(row)
            if t:
                rows.append(t)
            if len(rows) >= max_count:
                break
        return rows
    except Exception:
        return []


def _pending_cold_incr_tickets(main_path: str, db) -> List[dict]:
    """
    冷启动 CSV 中已在库内、且仍为 pending 且无 RAG 结论的工单。
    在存在 incremental_tickets.csv 时，增量批次本身不含 CS-*，需前置并入本批流水线。
    """
    if not main_path or not os.path.isfile(main_path):
        return []
    out: List[dict] = []
    for t in load_tickets_from_csv(main_path, max_count=500):
        tid = (t.get("ticket_id") or "").strip()
        if tid and db.exists(tid) and db.is_pending_needs_analysis(tid):
            out.append(t)
    return out


def _incr_payload_from_ticket_dict(t: Dict) -> Dict:
    """与 monitor 写入 incr_tickets 的结构一致。"""
    return {
        "ticket_id": t["ticket_id"],
        "ticket_content": t["ticket_content"],
        "user_id": t["user_id"],
        "timestamp": t["timestamp"],
        "urgency_level": t.get("urgency_level"),
        "category": t.get("category"),
        **(
            {"expected_ground_truth_id": t["expected_ground_truth_id"]}
            if t.get("expected_ground_truth_id")
            else {}
        ),
        **({"true_category": t["true_category"]} if t.get("true_category") else {}),
        **({"expected_tool": t["expected_tool"]} if t.get("expected_tool") else {}),
    }


def node_monitor(state: TicketState) -> TicketState:
    """
    节点 1: 监控新工单
    - SEED_CSV：从指定 CSV 顺序读取（全量/上限由 load_tickets_from_csv 控制）。
    - 增量：从 TICKETS_INCREMENTAL_CSV 按 monitor_next_batch_id 读取整批，不随机；批次号在状态中轮转。
    """
    db = get_database()
    new_tickets: List[dict] = []
    new_processed_ids: List[str] = []

    inc_path = resolve_repo_relative_path(MonitorConfig.TICKETS_INCREMENTAL_CSV)
    main_path = resolve_repo_relative_path(MonitorConfig.TICKETS_CSV_PATH)

    if MonitorConfig.SEED_CSV:
        csv_path = resolve_repo_relative_path(MonitorConfig.SEED_CSV)
        all_loaded = load_tickets_from_csv(csv_path, max_count=500)
        use_incremental_batch = False
        current_batch_id: Optional[int] = None
        next_batch_id: Optional[int] = None
    else:
        csv_path = inc_path if os.path.isfile(inc_path) else main_path
        use_incremental_batch = os.path.isfile(inc_path) and csv_path == inc_path
        cold_pending: List[dict] = []
        if use_incremental_batch:
            bmax = _max_batch_id_from_csv(inc_path)
            current_batch_id = int(state.get("monitor_next_batch_id") or 1)
            if current_batch_id < 1:
                current_batch_id = 1
            if current_batch_id > bmax:
                current_batch_id = 1
            inc_part = load_incremental_batch(inc_path, current_batch_id)
            cold_pending = _pending_cold_incr_tickets(main_path, db)
            all_loaded = cold_pending + inc_part
            next_batch_id = current_batch_id + 1 if current_batch_id < bmax else 1
        else:
            all_loaded = load_tickets_from_csv(csv_path, max_count=100)
            current_batch_id = None
            next_batch_id = None

    if not all_loaded:
        batch_note = (
            f" | 批次 Batch_ID={current_batch_id}"
            if use_incremental_batch and current_batch_id is not None
            else ""
        )
        src_note = (
            f"incremental={inc_path}（exists={os.path.isfile(inc_path)}）, "
            f"main={main_path}（exists={os.path.isfile(main_path)}）"
        )
        log_message = (
            "⚠️ 工单输入源无数据"
            f"{batch_note} | {src_note} | 原因：未找到工单文件、当前批次无数据或文件为空"
        )
        out: dict = {
            "incr_tickets": [],
            "processed_ids": [],
            "logs": [log_message],
        }
        if use_incremental_batch and next_batch_id is not None:
            out["monitor_next_batch_id"] = next_batch_id
        return out

    if MonitorConfig.SEED_CSV:
        need = len(all_loaded)
    elif use_incremental_batch:
        need = len(all_loaded)
    else:
        need = min(len(all_loaded), MonitorConfig.MIN_TICKETS_PER_BATCH)

    source_tag = (
        "incremental_tickets_csv"
        if use_incremental_batch
        else ("seed_csv" if MonitorConfig.SEED_CSV else "tickets_csv")
    )

    for t in all_loaded:
        tid = t["ticket_id"]
        if db.exists(tid):
            # 已在库：仅「仍待 RAG/行动」的冷启动单可再次进入本批流水线（避免增量模式下 CS-* 永远卡住）
            if db.is_pending_needs_analysis(tid):
                new_tickets.append(_incr_payload_from_ticket_dict(t))
                new_processed_ids.append(tid)
                if len(new_tickets) >= need:
                    break
            continue
        db.add_ticket({
            "ticket_id": tid,
            "ticket_content": t["ticket_content"],
            "source": source_tag,
            "timestamp": t["timestamp"],
            "risk_level": None,
            "urgency_level": t.get("urgency_level"),
            "category": t.get("category"),
            "status": "pending",
            "is_test": False,
        })
        new_tickets.append(_incr_payload_from_ticket_dict(t))
        new_processed_ids.append(tid)
        if len(new_tickets) >= need:
            break

    if new_tickets:
        ticket_ids = [r["ticket_id"] for r in new_tickets]
        joined_ids = ", ".join(ticket_ids)
        batch_note = (
            f" | 批次 Batch_ID={current_batch_id}"
            if use_incremental_batch and current_batch_id is not None
            else ""
        )
        cold_note = ""
        if use_incremental_batch and cold_pending:
            cold_note = f" | 含冷启动待分析 {len(cold_pending)} 条"
        log_message = (
            f"📥 成功拉取 {len(new_tickets)} 条工单{batch_note}{cold_note} | "
            f"输入源: {os.path.basename(csv_path)} | ID: {joined_ids} ✅ 已入库"
        )
    else:
        batch_note = (
            f" | 批次 Batch_ID={current_batch_id}"
            if use_incremental_batch and current_batch_id is not None
            else ""
        )
        src_name = os.path.basename(csv_path) if csv_path else "（未知）"
        total_loaded = len(all_loaded) if all_loaded else 0
        log_message = (
            f"⚠️ 本次未拉取到新工单{batch_note} | 输入源: {src_name} | "
            f"本批读取到 {total_loaded} 条，但均已在库中或无需再次分析"
        )

    result: dict = {
        "incr_tickets": new_tickets,
        "processed_ids": new_processed_ids,
        "logs": [log_message],
    }
    if use_incremental_batch and next_batch_id is not None:
        result["monitor_next_batch_id"] = next_batch_id

    return result
