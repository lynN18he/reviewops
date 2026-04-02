"""
UI 状态管理模块
集中管理 Streamlit session_state 的初始化
"""

import streamlit as st
import pandas as pd
import time
from src.services.database import get_database


def init_session_state(tickets_df: pd.DataFrame, calculate_metrics):
    """
    初始化 session_state（工单为 SSOT）

    Args:
        tickets_df: 工单数据 DataFrame（含 ticket_id, ticket_content, user_id, timestamp, urgency_level, category）
        calculate_metrics: 计算指标函数，返回 get_dashboard_metrics() 的 8 元组
    """
    # 检查并初始化 all_tickets（与 Graph 兼容：ticket_id, ticket_content, user_id, timestamp, urgency_level, category）
    if 'all_tickets' not in st.session_state:
        db = get_database()
        db_tickets = db.get_all_tickets()
        if db_tickets:
            st.session_state.all_tickets = [
                {
                    'ticket_id': r.get('ticket_id'),
                    'user_id': f"ticket_{r.get('ticket_id', '')}" if isinstance(r.get('ticket_id'), str) and not (r.get('ticket_id') or '').startswith('ticket_') else f"user_{str(r.get('ticket_id', ''))[:20]}",
                    'timestamp': r.get('created_at', ''),
                    'ticket_content': r.get('ticket_content', ''),
                    'urgency_level': r.get('urgency_level'),
                    'category': r.get('category'),
                }
                for r in db_tickets
            ]
        else:
            st.session_state.all_tickets = tickets_df.to_dict('records') if not tickets_df.empty else []
        st.session_state.last_run_increment = 0
        if len(st.session_state.all_tickets) > 0:
            init_df = pd.DataFrame(st.session_state.all_tickets)
            _m = calculate_metrics(init_df, None)
            if not isinstance(_m, tuple) or len(_m) < 4:
                raise ValueError(
                    "calculate_metrics 须至少返回 4 项（建议 8 项含分桶条数）。"
                )
            init_total, init_ai, init_esc, init_bug = _m[0], _m[1], _m[2], _m[3]
            st.session_state['prev_total_tickets'] = init_total
            st.session_state['prev_ai_resolution_rate'] = init_ai
            st.session_state['prev_human_escalation_rate'] = init_esc
            st.session_state['prev_bug_ident_rate'] = init_bug
        else:
            st.session_state['prev_total_tickets'] = 0
            st.session_state['prev_ai_resolution_rate'] = 0.0
            st.session_state['prev_human_escalation_rate'] = 0.0
            st.session_state['prev_bug_ident_rate'] = 0.0

    # 初始化 RAG 分析结果存储
    if 'latest_rag_results' not in st.session_state:
        st.session_state.latest_rag_results = []

    # 初始化增量巡检相关状态
    if 'last_run_time' not in st.session_state:
        st.session_state.last_run_time = None
    if 'incremental_rag_results' not in st.session_state:
        st.session_state.incremental_rag_results = []  # 存储本次巡检的RAG结果

    # 初始化历史巡检记录（实时风险动态流，Hero 区域使用 session_state）
    if 'incident_history' not in st.session_state:
        st.session_state.incident_history = []
    # 一次性清理：迁移到 B2B 工单后清空旧批次，避免展示历史中的「评论/无人机」残留
    if not st.session_state.get('incident_history_tickets_migrated', False):
        st.session_state.incident_history = []
        st.session_state['incident_history_tickets_migrated'] = True

    # 工作台批次流水账（不覆盖，向下堆叠）
    if 'run_history' not in st.session_state:
        st.session_state.run_history = []

    # 晨会简报（防丢失）
    if 'daily_briefing' not in st.session_state:
        st.session_state.daily_briefing = ""

    # 检查是否需要刷新页面以更新数据概览
    if st.session_state.get('need_refresh', False):
        st.session_state['need_refresh'] = False
        # 延迟刷新，让用户有时间看清工作流完成提示
        time.sleep(2)
        st.rerun()

