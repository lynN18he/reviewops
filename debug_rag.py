#!/usr/bin/env python3
"""
单点 RAG 调试：不走 DB / LangGraph，硬编码一条工单，逐步 print LLM 与工具原始交互。
运行：在项目根目录执行  python debug_rag.py
需已配置 DASHSCOPE_API_KEY；向量库需可用时工具才会返回非「未检索到相关文档」。
"""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.getenv("DASHSCOPE_API_KEY"):
    print("❌ 请设置环境变量 DASHSCOPE_API_KEY（可在 .env 中配置）")
    sys.exit(1)

from src.tongyi_check_response_patch import apply_patch

apply_patch()

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.tools import AGENT_SYSTEM_PROMPT, get_support_agent_tools
from src.utils import init_llm


def _tool_call_id(tc) -> str:
    return tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "") or ""


def _tool_call_name(tc):
    return tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)


def _tool_call_args(tc) -> dict:
    raw = (tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _normalize_msg_content(content) -> str:
    """与 rag 节点一致：str 或 Tongyi 的 content block 列表 → 可打印、可解析的字符串。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts).strip()
    return str(content).strip()


def _extract_json_substring(text: str) -> str:
    s = text.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    if "{" in s and "}" in s:
        return s[s.find("{") : s.rfind("}") + 1]
    return s


def debug_single_ticket() -> None:
    print("========== 🚀 开始单点调试 ==========")

    llm = init_llm()
    tools = get_support_agent_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    test_query = (
        "2月29号创建的订单全部显示成3月1号，我们这边没有任何改动，这种日期错误太低级了"
    )
    print(f"📥 [输入测试问题]: {test_query}\n")
    print(f"📋 [System prompt 长度]: {len(AGENT_SYSTEM_PROMPT)} 字符\n")

    messages: list = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=test_query),
    ]

    try:
        print("⏳ [发起第一轮 LLM 调用] bind_tools + invoke ...")
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        print(f"🤖 [第一轮原始返回 - content 类型]: {type(ai_msg.content).__name__}")
        print(f"🤖 [第一轮原始返回 - content]: {ai_msg.content!r}")
        print(f"🤖 [第一轮规范化 content]: {_normalize_msg_content(ai_msg.content)!r}")

        tcalls = getattr(ai_msg, "tool_calls", None) or []
        print(f"🛠️ [第一轮原始返回 - tool_calls 条数]: {len(tcalls)}")
        print(f"🛠️ [第一轮原始返回 - tool_calls 原文]: {tcalls!r}\n")

        if tcalls:
            for i, tc in enumerate(tcalls):
                name = _tool_call_name(tc)
                tc_id = _tool_call_id(tc)
                args = dict(_tool_call_args(tc))
                print(f"⚙️ [工具 {i + 1}/{len(tcalls)}] name={name!r} id={tc_id!r} args={args!r}")
                tool_fn = tool_map.get(name) if name else None
                if tool_fn:
                    if "query" not in args:
                        args["query"] = test_query
                    print(f"   → invoke 参数(补全 query 后): {args!r}")
                    tool_result = tool_fn.invoke(args)
                    full = str(tool_result)
                    print(f"📄 [工具检索结果全文长度]: {len(full)} 字符")
                    print(f"📄 [工具检索结果前 200 字]: {full[:200]!r}...")
                    if len(full) > 200:
                        print(f"📄 [工具检索结果后 120 字]: ...{full[-120:]!r}")
                    messages.append(
                        ToolMessage(content=str(tool_result), tool_call_id=tc_id)
                    )
                else:
                    print("❌ [未找到对应工具]")
                    messages.append(
                        ToolMessage(content="未知工具", tool_call_id=tc_id)
                    )

            print(f"\n📚 [第二轮前 messages 条数]: {len(messages)} (system + human + ai + tools)\n")
            print("⏳ [发起第二轮 LLM 调用] 未 bind_tools，携带 ToolMessage ...")
            final_msg = llm.invoke(messages)
            result_text = _normalize_msg_content(getattr(final_msg, "content", None))
            print(f"🎯 [第二轮返回 content 类型]: {type(final_msg.content).__name__}")
            print(f"🎯 [大模型最终原始输出]:\n{result_text}\n")
        else:
            print("⚠️ [大模型未调用任何工具，直接使用第一轮 content 作为最终输出]\n")
            result_text = _normalize_msg_content(ai_msg.content)
            print(f"🎯 [大模型最终原始输出]:\n{result_text}\n")

        print("🧹 [尝试解析 JSON]...")
        clean_json = _extract_json_substring(result_text)
        print(f"🧹 [抽取后待解析子串长度]: {len(clean_json)} 字符")
        print(f"🧹 [抽取后待解析子串预览]: {clean_json[:400]!r}{'...' if len(clean_json) > 400 else ''}\n")
        parsed_data = json.loads(clean_json)
        print("✅ [JSON 解析成功]")
        print(json.dumps(parsed_data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n🚨 [调试抛出异常]: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_single_ticket()
