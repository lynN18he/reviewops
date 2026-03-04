"""
筛选节点：筛选高危工单（P0/P1）
B2B SaaS 运维标准：核心业务阻断、系统级报错、客户情绪激烈且资损
"""

import json
from src.state import ReviewState
from src.utils import init_llm
from langchain_core.messages import HumanMessage

# 降级模式：LLM 失败时，工单文本包含以下任一关键词即视为高危
FALLBACK_SAAS_KEYWORDS = [
    "502", "504", "白屏", "宕机", "全不更新", "无法登陆",
    "无法登录", "登录失败", "同步失败", "订单同步", "大面积", "业务停摆",
    "资损", "理赔", "403", "401", "鉴权失效", "数据库超时",
]


def node_filter(state: ReviewState) -> ReviewState:
    """
    节点 2: 筛选高危工单（P0/P1）
    使用 LLM 按 B2B SaaS 运维标准判断是否为核心业务阻断、系统级报错或高情绪资损类工单。
    """
    llm = init_llm()
    raw_reviews = state.get("raw_reviews", [])

    if not raw_reviews:
        log_message = "⚠️ 筛选节点：无新工单需要筛选"
        return {
            "critical_reviews": [],
            "logs": [log_message]
        }

    tickets_text = "\n".join([
        f"工单ID {r['review_id']}: {r['review_text']}"
        for r in raw_reviews
    ])
    all_review_ids = [r["review_id"] for r in raw_reviews]

    filter_prompt = f"""请分析以下 B2B 电商/物流 SaaS 技术支持工单，筛选出需要优先处理的高危工单（P0/P1）。

工单列表：
{tickets_text}

高危工单筛选标准（满足任一即视为高危）：
1. 涉及核心业务阻断：无法登陆、页面白屏、订单同步大面积停滞、系统不可用等。
2. 包含明确的系统级报错信息：API 返回 502/504、数据库超时、403/401 鉴权彻底失效等。
3. 客户情绪极其激烈且涉及资损：业务停摆、要求理赔、强烈投诉等。

请返回 JSON 格式：
{{
  "critical_review_ids": [工单ID列表，必须使用完整ID，例如: {all_review_ids[:2] if len(all_review_ids) >= 2 else all_review_ids}],
  "reason": "筛选原因简述"
}}

重要：
- 必须使用完整的工单 ID（与上述列表一致）
- 请确保包含所有符合条件的高危工单 ID
- 只返回 JSON，不要有其他说明"""

    try:
        response = llm.invoke([HumanMessage(content=filter_prompt)])
        answer = response.content if hasattr(response, 'content') else str(response)

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

        critical_tickets = []
        for review in raw_reviews:
            review_id = review.get("review_id", "")
            if review_id in critical_ids:
                critical_tickets.append(review)
            else:
                base_id = review_id.split("_")[0] if "_" in review_id else review_id
                if str(base_id) in [str(cid) for cid in critical_ids] or base_id in [str(cid) for cid in critical_ids]:
                    critical_tickets.append(review)

        log_message = f"🔍 筛选节点：从 {len(raw_reviews)} 条工单中筛选出 {len(critical_tickets)} 条高危工单"
        if critical_tickets:
            log_message += f" (ID: {[r.get('review_id') for r in critical_tickets]})"
        elif critical_ids:
            log_message += f" | LLM返回的ID: {critical_ids}，但匹配失败"

        return {
            "critical_reviews": critical_tickets,
            "logs": [log_message]
        }

    except Exception as e:
        # 降级：按关键词正则/字符串匹配，不再使用 rating
        critical_tickets = []
        for review in raw_reviews:
            text = review.get("review_text", "") or ""
            if any(kw in text for kw in FALLBACK_SAAS_KEYWORDS):
                critical_tickets.append(review)

        log_message = f"🔍 筛选节点（降级模式）：从 {len(raw_reviews)} 条工单中筛选出 {len(critical_tickets)} 条高危工单"
        if critical_tickets:
            log_message += f" (ID: {[r.get('review_id') for r in critical_tickets]})"
        log_message += f" | LLM错误: {str(e)[:50]}"

        return {
            "critical_reviews": critical_tickets,
            "logs": [log_message]
        }
