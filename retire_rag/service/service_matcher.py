"""
ServiceMatcher — 服务智能导办引擎

从用户需求描述中提取结构化条件（区域/护理等级/预算），
查询机构数据库，生成个性化推荐。
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

import json
from model.factory import chat_model
from service.institution_db import search_institutions, get_all_districts
from utils.logger_handler import logger


class ServiceMatcher:
    """从自然语言需求中提取条件并匹配机构"""

    DISTRICT_KEYWORDS = [
        "朝阳", "海淀", "西城", "东城", "丰台", "通州",
        "石景山", "昌平", "大兴", "顺义", "房山", "门头沟",
        "附近", "周边", "家附近", "就近",
    ]

    CARE_KEYWORDS = {
        "自理": ["自理", "能自理", "身体健康", "可以自己"],
        "轻度失能": ["轻度", "稍微", "不太方便", "需要帮", "有点"],
        "中度失能": ["中度", "失能", "不能自理", "需要照顾", "需要护理", "卧床"],
        "重度失能": ["重度", "完全不能", "植物人", "临终", "插管"],
    }

    # 预算关键词映射
    PRICE_KEYWORDS = {
        "便宜": 5000, "实惠": 5000, "经济": 4000,
        "中档": 7000, "中端": 7000,
        "高端": 99999, "好一点": 99999, "高档": 99999,
    }

    def extract_requirements(self, query: str) -> dict:
        """从用户需求中提取结构化条件

        Returns:
            {"district": str|null, "care_level": str|null,
             "price_max": int|null, "needs": str}
        """
        # 先尝试 LLM 提取
        try:
            result = self._llm_extract(query)
        except Exception:
            result = self._keyword_extract(query)

        # 补充：关键词映射预算（LLM 可能漏掉口语化预算词）
        if result.get("price_max") is None:
            for kw, price in self.PRICE_KEYWORDS.items():
                if kw in query:
                    result["price_max"] = price
                    break

        return result

    def _llm_extract(self, query: str) -> dict:
        districts_str = "、".join(get_all_districts())
        prompt = f"""从以下养老需求中提取筛选条件，输出JSON。

字段：
- district: 区域名称（可选值：{districts_str}），未提及=null
- care_level: 护理等级（"自理"/"轻度失能"/"中度失能"/"重度失能"），未提及=null
- price_max: 月费预算上限（元，整数），未提及=null
- needs: 用一句话概括用户需求（15字以内）

只输出JSON，不要其他文字。

需求：{query}"""

        from langchain_core.messages import HumanMessage
        resp = chat_model.invoke([HumanMessage(content=prompt)])
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        result = json.loads(content)
        logger.info(f"[ServiceMatcher]条件提取：{result}")
        return result

    def _keyword_extract(self, query: str) -> dict:
        """关键词规则兜底"""
        district = None
        for kw in self.DISTRICT_KEYWORDS:
            if kw in query:
                if kw in ("附近", "周边", "家附近", "就近"):
                    district = None  # 保持null，后续可做IP定位
                else:
                    district = kw + "区"
                break

        care_level = None
        for level, keywords in self.CARE_KEYWORDS.items():
            if any(k in query for k in keywords):
                care_level = level
                break

        return {"district": district, "care_level": care_level,
                "price_max": None, "needs": query[:15]}

    @staticmethod
    def _normalize_care_level(level: str | None) -> str | None:
        """归一化护理等级：'失能' → '失能'（SQL LIKE 匹配所有含失能的级别）"""
        if not level:
            return None
        if "不能自理" in level or "卧床" in level or "重度" in level:
            return "重度失能"
        if "中度" in level or "失能" in level:
            return "失能"  # 模糊匹配，LIKE '%失能%' 覆盖轻/中/重度
        return level

    def match(self, query: str) -> dict:
        """执行完整的服务匹配流程

        Returns:
            {"requirements": {...}, "results": [...], "answer": str}
        """
        # 1. 提取条件
        requirements = self.extract_requirements(query)
        care_level = self._normalize_care_level(requirements.get("care_level"))
        district = requirements.get("district")
        price_max = requirements.get("price_max")

        # 2. 查询机构
        results = search_institutions(
            district=district,
            care_level=care_level,
            price_max=price_max,
            limit=5,
        )

        # 3. 生成推荐回答
        answer = self._build_recommendation(query, requirements, results)

        return {
            "requirements": requirements,
            "results": results,
            "answer": answer,
        }

    def _build_recommendation(self, query: str, requirements: dict,
                               results: list[dict]) -> str:
        """生成结构化的推荐回答"""
        if not results:
            return self._no_results_answer(requirements)

        care_label = requirements.get("care_level") or "未指定"
        district_label = requirements.get("district") or "全城"
        price_label = f"月费≤{requirements['price_max']}元" if requirements.get("price_max") else "不限"

        lines = [
            f"根据您的需求（护理等级：{care_label}，区域：{district_label}，预算：{price_label}），",
            f"为您找到 {len(results)} 家匹配机构：\n",
        ]

        for i, r in enumerate(results, 1):
            lines.append(
                f"**{i}. {r['name']}**  [{r['type']}]  ⭐ 推荐"
            )
            lines.append(f"   📍 {r['district']} | {r['address']}")
            lines.append(f"   💰 月费：{r['price_min']}-{r['price_max']}元")
            lines.append(f"   🛏️ 床位：{r['beds_avail']}/{r['beds_total']}（可用/总数）")
            lines.append(f"   🏥 护理：{r['care_levels']}")
            lines.append(f"   📞 {r['contact']}")
            lines.append(f"   📝 {r['description']}")
            if i != len(results):
                lines.append("")

        lines.append(f"\n📞 如需预约，请直接拨打机构电话或致电平台客服热线。")
        return "\n".join(lines)

    def _no_results_answer(self, requirements: dict) -> str:
        care = requirements.get("care_level") or "未指定"
        district = requirements.get("district") or "全城"
        return (
            f"很抱歉，当前在「{district} / {care}」条件下暂未找到匹配机构。\n\n"
            "建议：\n"
            "1. 放宽区域范围，查看相邻区域机构\n"
            "2. 拨打客服热线，由人工为您精准匹配\n"
            "3. 在「养老服务」页面浏览全部机构"
        )


# 全局单例
service_matcher = ServiceMatcher()
