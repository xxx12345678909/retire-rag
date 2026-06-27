"""
ChatService — 智慧养老AI助手业务大脑

统一入口 → 意图识别 → 路由业务流 → RAG检索 → 结构化返回
"""

from rag.rag_service import rag_service
from rag.query_expander import query_expander
from rag.profile_extractor import profile_extractor
from service.service_matcher import service_matcher
from service import persist
from utils.logger_handler import logger


class ChatService:
    """养老问答业务编排层

    职责：
    1. 意图识别（政策/服务/健康/通用）
    2. 路由到对应业务流
    3. 组装上下文（多轮对话记忆，SQLite持久化）
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
        self._session_turns: dict[str, int] = {}  # session_id → 当前轮次

    # ── 公共入口 ─────────────────────────────────

    def handle(self, query: str, session_id: str = "default", profile: str = "") -> dict:
        """统一处理入口"""
        # 1. 构建上下文查询（含历史对话）
        contextual_query = self._build_query(session_id, query)

        # 2. 意图识别（仅用原始问题，不含档案避免干扰）
        intent = self.detect_intent(contextual_query)

        # 3. 档案附加到RAG检索上下文（意图确定后）
        rag_query = contextual_query
        if profile:
            rag_query = contextual_query + " " + profile

        # 4. 路由到业务流
        if intent == "policy":
            result = self.policy_flow(rag_query)
        elif intent == "service":
            result = self.service_flow(rag_query)
        elif intent == "health":
            result = self.health_flow(rag_query)
        else:
            result = self.general_flow(rag_query)

        # 4. 保存会话历史
        self._save_history(session_id, query, result["answer"])

        result["intent"] = intent
        return result

    # ── 意图识别 ─────────────────────────────────

    def detect_intent(self, query: str) -> str:
        """基于关键词的意图识别（方案A - 稳定可靠）

        实际优先级：reject_diagnosis > policy > health > service > general
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

        # 政策类（优先于健康，避免档案中的健康词劫持政策问题）
        for kw in self.POLICY_KEYWORDS:
            if kw in q:
                return "policy"

        # 健康科普类
        for kw in self.HEALTH_KEYWORDS:
            if kw in q:
                return "health"

        # 服务类
        for kw in self.SERVICE_KEYWORDS:
            if kw in q:
                return "service"

        return "general"

    # ── 业务流 ───────────────────────────────────

    def policy_flow(self, query: str) -> dict:
        """政策匹配流：提取画像 + 关键词扩展 + RAG检索 + 条件匹配"""
        logger.info(f"[policy_flow]处理政策类问题：{query[:50]}...")

        # 1. 提取用户画像（年龄/户籍/社保/特殊群体）
        profile = profile_extractor.extract(query)

        # 2. 关键词扩展 + 多路RAG检索
        expanded = query_expander.expand(query)
        context, docs = rag_service.multi_retrieve_context(expanded, kb="policy")
        sources = rag_service.get_sources(docs)

        # 3. 画像驱动的条件匹配回答
        answer = self._assemble_policy_answer(query, context, docs, profile)

        return {
            "answer": answer,
            "kb": "policy",
            "sources": sources,
            "disclaimer": "\n\n📌 以上信息仅供参考，具体以当地民政部门最新政策为准。",
        }

    def service_flow(self, query: str) -> dict:
        """服务导办流：需求提取 → 机构数据库筛选 → 个性化推荐"""
        logger.info(f"[service_flow]处理服务类问题：{query[:50]}...")

        # 1. 机构数据库匹配（核心——结构化条件筛选）
        match_result = service_matcher.match(query)
        results = match_result.get("results", [])

        # 2. RAG 检索服务库（兜底——FAQ/流程说明）
        expanded = query_expander.expand(query)
        context, docs = rag_service.multi_retrieve_context(expanded, kb="service")
        sources = rag_service.get_sources(docs)

        # 3. 有机构结果 → 结构化推荐；无 → RAG 兜底
        if results:
            answer = match_result["answer"]
        else:
            answer = self._assemble_service_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "service",
            "sources": sources,
            "disclaimer": None,
        }

    def health_flow(self, query: str) -> dict:
        """健康问答流：关键词扩展 + 多路RAG检索健康库"""
        logger.info(f"[health_flow]处理健康类问题：{query[:50]}...")

        expanded = query_expander.expand(query)
        context, docs = rag_service.multi_retrieve_context(expanded, kb="health")
        sources = rag_service.get_sources(docs)

        answer = self._assemble_health_answer(query, context, docs)

        return {
            "answer": answer,
            "kb": "health",
            "sources": sources,
            "disclaimer": "\n\n⚠️ 免责声明：以上内容仅供科普参考，不构成医疗诊断或处方建议。如有健康问题，请及时咨询专业医生。",
        }

    def general_flow(self, query: str) -> dict:
        """通用RAG流：关键词扩展 + 多路RAG检索平台库"""
        logger.info(f"[general_flow]处理通用问题：{query[:50]}...")

        expanded = query_expander.expand(query)
        context, docs = rag_service.multi_retrieve_context(expanded, kb="platform")
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

    def _assemble_policy_answer(self, query: str, context: str, docs: list,
                                 profile: dict = None) -> str:
        """组装政策类回答 — 画像驱动的条件匹配

        当提取到用户画像（年龄/户籍/社保）时，调用 LLM 将画像条件
        与检索到的政策文档做匹配，输出个性化的福利匹配结果。
        无画像时回退到模板化展示。
        """
        if not docs or "未找到" in context:
            return (
                f"关于「{query}」，我目前的知识库中暂时没有找到对应的政策信息。\n\n"
                "建议您：\n"
                "1. 咨询当地民政部门或社区服务中心\n"
                "2. 拨打12349养老服务热线\n"
                "3. 访问当地人社局官网查询最新政策"
            )

        profile = profile or {}
        has_profile = any(v is not None for v in profile.values())

        if not has_profile:
            # 无画像 → 模板化展示
            return self._build_generic_policy_answer(docs)

        # 有画像 → LLM 条件匹配
        return self._build_matched_policy_answer(query, context, profile)

    def _build_generic_policy_answer(self, docs: list) -> str:
        """无画像时的通用政策展示"""
        lines = ["根据知识库中的政策信息，为您整理如下：\n"]
        for i, doc in enumerate(docs, 1):
            lines.append(f"{i}. {doc.page_content[:300]}")
        lines.append("\n📋 参考来源：")
        seen = set()
        for doc in docs:
            src = doc.metadata.get("source", "参考文档")
            if src not in seen:
                seen.add(src)
                lines.append(f"  - {src}")
        return "\n".join(lines)

    def _build_matched_policy_answer(self, query: str, context: str,
                                      profile: dict) -> str:
        """画像驱动的条件匹配回答"""
        profile_text = []
        age = profile.get("age")
        household = profile.get("household")
        ss = profile.get("social_security")
        sg = profile.get("special_group")

        if age: profile_text.append(f"年龄：{age}岁")
        if household: profile_text.append(f"户籍：{household}")
        if ss is not None: profile_text.append(f"社保：{'有' if ss else '无'}")
        if sg: profile_text.append(f"特殊群体：{sg}")

        prompt = f"""你是养老政策匹配专家。根据用户信息和政策文档，完成以下任务：

## 用户信息
{chr(10).join(profile_text) if profile_text else '未提供详细信息'}
原始问题：{query}

## 政策文档
{context[:3000]}

## 任务
1. 从政策文档中找出该用户**明确符合条件**的福利项目
2. 列出每个项目的：福利名称、申领条件对照、具体金额/标准、申请所需材料
3. 如果用户年龄/户籍/社保信息与某条政策无关，不要列出
4. 如果某条政策用户明显不符合（如70岁才能申领但用户65岁），说明"暂不符合，xx年后可申请"
5. 用温暖、易懂的语言，避免堆砌专业术语

只在回答末尾列出参考文档名，格式：📋 参考来源：\n- 文档名"""

        try:
            from langchain_core.messages import HumanMessage
            from model.factory import chat_model
            resp = chat_model.invoke([HumanMessage(content=prompt)])
            return resp.content.strip()
        except Exception as e:
            logger.warning(f"[policy匹配]LLM调用失败，回退模板：{str(e)}")
            return context[:1500]

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

    # ── 多轮对话记忆（SQLite 持久化）─────────────

    def _build_query(self, session_id: str, query: str) -> str:
        """构建含历史上下文的查询"""
        history = persist.get_session_history(session_id, limit=3)
        if not history:
            return query
        context_parts = []
        for h in history:
            context_parts.append(f"用户：{h['query']}")
            context_parts.append(f"助手：{h['answer'][:200]}")
        return "\n".join(context_parts + [f"用户：{query}"])

    def _save_history(self, session_id: str, query: str, answer: str):
        """保存会话历史到 SQLite"""
        if session_id not in self._session_turns:
            self._session_turns[session_id] = 0
        self._session_turns[session_id] += 1
        persist.save_session_turn(
            session_id, self._session_turns[session_id], query, answer
        )


# 全局单例
chat_service = ChatService()
