"""智慧养老AI助手 — 工具集

提供4个知识库的定向检索工具：
- rag_retrieve_policy:   政策法规库检索
- rag_retrieve_service:  养老服务库检索
- rag_retrieve_health:   健康科普库检索
- rag_retrieve_platform: 平台操作库检索

辅助工具：
- get_weather:      获取指定城市天气
- get_user_location: 获取用户所在城市
"""

from langchain_core.tools import tool

from rag.rag_service import rag_service
from rag.query_expander import query_expander
from utils.logger_handler import logger
import random


# ═══════════════════════════════════════════════════════
# 4个知识库检索工具
# ═══════════════════════════════════════════════════════


@tool
def rag_retrieve_policy(query: str) -> str:
    """【工具】从政策法规知识库检索养老政策信息

    涵盖：高龄补贴、养老服务补贴、长护险政策、养老机构管理条例等官方文件与解读。

    使用场景：用户询问补贴申请条件、政策标准、办理流程、福利待遇等政策相关问题。

    Args:
        query: 检索词字符串，如"高龄补贴申请条件""长护险报销比例"

    Returns:
        知识库中的原始参考资料文本
    """
    try:
        expanded = query_expander.expand(query)
        result = rag_service.multi_retrieve_context(expanded, kb="policy")[0]
        if "未找到" in result:
            logger.warning(f"[rag_retrieve_policy]未找到：{query}")
            return result
        logger.info(f"[rag_retrieve_policy]检索成功（扩展{len(expanded)}词）：{query}")
        return result
    except Exception as e:
        logger.error(f"[rag_retrieve_policy]失败：{str(e)}")
        return f"检索出错：{str(e)}"


@tool
def rag_retrieve_service(query: str) -> str:
    """【工具】从养老服务知识库检索服务信息

    涵盖：平台所有服务项目说明、预约流程、收费标准、常见问题FAQ。

    使用场景：用户询问养老院推荐、居家服务预约、机构查询等服务相关问题。

    Args:
        query: 检索词字符串，如"失能老人养老院推荐""助餐服务预约流程"

    Returns:
        知识库中的原始参考资料文本
    """
    try:
        expanded = query_expander.expand(query)
        result = rag_service.multi_retrieve_context(expanded, kb="service")[0]
        if "未找到" in result:
            logger.warning(f"[rag_retrieve_service]未找到：{query}")
            return result
        logger.info(f"[rag_retrieve_service]检索成功（扩展{len(expanded)}词）：{query}")
        return result
    except Exception as e:
        logger.error(f"[rag_retrieve_service]失败：{str(e)}")
        return f"检索出错：{str(e)}"


@tool
def rag_retrieve_health(query: str) -> str:
    """【工具】从健康科普知识库检索健康护理信息

    涵盖：老年慢性病护理、安全用药、饮食营养、急救常识等权威科普内容。

    ⚠️ 注意：所有健康类回答必须附加免责声明「仅供科普参考，不构成医疗诊断」。

    使用场景：用户询问老年健康护理、饮食建议、用药注意事项等问题。

    Args:
        query: 检索词字符串，如"糖尿病饮食注意事项""高血压老人日常护理"

    Returns:
        知识库中的原始参考资料文本
    """
    try:
        expanded = query_expander.expand(query)
        result = rag_service.multi_retrieve_context(expanded, kb="health")[0]
        if "未找到" in result:
            logger.warning(f"[rag_retrieve_health]未找到：{query}")
            return result
        logger.info(f"[rag_retrieve_health]检索成功（扩展{len(expanded)}词）：{query}")
        return result
    except Exception as e:
        logger.error(f"[rag_retrieve_health]失败：{str(e)}")
        return f"检索出错：{str(e)}"


@tool
def rag_retrieve_platform(query: str) -> str:
    """【工具】从平台操作知识库检索操作指南

    涵盖：网站功能使用指南、账号注册、预约流程等操作问题。

    使用场景：用户询问如何使用平台功能、操作步骤等问题。

    Args:
        query: 检索词字符串，如"如何注册账号""怎么查看我的预约"

    Returns:
        知识库中的原始参考资料文本
    """
    try:
        expanded = query_expander.expand(query)
        result = rag_service.multi_retrieve_context(expanded, kb="platform")[0]
        if "未找到" in result:
            logger.warning(f"[rag_retrieve_platform]未找到：{query}")
            return result
        logger.info(f"[rag_retrieve_platform]检索成功（扩展{len(expanded)}词）：{query}")
        return result
    except Exception as e:
        logger.error(f"[rag_retrieve_platform]失败：{str(e)}")
        return f"检索出错：{str(e)}"


# ═══════════════════════════════════════════════════════
# 辅助工具
# ═══════════════════════════════════════════════════════


@tool
def get_weather(city: str) -> str:
    """获取指定城市的实时天气信息

    用于回答与天气、季节对老人健康影响相关的问题。

    Args:
        city: 城市名称，如"北京""上海"

    Returns:
        天气信息字符串
    """
    # 演示用模拟数据（生产环境对接真实天气API）
    weather_data = {
        "北京": "晴，气温18~28°C，AQI 52 良，适合户外活动",
        "上海": "多云转阴，气温22~30°C，AQI 48 优，可能有小雨",
        "深圳": "晴间多云，气温26~33°C，AQI 35 优，注意防暑",
        "杭州": "小雨，气温20~27°C，AQI 42 优，路面湿滑注意安全",
        "合肥": "晴，气温19~29°C，AQI 55 良，适合户外活动",
    }
    return weather_data.get(city, f"城市{city}：晴，气温20~28°C，天气良好")


@tool
def get_user_location() -> str:
    """获取用户当前所在城市名称

    用于回答与用户地理位置相关的政策、服务问题时调用。

    Returns:
        城市名称字符串
    """
    return random.choice(["深圳", "合肥", "杭州"])
