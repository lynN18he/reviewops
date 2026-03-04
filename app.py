"""
ReviewOps - 用户反馈决策中台
一个帮助产品经理分析用户反馈的 B端 SaaS 原型
"""

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# ==================== UI 模块导入 ====================
from src.ui.styles import apply_page_config, apply_custom_styles
from src.ui.state import init_session_state
from src.ui.tab_dashboard import render_tab as render_dashboard_tab, render_dashboard_metrics
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
    # 映射为与 Graph/State 兼容的字段：review_id, review_text, user_id, timestamp, urgency_level, category
    if "Ticket_ID" in df.columns:
        df = df.rename(columns={"Ticket_ID": "review_id", "User_Message": "review_text"})
    else:
        df["review_id"] = df.index.astype(str).map(lambda i: f"TIK-{i}")
        df = df.rename(columns={"User_Message": "review_text"})
    df["user_id"] = df["review_id"].apply(lambda x: f"ticket_{x}")
    df["urgency_level"] = None
    df["category"] = None
    df["timestamp"] = ""
    # 保留 True_Category, Expected_Tool 供后续扩展
    return df

load_tickets.clear = getattr(load_tickets, "clear", lambda: None)

# 加载工单数据（单条/批量跑测时 User_Message 作为 query 传给 Agent）
tickets_df = load_tickets()

# ==================== 工具函数（SaaS 运维北极星指标） ====================
def calculate_metrics(df, session_state=None):
    """
    计算看板指标：今日工单总数、L1 智能拦截率、P0 研发升级率。
    兼容传入 session_state 以根据巡检结果动态计算拦截率/升级率；否则使用 Mock 值。
    """
    total_tickets = 0 if df.empty else len(df)
    if total_tickets == 0:
        return total_tickets, 0.0, 0.0

    # 尝试从 session_state 或历史结果计算 L1 拦截率、P0 升级率
    l1_rate, p0_rate = 72.5, 12.3  # 默认 Mock
    if session_state is not None:
        all_rag = session_state.get("incremental_rag_results", []) or session_state.get("latest_rag_results", [])
        all_actions = session_state.get("incremental_action_plans", [])
        # 从数据库补充：有 rag_result/action_plan 的历史记录
        try:
            from src.services.database import get_database
            db = get_database()
            history = db.get_history(limit=500)
            for r in history:
                rag = r.get("rag_result")
                action = r.get("action_plan")
                if isinstance(rag, dict) and rag:
                    all_rag = all_rag + [rag]
                if isinstance(action, dict) and action:
                    all_actions = all_actions + [action]
        except Exception:
            pass
        total_analyzed = len(all_rag) or 1
        if total_analyzed > 0:
            # L1 拦截：结论含「用户」「配置」「已知局限」等视为被拦截
            deflected = sum(
                1 for r in all_rag
                if isinstance(r, dict) and any(
                    k in (r.get("conclusion") or "")
                    for k in ("用户", "配置", "已知局限", "✅", "用户使用问题")
                )
            )
            l1_rate = round((deflected / total_analyzed) * 100, 1)
            # P0 升级：行动类型为 Jira Ticket 视为升级研发
            jira_count = sum(
                1 for a in all_actions
                if isinstance(a, dict) and (a.get("action_type") or "").strip() == "Jira Ticket"
            )
            p0_rate = round((jira_count / total_analyzed) * 100, 1)
    return total_tickets, l1_rate, p0_rate


