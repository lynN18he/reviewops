"""
ReviewOps Agentic Workflow - 基于 LangGraph 的自动化巡检系统
"""

import os
import time
import random
from typing import TypedDict, List, Literal
from operator import add
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatTongyi
import json

# 加载环境变量
load_dotenv()


# ==================== Mock 数据池 ====================
MOCK_DATA_POOL = [
    {
        "base_id": 101,
        "user_id": "user_001",
        "review_text": "夜间飞行时避障功能完全失效，差点撞墙，说明书上也没明确说明夜间不支持避障。",
        "rating": 1
    },
    {
        "base_id": 102,
        "user_id": "user_002",
        "review_text": "云台抖动严重，画面不稳定，重启后问题依然存在，怀疑是硬件质量问题。",
        "rating": 2
    },
    {
        "base_id": 103,
        "user_id": "user_003",
        "review_text": "快递包装破损，等了很久才收到，物流体验很差。",
        "rating": 2
    },
    {
        "base_id": 104,
        "user_id": "user_004",
        "review_text": "标称续航45分钟，实际只能飞20多分钟，续航严重虚标，感觉被欺骗了。",
        "rating": 1
    },
    {
        "base_id": 105,
        "user_id": "user_005",
        "review_text": "整体体验还不错，就是续航稍微短了点，其他功能都正常。",
        "rating": 4
    }
]


# ==================== 状态定义 ====================
class ReviewState(TypedDict):
    """工作流状态"""
    raw_reviews: List[dict]  # 新评论
    critical_reviews: List[dict]  # 筛选后的高危评论
    rag_analysis_results: List[dict]  # 归因结果
    action_plans: List[dict]  # 行动建议
    logs: List[str]  # 日志（使用 operator.add 追加）


# ==================== 状态 Reducer ====================
# 定义状态合并规则
def reducer(state: ReviewState, update: ReviewState) -> ReviewState:
    """合并状态更新"""
    # 对于列表类型，使用 operator.add 追加
    # 对于其他类型，直接覆盖
    merged = state.copy()
    
    # 合并列表（追加）
    if "logs" in update:
        merged["logs"] = state.get("logs", []) + update.get("logs", [])
    if "raw_reviews" in update:
        merged["raw_reviews"] = update.get("raw_reviews", [])
    if "critical_reviews" in update:
        merged["critical_reviews"] = update.get("critical_reviews", [])
    if "rag_analysis_results" in update:
        merged["rag_analysis_results"] = update.get("rag_analysis_results", [])
    if "action_plans" in update:
        merged["action_plans"] = update.get("action_plans", [])
    
    return merged


# ==================== 初始化 LLM ====================
def init_llm():
    """初始化 LLM"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
    
    return ChatTongyi(
        model="qwen-plus",
        temperature=0,
        dashscope_api_key=api_key
    )


# ==================== 节点定义 ====================

def node_monitor(state: ReviewState) -> ReviewState:
    """
    节点 1: 监控新评论
    动态模拟生成器：从 MOCK_DATA_POOL 随机采样，并添加时间戳后缀确保唯一性
    """
    # 动态采样：随机选取 1-2 条评论
    sample_size = random.randint(1, 2)
    sampled_templates = random.sample(MOCK_DATA_POOL, min(sample_size, len(MOCK_DATA_POOL)))
    
    # 为每条评论添加时间戳后缀，确保每次运行都被视为"新数据"
    current_timestamp = int(time.time())
    new_reviews = []
    
    for template in sampled_templates:
        review = {
            "review_id": f"{template['base_id']}_{current_timestamp}",
            "user_id": template['user_id'],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "review_text": template['review_text'],
            "rating": template['rating']
        }
        new_reviews.append(review)
    
    log_message = f"📥 监控节点：检测到 {len(new_reviews)} 条新评论 (ID: {[r['review_id'] for r in new_reviews]})"
    
    return {
        "raw_reviews": new_reviews,
        "logs": [log_message]
    }


def node_filter(state: ReviewState) -> ReviewState:
    """
    节点 2: 筛选高危评论
    使用 LLM 判断是否包含"故障/安全/质量"关键词
    """
    llm = init_llm()
    raw_reviews = state.get("raw_reviews", [])
    
    if not raw_reviews:
        log_message = "⚠️ 筛选节点：无新评论需要筛选"
        return {
            "critical_reviews": [],
            "logs": [log_message]
        }
    
    # 构建筛选 prompt，包含完整的 review_id
    reviews_text = "\n".join([
        f"评论ID {review['review_id']}: {review['review_text']} (评分: {review['rating']})"
        for i, review in enumerate(raw_reviews)
    ])
    
    # 提取所有 review_id 供参考
    all_review_ids = [review['review_id'] for review in raw_reviews]
    
    filter_prompt = f"""请分析以下用户评论，筛选出包含"故障/安全/质量问题"的高危评论。

