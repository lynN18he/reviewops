"""
ReviewOps - B2B SaaS 研发智能问诊中台
L2 Support Copilot · 让研发专注核心业务
"""

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 须在 import ChatTongyi 之前执行，避免 DashScope 报错被 KeyError 掩盖
from src.tongyi_check_response_patch import apply_patch

apply_patch()

# ==================== UI 模块导入 ====================
from src.ui.styles import apply_page_config, apply_custom_styles
from src.ui.state import init_session_state
from src.ui.tab_dashboard import render_page_dashboard, render_tab as render_workspace_tab
from src.ui.tab_playground import render_tab as render_playground_tab

# ==================== 页面配置 ====================
apply_page_config()
apply_custom_styles()

# ==================== 数据加载（B2B SaaS 工单） ====================
@st.cache_data(ttl=60)
def load_tickets():
    """加载工单数据：test_tickets.csv，表头 Ticket_ID, User_Message, True_Category, Expected_Tool。"""
    try:
        df = pd.read_csv("test_tickets.csv", encoding="utf-8")
    except Exception:
        return pd.DataFrame()
    if df.empty or "User_Message" not in df.columns:
        return pd.DataFrame()
    # 映射为与 Graph/State 兼容的字段：ticket_id, ticket_content, user_id, timestamp, urgency_level, category
    if "Ticket_ID" in df.columns:
        df = df.rename(columns={"Ticket_ID": "ticket_id", "User_Message": "ticket_content"})
    else:
        df["ticket_id"] = df.index.astype(str).map(lambda i: f"TIK-{i}")
        df = df.rename(columns={"User_Message": "ticket_content"})
    df["user_id"] = df["ticket_id"].apply(lambda x: f"ticket_{x}")
    df["urgency_level"] = None
    df["category"] = None
    df["timestamp"] = ""
    # 保留 True_Category, Expected_Tool 供后续扩展
    return df

load_tickets.clear = getattr(load_tickets, "clear", lambda: None)

# 加载工单数据（单条/批量跑测时 User_Message 作为 query 传给 Agent）
tickets_df = load_tickets()

# ==================== 工具函数（SaaS 运维北极星指标，来自 DB 实时统计） ====================
def calculate_metrics(df, session_state=None):
    """
    从 SQLite get_dashboard_metrics() 拉取大盘用指标。
    返回 8 元组：(total, ai_r, esc_r, bug_r, processed, resolved_n, escalate_n, jira_n)。
    """
    try:
        from src.services.database import get_database
        db = get_database()
        return db.get_dashboard_metrics()
    except Exception:
        return 0, 0.0, 0.0, 0.0, 0, 0, 0, 0


# ==================== 导航（三页；兼容历史 session 文案）====================
_NAV_OPTIONS = ("📊 晨会数据大盘", "⚡ 智能巡检工作台", "🔬 单票实验室")
if st.session_state.get("nav_radio") not in _NAV_OPTIONS:
    st.session_state.nav_radio = _NAV_OPTIONS[0]

env_api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()

# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("## 🔬 ReviewOps")
    st.caption("B2B SaaS 研发智能问诊中台")
    st.markdown("---")

    st.markdown(
        """
<div style="background-color: #1E293B; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155;">
    <h4 style="color: #F8FAFC; margin-top: 0px; font-size: 14px;">📦 当前产品</h4>
    <span style="color: #94A3B8; font-size: 13px;">B2B 电商履约与物流 SaaS<br>· saas_knowledge.txt</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    if env_api_key:
        st.markdown(
            """
<div style="background-color: #1E293B; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155;">
    <h4 style="color: #F8FAFC; margin-top: 0px; font-size: 14px;">🔑 API 配置</h4>
    <span style="color: #10B981; font-size: 13px;">✅ 已从环境变量读取</span>
</div>
            """,
            unsafe_allow_html=True,
        )
        api_key = env_api_key
    else:
        st.markdown(
            """
<div style="background-color: #1E293B; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155;">
    <h4 style="color: #F8FAFC; margin-top: 0px; font-size: 14px;">🔑 API 配置</h4>
    <span style="color: #FBBF24; font-size: 13px;">请填写下方密钥，或设置环境变量 DASHSCOPE_API_KEY</span>
</div>
            """,
            unsafe_allow_html=True,
        )
        api_key = st.text_input(
            "API Key",
            type="password",
            value="",
            placeholder="sk-...",
            help="或设置环境变量 DASHSCOPE_API_KEY",
            label_visibility="collapsed",
        )

    st.markdown(
        """
<div style="background-color: #1E293B; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155;">
    <h4 style="color: #F8FAFC; margin-top: 0px; font-size: 14px;">📊 数据源</h4>
    <span style="color: #94A3B8; font-size: 13px;">知识库: saas_knowledge.txt<br>工单集: test_tickets.csv</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🧭 导航")
    page_choice = st.radio(
        "导航菜单",
        list(_NAV_OPTIONS),
        key="nav_radio",
        label_visibility="collapsed",
    )
    st.markdown("---")

    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.caption("ReviewOps v1.0\n\nPowered by RAG + LLM")


# ==================== 全局状态初始化 ====================
init_session_state(tickets_df, calculate_metrics)

# ==================== 页面路由（各页自带 H1，无全局大标题）====================
if page_choice == "📊 晨会数据大盘":
    render_page_dashboard(calculate_metrics)
elif page_choice == "⚡ 智能巡检工作台":
    render_workspace_tab(api_key, calculate_metrics)
elif page_choice == "🔬 单票实验室":
    render_playground_tab(api_key)