def generate_ai_brief(df, _unused=None):
    """生成 B2B SaaS 技术简报（技术支持主管视角）。"""
    total = 0 if df.empty else len(df)
    brief = """
### 📋 技术简报

**整体系统健康度：** 今日工单量处于正常区间，核心服务（订单同步、物流轨迹）无大面积故障报告。

**核心故障发现：**
- 今日共处理 **{total}** 条工单。
- **Shopify 订单同步**：部分工单集中反馈 401/Token 失效，多为商家侧重置 API 后未在系统更新，已由 SOP 引导重新授权。
- **物流轨迹**：偶发 USPS 状态卡在 “In Transit”，与近期发版限流策略相关，已记录 JIRA 跟进。

**拦截成效：**
- 多数问题集中在 **Token 授权错误**、**Webhook 配置**，已由知识库与 SOP 成功拦截，无需升级研发。
- 建议继续强化 L1 话术与自助排查文档，降低重复类工单占比。

**研发关注建议：**
- 关注 JIRA-1042（阿拉伯语地址解析超时）排期与发版节奏。
- 监控 429 限流相关反馈，评估限流阈值是否需按客户分层调整。
""".format(total=total)
    return brief


def extract_product_name():
    """从业务场景推断产品/服务名称"""
    return "B2B 电商履约与物流 SaaS"


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("## 🔬 ReviewOps")
    st.markdown("*用户反馈决策中台*")
    
    st.divider()
    
    # 产品信息
    product_name = extract_product_name()
    st.markdown("### 📦 当前分析产品")
    st.info(f"**{product_name}**\n\n知识库已向量化存储（saas_knowledge.txt）")
    
    st.divider()
    
    # API Key 输入
    st.markdown("### 🔑 API 配置")
    
    # 优先从环境变量读取
    env_api_key = os.getenv("DASHSCOPE_API_KEY", "")
    default_api_key = env_api_key if env_api_key else ""
    
    # 如果环境变量中有，显示提示；否则允许用户输入
    if env_api_key:
        st.info("✅ 已从环境变量 `DASHSCOPE_API_KEY` 读取 API Key")
        api_key = env_api_key
    else:
        api_key = st.text_input(
            "DashScope API Key (阿里千问)",
            type="password",
            value="",
            placeholder="sk-... 或设置环境变量 DASHSCOPE_API_KEY",
            help="用于 RAG 深度分析功能。推荐方式：在项目根目录创建 .env 文件，添加 DASHSCOPE_API_KEY=your-key"
        )
        
        if api_key:
            st.success("✅ API Key 已配置（临时，仅本次会话有效）")
        else:
            st.warning("⚠️ 请配置 API Key 以启用 RAG 分析功能")
    
    st.divider()
    
    # 数据概览
    st.markdown("### 📊 数据源")
    st.caption(f"📄 工单数据: `test_tickets.csv`")
    st.caption(f"📋 知识库: `saas_knowledge.txt` (已向量化)")
    st.caption(f"💾 向量库: `./chroma_db`")
    st.caption(f"🕐 最后更新: 2025-01-15")


# ==================== 主界面 ====================
# 标题区
st.markdown('<h1 class="main-title">ReviewOps</h1>', unsafe_allow_html=True)
st.markdown("**用户反馈决策中台** · 让产品决策有据可依")
st.markdown("---")

# ==================== 全局状态初始化 ====================
init_session_state(tickets_df, calculate_metrics)

# ==================== 顶部 Dashboard ====================
render_dashboard_metrics(calculate_metrics, generate_ai_brief)

st.markdown("---")

# ==================== Tab 分页结构 ====================
# 使用容器统一模块大小
with st.container():
    tab_auto, tab_manual = st.tabs(["🛡️ 智能巡检控制台", "🔬 单条归因实验室"])

# ==================== Tab 1: 智能巡检控制台 ====================
with tab_auto:
    render_dashboard_tab(api_key, calculate_metrics, generate_ai_brief)

# ==================== Tab 2: 单条归因实验室 ====================
with tab_manual:
    render_playground_tab(api_key)

# ==================== 页脚 ====================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #6b7280; font-size: 0.85rem;">
        <p>🔬 ReviewOps v1.0 · 用户反馈决策中台</p>
        <p>Powered by RAG + LLM · Built with Streamlit</p>
    </div>
    """,
    unsafe_allow_html=True
)
