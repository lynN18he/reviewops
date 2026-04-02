#!/usr/bin/env python3
"""
黄金基线数据库预热脚本
读取 test_tickets.csv，调用 LangGraph 工作流进行真实 LLM 分析，将完整结果写入 SQLite。
运行方式：python seed_db.py
完成后启动 streamlit run app.py，大盘将展示已分析的基线数据。

重要：
- 本脚本**不会**自动读取你改过的 Prompt / tools.py / rag 拒答逻辑；它只是**当时**跑一遍图并把结果写入 reviewops.db。
- 若你刚调整了 RAG 拒答、向量阈值、injest 切分或知识库内容，**必须重新执行** `python seed_db.py`（会先清空 tickets），否则大盘里仍是**上一次**写入的「冷启动」分析，看起来像「还在胡说八道」。
- 建议同时确认已 `python injest.py` 重建 chroma_db，与当前 saas_knowledge.txt 一致。
- 向量库路径默认固定在**仓库根目录**下的 `chroma_db`（与运行 `seed_db.py` 时的**当前工作目录**无关）；若仍 10/10 拒答，请检查 `VECTOR_DB_PATH` 是否指到了别的目录。
"""

import os
import sys

# 必须在导入 graph 之前设置，使 monitor 使用 test_tickets.csv 且全量处理
os.environ["MONITOR_SEED_CSV"] = "test_tickets.csv"

from dotenv import load_dotenv

load_dotenv()

from src.tongyi_check_response_patch import apply_patch

apply_patch()

# 校验 API Key
if not os.getenv("DASHSCOPE_API_KEY"):
    print("❌ 请设置环境变量 DASHSCOPE_API_KEY")
    sys.exit(1)

from src.services.database import get_database
from src.graph import graph_app


def _preflight_vector_store() -> tuple[bool, str]:
    """
    seed 前检查 Chroma 是否可用；避免跑完全图后才发现 10/10 未命中（工具全返回「未检索到相关文档」）。
    """
    if os.getenv("SEED_SKIP_VECTOR_CHECK", "").lower() in ("1", "true", "yes"):
        return True, "（已跳过向量库检查 SEED_SKIP_VECTOR_CHECK）"

    from src.config import VectorStoreConfig
    from src.tools import _get_vectorstore

    path = os.path.abspath(os.path.expanduser(VectorStoreConfig.PERSIST_DIRECTORY))
    if not os.path.isdir(path):
        return (
            False,
            f"未找到向量库目录:\n   {path}\n"
            "   请在项目根目录执行（注意文件名是 injest 不是 ingest）:\n"
            "   python injest.py",
        )
    vs = _get_vectorstore()
    if not vs:
        return (
            False,
            "无法初始化 Chroma 向量库（常为依赖或 Embedding 初始化失败）。\n"
            "   请确认已安装依赖、DASHSCOPE_API_KEY 有效，且 VECTOR_DB_PATH 指向正确目录。",
        )
    try:
        n = int(vs._collection.count())
    except Exception as e:
        return False, f"读取向量条数失败: {e}"
    if n <= 0:
        return (
            False,
            f"向量库目录存在但条数为 0:\n   {path}\n"
            "   请先构建知识库向量:\n"
            "   python injest.py",
        )
    return True, f"向量库就绪：{n} 条 · {path}"


def main():
    ok, msg = _preflight_vector_store()
    if not ok:
        print("❌ 向量库预检未通过，已中止 seed（避免全线 RAG 拒答写进库）。")
        print(msg)
        sys.exit(1)
    print(f"📚 {msg}")

    db = get_database()
    cleared = db.clear_all_tickets()
    if cleared > 0:
        print(f"🗑️ 已清空 {cleared} 条旧数据，准备重建基线...")

    initial_state = {
        "incr_tickets": [],
        "critical_tickets": [],
        "rag_analysis_results": [],
        "diagnosis_routes": [],
        "diagnosis_category": [],
        "processed_route_types": [],
        "action_plans": [],
        "logs": [],
        "processed_ids": [],
    }

    print("🚀 启动 LangGraph 工作流，对 test_tickets.csv 进行全量 LLM 分析...")
    final_state = initial_state.copy()
    for event in graph_app.stream(initial_state):
        for node_name, node_output in event.items():
            if isinstance(node_output, dict):
                final_state.update(node_output)
            if isinstance(node_output, dict) and "logs" in node_output:
                for log in node_output.get("logs", []):
                    print(f"  {log}")

    incr = final_state.get("incr_tickets", [])
    plans = final_state.get("action_plans", [])
    rag_list = final_state.get("rag_analysis_results", [])
    count = len(incr)
    print(f"\n✅ 黄金基线数据库预热完成！共处理 {count} 条数据。")
    if plans:
        print(f"   其中 {len(plans)} 条已生成行动建议并写入 DB（status=analyzed）。")
    # 便于确认「知识库不相关 → 拒答」是否在当次运行中生效（依赖 rag 节点写入的 knowledge_relevant）
    if rag_list:
        refused = sum(1 for r in rag_list if r.get("knowledge_relevant") is False)
        print(f"   RAG 拒答/低相关（knowledge_relevant=false）: {refused} / {len(rag_list)} 条。")
        if refused == 0:
            print(
                "   ℹ️ 若预期应有拒答却仍全为 true，请检查 Prompt 与 injest 知识库是否一致。"
            )
        if refused == len(rag_list) and len(rag_list) > 0:
            print(
                "   ⚠️ 本次全部为 RAG 拒答。请确认已 `python injest.py`、Embedding 可用，"
                "并视情况放宽 RAG_SCORE_THRESHOLD。修复后请重新 `python seed_db.py`。"
            )


if __name__ == "__main__":
    main()
