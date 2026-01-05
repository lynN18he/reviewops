"""
智能巡检控制台 Tab
包含工作流触发、Metrics 渲染、Hero+History 列表等所有逻辑
"""

import streamlit as st
import pandas as pd
import time
import datetime
from src.ui.cards import render_incident_card
from src.graph import graph_app


def render_dashboard_metrics(calculate_metrics, generate_ai_brief):
    """
    渲染顶部 Dashboard（数据概览 + AI 简报）
    
    Args:
        calculate_metrics: 计算指标的函数
        generate_ai_brief: 生成 AI 简报的函数
    """
    # 使用容器统一模块大小
    with st.container():
        st.markdown("## 📈 数据概览")
        
        # 计算指标 - 基于 session_state.all_reviews（SSOT）
        all_reviews = st.session_state.get('all_reviews', [])
        
        # 确保 all_reviews 是列表且不为空
        if not all_reviews:
            all_reviews_df = pd.DataFrame(columns=['rating'])
        else:
            # 创建 DataFrame，确保所有评论都被包含
            all_reviews_df = pd.DataFrame(all_reviews)
            
            # 调试：检查数据
            if len(all_reviews_df) > 0:
                # 确保 rating 列存在且为数值类型
                if 'rating' not in all_reviews_df.columns:
                    all_reviews_df['rating'] = 0
                else:
                    # 确保 rating 是数值类型，处理可能的字符串或其他类型
                    all_reviews_df['rating'] = pd.to_numeric(all_reviews_df['rating'], errors='coerce').fillna(0)
                
                # 去重：基于 review_id 去重，避免重复计算
                if 'review_id' in all_reviews_df.columns:
                    all_reviews_df = all_reviews_df.drop_duplicates(subset=['review_id'], keep='last')
        
        # 计算指标（强制重新计算，不使用缓存）
        # 重要：每次页面渲染时都重新计算，确保使用最新数据
        total_reviews, avg_rating, negative_ratio = calculate_metrics(all_reviews_df)
        
        # 获取上次保存的值（用于计算增量）
        prev_total = st.session_state.get('prev_total_reviews', 0)
        prev_avg = st.session_state.get('prev_avg_rating', 0.0)
        prev_negative_ratio = st.session_state.get('prev_negative_ratio', 0.0)
        
        # 计算 delta 值（只有当有历史数据且总数变化时才计算）
        if prev_total > 0 and prev_total != total_reviews:
            # 总数发生变化，说明有新数据，计算增量
            avg_delta = avg_rating - prev_avg
            negative_delta = negative_ratio - prev_negative_ratio
        elif prev_total == 0:
            # 首次运行，没有历史数据
            avg_delta = None
            negative_delta = None
        else:
            # 总数未变化，但可能数据有更新，仍然计算增量
            avg_delta = avg_rating - prev_avg if prev_avg > 0 else None
            negative_delta = negative_ratio - prev_negative_ratio if prev_negative_ratio > 0 else None
        
        # 保存当前值作为下次的基准（每次都要更新，确保下次计算时使用最新值）
        # 重要：必须在每次渲染时更新，确保下次计算时使用最新值
        st.session_state['prev_total_reviews'] = total_reviews
        st.session_state['prev_avg_rating'] = avg_rating
        st.session_state['prev_negative_ratio'] = negative_ratio
        
        # 三个指标卡片
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 动态显示增量（基于 last_run_increment）
            delta_text = f"本次新增 {st.session_state.last_run_increment} 条" if st.session_state.last_run_increment > 0 else None
            st.metric(
                label="📝 总评论数",
                value=f"{total_reviews}",
                delta=delta_text,
                delta_color="normal"
            )
        
        with col2:
            # 显示平均评分，带增量变化
            delta_text_avg = f"{avg_delta:+.1f}" if avg_delta is not None and abs(avg_delta) > 0.01 else None
            st.metric(
                label="⭐ 平均评分",
                value=f"{avg_rating:.1f}",
                delta=delta_text_avg,
                delta_color="normal" if avg_delta is None or avg_delta >= 0 else "inverse"
            )
        
        with col3:
            # 显示负面评价占比，带增量变化
            delta_text_negative = f"{negative_delta:+.1f}%" if negative_delta is not None and abs(negative_delta) > 0.01 else None
            st.metric(
                label="😔 负面评价占比",
                value=f"{negative_ratio:.1f}%",
                delta=delta_text_negative,
                delta_color="inverse" if negative_delta is None or negative_delta <= 0 else "normal"
            )

    # AI 每日简报 - 使用容器统一大小
    with st.container():
        with st.expander("🤖 **AI 每日简报** - 点击展开", expanded=True):
            ai_brief = generate_ai_brief(all_reviews_df, negative_ratio)
            st.markdown(ai_brief)


