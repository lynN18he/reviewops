"""
智能巡检控制台 Tab
包含工作流触发、Metrics 渲染、Hero+History 列表等所有逻辑
"""

import streamlit as st
import pandas as pd
import time
import datetime
from zoneinfo import ZoneInfo
from src.ui.cards import render_incident_card
from src.graph import graph_app
from src.services.database import get_database
from src.utils import sanitize_stored_rag_text_for_ui
from langchain_core.messages import HumanMessage


def _section_gap():
    """模块间留白，替代 st.markdown('---')。"""
    st.markdown('<div class="ro-section-gap" aria-hidden="true"></div>', unsafe_allow_html=True)


def _briefing_today_zh() -> str:
    """晨报页眉用本地日（上海），避免模型乱写 2024、6 月 XX 日等占位。"""
    try:
        d = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        d = datetime.date.today()
    return f"{d.year}年{d.month}月{d.day}日"


def _generate_daily_briefing() -> str:
    """
    从 DB 拉取过去 24 小时内 analyzed/resolved 工单作为叙事采样，调用 LLM 生成晨会技术简报。
    全库健康度数字与顶部「数据概览」及黄金分桶一致；带时间窗口、数量上限与 Token 过载保护。
    """
    date_zh = _briefing_today_zh()
    db = get_database()
    total_count, ai_closure_rate = db.get_briefing_stats_24h()
    tickets = db.get_briefing_tickets_24h(limit=100)
    intercepted_24h = db.get_intercepted_count_24h()
    # 与顶部「数据概览」同一套全库黄金指标，避免 LLM 在「24h 无样本」时编造与大盘矛盾的数字
    dash = db.get_dashboard_metrics()
    _, d_ai, d_esc, d_bug, _, _, _, _ = dash
    br = db.get_briefing_library_breakdown()
    (
        bt,
        processed_count,
        n_pending,
        n_jira,
        n_esc,
        n_ai,
        n_int,
        n_email,
    ) = (
        br["total"],
        br["processed"],
        br["n_pending"],
        br["n_jira"],
        br["n_escalate"],
        br["n_ai_closure"],
        br["n_intercepted"],
        br["n_email_closure"],
    )
    pct_int_total = round((n_int / bt) * 100, 1) if bt else 0.0
    pct_int_proc = round((n_int / processed_count) * 100, 1) if processed_count else 0.0
    lines = []
    for t in tickets:
        tid = t.get("ticket_id", "")
        content = (t.get("ticket_content") or "").strip()[:120]
        conclusion = ""
        action_type = ""
        rr = t.get("rag_result")
        ap = t.get("action_plan")
        if rr and isinstance(rr, dict):
            conclusion = (rr.get("conclusion") or "").strip()
        if ap and isinstance(ap, dict):
            action_type = (ap.get("action_type") or "").strip()
        lines.append(f"- [{tid}] 归因: {conclusion} | 动作: {action_type} | 用户反馈: {content}...")
    ticket_data_str = "\n".join(lines) if lines else "（暂无工单数据）"

    exec_line = (
        f"截至目前，系统共完成 {processed_count} 条工单的智能诊断。其中，AI 成功闭环 {n_ai} 条（占 {d_ai:.1f}%），"
        f"为一线客服提供了精准的防御支持。另有 {n_esc} 条疑难客诉流转至研发，检出已知系统缺陷 {n_jira} 起。"
        f"系统整体路由分发逻辑运转健康。"
    )
    preamble = (
        f"> 📌 **数据口径**：下方「24 小时工单列表」仅为近 24h 内 **status ∈ analyzed/resolved** 的采样（最多 {len(tickets)} 条），"
        f"用于归因与故障分布举例。**累计接单**共 **{bt}** 条（含待分析 **{n_pending}** 条）；"
        f"**三率分母**均为 **已完成 AI 分析/已流出待分析队列** 的 **{processed_count}** 条，与页面数据概览一致。\n"
        f"> 💼 **整体画像（第一节请用类似业务汇报语态展开，数字须与下表一致）**：{exec_line}\n"
        f"> 📥 **近 24 小时窗口**：上述采样共 {total_count} 条；其中 AI 智能闭环（邮件/拦截分桶口径）占比约 {ai_closure_rate}%。"
        f"近 24h 内新增 **筛选拦截（intercepted）** **{intercepted_24h}** 条（按 created_at）。\n"
        f"> 📊 **指标锚点**（三率分母 = 已处理 {processed_count} 条）：\n"
        f">   - **AI 智能闭环**：{d_ai:.1f}%（**{n_ai} 条**）— **筛选拦截** **{n_int} 条**（占已处理 {pct_int_proc}%，占累计 {pct_int_total}%），"
        f"**邮件/SOP 等闭环其余** **{n_email} 条**；\n"
        f">   - **疑难转人工**：{d_esc:.1f}%（**{n_esc} 条**）；**已知缺陷/Jira**：{d_bug:.1f}%（**{n_jira} 条**）。\n"
        f"> 🔍 若「24 小时采样」为 0 而全库非 0，须说明**时间窗口不同**，不得用 0 覆盖全库事实。\n\n"
    )

    prompt = f"""你是一个资深的 B2B SaaS 研发总监。请根据以下数据生成晨会技术简报正文。

{preamble}📋 **24 小时内工单明细采样**（无则下方为占位）：
{ticket_data_str}

**输出格式（严格遵守）**
- 不要输出文档总标题、不要输出「日期：」行；页眉已由系统固定，简报日期为 **{date_zh}**。
- 禁止日期占位符（「XX 日」「待定」「TBD」等）与虚构公历日期。
- 需要指时间时，仅用「近 24 小时统计窗口」「全库累计」等相对表述。
- **视觉风格**：与控制台「工作流运行」日志一致——小节标题必须带下列 emoji（不可替换顺序与符号）；列表子项在语义合适时可用 📥（数据/同步）、🔍（排查/筛选）、✅（完成/闭环）、⚠️（风险）等开头，避免堆砌。
- **第一节硬性要求**：`## 1. 📊 整体系统健康度` 以业务汇报语态撰写（可参考上文「整体画像」），**每个比例须同时给出人数**；**筛选拦截**须写清条数及占「已处理」分母的比例；可补充累计 {bt} 条接单、{n_pending} 条仍待分析；禁止生硬堆砌符号与重复粘贴表格。

请以 Markdown 输出且**仅包含**下面四个二级标题（行首必须是 `##`），标题与 emoji、序号逐字一致；每个标题下写实际正文（1～3 段或列表），勿输出任何括号内的写作提示。

## 1. 📊 整体系统健康度
## 2. ⚠️ 核心故障与异常分布
## 3. ✅ AI 智能闭环与疑难分流成效
## 4. 💡 研发关注建议

语言精简、客观、管理视角。"""

    fixed_header = (
        f"### 🚀 智能巡检系统晨会技术简报\n\n"
        f"📅 **简报日期：** {date_zh}（Asia/Shanghai）\n\n"
        f"---\n\n"
    )

    try:
        from src.utils import init_llm
        llm = init_llm()
        resp = llm.invoke([HumanMessage(content=prompt)])
        body = (resp.content or "").strip()
        return fixed_header + body
    except Exception as e:
        return f"❌ 简报生成失败: {str(e)}"


