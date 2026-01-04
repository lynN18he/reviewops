"""
行动生成节点：基于归因结果生成行动建议
"""

import json
from src.state import ReviewState
from src.utils import init_llm
from src.config import ActionConfig
from langchain_core.messages import HumanMessage


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
                "action_type": result.get("action_type", ActionConfig.DEFAULT_ACTION_TYPE),
                "title": result.get("title", ""),
                "content": result.get("content", ""),
                "priority": result.get("priority", ActionConfig.DEFAULT_PRIORITY)
            })
            
        except Exception as e:
            # 如果解析失败，使用默认值
            action_plans.append({
                "review_id": rag_result.get("review_id"),
                "action_type": ActionConfig.DEFAULT_ACTION_TYPE,
                "title": f"处理评论 {rag_result.get('review_id')} 的问题",
                "content": review_text,
                "priority": ActionConfig.DEFAULT_PRIORITY
            })
    
    log_message = f"💡 行动生成节点：生成 {len(action_plans)} 个行动建议"
    
    return {
        "action_plans": action_plans,
        "logs": [log_message]
    }