def render_tab(api_key, calculate_metrics, generate_ai_brief):
    """
    渲染智能巡检控制台 Tab
    
    Args:
        api_key: DashScope API Key
        calculate_metrics: 计算指标的函数
        generate_ai_brief: 生成 AI 简报的函数
    """
    st.markdown("### ⚡ 智能工作流")
    st.caption("基于 LangGraph 的自动化巡检系统，自动监控、筛选、分析和生成行动建议")
    
    # 优化按钮布局：左侧按钮，右侧信息
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        workflow_button = st.button("⚡ 运行智能工作流", type="primary", use_container_width=True, key="workflow_btn_auto")
    with col_info:
        # 垂直居中显示上次巡检时间，使用灰色小字
        last_run_time = st.session_state.get('last_run_time', '从未')
        st.markdown(
            f"<div style='padding-top: 10px; color: #6b7280; font-size: 0.9rem;'>🕒 上次自动巡检：{last_run_time}</div>",
            unsafe_allow_html=True
        )
    
    # ==================== 智能工作流执行 ====================
    # Trigger (按钮部分): 只负责运行 Graph，将结果追加到 st.session_state.incident_history
    # 之后立刻调用 st.rerun()，不在这里写任何 st.markdown 或 UI 渲染代码！
    if workflow_button:
        # 检查 API Key
        if not api_key:
            st.error("❌ 请先在侧边栏配置 DashScope API Key")
            st.stop()
        
        try:
            # 记录本次巡检开始时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 初始化状态（增量巡检：保留已处理的ID）
            initial_state = {
                "raw_reviews": [],
                "critical_reviews": [],
                "rag_analysis_results": [],
                "action_plans": [],
                "logs": [],
                "processed_ids": st.session_state.get('processed_ids', [])  # 保留历史已处理ID
            }
            
            # 清空本次巡检的结果（只保留历史数据）
            st.session_state.incremental_rag_results = []
            st.session_state.incremental_action_plans = []
            
            # 使用 st.status 展示实时日志（恢复运行过程显示）
            with st.status("🔄 工作流运行中...", expanded=True) as status:
                st.write("🚀 启动智能工作流...")
                
                # 数据同步：使用 stream() 监听流式输出
                final_state = initial_state.copy()
                for event in graph_app.stream(initial_state):
                    # 遍历每个节点的输出
                    for node_name, node_output in event.items():
                        # 合并状态
                        if isinstance(node_output, dict):
                            final_state.update(node_output)
                        
                        # 检测 node_monitor 产出的 raw_reviews
                        if node_name == "monitor" and isinstance(node_output, dict) and "raw_reviews" in node_output:
                            new_reviews = node_output.get("raw_reviews", [])
                            if new_reviews:
                                # 数据同步：立即追加到 session_state.all_reviews（增量累加）
                                st.session_state.all_reviews.extend(new_reviews)
                                st.session_state.last_run_increment = len(new_reviews)
                                st.write(f"📥 数据同步：已添加 {len(new_reviews)} 条新评论到全局状态（累计：{len(st.session_state.all_reviews)} 条）")
                        
                        # 检测 node_rag_analysis 产出的 rag_analysis_results（本次巡检的新增结果）
                        if node_name == "rag_analysis" and isinstance(node_output, dict) and "rag_analysis_results" in node_output:
                            rag_results = node_output.get("rag_analysis_results", [])
                            if rag_results:
                                # 保存本次巡检的RAG结果（增量）
                                st.session_state.incremental_rag_results.extend(rag_results)
                                # 同时更新全局最新结果（用于兼容性）
                                st.session_state.latest_rag_results = rag_results
                                st.write(f"📄 本次巡检发现 {len(rag_results)} 条RAG归因结果（累计：{len(st.session_state.incremental_rag_results)} 条）")
                        
                        # 检测 node_action_gen 产出的 action_plans（本次巡检的新增结果）
                        if node_name == "action_gen" and isinstance(node_output, dict) and "action_plans" in node_output:
                            action_plans = node_output.get("action_plans", [])
                            if action_plans:
                                # 保存本次巡检的行动建议（增量）
                                st.session_state.incremental_action_plans = action_plans
                                st.write(f"💡 本次巡检生成 {len(action_plans)} 条行动建议")
                        
                        # 更新已处理的ID集合（用于幂等性）
                        if isinstance(node_output, dict) and "processed_ids" in node_output:
                            processed_ids = node_output.get("processed_ids", [])
                            if processed_ids:
                                existing_ids = set(st.session_state.get('processed_ids', []))
                                new_ids = set(processed_ids)
                                st.session_state['processed_ids'] = list(existing_ids | new_ids)
                        
                        # 实时显示日志
                        if isinstance(node_output, dict) and "logs" in node_output:
                            logs = node_output.get("logs", [])
                            for log in logs:
                                st.write(log)
                                time.sleep(0.2)  # 模拟实时更新
                
                status.update(label="✅ 工作流执行完成", state="complete")
                st.write("⏳ 正在刷新页面以更新统计数据...")
                time.sleep(1)
            
            # 更新上次巡检时间
            st.session_state.last_run_time = current_time
            
            # ==================== 数据处理：保存到历史记录 ====================
            result = final_state
            rag_results = result.get("rag_analysis_results", [])
            action_plans = result.get("action_plans", [])
            
            # 生成批次记录，插入到历史记录头部（最新的在最上面）
            batch_record = {
                'time': current_time,
                'rag_results': rag_results,
                'actions': action_plans,
                'new_reviews_count': len(final_state.get("raw_reviews", [])),
                'critical_count': len(result.get("critical_reviews", []))
            }
            
            # 插入到头部（Prepend）
            st.session_state.incident_history.insert(0, batch_record)
            
            # 存储结果到 session_state（用于兼容性）
            st.session_state['workflow_result'] = result
            st.session_state['workflow_completed'] = True
            st.session_state['need_refresh'] = True
            
            # 立即调用 st.rerun() 触发页面刷新，让渲染区域显示新数据
            st.rerun()
            
        except ImportError as e:
            st.error(f"❌ 无法导入工作流模块: {e}")
            st.info("💡 请确保 `src/graph.py` 文件存在且已正确配置")
        except Exception as e:
            st.error(f"❌ 工作流执行失败: {e}")
            st.exception(e)
    
    # ==================== 持久化渲染区域：实时风险动态流 ====================
    incident_history = st.session_state.get('incident_history', [])
    
    if incident_history:
        st.markdown("---")
        
        # ==================== Part A: 最新动态 (Hero Section) ====================
        latest_batch = incident_history[0]
        latest_rag_results = latest_batch.get('rag_results', [])
        latest_actions = latest_batch.get('actions', [])
        latest_time = latest_batch.get('time', '未知时间')
        latest_new_reviews = latest_batch.get('new_reviews_count', 0)
        
        # 检查是否有 P0 级风险（High 优先级的 Action 或产品缺陷的 RAG）
        has_p0_risk = False
        if latest_actions:
            has_p0_risk = any(action.get('priority') == 'High' for action in latest_actions)
        if not has_p0_risk and latest_rag_results:
            has_p0_risk = any('产品缺陷' in rag.get('conclusion', '') for rag in latest_rag_results)
        
        # 显示标题和统计
        col_title, col_stats = st.columns([2, 1])
        with col_title:
            st.markdown("### 🚨 本次巡检发现 (Latest)")
        with col_stats:
            st.caption(f"📅 {latest_time} · 新增 {latest_new_reviews} 条评论")
        
        # 如果有 P0 级风险，使用 st.error 容器包裹增强警示感
        if has_p0_risk:
            st.error("⚠️ **检测到高风险问题，请立即处理！**")
        
        # Case-Based 成组渲染：通过 review_id 匹配 RAG 和 Action
        if latest_rag_results:
            # 创建 action 字典，以 review_id 为 key，方便查找
            # 支持完整匹配和部分匹配（处理可能的 ID 格式差异）
            action_dict = {}
            for action in latest_actions:
                review_id = action.get('review_id')
                if review_id:
                    action_dict[review_id] = action
                    # 也支持 base_id 匹配（如果 review_id 包含下划线）
                    if '_' in str(review_id):
                        base_id = str(review_id).split('_')[0]
                        if base_id not in action_dict:
                            action_dict[base_id] = action
            
            for item_idx, rag_result in enumerate(latest_rag_results):
                # 通过 review_id 匹配对应的 Action
                review_id = rag_result.get("review_id")
                action_item = None
                
                if review_id:
                    # 优先完整匹配
                    action_item = action_dict.get(review_id)
                    # 如果完整匹配失败，尝试 base_id 匹配
                    if not action_item and '_' in str(review_id):
                        base_id = str(review_id).split('_')[0]
                        action_item = action_dict.get(base_id)
                
                # 如果还是没匹配到，尝试按索引匹配（兜底方案）
                if not action_item and item_idx < len(latest_actions):
                    action_item = latest_actions[item_idx]
                
                # 渲染完整的 Case（RAG + Action 成对）
                render_incident_card(rag_result, action_item, batch_idx=0, item_idx=item_idx)
                # Case 之间的分隔
                if item_idx < len(latest_rag_results) - 1:
                    st.markdown("")  # 空白间隔，避免文字粘连
        
        # ==================== Part B: 历史回溯 (Scrollable Container) ====================
        history_batches = incident_history[1:] if len(incident_history) > 1 else []
        
        if history_batches:
            st.divider()  # 分割线，清晰区分最新和历史
            st.markdown("#### 📜 历史巡检记录")
            
            # 使用固定高度的滚动容器
            with st.container(height=500, border=False):
                for batch_idx, batch in enumerate(history_batches, start=1):
                    batch_time = batch.get('time', '未知时间')
                    rag_results = batch.get('rag_results', [])
                    actions = batch.get('actions', [])
                    new_reviews_count = batch.get('new_reviews_count', 0)
                    
                    # 使用 expander 折叠历史批次
                    with st.expander(f"📅 巡检批次: {batch_time} (新增 {new_reviews_count} 条评论)", expanded=False):
                        # Case-Based 成组渲染：通过 review_id 匹配 RAG 和 Action
                        if rag_results:
                            # 创建 action 字典，以 review_id 为 key，方便查找
                            # 支持完整匹配和部分匹配（处理可能的 ID 格式差异）
                            action_dict = {}
                            for action in actions:
                                review_id = action.get('review_id')
                                if review_id:
                                    action_dict[review_id] = action
                                    # 也支持 base_id 匹配（如果 review_id 包含下划线）
                                    if '_' in str(review_id):
                                        base_id = str(review_id).split('_')[0]
                                        if base_id not in action_dict:
                                            action_dict[base_id] = action
                            
                            for item_idx, rag_result in enumerate(rag_results):
                                # 通过 review_id 匹配对应的 Action
                                review_id = rag_result.get("review_id")
                                action_item = None
                                
                                if review_id:
                                    # 优先完整匹配
                                    action_item = action_dict.get(review_id)
                                    # 如果完整匹配失败，尝试 base_id 匹配
                                    if not action_item and '_' in str(review_id):
                                        base_id = str(review_id).split('_')[0]
                                        action_item = action_dict.get(base_id)
                                
                                # 如果还是没匹配到，尝试按索引匹配（兜底方案）
                                if not action_item and item_idx < len(actions):
                                    action_item = actions[item_idx]
                                
                                # 渲染完整的 Case（RAG + Action 成对）
                                render_incident_card(rag_result, action_item, batch_idx=batch_idx, item_idx=item_idx)
                                # Case 之间的分隔
                                if item_idx < len(rag_results) - 1:
                                    st.markdown("")  # 空白间隔，避免文字粘连
                        
                        # 批次之间的分隔
                        if batch_idx < len(history_batches):
                            st.markdown("")
    else:
        # 如果工作流未运行，显示提示
        st.info("👆 点击上方「运行智能工作流」按钮，开始首次增量巡检")

