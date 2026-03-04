"""
监控节点：检测新评论
支持两种输入源：MOCK_DATA_POOL（默认）或 test_tickets.csv（B2B 工单，需配置 MONITOR_USE_TICKETS_CSV=true）
"""

import os
import time
import random
from src.state import ReviewState
from src.config import MonitorConfig
from src.services.database import get_database


def load_tickets_from_csv(csv_path: str, max_count: int = 50):
    """
    从 test_tickets.csv 读取工单列表，供 Monitor 作为输入源。
    返回列表，每项为 dict：review_id（=Ticket_ID）, review_text（=User_Message）, user_id, timestamp, rating。
    调用方需自行按 db.exists(review_id) 与 processed_ids 过滤未处理工单。
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
                "rating": 2,  # B2B 工单默认视为潜在客诉，便于进入 Filter/RAG
            })
            if len(rows) >= max_count:
                break
        return rows
    except Exception:
        return []


# ==================== Mock 数据池 ====================
# 优化后的 Mock 数据，更符合 RAG 场景
# 包含正面、负面、中性评论，便于测试各种场景
MOCK_DATA_POOL = {
    # 负面评论池（rating 1-2）
    "negative": [
        # 案例 1：产品缺陷 - 电池续航虚标
        {
            "base_id": 101,
            "user_id": "user_001",
            "review_text": "标称续航45分钟，实际只能飞20多分钟，续航严重虚标，感觉被欺骗了。多次测试都是这样，明显是产品参数造假。",
            "rating": 1
        },
        # 案例 2：产品缺陷 - 云台开机自检失败
        {
            "base_id": 102,
            "user_id": "user_002",
            "review_text": "云台开机自检失败，画面一直抖动，重启后问题依然存在，怀疑是硬件质量问题。已经返修一次了，还是同样的问题。",
            "rating": 1
        },
        # 案例 3：用户误解 - 夜间飞行避障失效
        {
            "base_id": 103,
            "user_id": "user_003",
            "review_text": "夜间飞行时避障功能完全失效，差点撞墙，说明书上也没明确说明夜间不支持避障。",
            "rating": 2
        },
        # 案例 4：用户误解 - 运动模式下无法避障
        {
            "base_id": 104,
            "user_id": "user_004",
            "review_text": "运动模式下避障功能不工作，差点撞树。说明书里没有明确说明运动模式会关闭避障，这是设计缺陷还是我理解错了？",
            "rating": 2
        },
        # 案例 5：无关噪音 - 快递慢（应在 Filter 阶段被过滤，或归为 Other）
        {
            "base_id": 105,
            "user_id": "user_005",
            "review_text": "快递包装破损，等了很久才收到，物流体验很差。",
            "rating": 2
        }
    ],
    # 正面评论池（rating 4-5）
    "positive": [
        {
            "base_id": 201,
            "user_id": "user_101",
            "review_text": "产品非常满意！画质清晰，稳定性很好，续航也达到了宣传的标准。操作简单，新手也能快速上手。强烈推荐！",
            "rating": 5
        },
        {
            "base_id": 202,
            "user_id": "user_102",
            "review_text": "性价比很高，功能齐全，避障系统很灵敏，拍摄效果超出预期。客服态度也很好，有问题及时解决。",
            "rating": 5
        },
        {
            "base_id": 203,
            "user_id": "user_103",
            "review_text": "整体体验不错，画质清晰，云台稳定，电池续航基本符合预期。虽然有些小问题，但总体满意。",
            "rating": 4
        },
        {
            "base_id": 204,
            "user_id": "user_104",
            "review_text": "产品做工精细，飞行稳定，拍摄效果很好。说明书清晰易懂，上手很快。值得购买！",
            "rating": 4
        }
    ],
    # 中性评论池（rating 3）
    "neutral": [
        {
            "base_id": 301,
            "user_id": "user_201",
            "review_text": "产品还可以，画质一般，稳定性还行。价格适中，但功能没有特别突出的地方。",
            "rating": 3
        }
    ]
}


def node_monitor(state: ReviewState) -> ReviewState:
    """
    节点 1: 监控新评论
    输入源二选一（由配置决定）：
    - USE_TICKETS_CSV=True：从 test_tickets.csv 读取 B2B 工单（User_Message 作为评论内容）
    - 否则：从 MOCK_DATA_POOL 随机采样，带时间戳确保唯一性
    增量模拟：仅当 review_id 不在 DB 且未在 processed_ids 中时才入库。
    """
    db = get_database()
    processed_ids = set(state.get("processed_ids", []))
    new_reviews = []
    new_processed_ids = []
    csv_path = MonitorConfig.TICKETS_CSV_PATH
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(os.getcwd(), csv_path)

    # 输入源：从 test_tickets.csv 读取工单（B2B 场景）
    if MonitorConfig.USE_TICKETS_CSV:
        tickets = load_tickets_from_csv(csv_path, max_count=MonitorConfig.MIN_REVIEWS_PER_BATCH + 5)
        for t in tickets:
            rid = t["review_id"]
            if db.exists(rid) or rid in processed_ids:
                continue
            review_data = {
                "review_id": rid,
                "content": t["review_text"],
                "source": "test_tickets_csv",
                "rating": t["rating"],
                "timestamp": t["timestamp"],
                "risk_level": None,
            }
            db.add_review(review_data)
            new_reviews.append({
                "review_id": rid,
                "user_id": t["user_id"],
                "timestamp": t["timestamp"],
                "review_text": t["review_text"],
                "rating": t["rating"],
            })
            new_processed_ids.append(rid)
            if len(new_reviews) >= MonitorConfig.MIN_REVIEWS_PER_BATCH:
                break
        log_message = f"📅 工单输入源：{csv_path} | 本次新增 {len(new_reviews)} 条工单"
        if new_reviews:
            log_message += f" | ID: {[r['review_id'] for r in new_reviews]} | ✅ 已入库"
        return {
            "raw_reviews": new_reviews,
            "processed_ids": new_processed_ids,
            "logs": [log_message],
        }

    # 默认输入源：MOCK_DATA_POOL 随机采样
    current_timestamp_ns = time.time_ns()
    if MonitorConfig.MUST_HAVE_POSITIVE and MOCK_DATA_POOL["positive"]:
        positive_template = random.choice(MOCK_DATA_POOL["positive"])
        unique_suffix = f"{current_timestamp_ns}_{random.randint(1000, 9999)}"
        review_id = f"{positive_template['base_id']}_{unique_suffix}"
        
        # 检查数据库：只有不存在的数据才处理
        if not db.exists(review_id) and review_id not in processed_ids:
            # 准备评论数据
            review_data = {
                "review_id": review_id,
                "content": positive_template['review_text'],
                "source": "mock",
                "rating": positive_template['rating'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "risk_level": None  # 初始时风险等级未知，后续由 Filter 节点确定
            }
            
            # 入库
            db.add_review(review_data)
            
            # 构建返回给 Graph 的 review 对象
            review = {
                "review_id": review_id,
                "user_id": positive_template['user_id'],
                "timestamp": review_data["timestamp"],
                "review_text": positive_template['review_text'],
                "rating": positive_template['rating']
            }
            new_reviews.append(review)
            new_processed_ids.append(review_id)
    
    # 2. 再从负面或中性评论中随机选择至少 1 条（确保总数 >= 配置的最小值）
    remaining_needed = max(1, MonitorConfig.MIN_REVIEWS_PER_BATCH - len(new_reviews))
    all_other_templates = MOCK_DATA_POOL["negative"] + MOCK_DATA_POOL["neutral"]
    
    if all_other_templates:
        # 随机选择剩余需要的评论数量（可以多选几条增加随机性）
        additional_count = random.randint(remaining_needed, min(remaining_needed + 1, len(all_other_templates)))
        sampled_others = random.sample(all_other_templates, min(additional_count, len(all_other_templates)))
        
        for template in sampled_others:
            unique_suffix = f"{current_timestamp_ns}_{random.randint(1000, 9999)}"
            review_id = f"{template['base_id']}_{unique_suffix}"
            
            # 检查数据库：只有不存在的数据才处理
            if db.exists(review_id) or review_id in processed_ids:
                continue
            
            # 准备评论数据
            review_data = {
                "review_id": review_id,
                "content": template['review_text'],
                "source": "mock",
                "rating": template['rating'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "risk_level": None  # 初始时风险等级未知，后续由 Filter 节点确定
            }
            
            # 入库
            db.add_review(review_data)
            
            # 构建返回给 Graph 的 review 对象
            review = {
                "review_id": review_id,
                "user_id": template['user_id'],
                "timestamp": review_data["timestamp"],
                "review_text": template['review_text'],
                "rating": template['rating']
            }
            new_reviews.append(review)
            new_processed_ids.append(review_id)
    
    # 模拟时间推进感
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    positive_count = sum(1 for r in new_reviews if r.get('rating', 0) >= 4)
    negative_count = sum(1 for r in new_reviews if r.get('rating', 0) < 3)
    neutral_count = len(new_reviews) - positive_count - negative_count
    log_message = f"📅 模拟时间推进：{current_time_str} | 检测到 {len(new_reviews)} 条新增评论"
    log_message += f" (正面: {positive_count} 条, 负面: {negative_count} 条, 中性: {neutral_count} 条)"
    if new_reviews:
        log_message += f" | ID: {[r['review_id'] for r in new_reviews]}"
        log_message += f" | ✅ 已入库 {len(new_reviews)} 条新评论"
    
    return {
        "raw_reviews": new_reviews,
        "processed_ids": new_processed_ids,
        "logs": [log_message]
    }

