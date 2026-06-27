"""
QueryExpander — 查询关键词扩展器

在 RAG 检索前将用户自然语言问题扩展为多条检索词，
多路召回后合并去重，提升知识库覆盖率。
"""

from utils.packaging_patch import *  # noqa: F401,F403

from model.factory import chat_model
from utils.logger_handler import logger


class QueryExpander:
    """基于 LLM 的查询扩展器（带 LRU 缓存）

    核心逻辑：
    1. 缓存命中 → 直接返回，零 API 调用
    2. 极简短词（≤2字）→ 跳过扩展
    3. 缓存未命中 → Qwen 生成 3 个规范检索词
    4. 原始问题作为第一个检索词（保底）
    5. 写入缓存（LRU 淘汰，上限 200 条）
    """

    def __init__(self, cache_size: int = 200):
        self._cache: dict[str, list[str]] = {}
        self._cache_size = cache_size
        self._hits = 0
        self._misses = 0

    def expand(self, query: str, n: int = 3) -> list[str]:
        """扩展查询为多个检索关键词

        Args:
            query: 用户原始自然语言提问
            n: 额外生成的检索词数量（不含原始提问）

        Returns:
            检索词列表，第一个元素始终为原始提问
        """
        key = query.strip()

        # ── 缓存命中（LRU：命中时移到末尾）──
        if key in self._cache:
            self._hits += 1
            self._cache[key] = self._cache.pop(key)  # 移到末尾，实现真 LRU
            logger.info(
                f"[QueryExpander]缓存命中 ({self._hits}h/{self._misses}m): "
                f"{key[:30]}... → {len(self._cache[key])}个词"
            )
            return self._cache[key]

        # ── 极短查询不扩展 ──
        if len(key) <= 2:
            logger.info(f"[QueryExpander]短词跳过扩展：'{key}'")
            result = [key]
            self._cache[key] = result
            return result

        # ── LLM 扩展 ──
        self._misses += 1
        result = self._call_llm(key, n)

        # ── 写入缓存 + LRU 淘汰 ──
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        return result

    def _call_llm(self, query: str, n: int) -> list[str]:
        """调用 LLM 生成扩展检索词"""
        prompt = f"""你是一个养老领域RAG系统的检索词生成器。

任务：将用户的自然语言问题扩展为{n}个不同的检索关键词/短语。

规则：
1. 将口语化表述转换为正式术语（如"能领多少钱"→"养老金发放标准"）
2. 覆盖问题的不同维度（政策名称、申请条件、办理流程等）
3. 每行一个关键词，只输出关键词本身，不要编号、解释或额外文字
4. 关键词长度控制在2-15个汉字

用户问题：{query}"""

        try:
            from langchain_core.messages import HumanMessage
            resp = chat_model.invoke([HumanMessage(content=prompt)])
            content = resp.content.strip()

            keywords = []
            for line in content.split("\n"):
                k = line.strip().lstrip("0123456789.、-· ").strip()
                if len(k) >= 2 and k not in keywords:
                    keywords.append(k)

            result = [query] + [k for k in keywords if k != query]

            logger.info(f"[QueryExpander]LLM扩展 ({self._hits}h/{self._misses}m): "
                        f"{query[:30]}... → {len(result)} 个检索词")
            return result[:n + 1]

        except Exception as e:
            logger.warning(f"[QueryExpander]扩展失败，回退到原始查询：{str(e)}")
            return [query]

    @property
    def stats(self) -> dict:
        """缓存统计"""
        return {
            "cache_size": len(self._cache),
            "max_size": self._cache_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / max(1, self._hits + self._misses) * 100:.1f}%",
        }


# 全局单例
query_expander = QueryExpander()
