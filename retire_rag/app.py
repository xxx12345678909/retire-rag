"""智慧养老AI助手 — FastAPI 后端

统一 API 入口：
- POST /api/v1/chat        主问答入口
- GET  /api/v1/kb/stats    知识库统计
- POST /admin/docs/upload   文档上传
- GET  /admin/logs          问答日志
- POST /admin/logs/feedback 回答反馈

启动：uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

import os
import json
import uuid
from contextlib import asynccontextmanager

# 关闭 Chroma 遥测上报（消除启动时的 telemetry 警告）
os.environ["CHROMA_TELEMETRY_IMPL"] = "none"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 修补损坏的 packaging 元数据 ─────────────────
# 环境中存在空的 packaging-23.1.dist-info 目录遮蔽了有效的 packaging-26.2.dist-info，
# 导致 importlib.metadata.version('packaging') 返回 None，
# 进而导致 transformers 依赖版本检查失败（影响 langchain_text_splitters 和 langgraph）。
# 此补丁必须在所有可能触发 transformers 导入的项目模块之前执行。
import importlib.metadata as _importlib_metadata
_orig_version = _importlib_metadata.version

def _patched_version(package_name: str) -> str:
    v = _orig_version(package_name)
    if v is None and package_name == "packaging":
        return "26.2"
    return v

_importlib_metadata.version = _patched_version
# ──────────────────────────────────────────────

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from service.chat_service import chat_service
from service import persist
from agent.react_agent import agent as react_agent
from utils.config_handler import chroma_conf
from utils.logger_handler import logger
from utils.debug import Trace, runtime, DEBUG

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载知识库"""
    from rag.vector_store import VectorStoreService
    vs = VectorStoreService()
    vs.load_document()
    logger.info("[startup]知识库加载完成")
    yield


app = FastAPI(
    title="智慧养老AI助手 API",
    description="基于RAG的智慧养老知识问答平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    use_agent: bool = False  # True=React Agent, False=ChatService（规则路由）


class ChatResponse(BaseModel):
    answer: str
    intent: Optional[str] = None
    kb: Optional[str] = None
    sources: list[dict] = []
    disclaimer: Optional[str] = None
    session_id: str = "default"


class FeedbackRequest(BaseModel):
    log_id: str
    score: int  # 1 = 有用, -1 = 无帮助
    comment: str = ""


# ═══════════════════════════════════════════════════════
# 前端对话 API
# ═══════════════════════════════════════════════════════

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """统一对话入口"""
    runtime.requests += 1
    trace = Trace(req.query)
    logger.info(f"[API] trace={trace.trace_id} query={req.query[:80]}...")

    # ── 诊断拒答 ──
    intent = chat_service.detect_intent(req.query)
    trace.step("intent", intent)
    if intent == "reject_diagnosis":
        return chat_service.reject_diagnosis()

    # ── 执行 ──
    if req.use_agent and react_agent is not None and react_agent.agent is not None:
        trace.step("agent_start")
        answer = react_agent.execute(req.query)
        trace.step("agent_done")
        trace.log()
        return ChatResponse(
            answer=answer, intent=intent, kb=None, sources=[],
            disclaimer=(
                "⚠️ 免责声明：以上内容仅供科普参考，不构成医疗诊断或处方建议。"
                if intent == "health" else None
            ),
            session_id=req.session_id,
        )

    result = chat_service.handle(req.query, req.session_id)
    trace.step("done", f"kb={result.get('kb')}")

    # ── 持久化 ──
    log_entry = {
        "id": trace.trace_id,
        "timestamp": datetime.now().isoformat(),
        "query": req.query,
        "answer": result["answer"][:2000],
        "intent": result.get("intent"),
        "kb": result.get("kb"),
        "sources": [s["title"] for s in result.get("sources", [])],
        "feedback": None,
        "session_id": req.session_id,
    }
    persist.save_qa_log(log_entry)
    trace.log()

    response = ChatResponse(
        answer=result["answer"],
        intent=result.get("intent"),
        kb=result.get("kb"),
        sources=result.get("sources", []),
        disclaimer=result.get("disclaimer"),
        session_id=req.session_id,
    )

    # 调试模式：附加 trace 信息
    if DEBUG:
        return JSONResponse({
            **response.model_dump(),
            "_debug": trace.summary(),
            "_stats": runtime.snapshot(),
        })

    return response


# ═══════════════════════════════════════════════════════
# 知识库管理 API
# ═══════════════════════════════════════════════════════

@app.get("/api/v1/kb/stats")
async def kb_stats():
    """获取各知识库统计信息"""
    from rag.rag_service import rag_service
    stats = rag_service.get_kb_stats()
    return {"data": stats}


@app.post("/admin/docs/upload")
async def upload_document(
    file: UploadFile = File(...),
    kb: str = Form("platform"),  # policy/service/health/platform
):
    """上传文档到指定知识库

    支持格式：PDF, TXT
    上传后自动分块、向量化、写入对应Chroma集合
    """
    if file.filename is None:
        return JSONResponse({"error": "文件名不能为空"}, status_code=400)

    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".txt", ".docx"]:
        return JSONResponse(
            {"error": f"不支持的文件格式：{ext}，仅支持 PDF、TXT 和 DOCX"},
            status_code=400,
        )

    kb_names = ["policy", "service", "health", "platform"]
    if kb not in kb_names:
        return JSONResponse(
            {"error": f"未知知识库：{kb}，可选值：{kb_names}"},
            status_code=400,
        )

    # 保存到对应知识库目录
    data_dir = Path(chroma_conf["collections"][kb]["data_path"])
    data_dir.mkdir(parents=True, exist_ok=True)

    # 避免文件名冲突
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = data_dir / safe_name

    try:
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"[admin]文档上传成功：{save_path} → kb={kb}")

        # 触发向量化加载
        from rag.vector_store import VectorStoreService
        vs = VectorStoreService()
        vs.load_document(kb=kb)

        return {
            "message": "文档上传并向量化成功",
            "kb": kb,
            "filename": file.filename,
            "saved_as": safe_name,
        }

    except Exception as e:
        logger.error(f"[admin]文档上传失败：{str(e)}")
        return JSONResponse({"error": f"上传失败：{str(e)}"}, status_code=500)