def render_dashboard_metrics(calculate_metrics):
    """
    渲染顶部 Dashboard：单日流量（Demo 用全库）、AI 闭环率、节省工时、需研发介入量；无 delta。
    """
    with st.container():
        st.markdown("## 📈 数据概览")
        all_tickets = st.session_state.get('all_tickets', [])
        if not all_tickets:
            all_tickets_df = pd.DataFrame()
        else:
            all_tickets_df = pd.DataFrame(all_tickets)
            if 'ticket_id' in all_tickets_df.columns:
                all_tickets_df = all_tickets_df.drop_duplicates(subset=['ticket_id'], keep='last')
        _met = calculate_metrics(all_tickets_df, st.session_state)
        (
            today_total,
            ai_resolution_rate,
            _esc_rate,
            _bug_rate,
            _processed,
            resolved_count,
            escalated_count,
            jira_count,
        ) = (
            _met[0],
            _met[1],
            _met[2],
            _met[3],
            _met[4],
            _met[5],
            _met[6],
            _met[7],
        )
        st.session_state["prev_total_tickets"] = today_total
        st.session_state["prev_ai_resolution_rate"] = ai_resolution_rate
        st.session_state["prev_human_escalation_rate"] = _esc_rate
        st.session_state["prev_bug_ident_rate"] = _bug_rate

        hours_saved = resolved_count * 0.25
        rd_attention = escalated_count + jira_count

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                label="📥 今日新增工单",
                value=f"{today_total}",
                help="今日系统接入的客诉总数。（当前 Demo 以全库条数模拟单日流量；生产可改为 created_at 当日。）",
            )
        with col2:
            st.metric(
                label="🤖 AI 独立闭环率",
                value=f"{ai_resolution_rate:.1f}%",
                help="分母为已完成分析工单（非 pending）。含邮件草稿与筛选拦截，代表无需人工介入即可处理的比例。",
            )
        with col3:
            st.metric(
                label="⏱️ 约节省客服工时",
                value=f"{hours_saved:.1f} h",
                help="按人工平均处理单票耗时 15 分钟（0.25 h）× AI 独立闭环单量估算，反映降本增效 ROI。",
            )
        with col4:
            st.metric(
                label="🚨 需研发介入单量",
                value=f"{rd_attention}",
                help="包含超纲转人工的疑难单，以及确认为底层 Bug 的 Jira 缺陷单。需研发团队重点关注。",
            )


