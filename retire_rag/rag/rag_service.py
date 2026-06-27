"""
RAG 检索服务：支持4个养老知识库的定向检索
"""
from langchain_core.documents import Document

from rag.vector_store import VectorStoreService
from utils.logger_handler import logger


class RagService:
    """多知识库RAG检索服务

    提供4个知识库的独立检索能力：
    - policy:   政策法规（补贴、长护险、养老机构管理条例）
    - service:  养老服务（项目说明、预约流程、收费标准、FAQ）
    - health:   健康科普（慢性病护理、用药、饮食、急救）
    - platform: 平台操作（使用指南、账号注册、预约流程）
    """

    KB_NAMES = ["policy", "service", "health", "platform"]

    KB_LABELS = {
        "policy": "政策法规库",
        "service": "养老服务库",
        "health": "健康科普库",
        "platform": "平台操作库",
    }

    def __init__(self):
        self.vector_store = VectorStoreService()

    def search(self, query: str, kb: str = "platform", k: int = None) -> list[Document]:
        """检索指定知识库

        Args:
            query: 检索词
            kb: 知识库名称 (policy/service/health/platform)
            k: 返回文档数，默认使用配置值

        Returns:
            检索到的文档列表，每个文档包含 page_content 和 metadata
        """
        if kb not in self.KB_NAMES:
            logger.warning(f"[RagService]未知知识库'{kb}'，回退到platform")
            kb = "platform"

        retriever = self.vector_store.get_retriever(kb)
        docs = retriever.invoke(query)

        logger.info(f"[RagService]检索'{self.KB_LABELS[kb]}'：query='{query}'，返回{len(docs)}条")
        return docs

    def multi_search(self, queries: list[str], kb: str = "platform", k: int = None) -> list[Document]:
        """多查询检索：对多个扩展查询词分别检索，合并去重

        用于 QueryExpander 扩展后的多路召回场景。

        Args:
            queries: 扩展后的检索词列表
            kb: 知识库名称
            k: 每个查询返回的文档数，默认使用配置值

        Returns:
            去重合并后的文档列表
        """
        seen_contents: set[str] = set()
        merged: list[Document] = []

        for q in queries:
            docs = self.search(q, kb=kb, k=k)
            for doc in docs:
                # 用 page_content 前100字符做去重指纹
                fingerprint = doc.page_content[:100].strip()
                if fingerprint not in seen_contents:
                    seen_contents.add(fingerprint)
                    merged.append(doc)

        logger.info(
            f"[RagService]多查询检索：{len(queries)}个查询词 → "
            f"合并去重后 {len(merged)} 条结果"
        )
        return merged

    def retrieve_context(self, query: str, kb: str = "platform") -> str:
        """检索并返回纯文本上下文（单查询，向后兼容）"""
        docs = self.search(query, kb)
        return self.build_context(docs)

    def multi_retrieve_context(self, queries: list[str], kb: str = "platform") -> tuple[str, list[Document]]:
        """多查询检索并返回上下文 + 文档列表

        Returns:
            (context_text, docs) — 上下文字符串和去重后的文档列表
        """
        docs = self.multi_search(queries, kb)
        return self.build_context(docs), docs

    @staticmethod
    def build_context(docs: list[Document]) -> str:
        """将文档列表拼接为纯文本上下文

        Args:
            docs: Document 列表

        Returns:
            拼接后的纯文本上下文。空列表返回"未找到"提示。
        """
        if not docs:
            return "知识库中未找到相关资料"

        return "\n---\n".join([
            f"[来源：{doc.metadata.get('source', '未知文档')}]\n{doc.page_content}"
            for doc in docs
        ])

    def get_sources(self, docs: list[Document]) -> list[dict]:
        """从检索文档中提取来源信息

        Returns:
            [{"title": "...", "snippet": "..."}, ...]
        """
        seen = set()
        sources = []
        for doc in docs:
            title = doc.metadata.get("source", "未知来源")
            if title not in seen:
                seen.add(title)
                sources.append({
                    "title": title,
                    "snippet": doc.page_content[:120] if doc.page_content else "",
                })
        return sources

    def get_kb_stats(self) -> dict:
        """获取各知识库的统计信息"""
        return {
            kb: {
                "label": self.KB_LABELS[kb],
                "vector_count": self.vector_store.get_vector_count(kb),
            }
            for kb in self.KB_NAMES
        }


# 全局单例
rag_service = RagService()
