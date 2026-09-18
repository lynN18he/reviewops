"""
测试 RAG 分析节点
"""

import pytest
from unittest.mock import patch, MagicMock
from src.nodes.rag import node_rag_analysis
from src.state import TicketState


class TestNodeRagAnalysis:
    """测试 RAG 分析节点（工单归因）"""

    def test_node_rag_empty_critical_tickets(self):
        """测试空高危工单列表"""
        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert result["rag_analysis_results"] == []
        assert len(result["logs"]) > 0
        assert "无高危工单需要分析" in result["logs"][0]

    @patch("src.nodes.rag._search_chroma")
    @patch("src.nodes.rag.init_llm")
    def test_node_rag_with_llm_success(self, mock_init_llm, mock_search_chroma):
        """测试 LLM 归因分析成功（含未调工具时的兜底检索 + 收口 llm.invoke）"""
        mock_search_chroma.return_value = "SOP片段\n[METADATA_SOURCE: SOP-001]"
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = ""
        mock_response.tool_calls = None
        mock_bound = MagicMock()
        mock_bound.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_bound
        final = MagicMock()
        final.content = """{
            "knowledge_relevant": true,
            "conclusion": "✅ 配置问题，建议按 SOP 重新授权",
            "reason": "知识库/SOP 中有说明",
            "evidence": "相关证据"
        }"""
        mock_llm.invoke.return_value = final
        mock_init_llm.return_value = mock_llm

        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [
                {
                    "ticket_id": "TIK-054",
                    "ticket_content": "调用 create order API 一直返回 401 Unauthorized",
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["ticket_id"] == "TIK-054"
        assert "conclusion" in rag_result
        assert "reason" in rag_result
        assert "evidence" in rag_result
        assert rag_result.get("knowledge_relevant") is True

    @patch("src.nodes.rag._search_chroma")
    @patch("src.nodes.rag.init_llm")
    def test_node_rag_json_parse_error(self, mock_init_llm, mock_search_chroma):
        """测试 JSON 解析错误处理"""
        mock_search_chroma.return_value = "未检索到相关文档"
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = ""
        mock_response.tool_calls = None
        mock_bound = MagicMock()
        mock_bound.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_bound
        mock_llm.invoke.return_value = MagicMock(content="这不是有效的 JSON")
        mock_init_llm.return_value = mock_llm

        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [
                {
                    "ticket_id": "TIK-055",
                    "ticket_content": "批量查询接口报 429",
                }
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)

        assert len(result["rag_analysis_results"]) > 0
        rag_result = result["rag_analysis_results"][0]
        assert rag_result["conclusion"] == "❓ 需要人工判断"
        assert (
            "JSON 解析失败" in rag_result["reason"]
            or "RAG 分析失败" in rag_result["reason"]
            or "模型未返回有效 JSON" in rag_result["reason"]
        )

    @patch("src.nodes.rag.init_llm")
    def test_node_rag_llm_network_error_user_facing(self, mock_init_llm):
        """LLM 连接失败时不应把 HTTPSConnectionPool 等原文写入 reason"""
        mock_llm = MagicMock()
        mock_bound = MagicMock()
        mock_bound.invoke.side_effect = ConnectionError(
            "HTTPSConnectionPool(host='dashscope.aliyuncs.com', port=443): Max retries exceeded"
        )
        mock_llm.bind_tools.return_value = mock_bound
        mock_init_llm.return_value = mock_llm

        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [
                {"ticket_id": "TIK-NET", "ticket_content": "测试网络异常展示"},
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)
        rag_result = result["rag_analysis_results"][0]
        assert "HTTPSConnectionPool" not in (rag_result.get("reason") or "")
        assert "dashscope.aliyuncs.com" not in (rag_result.get("reason") or "")
        assert rag_result.get("knowledge_relevant") is False
        assert "网络" in (rag_result.get("conclusion") or "") or "暂不可用" in (rag_result.get("conclusion") or "")

    @patch("src.nodes.rag.init_llm")
    @patch("src.nodes.rag.get_support_agent_tools")
    def test_tool_calls_then_plain_llm_for_json(self, mock_get_tools, mock_init_llm):
        """首轮仅 tool_calls、content 为空时，应执行工具后用未绑定工具的 llm.invoke 产出 JSON"""
        from langchain_core.tools import tool

        @tool
        def fake_search(query: str) -> str:
            """测试用假检索。"""
            return "hit doc\n[METADATA_SOURCE: SOP-001]"

        mock_get_tools.return_value = [fake_search]

        first = MagicMock()
        first.content = ""
        first.tool_calls = [
            {"id": "call_1", "name": "fake_search", "args": {"query": "x"}},
        ]
        final_json = MagicMock()
        final_json.content = """{
            "knowledge_relevant": true,
            "conclusion": "配置问题",
            "reason": "SOP",
            "evidence": "来源索引: [SOP-001]"
        }"""

        mock_bound = MagicMock()
        mock_bound.invoke.return_value = first

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound
        mock_llm.invoke.return_value = final_json
        mock_init_llm.return_value = mock_llm

        state: TicketState = {
            "incr_tickets": [],
            "critical_tickets": [
                {"ticket_id": "TIK-TC", "ticket_content": "401 错误"},
            ],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": [],
            "processed_ids": [],
        }

        result = node_rag_analysis(state)
        rag = result["rag_analysis_results"][0]
        assert rag["conclusion"] == "配置问题"
        assert rag.get("knowledge_relevant") is True
        mock_llm.invoke.assert_called_once()


def test_user_facing_rag_failure_dashscope_quota():
    from src.nodes.rag import _user_facing_rag_failure

    exc = RuntimeError("code: AllocationQuota.FreeTierOnly message: free tier exhausted")
    conclusion, reason, _ = _user_facing_rag_failure(exc)
    assert "额度" in conclusion
    assert "百炼" in reason or "免费" in reason


def test_user_facing_rag_failure_keyerror_request():
    from src.nodes.rag import _user_facing_rag_failure

    conclusion, reason, _ = _user_facing_rag_failure(KeyError("request"))
    assert "KeyError" in reason or "掩盖" in reason