def render_page_dashboard(calculate_metrics):
    """
    渲染晨会数据大盘页面：数据概览 + 简报生成按钮 + 历史巡检明细（来自 DB）
    """
    st.markdown("# 📊 晨会数据大盘")
    st.caption("指标概览、AI 晨报与工单闭环工作台")
    st.divider()
    render_dashboard_metrics(calculate_metrics)

    _section_gap()
    st.markdown("## 📰 AI 技术简报")
    st.caption(
        "叙事与归因举例来自近 24 小时内「已分析/已闭环」工单采样；全库拆解与比例锚点见简报第一节，并与上方数据概览同源。"
    )

    if st.button("🚀 基于真实大盘数据生成晨报", type="primary", key="generate_brief_btn"):
        with st.spinner("📥 正在同步数据并由 AI 生成晨报..."):
            st.session_state.daily_briefing = _generate_daily_briefing()
        st.rerun()

    if st.session_state.get("daily_briefing"):
        with st.expander("📰 展开查看 AI 技术简报全文", expanded=False):
            st.markdown(st.session_state.daily_briefing)

    _section_gap()
    st.markdown("## 🗂️ 工单工作台")

    db = get_database()
    vis = db.get_inbox_visibility_summary()
    inbox_n = int(vis.get("analyzed_inbox", 0) or 0)
    esc_n = int(vis.get("analyzed_escalate", 0) or 0)
    esc_rows = db.get_escalate_queue_tickets(limit=100)

    tab_frontline, tab_l2 = st.tabs(
        [
            f"📋 一线待办 · {inbox_n}",
            f"🛡️ 研发疑难 · {esc_n}",
        ]
    )

    with tab_frontline:
        tab_pending, tab_resolved = st.tabs(["🔴 待处理", "✅ 已闭环"])
        with tab_pending:
            pending_records = db.get_pending_tickets(limit=100)
            if not pending_records:
                st.caption("暂无待处理工单。")
            else:
                with st.container(height=720, border=False):
                    for idx, record in enumerate(pending_records):
                        rag_result = record.get("rag_result")
                        action_plan = record.get("action_plan")
                        ticket_id = record.get("ticket_id", "")
                        if rag_result and isinstance(rag_result, dict):
                            rag_result_obj = rag_result.copy()
                            rag_result_obj["ticket_id"] = ticket_id
                            rag_result_obj["ticket_content"] = record.get("ticket_content", "")
                            action_item = None
                            if action_plan and isinstance(action_plan, dict):
                                action_item = action_plan.copy()
                                action_item["ticket_id"] = ticket_id
                            render_incident_card(
                                rag_result_obj,
                                action_item,
                                batch_idx=0,
                                item_idx=idx,
                                show_resolve_button=True,
                                resolve_callback=lambda tid=ticket_id: db.resolve_ticket(tid),
                            )
                            if idx < len(pending_records) - 1:
                                st.markdown("")

        with tab_resolved:
            resolved_records = db.get_resolved_tickets(limit=100)
            if not resolved_records:
                st.caption("暂无已闭环记录")
            else:
                with st.container(height=720, border=False):
                    for idx, record in enumerate(resolved_records):
                        rag_result = record.get("rag_result")
                        action_plan = record.get("action_plan")
                        if rag_result and isinstance(rag_result, dict):
                            rag_result_obj = rag_result.copy()
                            rag_result_obj["ticket_id"] = record.get("ticket_id")
                            rag_result_obj["ticket_content"] = record.get("ticket_content", "")
                            action_item = None
                            if action_plan and isinstance(action_plan, dict):
                                action_item = action_plan.copy()
                                action_item["ticket_id"] = record.get("ticket_id")
                            render_incident_card(
                                rag_result_obj, action_item, batch_idx=1, item_idx=idx
                            )
                            if idx < len(resolved_records) - 1:
                                st.markdown("")

    with tab_l2:
        if not esc_rows:
            st.caption("暂无转 L2 疑难单。")
        else:
            table_rows = []
            for er in esc_rows:
                tid = (er.get("ticket_id") or "").strip()
                raw_q = (er.get("ticket_content") or "").strip()
                rag = er.get("rag_result")
                if not isinstance(rag, dict):
                    rag = {}
                evidence = sanitize_stored_rag_text_for_ui((rag.get("evidence") or "").strip())
                conclusion = sanitize_stored_rag_text_for_ui((rag.get("conclusion") or "").strip())
                reason = sanitize_stored_rag_text_for_ui((rag.get("reason") or "").strip())
                diag = evidence or " | ".join(x for x in (conclusion, reason) if x) or "—"
                table_rows.append(
                    {
                        "工单单号": tid,
                        "原始问题": raw_q,
                        "诊断依据": diag,
                    }
                )
            df_escalated = pd.DataFrame(table_rows)
            # 交互式表易省略长文本；静态 st.table 按行撑开，完整展示「原始问题 / 诊断依据」
            st.table(df_escalated)


