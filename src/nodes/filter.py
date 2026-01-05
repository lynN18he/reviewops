"""
筛选节点：筛选高危评论
"""

import json
from src.state import ReviewState
from src.utils import init_llm
from langchain_core.messages import HumanMessage


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
        # 如果 LLM 筛选失败，使用降级规则：rating < threshold 或包含关键词
        from src.config import FilterConfig
        keywords = FilterConfig.KEYWORDS
        rating_threshold = FilterConfig.RATING_THRESHOLD
        critical_reviews = []
        
        for review in raw_reviews:
            rating = review.get("rating", 5)
            review_text = review.get("review_text", "")
            
            # 评分低于阈值，或者包含关键词
            if rating < rating_threshold or any(keyword in review_text for keyword in keywords):
                critical_reviews.append(review)
        
        log_message = f"🔍 筛选节点（降级模式）：筛选出 {len(critical_reviews)} 条高危评论"
        if critical_reviews:
            log_message += f" (ID: {[r.get('review_id') for r in critical_reviews]})"
        log_message += f" | LLM错误: {str(e)[:50]}"
        
        return {
            "critical_reviews": critical_reviews,
            "logs": [log_message]
        }

