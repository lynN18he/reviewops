"""
UI 状态管理模块
集中管理 Streamlit session_state 的初始化
"""

import streamlit as st
import pandas as pd
import time


def init_session_state(reviews_df: pd.DataFrame, calculate_metrics):
    """
    初始化 session_state
    
    Args:
        reviews_df: 初始评论数据 DataFrame
        calculate_metrics: 计算指标的函数
    """
    # 检查并初始化 all_reviews（Single Source of Truth）
    if 'all_reviews' not in st.session_state:
        # 初始化：从 CSV 文件加载历史数据
        st.session_state.all_reviews = reviews_df.to_dict('records')
        st.session_state.last_run_increment = 0
        # 初始化指标基准值（用于计算增量）
        if len(st.session_state.all_reviews) > 0:
            init_df = pd.DataFrame(st.session_state.all_reviews)
            if 'rating' in init_df.columns:
                init_df['rating'] = pd.to_numeric(init_df['rating'], errors='coerce').fillna(0)
                init_total, init_avg, init_negative = calculate_metrics(init_df)
                st.session_state['prev_total_reviews'] = init_total
                st.session_state['prev_avg_rating'] = init_avg
                st.session_state['prev_negative_ratio'] = init_negative
            else:
                st.session_state['prev_total_reviews'] = 0
                st.session_state['prev_avg_rating'] = 0.0
                st.session_state['prev_negative_ratio'] = 0.0
        else:
            st.session_state['prev_total_reviews'] = 0
            st.session_state['prev_avg_rating'] = 0.0
            st.session_state['prev_negative_ratio'] = 0.0

    # 初始化 RAG 分析结果存储
    if 'latest_rag_results' not in st.session_state:
        st.session_state.latest_rag_results = []

    # 初始化增量巡检相关状态
    if 'last_run_time' not in st.session_state:
        st.session_state.last_run_time = None
    if 'incremental_rag_results' not in st.session_state:
        st.session_state.incremental_rag_results = []  # 存储本次巡检的RAG结果

    # 初始化历史巡检记录（实时风险动态流）
    if 'incident_history' not in st.session_state:
        st.session_state.incident_history = []  # 存储所有历史巡检批次

    # 检查是否需要刷新页面以更新数据概览
    if st.session_state.get('need_refresh', False):
        st.session_state['need_refresh'] = False
        # 延迟刷新，让用户有时间看清工作流完成提示
        time.sleep(2)
        st.rerun()