评论列表：
{reviews_text}

筛选标准（满足任一条件即视为高危）：
1. 评分低于3星（rating < 3）
2. 包含故障、失效、安全问题、质量问题等关键词
3. 涉及产品缺陷或安全隐患（如：避障失效、云台抖动、功能不工作等）

请返回 JSON 格式，包含：
{{
  "critical_review_ids": [评论ID列表，必须使用完整的review_id，例如: {all_review_ids[:2] if len(all_review_ids) >= 2 else all_review_ids}],
  "reason": "筛选原因"
}}

重要：
- 必须使用完整的 review_id（包含时间戳部分）
- 请确保包含所有符合条件的高危评论ID
- 只返回 JSON，不要有其他说明"""
    
    try:
        response = llm.invoke([HumanMessage(content=filter_prompt)])
        answer = response.content if hasattr(response, 'content') else str(response)
        
        # 解析 JSON
        json_str = answer.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()
        
        result = json.loads(json_str)
        critical_ids = result.get("critical_review_ids", [])
        
        # 筛选出高危评论（支持完整ID或base_id匹配）
        critical_reviews = []
        for review in raw_reviews:
            review_id = review.get("review_id", "")
            # 尝试完整ID匹配
            if review_id in critical_ids:
                critical_reviews.append(review)
            else:
                # 尝试base_id匹配（如果LLM返回的是数字ID）
                base_id = review_id.split("_")[0] if "_" in review_id else review_id
                if str(base_id) in [str(cid) for cid in critical_ids] or base_id in [str(cid) for cid in critical_ids]:
                    critical_reviews.append(review)
        
        log_message = f"🔍 筛选节点：从 {len(raw_reviews)} 条评论中筛选出 {len(critical_reviews)} 条高危评论"
        if critical_reviews:
            log_message += f" (ID: {[r.get('review_id') for r in critical_reviews]})"
        elif critical_ids:
            log_message += f" | LLM返回的ID: {critical_ids}，但匹配失败"
        
        return {
            "critical_reviews": critical_reviews,
            "logs": [log_message]
        }
        
    except Exception as e:
        # 如果 LLM 筛选失败，使用降级规则：rating < 3 或包含关键词
        keywords = ["故障", "失效", "问题", "坏", "不工作", "安全", "危险", "质量", "避障", "抖动", "不稳定", "撞", "差点", "虚标", "欺骗"]
        critical_reviews = []
        
        for review in raw_reviews:
            rating = review.get("rating", 5)
            review_text = review.get("review_text", "")
            
            # 评分低于3星，或者包含关键词
            if rating < 3 or any(keyword in review_text for keyword in keywords):
                critical_reviews.append(review)
        
        log_message = f"🔍 筛选节点（降级模式）：筛选出 {len(critical_reviews)} 条高危评论"
        if critical_reviews:
            log_message += f" (ID: {[r.get('review_id') for r in critical_reviews]})"
        log_message += f" | LLM错误: {str(e)[:50]}"
        
        return {
            "critical_reviews": critical_reviews,
            "logs": [log_message]
        }


def node_rag_analysis(state: ReviewState) -> ReviewState:
    """
    节点 3: RAG 归因分析
    暂时使用基础逻辑，简单调用 LLM 生成归因
    """
    llm = init_llm()
    critical_reviews = state.get("critical_reviews", [])
    
    if not critical_reviews:
        log_message = "⚠️ RAG 分析节点：无高危评论需要分析"
        return {
            "rag_analysis_results": [],
            "logs": [log_message]
        }
    
    rag_results = []
    
    for review in critical_reviews:
        review_text = review.get("review_text", "")
        review_id = review.get("review_id")
        
        # 基础 RAG 分析（占位逻辑）
        # TODO: 后续可以接入真实的向量检索
        rag_prompt = f"""请分析以下用户反馈，判断这是用户使用问题还是产品缺陷。

用户反馈：{review_text}

请返回 JSON 格式：
{{
  "review_id": {review_id},
  "conclusion": "✅ 产品已知局限" 或 "⚠️ 需进一步调查" 或 "❓ 用户使用问题",
  "reason": "分析原因"
}}

