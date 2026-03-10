"""
UI 样式管理模块
集中管理所有 CSS 样式和页面配置
"""

import streamlit as st


def apply_page_config():
    """应用页面配置"""
    st.set_page_config(
        page_title="ReviewOps · B2B SaaS 研发智能问诊中台",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded"
    )


def apply_custom_styles():
    """应用自定义 CSS 样式"""
    st.markdown("""
    <style>
        /* 主题色彩系统 */
        :root {
            --primary: #6366f1;
            --secondary: #8b5cf6;
            --accent: #06b6d4;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }
        
        /* 指标卡片样式 */
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
            padding: 1.2rem;
            border-radius: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15);
        }
        
        [data-testid="stMetric"] label {
            color: #a5b4fc !important;
            font-weight: 500;
        }
        
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #e0e7ff !important;
            font-weight: 700;
        }
        
        /* 侧边栏样式 - 优化颜色使其更明显和用户友好 */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1e293b 0%, #334155 100%) !important;
            border-right: 2px solid rgba(99, 102, 241, 0.3);
        }
        
        [data-testid="stSidebar"] .stMarkdown h1,
        [data-testid="stSidebar"] .stMarkdown h2,
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: #e0e7ff !important;
            font-weight: 600;
        }
        
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] .stMarkdown {
            color: #cbd5e1 !important;
        }
        
        [data-testid="stSidebar"] .stInfo {
            background-color: rgba(99, 102, 241, 0.15) !important;
            border-left: 3px solid #6366f1 !important;
            color: #e0e7ff !important;
        }
        
        [data-testid="stSidebar"] .stSuccess {
            background-color: rgba(16, 185, 129, 0.15) !important;
            border-left: 3px solid #10b981 !important;
            color: #d1fae5 !important;
        }
        
        [data-testid="stSidebar"] .stWarning {
            background-color: rgba(245, 158, 11, 0.15) !important;
            border-left: 3px solid #f59e0b !important;
            color: #fef3c7 !important;
        }
        
        [data-testid="stSidebar"] .stCaption {
            color: #94a3b8 !important;
        }
        
        [data-testid="stSidebar"] .stDivider {
            border-color: rgba(99, 102, 241, 0.2) !important;
        }
        
        [data-testid="stSidebar"] input[type="text"],
        [data-testid="stSidebar"] input[type="password"] {
            background-color: rgba(30, 41, 59, 0.5) !important;
            border: 1px solid rgba(99, 102, 241, 0.3) !important;
            color: #e0e7ff !important;
        }
        
        [data-testid="stSidebar"] input[type="text"]:focus,
        [data-testid="stSidebar"] input[type="password"]:focus {
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2) !important;
        }
        
        /* 按钮样式 */
        .stButton > button {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(99, 102, 241, 0.5);
        }
        
        /* 表格样式 */
        .stDataFrame {
            border-radius: 12px;
            overflow: hidden;
        }
        
        /* Expander 样式 */
        .streamlit-expanderHeader {
            background: rgba(99, 102, 241, 0.1);
            border-radius: 8px;
        }
        
        /* 主标题 */
        .main-title {
            background: linear-gradient(90deg, #6366f1, #8b5cf6, #06b6d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 0;
        }
        
        /* 信息卡片 */
        .info-card {
            background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            margin: 1rem 0;
        }
        
        /* 行动项卡片容器 */
        .action-card {
            background: #ffffff;
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            border: 1px solid #e5e7eb;
            transition: all 0.2s ease;
        }
        
        .action-card:hover {
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
            transform: translateY(-2px);
        }
        
        /* 高优先级 */
        .action-card.high-priority {
            border-left: 4px solid #ef4444;
        }
        
        /* 中优先级 */
        .action-card.medium-priority {
            border-left: 4px solid #f59e0b;
        }
        
        /* 常规优先级 */
        .action-card.low-priority {
            border-left: 4px solid #10b981;
        }
        
        /* 优先级标签 */
        .priority-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 0.5rem;
        }
        
        .priority-badge.high {
            background: #fef2f2;
            color: #dc2626;
        }
        
        .priority-badge.medium {
            background: #fffbeb;
            color: #d97706;
        }
        
        .priority-badge.low {
            background: #ecfdf5;
            color: #059669;
        }
        
        /* 行动标题 */
        .action-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #1f2937;
            margin: 0.5rem 0;
        }
        
        /* 行动详情 */
        .action-detail {
            color: #4b5563;
            font-size: 0.95rem;
            line-height: 1.6;
            margin: 0.75rem 0;
        }
        
        /* 元信息 */
        .action-meta {
            display: flex;
            gap: 1.5rem;
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid #f3f4f6;
        }
        
        .meta-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #6b7280;
            font-size: 0.85rem;
        }
        
        .meta-item strong {
            color: #374151;
        }
        
        /* 分割线 */
        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), transparent);
            margin: 2rem 0;
        }
        
        /* Toast 通知位置调整 - 让弹框更靠近按钮 */
        [data-testid="stToast"] {
            position: fixed !important;
            top: 20px !important;
            right: 20px !important;
            z-index: 999999 !important;
            min-width: 300px !important;
            max-width: 400px !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
            border-radius: 12px !important;
            animation: slideInRight 0.3s ease-out !important;
        }
        
        @keyframes slideInRight {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        /* 确保 toast 内容可见 */
        [data-testid="stToast"] > div {
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
            color: #e0e7ff !important;
            padding: 1rem 1.25rem !important;
            border: 1px solid rgba(99, 102, 241, 0.3) !important;
        }
        
        [data-testid="stToast"] [data-baseweb="notification"] {
            background: transparent !important;
            color: #e0e7ff !important;
        }
    </style>
    """, unsafe_allow_html=True)

