"""
RAG 分析节点：基于产品说明书进行归因分析
"""

import json
import os
from src.state import ReviewState
from src.utils import init_llm
from langchain_core.messages import HumanMessage


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
        from src.config import EmbeddingConfig, VectorStoreConfig
        
        api_key = EmbeddingConfig.get_api_key()
        if api_key:
            embeddings = DashScopeEmbeddings(
                model=EmbeddingConfig.MODEL,
                dashscope_api_key=api_key
            )
            vectorstore = Chroma(
                persist_directory=VectorStoreConfig.PERSIST_DIRECTORY,
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
                    from src.config import VectorStoreConfig
                    docs_with_scores = vectorstore.similarity_search_with_score(query, k=VectorStoreConfig.TOP_K)
                    # 过滤低相关性结果
                    relevant_docs = []
                    for doc, distance in docs_with_scores:
                        if distance < VectorStoreConfig.DISTANCE_THRESHOLD:
                            relevant_docs.append(doc)
                    
                    if relevant_docs:
                        # 构建上下文
                        max_docs = min(VectorStoreConfig.MAX_DOCS_IN_CONTEXT, len(relevant_docs))
                        context = "\n\n".join([
                            doc.page_content[:VectorStoreConfig.MAX_CONTEXT_LENGTH] 
                            for doc in relevant_docs[:max_docs]
                        ])
                        
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

