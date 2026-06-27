"""
ChatService — 智慧养老AI助手业务大脑

统一入口 → 意图识别 → 路由业务流 → RAG检索 → 结构化返回
"""

from rag.rag_service import rag_service
from utils.logger_handler import logger


class ChatService:
    """养老问答业务编排层

    职责：
    1. 意图识别（政策/服务/健康/通用）
    2. 路由到对应业务流
    3. 组装上下文（多轮对话记忆）
    4. 统一响应格式（含来源引用、免责声明）
    """

    # 意图关键词映射
    POLICY_KEYWORDS = [
        "补贴", "政策", "高龄", "津贴", "长护险", "养老金", "退休金",
        "申请条件", "办理流程", "社保", "户籍", "低保", "补助",
        "养老服务补贴", "残疾", "优抚",
    ]
    SERVICE_KEYWORDS = [
        "养老院", "养老机构", "护理院", "照顾", "失能", "托管",
        "预约", "收费", "价格", "床位", "居家服务", "助餐",
        "助洁", "助医", "陪护", "上门", "日间照料", "社区", "推荐",
    ]
    HEALTH_KEYWORDS = [
        "吃什么", "饮食", "糖尿病", "高血压", "心脏病", "中风",
        "慢性病", "用药", "服药", "血压", "血糖", "血脂",
        "护理", "康复", "锻炼", "运动", "急救", "摔倒",
        "骨质疏松", "老年痴呆", "睡眠", "便秘", "身体",
    ]

    def __init__(self):
        # 简单的内存会话存储（生产环境应换 Redis）
        self._sessions: dict[str, list[dict]] = {}

    # ── 公共入口 ─────────────────────────────────

    def handle(self, query: str, session_id: str = "default") -> dict:
        """统一处理入口

        Args:
            query: 用户自然语言提问
            session_id: 会话ID（用于多轮对话）

        Returns:
            {
                "answer": str,
                "intent": str,
                "kb": str,
                "sources": [{"title": str, "snippet": str}],
                "disclaimer": str | None,
            }
        """
        # 1. 构建上下文查询（含历史对话）
        contextual_query = self._build_query(session_id, query)

        # 2. 意图识别（基于含历史的上下文，支持多轮追问）
        intent = self.detect_intent(contextual_query)

        # 3. 路由到业务流
        if intent == "policy":
            result = self.policy_flow(contextual_query)
        elif intent == "service":
            result = self.service_flow(contextual_query)
        elif intent == "health":
            result = self.health_flow(contextual_query)
        else:
            result = self.general_flow(contextual_query)

        # 4. 保存会话历史
        self._save_history(session_id, query, result["answer"])

        result["intent"] = intent
        return result

    # ── 意图识别 ─────────────────────────────────

    def detect_intent(self, query: str) -> str:
        """基于关键词的意图识别（方案A - 稳定可靠）

        优先级：health > policy > service > general
        """
        q = query.lower()

        # 医疗诊断类 → 直接拒答标记
        diagnosis_patterns = [
            "我是什么病", "得了什么病", "是不是病", "确诊",
            "开药", "开个药", "处方", "药方", "吃什么药", "该吃什么药",
            "怎么治", "能治吗", "治得好吗", "开个方",
            "推荐个药", "买什么药", "给我开", "帮我开",
        ]
        for p in diagnosis_patterns:
            if p in q:
                return "reject_diagnosis"

        # 健康科普类
        for kw in self.HEALTH_KEYWORDS:
            if kw in q:
                return "health"

        # 政策类
        for kw in self.POLICY_KEYWORDS:
            if kw in q:
                return "policy"

        # 服务类
        for kw in self.SERVICE_KEYWORDS:
            if kw in q:
                return "service"

        return "general"

    # ── 业务流 ───────────────────────────────────

    def policy_flow(self, query: str) -> dict:
        """政策匹配流：提取用户条件 + RAG检索政策库"""
        logger.info(f"[policy_flow]处理政策类问题：{query[:50]}...")

        # RAG检索政策知识库
        docs = rag_service.search(query, kb="policy")
        context = rag_service.retrieve_context(query, kb="policy")
        sources = rag_service.get_sources(docs)

        answer = self._assemble_policy_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "policy",
            "sources": sources,
            "disclaimer": "\n\n📌 以上信息仅供参考，具体以当地民政部门最新政策为准。",
        }

    def service_flow(self, query: str) -> dict:
        """服务导办流：RAG检索服务库 → 推荐"""
        logger.info(f"[service_flow]处理服务类问题：{query[:50]}...")

        docs = rag_service.search(query, kb="service")
        context = rag_service.retrieve_context(query, kb="service")
        sources = rag_service.get_sources(docs)

        answer = self._assemble_service_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "service",
            "sources": sources,
            "disclaimer": None,
        }

    def health_flow(self, query: str) -> dict:
        """健康问答流：RAG检索健康库 + 强制免责声明"""
        logger.info(f"[health_flow]处理健康类问题：{query[:50]}...")

        docs = rag_service.search(query, kb="health")
        context = rag_service.retrieve_context(query, kb="health")
        sources = rag_service.get_sources(docs)

        answer = self._assemble_health_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "health",
            "sources": sources,
            "disclaimer": "\n\n⚠️ 免责声明：以上内容仅供科普参考，不构成医疗诊断或处方建议。如有健康问题，请及时咨询专业医生。",
        }

    def general_flow(self, query: str) -> dict:
        """通用RAG流：默认检索平台操作库"""
        logger.info(f"[general_flow]处理通用问题：{query[:50]}...")

        docs = rag_service.search(query, kb="platform")
        context = rag_service.retrieve_context(query, kb="platform")
        sources = rag_service.get_sources(docs)

        answer = self._assemble_general_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "platform",
            "sources": sources,
            "disclaimer": None,
        }

    # ── 拒答处理 ─────────────────────────────────

    def reject_diagnosis(self) -> dict:
        """拒答医疗诊断类问题"""
        return {
            "answer": "很抱歉，AI助手无法提供医疗诊断服务。建议您带老人到正规医疗机构就诊，由专业医生进行诊断和治疗。\n\n如有紧急情况，请立即拨打120急救电话。",
            "kb": None,
            "sources": [],
            "disclaimer": None,
            "intent": "reject",
        }

    # ── 回答拼装（模板化，后续可接LLM生成） ─────

    def _assemble_policy_answer(self, query: str, context: str, docs: list) -> str:
        """组装政策类回答"""
        if not docs or "未找到" in context:
            return (
                f"关于「{query}」，我目前的知识库中暂时没有找到对应的政策信息。\n\n"
                "建议您：\n"
                "1. 咨询当地民政部门或社区服务中心\n"
                "2. 拨打12349养老服务热线\n"
                "3. 访问当地人社局官网查询最新政策"
            )

        # 简单模板组装（后续接LLM生成更好）
        lines = ["根据知识库中的政策信息，为您整理如下：\n"]
        for i, doc in enumerate(docs, 1):
            src = doc.metadata.get("source", "参考文档")
            lines.append(f"{i}. {doc.page_content[:300]}")
        lines.append("\n📋 参考来源：")
        seen = set()
        for doc in docs:
            src = doc.metadata.get("source", "参考文档")
            if src not in seen:
                seen.add(src)
                lines.append(f"  - {src}")

        return "\n".join(lines)

    def _assemble_service_answer(self, query: str, context: str, docs: list) -> str:
        """组装服务类回答"""
        if not docs or "未找到" in context:
            return (
                f"关于「{query}」，我目前的知识库中暂时没有找到匹配的服务信息。\n\n"
                "建议您：\n"
                "1. 拨打平台客服热线获取帮助\n"
                "2. 在「养老服务」页面浏览全部服务项目"
            )

        lines = ["根据您的需求，为您找到以下相关信息：\n"]
        for i, doc in enumerate(docs, 1):
            lines.append(f"**{i}.** {doc.page_content[:300]}\n")

        lines.append("📋 参考来源：")
        seen = set()
        for doc in docs:
            src = doc.metadata.get("source", "参考文档")
            if src not in seen:
                seen.add(src)
                lines.append(f"  - {src}")

        return "\n".join(lines)

    def _assemble_health_answer(self, query: str, context: str, docs: list) -> str:
        """组装健康类回答"""
        if not docs or "未找到" in context:
            return (
                f"关于「{query}」，我目前的知识库中暂时没有找到相关的健康科普内容。\n\n"
                "建议您咨询专业医生或查阅权威医学网站获取准确信息。"
            )

        lines = ["以下内容仅供科普参考，不替代医疗诊断：\n"]
        for i, doc in enumerate(docs, 1):
            lines.append(f"{i}. {doc.page_content[:300]}\n")

        lines.append("📋 参考来源：")
        seen = set()
        for doc in docs:
            src = doc.metadata.get("source", "参考文档")
            if src not in seen:
                seen.add(src)
                lines.append(f"  - {src}")

        return "\n".join(lines)

    def _assemble_general_answer(self, query: str, context: str, docs: list) -> str:
        """组装通用/平台操作类回答"""
        if not docs or "未找到" in context:
            return (
                f"抱歉，我没有完全理解「{query}」的意思。\n\n"
                "您可以尝试：\n"
                "1. 换个方式提问，比如「如何预约居家服务」\n"
                "2. 选择下方快捷入口进入对应功能页面\n"
                "3. 拨打客服热线获取人工帮助"
            )

        lines = ["为您找到以下相关信息：\n"]
        for i, doc in enumerate(docs, 1):
            lines.append(f"{i}. {doc.page_content[:300]}\n")

        lines.append("📋 参考来源：")
        seen = set()
        for doc in docs:
            src = doc.metadata.get("source", "参考文档")
            if src not in seen:
                seen.add(src)
                lines.append(f"  - {src}")

        return "\n".join(lines)

    # ── 多轮对话记忆 ─────────────────────────────

    def _build_query(self, session_id: str, query: str) -> str:
        """构建含历史上下文的查询"""
        history = self._sessions.get(session_id, [])
        if not history:
            return query
        # 取最近3轮对话拼入上下文
        recent = history[-3:]
        context_parts = []
        for h in recent:
            context_parts.append(f"用户：{h['query']}")
            context_parts.append(f"助手：{h['answer'][:200]}")
        return "\n".join(context_parts + [f"用户：{query}"])

    def _save_history(self, session_id: str, query: str, answer: str):
        """保存会话历史"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append({"query": query, "answer": answer})
        # 保留最近10轮
        if len(self._sessions[session_id]) > 10:
            self._sessions[session_id] = self._sessions[session_id][-10:]


# 全局单例
chat_service = ChatService()
