"""Agent 中间件

提供工具执行监控和日志记录。
"""

from utils.logger_handler import logger


def monitor_tool_call(tool_name: str, args: dict) -> None:
    """工具调用监控"""
    logger.info(f"[tool_monitor]调用工具：{tool_name}")
    logger.info(f"[tool_monitor]参数：{args}")


def log_model_call(message_count: int) -> None:
    """模型调用前日志"""
    logger.info(f"[model_call]即将调用LLM，消息数：{message_count}")