只返回 JSON，不要有其他说明。"""
        
        try:
            response = llm.invoke([HumanMessage(content=rag_prompt)])
            answer = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 JSON
            json_str = answer.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            elif json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            result = json.loads(json_str)
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": result.get("conclusion", "❓ 需要人工判断"),
                "reason": result.get("reason", "")
            })
            
        except Exception as e:
            # 如果解析失败，使用默认值
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": "❓ 需要人工判断",
                "reason": f"LLM 分析失败: {str(e)}"
            })
    
    log_message = f"📄 RAG 分析节点：完成 {len(rag_results)} 条评论的归因分析"
    
    return {
        "rag_analysis_results": rag_results,
        "logs": [log_message]
    }


def node_action_gen(state: ReviewState) -> ReviewState:
    """
    节点 4: 生成行动建议
    基于归因生成 JSON 格式的 Action
    """
    llm = init_llm()
    rag_results = state.get("rag_analysis_results", [])
    
    if not rag_results:
        log_message = "⚠️ 行动生成节点：无归因结果需要生成行动"
        return {
            "action_plans": [],
            "logs": [log_message]
        }
    
    action_plans = []
    
    for rag_result in rag_results:
        review_text = rag_result.get("review_text", "")
        conclusion = rag_result.get("conclusion", "")
        reason = rag_result.get("reason", "")
        
        # 生成行动建议
        action_prompt = f"""基于以下归因分析，生成具体的行动建议。

用户反馈：{review_text}
归因结论：{conclusion}
分析原因：{reason}

请返回 JSON 格式：
{{
  "action_type": "Jira Ticket" 或 "Doc Update" 或 "Email Draft" 或 "Meeting",
  "title": "行动标题",
  "content": "详细内容",
  "priority": "High" 或 "Medium" 或 "Low"
}}

只返回 JSON，不要有其他说明。"""
        
        try:
            response = llm.invoke([HumanMessage(content=action_prompt)])
            answer = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 JSON
            json_str = answer.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            elif json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            result = json.loads(json_str)
            action_plans.append({
                "review_id": rag_result.get("review_id"),
                "action_type": result.get("action_type", "Jira Ticket"),
                "title": result.get("title", ""),
                "content": result.get("content", ""),
                "priority": result.get("priority", "Medium")
            })
            
        except Exception as e:
            # 如果解析失败，使用默认值
            action_plans.append({
                "review_id": rag_result.get("review_id"),
                "action_type": "Jira Ticket",
                "title": f"处理评论 {rag_result.get('review_id')} 的问题",
                "content": review_text,
                "priority": "Medium"
            })
    
    log_message = f"💡 行动生成节点：生成 {len(action_plans)} 个行动建议"
    
    return {
        "action_plans": action_plans,
        "logs": [log_message]
    }


# ==================== 条件路由 ====================
def should_continue_analysis(state: ReviewState) -> Literal["rag_analysis", "end"]:
    """判断是否继续 RAG 分析"""
    critical_reviews = state.get("critical_reviews", [])
    if len(critical_reviews) > 0:
        return "rag_analysis"
    return "end"


# ==================== 构建图 ====================
def build_graph():
    """构建 LangGraph 工作流"""
    # 创建状态图，指定 reducer
    workflow = StateGraph(ReviewState)
    
    # 添加节点
    workflow.add_node("monitor", node_monitor)
    workflow.add_node("filter", node_filter)
    workflow.add_node("rag_analysis", node_rag_analysis)
    workflow.add_node("action_gen", node_action_gen)
    
    # 设置入口点
    workflow.set_entry_point("monitor")
    
    # 添加边
    workflow.add_edge("monitor", "filter")
    
    # 条件路由：filter 后判断是否继续
    workflow.add_conditional_edges(
        "filter",
        should_continue_analysis,
        {
            "rag_analysis": "rag_analysis",
            "end": END
        }
    )
    
    workflow.add_edge("rag_analysis", "action_gen")
    workflow.add_edge("action_gen", END)
    
    # 编译图
    graph_app = workflow.compile()
    
    return graph_app


# ==================== 导出 ====================
# 创建全局图实例
graph_app = build_graph()


if __name__ == "__main__":
    # 测试工作流
    initial_state = {
        "raw_reviews": [],
        "critical_reviews": [],
        "rag_analysis_results": [],
        "action_plans": [],
        "logs": []
    }
    
    print("🚀 开始运行 ReviewOps 工作流...")
    result = graph_app.invoke(initial_state)
    
    print("\n📊 最终状态：")
    print(f"原始评论数: {len(result.get('raw_reviews', []))}")
    print(f"高危评论数: {len(result.get('critical_reviews', []))}")
    print(f"归因结果数: {len(result.get('rag_analysis_results', []))}")
    print(f"行动建议数: {len(result.get('action_plans', []))}")
    
    print("\n📝 日志：")
    for log in result.get("logs", []):
        print(f"  {log}")
    
    print("\n💡 行动建议：")
    for action in result.get("action_plans", []):
        print(f"  - {action.get('title')} ({action.get('action_type')})")