# ═══════════════════════════════════════════════════════
# 问答日志 API
# ═══════════════════════════════════════════════════════

@app.get("/admin/kb/reload")
async def reload_knowledge_base(kb: str = None):
    """重新加载知识库数据（扫描data目录并向量化）

    访问方式：浏览器打开 http://127.0.0.1:8000/admin/kb/reload
    或指定KB：http://127.0.0.1:8000/admin/kb/reload?kb=policy
    """
    from rag.vector_store import VectorStoreService
    vs = VectorStoreService()
    try:
        vs.load_document(kb=kb)
        stats = {
            k: vs.get_vector_count(k)
            for k in vs.KB_NAMES
        }
        return {
            "message": "知识库加载完成",
            "kb_loaded": kb or "all",
            "stats": stats,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/admin/logs")
async def get_logs(limit: int = 50, kb: str = None):
    """获取问答日志（SQLite 持久化）"""
    logs = persist.get_qa_logs(limit=limit, kb=kb)
    return {"data": logs, "total": len(logs)}


@app.post("/admin/logs/feedback")
async def submit_feedback(fb: FeedbackRequest):
    """提交回答质量反馈"""
    ok = persist.update_feedback(fb.log_id, fb.score, fb.comment)
    if ok:
        logger.info(f"[admin]反馈已记录：log_id={fb.log_id} score={fb.score}")
        return {"message": "反馈已提交，感谢您的评价！"}
    return JSONResponse({"error": "未找到对应日志"}, status_code=404)


@app.get("/admin/kb/chunk-config")
async def get_chunk_cfg():
    """获取分片配置"""
    return {"data": persist.get_chunk_config()}


@app.put("/admin/kb/chunk-config")
async def update_chunk_cfg(key: str, value: str):
    """更新分片配置"""
    persist.save_chunk_config(key, value)
    return {"message": "配置已更新", "key": key, "value": value}


# ═══════════════════════════════════════════════════════
# 调试端点
# ═══════════════════════════════════════════════════════

@app.get("/admin/debug/stats")
async def debug_stats():
    """运行时统计：LLM调用次数、缓存命中率、最近错误"""
    from rag.query_expander import query_expander
    return {
        "runtime": runtime.snapshot(),
        "kb_stats": {
            kb: rag_service.get_vector_count(kb)
            for kb in rag_service.KB_NAMES
        },
    }


@app.post("/admin/debug/dry-run")
async def debug_dry_run(req: ChatRequest):
    """空跑模式：只执行检索和意图识别，不调 LLM（用于测试 RAG 覆盖）"""
    from rag.query_expander import query_expander

    trace = Trace(req.query)
    intent = chat_service.detect_intent(req.query)
    trace.step("intent", intent)

    if intent == "reject_diagnosis":
        return {"intent": intent, "kb": None, "docs": 0, "trace": trace.summary()}

    # 执行扩展 + 检索，但不调 LLM 生成回答
    kb_map = {"policy": "policy", "service": "service", "health": "health", "general": "platform"}
    kb = kb_map.get(intent, "platform")

    expanded = query_expander.expand(req.query)
    docs = rag_service.multi_search(expanded, kb=kb)
    trace.step("retrieve", f"{len(docs)} docs")

    trace.log()
    return {
        "intent": intent,
        "kb": kb,
        "expanded_queries": expanded,
        "docs_found": len(docs),
        "sources": rag_service.get_sources(docs),
        "trace": trace.summary(),
    }


# ═══════════════════════════════════════════════════════
# 静态文件（前端原型）
# ═══════════════════════════════════════════════════════

front_dir = Path(__file__).resolve().parent.parent / "front"
if front_dir.exists():
    app.mount("/front", StaticFiles(directory=str(front_dir), html=True), name="front")


# ═══════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════

@app.get("/")
async def root():
    """根路径重定向到前端原型"""
    return RedirectResponse(url="/front/产品原型.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "智慧养老AI助手", "version": "1.0.0"}


# ═══════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
