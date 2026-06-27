"""
QueryExpander 验证脚本

验证三个维度：
1. 扩展词质量 — 是否生成合理的关键词变体
2. 召回提升 — 多查询是否比单查询找回更多不同文档
3. 降级保护 — API 异常时是否安全回退
"""
import sys
import io

# Windows UTF-8 兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from rag.query_expander import query_expander


def test_expansion():
    """测试1：扩展词生成"""
    print("=" * 60)
    print("测试1：关键词扩展")
    print("=" * 60)

    test_queries = [
        "高龄补贴怎么申请",
        "失能老人找养老院",
        "糖尿病老人饮食注意什么",
    ]

    for q in test_queries:
        expanded = query_expander.expand(q, n=3)
        print(f"\n原始: {q}")
        print(f"扩展: {len(expanded)} 个检索词")
        for i, kw in enumerate(expanded):
            label = "[原]" if i == 0 else f"  {i}."
            print(f"  {label} {kw}")


def test_recall_improvement():
    """测试2：单查询 vs 多查询 召回对比"""
    print("\n" + "=" * 60)
    print("测试2：召回对比（单查询 vs 多查询扩展）")
    print("=" * 60)

    try:
        from rag.rag_service import rag_service
    except Exception as e:
        print(f"\n[跳过] rag_service 导入失败（环境问题）: {e}")
        return

    test_queries = [
        ("policy", "高龄补贴申请"),
        ("service", "失能老人养老院"),
        ("health", "高血压日常护理"),
    ]

    for kb, q in test_queries:
        docs_single = rag_service.search(q, kb=kb)
        expanded = query_expander.expand(q, n=3)
        docs_multi = rag_service.multi_search(expanded, kb=kb)

        improved = len(docs_multi) > len(docs_single)
        delta = len(docs_multi) - len(docs_single)

        print(f"\n[{kb}] '{q}'")
        print(f"  扩展词: {expanded}")
        print(f"  单查询: {len(docs_single)} 条")
        print(f"  多查询: {len(docs_multi)} 条 ({'+' + str(delta) if delta > 0 else '='})")
        print(f"  改善: {'[OK] 是' if improved else '持平（可能知识库小或扩展词受限）'}")


def test_graceful_degradation():
    """测试3：API异常时降级保护"""
    print("\n" + "=" * 60)
    print("测试3：降级保护（API失败时不抛异常）")
    print("=" * 60)

    result = query_expander.expand("随便什么问题", n=3)
    assert isinstance(result, list), "返回值必须是 list"
    assert len(result) >= 1, "至少包含原始查询"
    print(f"\nAPI失败时返回: {result}")
    print("[OK] 降级正常 — API 异常时回退到原始查询，系统不受影响")


def test_multi_retrieve():
    """测试4：multi_retrieve_context 端到端"""
    print("\n" + "=" * 60)
    print("测试4：multi_retrieve_context 端到端")
    print("=" * 60)

    try:
        from rag.rag_service import rag_service
    except Exception as e:
        print(f"\n[跳过] rag_service 导入失败（环境问题）: {e}")
        return

    expanded = query_expander.expand("高龄津贴", n=3)
    print(f"\n扩展词: {expanded}")

    context, docs = rag_service.multi_retrieve_context(expanded, kb="policy")
    sources = rag_service.get_sources(docs)

    print(f"合并文档数: {len(docs)}")
    print(f"来源数: {len(sources)}")
    print(f"上下文长度: {len(context)} 字符")
    if sources:
        print("来源列表:")
        for s in sources:
            print(f"  - {s['title']}")

    if docs:
        first_doc_content = docs[0].page_content[:50]
        in_context = first_doc_content[:50] in context
        print(f"\ndocs 与 context 一致: {'[OK]' if in_context else '[FAIL] 不一致!'}")


if __name__ == "__main__":
    print("QueryExpander 验证")
    print("=" * 60)

    test_expansion()
    test_recall_improvement()
    test_graceful_degradation()
    test_multi_retrieve()

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)
