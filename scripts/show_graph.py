#!/usr/bin/env python3
"""
在终端查看 LangGraph 工作流图。
用法：
  python scripts/show_graph.py          # 打印 ASCII + Mermaid
  python scripts/show_graph.py -o graph.mmd   # 将 Mermaid 保存到文件
"""
import argparse
import sys

# 确保项目根在 path 中
sys.path.insert(0, ".")


def main():
    parser = argparse.ArgumentParser(description="查看 ReviewOps LangGraph 工作流图")
    parser.add_argument("-o", "--output", metavar="FILE", help="将 Mermaid 代码保存到文件（可用 mermaid.live 打开）")
    args = parser.parse_args()

    from src.graph import graph_app

    g = graph_app.get_graph()

    print("=" * 60)
    print("LangGraph 工作流 · ASCII 预览")
    print("=" * 60)
    try:
        print(g.draw_ascii())
    except ImportError as e:
        print("(需要安装 grandalf 才能显示 ASCII 图: pip install grandalf)")
        print(str(e))

    print()
    print("=" * 60)
    print("Mermaid 代码（可复制到 https://mermaid.live 渲染）")
    print("=" * 60)
    mermaid_code = g.draw_mermaid()
    print(mermaid_code)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"\n已保存到: {args.output}")


if __name__ == "__main__":
    main()
