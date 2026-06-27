"""智慧养老AI助手 — React Agent

基于 LangGraph 的 ReAct Agent，支持：
- 自主思考 → 工具调用 → 观察 → 再思考
- 4个养老知识库定向检索
- 多轮对话

注意：React Agent 模式目前存在版本兼容问题。
当 Agent 不可用时（create_react_agent 导入失败），
不要阻塞整个应用启动 — ChatService 模式仍然可用。
"""
from langchain_core.messages import HumanMessage
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (
    rag_retrieve_policy,
    rag_retrieve_service,
    rag_retrieve_health,
    rag_retrieve_platform,
    get_weather,
    get_user_location,
)
from utils.logger_handler import logger


class ReactAgent:
    """智慧养老 React Agent

    使用 LangGraph 的 create_react_agent 实现 ReAct 循环：
    Thought → Action → Observation → Thought → ... → Final Answer
    """

    def __init__(self):
        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            logger.warning(
                "[ReactAgent] create_react_agent 不可用，"
                "Agent 模式已禁用，ChatService 仍可正常使用"
            )
            self.agent = None
            return

        system_prompt = load_system_prompts()

        tools = [
            rag_retrieve_policy,
            rag_retrieve_service,
            rag_retrieve_health,
            rag_retrieve_platform,
            get_weather,
            get_user_location,
        ]

        self.agent = create_react_agent(
            model=chat_model,
            tools=tools,
            prompt=system_prompt if isinstance(system_prompt, str) else str(system_prompt),
        )

    def execute_stream(self, query: str):
        """流式执行问答

        Args:
            query: 用户提问

        Yields:
            流式输出的文本块
        """
        input_dict = {
            "messages": [HumanMessage(content=query)]
        }

        for chunk in self.agent.stream(input_dict, stream_mode="values"):
            if "messages" in chunk:
                latest_message = chunk["messages"][-1]
                if hasattr(latest_message, "content") and latest_message.content:
                    yield latest_message.content.strip() + "\n"

    def execute(self, query: str) -> str:
        """非流式执行，返回完整回答"""
        result = []
        for chunk in self.execute_stream(query):
            result.append(chunk)
        return "".join(result)


# 懒初始化：create_react_agent 不可用时跳过，agent 保留为 None
try:
    agent = ReactAgent()
except ImportError:
    agent = None