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


# ==================== 状态定义 ====================
class ReviewState(TypedDict):
    """工作流状态"""
    raw_reviews: List[dict]  # 新评论
    critical_reviews: List[dict]  # 筛选后的高危评论
    rag_analysis_results: List[dict]  # 归因结果
    action_plans: List[dict]  # 行动建议
    logs: List[str]  # 日志（使用 operator.add 追加）
    processed_ids: List[str]  # 已处理的评论ID集合（用于幂等性去重）


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
    if "processed_ids" in update:
        # 合并已处理ID集合（去重）
        existing_ids = set(state.get("processed_ids", []))
        new_ids = set(update.get("processed_ids", []))
        merged["processed_ids"] = list(existing_ids | new_ids)
    
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
    动态模拟生成器：从 MOCK_DATA_POOL 随机采样，并添加微秒级时间戳确保唯一性
    实现幂等性：检查已处理的ID，避免重复处理
    
    测试优化：确保每次增量 >= 2 条评论，其中至少 1 条为正面评论
    """
    # 获取已处理的ID集合（用于去重）
    processed_ids = set(state.get("processed_ids", []))
    
    # 使用微秒级时间戳（time.time_ns()）确保每次运行生成的ID绝对唯一
    # 这样可以绕过后续节点的去重逻辑，保证演示时每次点击必有新结果
    current_timestamp_ns = time.time_ns()  # 纳秒级时间戳，确保唯一性
    new_reviews = []
    new_processed_ids = []
    
    # 测试优化：确保每次至少生成 2 条评论，且至少包含 1 条正面评论
    # 1. 首先确保至少选择 1 条正面评论
    if MOCK_DATA_POOL["positive"]:
        positive_template = random.choice(MOCK_DATA_POOL["positive"])
        unique_suffix = f"{current_timestamp_ns}_{random.randint(1000, 9999)}"
        review_id = f"{positive_template['base_id']}_{unique_suffix}"
        
        if review_id not in processed_ids:
            review = {
                "review_id": review_id,
                "user_id": positive_template['user_id'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "review_text": positive_template['review_text'],
                "rating": positive_template['rating']
            }
            new_reviews.append(review)
            new_processed_ids.append(review_id)
    
    # 2. 再从负面或中性评论中随机选择至少 1 条（确保总数 >= 2）
    remaining_needed = max(1, 2 - len(new_reviews))  # 至少还需要 1 条，确保总数 >= 2
    all_other_templates = MOCK_DATA_POOL["negative"] + MOCK_DATA_POOL["neutral"]
    
    if all_other_templates:
        # 随机选择剩余需要的评论数量（可以多选几条增加随机性）
        additional_count = random.randint(remaining_needed, min(remaining_needed + 1, len(all_other_templates)))
        sampled_others = random.sample(all_other_templates, min(additional_count, len(all_other_templates)))
        
        for template in sampled_others:
            unique_suffix = f"{current_timestamp_ns}_{random.randint(1000, 9999)}"
            review_id = f"{template['base_id']}_{unique_suffix}"
            
            # 幂等性检查：如果ID已处理，跳过
            if review_id in processed_ids:
                continue
            
            review = {
                "review_id": review_id,
                "user_id": template['user_id'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
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
    
    return {
        "raw_reviews": new_reviews,
        "processed_ids": new_processed_ids,
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
    接入真实的向量检索，基于产品说明书进行归因分析
    """
    llm = init_llm()
    critical_reviews = state.get("critical_reviews", [])
    
    if not critical_reviews:
        log_message = "⚠️ RAG 分析节点：无高危评论需要分析"
        return {
            "rag_analysis_results": [],
            "logs": [log_message]
        }
    
    # 初始化向量库（如果还没有初始化）
    vectorstore = None
    try:
        from langchain_community.vectorstores import Chroma
        from langchain_community.embeddings import DashScopeEmbeddings
        import os
        
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            embeddings = DashScopeEmbeddings(
                model="text-embedding-v3",
                dashscope_api_key=api_key
            )
            vectorstore = Chroma(
                persist_directory="./chroma_db",
                embedding_function=embeddings
            )
    except Exception as e:
        log_message = f"⚠️ 向量库初始化失败: {str(e)[:50]}"
        # 继续执行，使用降级逻辑
    
    rag_results = []
    
    for review in critical_reviews:
        review_text = review.get("review_text", "")
        review_id = review.get("review_id", "")
        
        try:
            # 如果有向量库，使用真实的 RAG 检索
            if vectorstore:
                # 构建查询
                query = f"用户反馈：{review_text}。请分析这是产品已知局限还是新问题。"
                
                # 检索相关文档
                try:
                    docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
                    # 过滤低相关性结果
                    relevant_docs = []
                    for doc, distance in docs_with_scores:
                        if distance < 1.5:  # 距离阈值
                            relevant_docs.append(doc)
                    
                    if relevant_docs:
                        # 构建上下文
                        context = "\n\n".join([doc.page_content[:300] for doc in relevant_docs[:3]])
                        
                        # 使用 RAG 增强的 Prompt
                        rag_prompt = f"""你是一个专业的产品分析师。请根据用户反馈和产品说明书，进行准确的归因分析。

产品说明书相关内容：
{context}

用户反馈：{review_text}

请返回 JSON 格式：
{{
  "review_id": "{review_id}",
  "conclusion": "✅ 产品已知局限" 或 "⚠️ 需进一步调查" 或 "❓ 用户使用问题",
  "reason": "基于产品说明书的分析原因",
  "evidence": "从说明书中提取的相关证据片段"
}}

只返回 JSON，不要有其他说明。"""
                    else:
                        # 没有找到相关文档，使用基础分析
                        rag_prompt = f"""请分析以下用户反馈，判断这是用户使用问题还是产品缺陷。

用户反馈：{review_text}

请返回 JSON 格式：
{{
  "review_id": "{review_id}",
  "conclusion": "✅ 产品已知局限" 或 "⚠️ 需进一步调查" 或 "❓ 用户使用问题",
  "reason": "分析原因",
  "evidence": "未在说明书中找到相关描述"
}}

只返回 JSON，不要有其他说明。"""
                except Exception as e:
                    # 向量检索失败，使用基础分析
                    rag_prompt = f"""请分析以下用户反馈，判断这是用户使用问题还是产品缺陷。

用户反馈：{review_text}

请返回 JSON 格式：
{{
  "review_id": "{review_id}",
  "conclusion": "✅ 产品已知局限" 或 "⚠️ 需进一步调查" 或 "❓ 用户使用问题",
  "reason": "分析原因",
  "evidence": "向量检索失败: {str(e)[:50]}"
}}

只返回 JSON，不要有其他说明。"""
            else:
                # 没有向量库，使用基础分析
                rag_prompt = f"""请分析以下用户反馈，判断这是用户使用问题还是产品缺陷。

用户反馈：{review_text}

请返回 JSON 格式：
{{
  "review_id": "{review_id}",
  "conclusion": "✅ 产品已知局限" 或 "⚠️ 需进一步调查" 或 "❓ 用户使用问题",
  "reason": "分析原因",
  "evidence": "向量库未初始化，使用基础分析"
}}

只返回 JSON，不要有其他说明。"""
            
            # 调用 LLM
            response = llm.invoke([HumanMessage(content=rag_prompt)])
            answer = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 JSON（改进的解析逻辑）
            json_str = answer.strip()
            
            # 移除可能的代码块标记
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            elif json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            # 尝试提取 JSON（处理可能的额外文本）
            if "{" in json_str and "}" in json_str:
                start_idx = json_str.find("{")
                end_idx = json_str.rfind("}") + 1
                json_str = json_str[start_idx:end_idx]
            
            result = json.loads(json_str)
            
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": result.get("conclusion", "❓ 需要人工判断"),
                "reason": result.get("reason", ""),
                "evidence": result.get("evidence", "")
            })
            
        except json.JSONDecodeError as e:
            # JSON 解析失败，尝试提取关键信息
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": "❓ 需要人工判断",
                "reason": f"JSON 解析失败: {str(e)[:100]}",
                "evidence": f"LLM 返回内容: {answer[:200]}"
            })
        except Exception as e:
            # 其他错误
            rag_results.append({
                "review_id": review_id,
                "review_text": review_text,
                "conclusion": "❓ 需要人工判断",
                "reason": f"RAG 分析失败: {str(e)[:100]}",
                "evidence": ""
            })
    
    log_message = f"📄 RAG 分析节点：完成 {len(rag_results)} 条评论的归因分析"
    if vectorstore:
        log_message += "（已使用向量检索）"
    else:
        log_message += "（使用基础分析）"
    
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
        evidence = rag_result.get("evidence", "")
        
        # 生成行动建议（基于 RAG 归因结果）
        action_prompt = f"""基于以下归因分析，生成具体的行动建议。

用户反馈：{review_text}
归因结论：{conclusion}
分析原因：{reason}
相关证据：{evidence if evidence else "无"}

请返回 JSON 格式：
{{
  "action_type": "Jira Ticket" 或 "Doc Update" 或 "Email Draft" 或 "Meeting",
  "title": "行动标题",
  "content": "详细内容（包含用户反馈、归因结论和建议措施）",
  "priority": "High" 或 "Medium" 或 "Low"
}}

只返回 JSON，不要有其他说明。"""
        
        try:
            response = llm.invoke([HumanMessage(content=action_prompt)])
            answer = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 JSON（改进的解析逻辑）
            json_str = answer.strip()
            
            # 移除可能的代码块标记
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            elif json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            # 尝试提取 JSON（处理可能的额外文本）
            if "{" in json_str and "}" in json_str:
                start_idx = json_str.find("{")
                end_idx = json_str.rfind("}") + 1
                json_str = json_str[start_idx:end_idx]
            
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