def _render_patrol_batch_expanders(run_history: list) -> None:
    """智能巡检页「批次流水账」：多条 expander + 跳转大盘按钮（供流水线容器内复用）。"""
    if not run_history:
        return
    st.caption("📋 批次流水账")
    for batch_idx, batch in enumerate(run_history):
        batch_id = batch.get("batch_id", "")
        total_count = batch.get("total_count", 0)
        high_risk = batch.get("high_risk_tickets", [])
        scanned_ids_raw = batch.get("scanned_ids", "—")
        id_list = [x.strip() for x in scanned_ids_raw.split(",") if x.strip()] if scanned_ids_raw and scanned_ids_raw != "—" else []
        display_ids = ", ".join(id_list[:2]) + "...等" if len(id_list) > 3 else (", ".join(id_list) if id_list else "—")
        time_str = batch_id.split(" ")[1][:5] if " " in batch_id else batch_id[:5]

        has_anomaly = len(high_risk) > 0
        if has_anomaly:
            title = f"▼ 🕒 {time_str} 批次 | 扫描 {total_count} 条 ({display_ids}) | 🚨 发现 {len(high_risk)} 条高危"
            expanded = True
        else:
            title = f"▶ 🕒 {time_str} 批次 | 扫描 {total_count} 条 ({display_ids}) | ✅ 未发现高危异常"
            expanded = False

        with st.expander(title, expanded=expanded):
            st.caption(f"📄 **本批次完整扫描清单:** {', '.join(id_list) if id_list else scanned_ids_raw}")
            if has_anomaly:
                for item in high_risk:
                    cat = item.get("category", "其他")
                    tid = item.get("ticket_id", "")
                    summary = item.get("summary", "")
                    action = item.get("action", "")
                    st.markdown(f"- **[{cat}]** `{tid}` {summary} ➡️ {action}")
                st.write("")

                def _jump_to_dashboard():
                    st.session_state.nav_radio = "📊 晨会数据大盘"

                st.button(
                    "👉 异常已同步至全局待办！前往【晨会数据大盘】闭环处理",
                    key=f"jump_to_dash_{batch_idx}_{batch_id}",
                    type="secondary",
                    width="stretch",
                    on_click=_jump_to_dashboard,
                )
            else:
                st.caption("本批次无高危项；常规单已由 Agent 自动处理。")


