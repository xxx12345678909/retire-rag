"""
ProfileExtractor — 用户画像提取器

从自然语言提问中提取年龄、户籍、社保等结构化信息，
用于政策智能匹配场景。
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
from utils.logger_handler import logger


class ProfileExtractor:
    """从用户自然语言中提取结构化画像

    输出 JSON：{"age": int|null, "household": "城镇"/"农村"/null,
                "social_security": true/false/null,
                "special_group": "低保"/"失能"/"优抚"/null}
    """

    def extract(self, query: str) -> dict:
        """提取用户画像

        Args:
            query: 用户自然语言提问

        Returns:
            {"age": 75, "household": "农村", "social_security": true, "special_group": null}
            提取失败时返回全 null
        """
        prompt = f"""从以下养老咨询问题中提取用户信息，输出JSON。

字段：
- age: 年龄数字，未提及则为null
- household: "城镇"或"农村"，未提及则为null
- social_security: 有社保=true，无社保=false，未提及=null
- special_group: "低保"/"失能"/"优抚"/"残疾"，未提及=null

只输出JSON，不要其他文字。

问题：{query}"""

        try:
            from langchain_core.messages import HumanMessage
            resp = chat_model.invoke([HumanMessage(content=prompt)])
            content = resp.content.strip()

            # 清理 markdown 代码块包装
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            profile = json.loads(content)
            logger.info(f"[ProfileExtractor]提取成功：{profile}")
            return profile

        except Exception as e:
            logger.warning(f"[ProfileExtractor]提取失败：{str(e)}，返回空画像")
            return {"age": None, "household": None, "social_security": None, "special_group": None}


# 全局单例
profile_extractor = ProfileExtractor()
