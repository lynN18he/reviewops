"""
智能巡检控制台 Tab
包含工作流触发、Metrics 渲染、Hero+History 列表等所有逻辑
"""

import streamlit as st
import pandas as pd
import time
import datetime
from collections import defaultdict
from src.ui.cards import render_incident_card
from src.graph import graph_app
from src.services.database import get_database


def render_dashboard_metrics(calculate_metrics, generate_ai_brief):
    """
    渲染顶部 Dashboard：SaaS 运维北极星指标 + 技术简报
    """
    with st.container():
        st.markdown("## 📈 数据概览")
        all_reviews = st.session_state.get('all_reviews', [])
        if not all_reviews:
            all_reviews_df = pd.DataFrame()
        else:
            all_reviews_df = pd.DataFrame(all_reviews)
            if 'review_id' in all_reviews_df.columns:
                all_reviews_df = all_reviews_df.drop_duplicates(subset=['review_id'], keep='last')
        total_tickets, l1_rate, p0_rate = calculate_metrics(all_reviews_df, st.session_state)
        prev_total = st.session_state.get('prev_total_tickets', 0)
        prev_l1 = st.session_state.get('prev_l1_rate', 0.0)
        prev_p0 = st.session_state.get('prev_p0_rate', 0.0)
        st.session_state['prev_total_tickets'] = total_tickets
        st.session_state['prev_l1_rate'] = l1_rate
        st.session_state['prev_p0_rate'] = p0_rate
        delta_total = f"本次新增 {st.session_state.get('last_run_increment', 0)} 条工单" if st.session_state.get('last_run_increment', 0) > 0 else None
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="📋 今日工单总数", value=f"{total_tickets}", delta=delta_total, delta_color="normal")
        with col2:
            st.metric(label="🛡️ L1 智能拦截率", value=f"{l1_rate}%", delta=None, delta_color="normal")
        with col3:
            st.metric(label="🔺 P0 研发升级率", value=f"{p0_rate}%", delta=None, delta_color="normal")
    with st.container():
        with st.expander("🤖 **AI 技术简报** - 点击展开", expanded=True):
            st.markdown(generate_ai_brief(all_reviews_df, None))


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
                                st.write(f"📥 数据同步：已添加 {len(new_reviews)} 条新工单到全局状态（累计：{len(st.session_state.all_reviews)} 条）")
                        
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
            
            # ==================== 数据处理：保存到 session_state（用于 Hero Section） ====================
            # 注意：数据库保存已在 monitor 和 action 节点中完成，这里只更新 session_state
            result = final_state
            rag_results = result.get("rag_analysis_results", [])
            action_plans = result.get("action_plans", [])
            raw_reviews = result.get("raw_reviews", [])
            critical_reviews = result.get("critical_reviews", [])
            
            # 生成批次记录（用于 session_state，保持兼容性）
            batch_record = {
                'time': current_time,
                'rag_results': rag_results,
                'actions': action_plans,
                'new_reviews_count': len(raw_reviews),
                'critical_count': len(critical_reviews)
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
    # Hero Section：使用 session_state 中的最新批次（保持即时感）
    incident_history = st.session_state.get('incident_history', [])
    
    # 从数据库读取历史记录（用于历史记录部分）
    db = get_database()
    db_history = db.get_history(limit=50)  # 获取更多记录以过滤
    
    # 获取 Hero Section 中已显示的 review_id 集合（如果有）
    hero_review_ids = set()
    if incident_history:
        latest_batch = incident_history[0]
        latest_rag_results = latest_batch.get('rag_results', [])
        if latest_rag_results:
            hero_review_ids = {r.get("review_id") for r in latest_rag_results if r.get("review_id")}
    
    # 过滤掉 Hero Section 中已显示的记录，只保留有 RAG 结果和 Action 的记录
    filtered_history = [
        record for record in db_history
        if record.get("review_id") not in hero_review_ids
        and record.get("rag_result") is not None
        and record.get("action_plan") is not None
    ]
    
    # ==================== Part A: 最新动态 (Hero Section) ====================
    if incident_history:
        st.markdown("---")
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
            has_p0_risk = any('缺陷' in rag.get('conclusion', '') for rag in latest_rag_results)
        
        # 显示标题和统计
        col_title, col_stats = st.columns([2, 1])
        with col_title:
            st.markdown("### 🚨 本次巡检发现 (Latest)")
        with col_stats:
            st.caption(f"📅 {latest_time} · 新增 {latest_new_reviews} 条工单")
        
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
    # 历史记录部分独立显示，即使 Hero Section 为空也会显示
    if filtered_history:
        if incident_history:
            st.divider()  # 分割线，清晰区分最新和历史
        else:
            st.markdown("---")  # 如果没有 Hero Section，直接显示分割线
        st.markdown("#### 📜 历史巡检记录")
        
        # 使用固定高度的滚动容器
        with st.container(height=500, border=False):
            # 按时间分组（简化：按日期分组）
            grouped_by_date = defaultdict(list)
            for record in filtered_history:
                created_at = record.get('created_at', '')
                # 提取日期部分（YYYY-MM-DD）
                date_key = created_at.split(' ')[0] if ' ' in created_at else created_at
                grouped_by_date[date_key].append(record)
            
            # 按日期倒序显示
            sorted_dates = sorted(grouped_by_date.keys(), reverse=True)
            
            for date_idx, date_key in enumerate(sorted_dates):
                records = grouped_by_date[date_key]
                
                # 使用 expander 折叠历史批次
                with st.expander(f"📅 {date_key} (共 {len(records)} 条记录)", expanded=False):
                    for item_idx, record in enumerate(records):
                        # 从数据库记录中提取 RAG 结果和 Action 计划
                        rag_result = record.get('rag_result')
                        action_plan = record.get('action_plan')
                        
                        # 构建 RAG 结果对象（兼容 render_incident_card 的格式）
                        # 注意：get_history() 已经将 JSON 解析为字典，直接使用即可
                        if rag_result and isinstance(rag_result, dict):
                            rag_result_obj = rag_result.copy()
                            # 确保包含 review_id 和 review_text
                            rag_result_obj['review_id'] = record.get('review_id')
                            rag_result_obj['review_text'] = record.get('content', '')
                            
                            # 构建 Action 计划对象（兼容格式）
                            action_item = None
                            if action_plan and isinstance(action_plan, dict):
                                action_item = action_plan.copy()
                                action_item['review_id'] = record.get('review_id')
                            
                            # 渲染完整的 Case（RAG + Action 成对）
                            render_incident_card(
                                rag_result_obj,
                                action_item,
                                batch_idx=date_idx + 1,
                                item_idx=item_idx
                            )
                            
                            # Case 之间的分隔
                            if item_idx < len(records) - 1:
                                st.markdown("")  # 空白间隔，避免文字粘连
                    
                    # 日期批次之间的分隔
                    if date_idx < len(sorted_dates) - 1:
                        st.markdown("")
    elif not incident_history:
        # 如果工作流未运行且没有历史记录，显示提示
        st.info("👆 点击上方「运行智能工作流」按钮，开始首次增量巡检")