def render_tab(api_key, calculate_metrics):
    """
    渲染智能巡检工作台（LangGraph 调度控制台）
    """
    st.markdown("# ⚡ 智能巡检调度中心")
    st.caption("基于 LangGraph 的自动化巡检系统，监控、筛选、分析并生成行动建议。")
    st.divider()
    st.markdown("### 🎛️ 调度控制台")
    col_btn, col_status = st.columns([1, 2])
    with col_btn:
        start_btn = st.button(
            "▶️ 运行全量智能工作流",
            type="primary",
            use_container_width=True,
            key="workflow_btn_auto",
        )
    with col_status:
        last_run_time = st.session_state.get("last_run_time")
        if last_run_time and str(last_run_time).strip() and str(last_run_time) != "从未":
            last_disp = str(last_run_time)
        else:
            last_disp = "尚未运行"
        st.caption(f"系统状态：🟢 空闲就绪 · 上次巡检：{last_disp}")

    st.markdown("### 📟 运行流水线 (Pipeline Logs)")
    log_container = st.container(border=True)

    # ==================== 智能工作流执行 ====================
    # Trigger: 在边框容器内运行 Graph，完成后 st.rerun()
    with log_container:
        if start_btn:
            # 检查 API Key
            if not api_key:
                st.error("❌ 请先在侧边栏配置 DashScope API Key")
                st.stop()

            try:
                # 记录本次巡检开始时间
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
                # 初始化状态（增量巡检：保留已处理的ID）
                initial_state = {
                    "incr_tickets": [],
                    "critical_tickets": [],
                    "rag_analysis_results": [],
                    "diagnosis_routes": [],
                    "diagnosis_category": [],
                    "processed_route_types": [],
                    "action_plans": [],
                    "logs": [],
                    "processed_ids": st.session_state.get('processed_ids', [])
                }
            
                # 清空本次巡检的结果（只保留历史数据）
                st.session_state.incremental_rag_results = []
                st.session_state.incremental_action_plans = []
            
                # 使用 st.status 展示实时日志（恢复运行过程显示）
                with st.status("🚀 工作流运行中...", expanded=True) as status:
                    st.write("🚀 启动智能工作流...")
                
                    # 数据同步：使用 stream() 监听流式输出
                    final_state = initial_state.copy()
                    for event in graph_app.stream(initial_state):
                        # 遍历每个节点的输出
                        for node_name, node_output in event.items():
                            # 合并状态
                            if isinstance(node_output, dict):
                                final_state.update(node_output)
                        
                            # 检测 node_monitor 产出的 incr_tickets
                            if node_name == "monitor" and isinstance(node_output, dict) and "incr_tickets" in node_output:
                                new_tickets = node_output.get("incr_tickets", [])
                                if new_tickets:
                                    st.session_state.all_tickets.extend(new_tickets)
                                    st.session_state.last_run_increment = len(new_tickets)
                                    st.write(f"📥 数据同步：已添加 {len(new_tickets)} 条新工单到全局状态（累计：{len(st.session_state.all_tickets)} 条）")
                        
                            # 检测 node_rag_analysis 产出的 rag_analysis_results（本次巡检的新增结果）
                            if node_name == "rag_analysis" and isinstance(node_output, dict) and "rag_analysis_results" in node_output:
                                rag_results = node_output.get("rag_analysis_results", [])
                                if rag_results:
                                    # 保存本次巡检的RAG结果（增量）
                                    st.session_state.incremental_rag_results.extend(rag_results)
                                    # 同时更新全局最新结果（用于兼容性）
                                    st.session_state.latest_rag_results = rag_results
                                    st.write(f"📄 本次巡检发现 {len(rag_results)} 条RAG归因结果（累计：{len(st.session_state.incremental_rag_results)} 条）")
                        
                            # 检测任意动作节点产出的 action_plans（累积）
                            if node_name in ("generate_email_node", "generate_jira_node", "escalate_human_node") and isinstance(node_output, dict) and "action_plans" in node_output:
                                action_plans = node_output.get("action_plans", [])
                                if action_plans:
                                    st.session_state.incremental_action_plans = action_plans
                                    st.write(f"💡 本次巡检行动建议累计 {len(action_plans)} 条")
                        
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
                
                    # 折叠时在标题中透出本次处理的工单 ID
                    incr_tickets = final_state.get("incr_tickets", [])
                    scanned_ids_str = ", ".join(t.get("ticket_id", "") for t in incr_tickets if t.get("ticket_id"))
                    if incr_tickets:
                        status.update(
                            label=f"✅ 扫描完成！处理单号: {scanned_ids_str}。结果将写入本页流水线区域。",
                            state="complete",
                            expanded=False
                        )
                    else:
                        status.update(
                            label="✅ 扫描完成！本次未拉取到新工单。",
                            state="complete",
                            expanded=False
                        )
                    st.write("⏳ 正在刷新页面以更新统计数据...")
                    time.sleep(1)
            
                # 更新上次巡检时间
                st.session_state.last_run_time = current_time

                # ==================== 批次流水账：插入 run_history，不覆盖 ====================
                result = final_state
                rag_results = result.get("rag_analysis_results", [])
                action_plans = result.get("action_plans", [])
                incr_tickets = result.get("incr_tickets", [])
                total_count = len(incr_tickets)

                action_dict = {}
                for action in action_plans:
                    tid = action.get("ticket_id")
                    if tid:
                        action_dict[tid] = action
                        if "_" in str(tid):
                            base_id = str(tid).split("_")[0]
                            if base_id not in action_dict:
                                action_dict[base_id] = action

                high_risk_tickets = []
                for idx, rag_result in enumerate(rag_results):
                    tid = rag_result.get("ticket_id")
                    action_item = action_dict.get(tid)
                    if not action_item and tid and "_" in str(tid):
                        action_item = action_dict.get(str(tid).split("_")[0])
                    if not action_item and idx < len(action_plans):
                        action_item = action_plans[idx]
                    at = (action_item.get("action_type") or "").strip() if action_item else ""
                    if at not in ("Jira Ticket", "Email Draft"):
                        continue
                    conclusion = rag_result.get("conclusion", "")
                    content = (rag_result.get("ticket_content") or "").strip()[:40]
                    if "缺陷" in conclusion or "需进一步调查" in conclusion:
                        category = "系统缺陷"
                    elif "用户" in conclusion or "配置" in conclusion:
                        category = "用户/配置"
                    else:
                        category = "其他"
                    action_text = "**[已推送 P0 Jira]**" if at == "Jira Ticket" else "*已发送邮件 SOP*"
                    high_risk_tickets.append({
                        "ticket_id": tid,
                        "category": category,
                        "summary": content + ("…" if len((rag_result.get("ticket_content") or "")) > 40 else ""),
                        "action": action_text,
                    })
                safe_count = total_count - len(high_risk_tickets)
                scanned_ids_str = ", ".join(t.get("ticket_id", "") for t in incr_tickets if t.get("ticket_id"))

                batch_id = current_time
                batch_record = {
                    "batch_id": batch_id,
                    "total_count": total_count,
                    "high_risk_tickets": high_risk_tickets,
                    "safe_count": safe_count,
                    "scanned_ids": scanned_ids_str,
                }
                if "run_history" not in st.session_state:
                    st.session_state.run_history = []
                st.session_state.run_history.insert(0, batch_record)

                st.session_state["workflow_result"] = result
                st.session_state["workflow_completed"] = True
                st.session_state["diagnosis_category"] = result.get("diagnosis_category", [])
                st.session_state["need_refresh"] = True

                st.rerun()
            
            except ImportError as e:
                st.error(f"❌ 无法导入工作流模块: {e}")
                st.caption("请确保 `src/graph.py` 存在且已正确配置。")
            except Exception as e:
                st.error(f"❌ 工作流执行失败: {e}")
                st.exception(e)
        elif st.session_state.get("run_history"):
            try:
                st.success("✅ 巡检任务已完成！", icon="✨")
            except TypeError:
                st.success("✅ 巡检任务已完成！")
            _render_patrol_batch_expanders(st.session_state.get("run_history") or [])
        else:
            st.markdown(
                "<div style='color: #64748b; padding: 20px; text-align: center;'>"
                "等待触发... 运行「全量智能工作流」后，此处将实时打印日志及批次结果。</div>",
                unsafe_allow_html=True,
            )

