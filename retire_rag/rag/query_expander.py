"""
QueryExpander — 查询关键词扩展器

在 RAG 检索前将用户自然语言问题扩展为多条检索词，
多路召回后合并去重，提升知识库覆盖率。
"""

# ── 修补损坏的 packaging 元数据 ─────────────────
import importlib.metadata as _importlib_metadata
_orig_version = _importlib_metadata.version

def _patched_version(package_name: str) -> str:
    v = _orig_version(package_name)
    if v is None and package_name == "packaging":
        return "26.2"
    return v

_importlib_metadata.version = _patched_version
# ──────────────────────────────────────────────

from model.factory import chat_model
from utils.logger_handler import logger


class QueryExpander:
    """基于 LLM 的查询扩展器

    核心逻辑：
    1. 用户口语提问 → Qwen 生成 3-5 个规范检索词
    2. 原始问题作为第一个检索词（保底）
    3. 去重后返回
    """

    def expand(self, query: str, n: int = 3) -> list[str]:
        """扩展查询为多个检索关键词

        Args:
            query: 用户原始自然语言提问
            n: 额外生成的检索词数量（不含原始提问）

        Returns:
            检索词列表，第一个元素始终为原始提问
        """
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

            # 解析模型输出为关键词列表
            keywords = []
            for line in content.split("\n"):
                k = line.strip().lstrip("0123456789.、-· ").strip()
                if len(k) >= 2 and k not in keywords:
                    keywords.append(k)

            # 原始问题作为第一个检索词（保底），扩展词追加到后面
            result = [query] + [k for k in keywords if k != query]

            logger.info(f"[QueryExpander]扩展完成：{query[:30]}... → {len(result)} 个检索词")
            return result[:n + 1]  # 总数不超过 n+1

        except Exception as e:
            logger.warning(f"[QueryExpander]扩展失败，回退到原始查询：{str(e)}")
            return [query]


# 全局单例
query_expander = QueryExpander()
