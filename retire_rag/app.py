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

from fastapi import FastAPI, UploadFile, File, Form, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from service.chat_service import chat_service
from service import persist
from service import booking_service
from service.institution_db import search_institutions, get_all_districts
from service.booking_admin import get_all_bookings, update_booking_status
from service.sos_service import trigger_sos as sos_trigger, get_active_alerts as sos_active, resolve_alert as sos_resolve
from agent.react_agent import agent as react_agent
from utils.config_handler import chroma_conf
from utils.logger_handler import logger
from utils.debug import Trace, runtime, DEBUG
from auth.auth_routes import router as auth_router
from auth.auth_service import get_user_by_token, init_db
from service.user_service import init_db as init_user_db, bind_family, get_family
from service.health_service import init_db as init_health_db, get_profile, upsert_profile


async def get_current_user(request: Request):
    """从 Authorization 头提取 token 并返回用户信息，未认证返回 None"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    return get_user_by_token(token)

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

app.include_router(auth_router)

# 启动时初始化认证数据库 + 预约数据库 + 用户/健康档案数据库
@app.on_event("startup")
async def startup_auth():
    init_db()
    booking_service.init_db()
    init_user_db()
    init_health_db()


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
    current_user: dict = Depends(get_current_user),
):
    """上传文档到指定知识库

    支持格式：PDF, TXT
    上传后自动分块、向量化、写入对应Chroma集合
    """
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
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
async def reload_knowledge_base(
    kb: str = None,
    current_user: dict = Depends(get_current_user),
):
    """重新加载知识库数据（扫描data目录并向量化）

    访问方式：浏览器打开 http://127.0.0.1:8000/admin/kb/reload
    或指定KB：http://127.0.0.1:8000/admin/kb/reload?kb=policy
    """
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
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
async def get_logs(
    limit: int = 50,
    kb: str = None,
    current_user: dict = Depends(get_current_user),
):
    """获取问答日志（SQLite 持久化）"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    logs = persist.get_qa_logs(limit=limit, kb=kb)
    return {"data": logs, "total": len(logs)}


@app.post("/admin/logs/feedback")
async def submit_feedback(
    fb: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """提交回答质量反馈"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    ok = persist.update_feedback(fb.log_id, fb.score, fb.comment)
    if ok:
        logger.info(f"[admin]反馈已记录：log_id={fb.log_id} score={fb.score}")
        return {"message": "反馈已提交，感谢您的评价！"}
    return JSONResponse({"error": "未找到对应日志"}, status_code=404)


@app.get("/admin/kb/chunk-config")
async def get_chunk_cfg(current_user: dict = Depends(get_current_user)):
    """获取分片配置"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    return {"data": persist.get_chunk_config()}


@app.put("/admin/kb/chunk-config")
async def update_chunk_cfg(
    key: str,
    value: str,
    current_user: dict = Depends(get_current_user),
):
    """更新分片配置"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    persist.save_chunk_config(key, value)
    return {"message": "配置已更新", "key": key, "value": value}


# ═══════════════════════════════════════════════════════
# 养老机构查询 API
# ═══════════════════════════════════════════════════════

@app.get("/admin/institutions")
async def get_institutions(
    district: str = None,
    care_level: str = None,
    price_max: int = None,
    limit: int = 20,
):
    """查询养老机构列表，支持按区域/护理等级/价格筛选"""
    all_results = search_institutions(
        district=district,
        care_level=care_level,
        price_max=price_max,
        limit=9999,
    )
    total = len(all_results)
    data = all_results[:limit]
    return {"data": data, "total": total}


@app.get("/api/institutions/districts")
async def institution_districts():
    """获取所有养老机构所在区域"""
    districts = get_all_districts()
    return {"data": districts}


# ═══════════════════════════════════════════════════════
# 养老服务预约 API
# ═══════════════════════════════════════════════════════

class BookingRequest(BaseModel):
    service_id: int = 0
    service_key: str = ""
    date: str
    time_slot: str
    notes: str = ""


@app.get("/api/services")
async def list_services():
    """获取所有可预约服务项"""
    services = booking_service.get_all_services()
    return {"data": services}


@app.post("/api/services/book")
async def book_service(
    req: BookingRequest,
    current_user: dict = Depends(get_current_user),
):
    """预约服务（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    # 支持 service_key（前端字符串ID）映射到 service_id
    service_id = req.service_id
    if not service_id and req.service_key:
        svc = booking_service.get_service_by_key(req.service_key)
        if svc:
            service_id = svc["id"]
    if not service_id:
        return JSONResponse({"error": "请指定服务类型"}, status_code=400)

    result = booking_service.create_booking(
        user_id=current_user["id"],
        service_id=service_id,
        date=req.date,
        time_slot=req.time_slot,
        notes=req.notes or None,
    )
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "预约失败")}, status_code=400)

    return {"message": "预约成功", "booking_id": result["booking_id"]}


@app.get("/api/services/orders")
async def list_user_bookings(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的预约记录（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)

    bookings = booking_service.get_user_bookings(
        user_id=current_user["id"],
        limit=limit,
    )
    return {"data": bookings}


@app.put("/api/services/bookings/{booking_id}/cancel")
async def cancel_my_booking(
    booking_id: int,
    current_user: dict = Depends(get_current_user),
):
    """用户取消自己的预约"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    from service.booking_admin import update_booking_status
    ok = update_booking_status(booking_id, "cancelled")
    if ok:
        return {"message": "已取消"}
    return JSONResponse({"error": "未找到该预约"}, status_code=404)


@app.get("/admin/bookings")
async def admin_bookings(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """管理员：查看所有预约记录"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    return {"data": get_all_bookings(limit)}


class BookingStatusRequest(BaseModel):
    status: str  # confirmed / cancelled


@app.put("/admin/bookings/{booking_id}/status")
async def admin_booking_status(
    booking_id: int,
    req: BookingStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    """管理员：审批预约（确认/取消）"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    ok = update_booking_status(booking_id, req.status)
    if ok:
        return {"message": "状态已更新"}
    return JSONResponse({"error": "未找到该预约"}, status_code=404)


# ═══════════════════════════════════════════════════════
# 用户档案与家庭绑定 API
# ═══════════════════════════════════════════════════════

class FamilyBindRequest(BaseModel):
    name: str
    phone: str = ""
    id_card: str = ""
    relation: str = "其他"
    notes: str = ""


class HealthProfileRequest(BaseModel):
    elder_name: str
    age: int
    chronic_diseases: str = ""
    medications: str = ""
    notes: str = ""


@app.get("/api/user/profile")
async def user_profile(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    return {"data": current_user}


@app.post("/api/user/family-bind")
async def family_bind(
    req: FamilyBindRequest,
    current_user: dict = Depends(get_current_user),
):
    """绑定家庭成员（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    member = bind_family(
        user_id=current_user["id"],
        name=req.name,
        phone=req.phone,
        relation=req.relation,
        notes=req.notes,
    )
    return {"message": "绑定成功", "data": member}


@app.get("/api/user/family")
async def family_list(current_user: dict = Depends(get_current_user)):
    """获取当前用户的家庭成员列表（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    members = get_family(user_id=current_user["id"])
    return {"data": members}


@app.get("/api/health/profile")
async def health_profile(current_user: dict = Depends(get_current_user)):
    """获取当前用户的健康档案（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    profile = get_profile(user_id=current_user["id"])
    if profile is None:
        return JSONResponse({"error": "健康档案不存在"}, status_code=404)
    return {"data": profile}


@app.put("/api/health/profile")
async def health_profile_update(
    req: HealthProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建或更新健康档案（需登录）"""
    if not current_user:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    profile = upsert_profile(
        user_id=current_user["id"],
        elder_name=req.elder_name,
        age=req.age,
        chronic_diseases=req.chronic_diseases,
        medications=req.medications,
        notes=req.notes,
    )
    return {"message": "保存成功", "data": profile}


# ═══════════════════════════════════════════════════════
# 紧急呼叫 (SOS)
# ═══════════════════════════════════════════════════════

@app.post("/api/sos/trigger")
async def sos_trigger_endpoint(current_user: dict = Depends(get_current_user)):
    """用户触发紧急呼叫"""
    username = current_user["username"] if current_user else "匿名用户"
    user_id = current_user["id"] if current_user else None
    phone = current_user.get("phone", "") if current_user else ""
    # 获取紧急联系人（家属）
    family_info = ""
    if user_id:
        from service.user_service import get_family
        members = get_family(user_id)
        if members:
            family_info = "；".join(f"{m['name']} {m.get('phone','')}（{m['relation']}）" for m in members[:3])
    message = f"紧急求助！请立即联系！" + (f" 紧急联系人：{family_info}" if family_info else "")
    alert = sos_trigger(user_id=user_id, username=username, phone=phone, message=message)
    return {"message": "紧急呼叫已发送，工作人员将尽快响应", "alert": alert}


@app.get("/admin/sos/alerts")
async def sos_alerts(current_user: dict = Depends(get_current_user)):
    """管理员：获取活跃 SOS 警报"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    return {"data": sos_active()}


@app.put("/admin/sos/{alert_id}/resolve")
async def sos_mark_resolved(alert_id: int, current_user: dict = Depends(get_current_user)):
    """管理员：标记 SOS 已处理"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    sos_resolve(alert_id)
    return {"message": "已标记为已处理"}



# ═══════════════════════════════════════════════════════
# 政策大厅 API
# ═══════════════════════════════════════════════════════


@app.get("/api/policy/list")
async def policy_list():
    """政策大厅：按分类返回政策列表（静态数据，基于 data/policy/ 实际文件）"""
    return {
        "categories": [
            {
                "name": "高龄津贴",
                "icon": "💰",
                "policies": [
                    {
                        "title": "高龄老人津贴发放实施细则（2026版）",
                        "summary": "凡具有本市户籍、年满70周岁及以上的老年人，均可申请高龄老人津贴。津贴标准按年龄段分档发放，70-79周岁每人每月100元，80-89周岁每人每月200元，90-99周岁每人每月300元，100周岁及以上每人每月500元。",
                        "source": "养老政策法规汇编.txt",
                    },
                ],
            },
            {
                "name": "养老服务补贴",
                "icon": "🏠",
                "policies": [
                    {
                        "title": "居家养老服务补贴管理办法（2026版）",
                        "summary": "对经济困难的失能、半失能老年人给予居家养老服务补贴，补贴标准根据老年人能力评估等级确定，轻度失能每人每月200元，中度失能每人每月400元，重度失能每人每月600元，用于购买助餐、助浴、助洁等居家养老服务。",
                        "source": "养老政策法规汇编.txt",
                    },
                    {
                        "title": "养老机构运营补贴实施细则",
                        "summary": "对社会力量兴办的养老机构给予运营补贴，根据收住老年人能力评估等级和床位入住率给予差异化补贴，每床每月补贴200-500元，鼓励养老机构提升服务质量和管理水平。",
                        "source": "养老政策法规汇编.txt",
                    },
                ],
            },
            {
                "name": "养老金制度",
                "icon": "📋",
                "policies": [
                    {
                        "title": "关于2025年调整退休人员基本养老金的通知",
                        "summary": "从2025年1月1日起调整企业和机关事业单位退休人员基本养老金水平，全国调整比例按2024年月人均基本养老金的5.2%确定，采取定额调整、挂钩调整与适当倾斜相结合的办法。",
                        "source": "人力资源社会保障部 财政部关于2025年调整退休人员基本养老金的通知_国务院部门文件_中国政府网.pdf",
                    },
                    {
                        "title": "关于全面实施个人养老金制度的通知",
                        "summary": "自2025年1月1日起在全国范围内全面实施个人养老金制度，参加人每年缴纳个人养老金额度上限为12000元，可享受税收优惠政策，个人养老金账户实行封闭运行。",
                        "source": "人力资源社会保障部 财政部 国家税务总局 金融监管总局 中国证监会关于全面实施个人　养老金制度的通知__2025年第6号国务院公报_中国政府网.pdf",
                    },
                    {
                        "title": "个人养老金领取有关问题通知",
                        "summary": "明确个人养老金领取条件、领取方式和办理流程，参加人达到领取基本养老金年龄、完全丧失劳动能力、出国（境）定居等情形可领取个人养老金，可一次性或分期领取。",
                        "source": "人力资源社会保障部 财政部 国家税务总局 金融监管总局 中国证监会关于领取个人养老金有关问题的通知_国务院部门文件_中国政府网.pdf",
                    },
                ],
            },
            {
                "name": "长护险/失业险",
                "icon": "🏥",
                "policies": [
                    {
                        "title": "大龄领取失业保险金人员参加企业职工基本养老保险通知",
                        "summary": "对领取失业保险金且距法定退休年龄不足1年的大龄失业人员，由失业保险基金按规定为其缴纳企业职工基本养老保险费，确保其养老保险缴费不中断，保障退休后的养老待遇。",
                        "source": "人力资源社会保障部等三部门印发《关于大龄领取失业保险金人员参加企业职工基本养老保险有关问题的通知》_部门动态_中国政府网.pdf",
                    },
                    {
                        "title": "长期护理保险试点实施办法（2026版）",
                        "summary": "为长期失能人员的基本生活照料和与基本生活密切相关的医疗护理提供资金或服务保障，保障范围包括基本生活照料和与之密切相关的医疗护理，按失能等级确定待遇标准。",
                        "source": "养老政策法规汇编.txt",
                    },
                ],
            },
        ],
    }


# ═══════════════════════════════════════════════════════
# 调试端点
# ═══════════════════════════════════════════════════════

@app.get("/admin/debug/stats")
async def debug_stats(current_user: dict = Depends(get_current_user)):
    """运行时统计：LLM调用次数、缓存命中率、最近错误"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    from rag.rag_service import rag_service
    return {
        "runtime": runtime.snapshot(),
        "kb_stats": {
            kb: rag_service.vector_store.get_vector_count(kb)
            for kb in rag_service.KB_NAMES
        },
    }


@app.post("/admin/debug/dry-run")
async def debug_dry_run(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """空跑模式：只执行检索和意图识别，不调 LLM（用于测试 RAG 覆盖）"""
    if not current_user or current_user["role"] != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    from rag.query_expander import query_expander
    from rag.rag_service import rag_service

    trace = Trace(req.query)
    intent = chat_service.detect_intent(req.query)
    trace.step("intent", intent)

    if intent == "reject_diagnosis":
        return {"intent": intent, "kb": None, "docs": 0, "trace": trace.summary()}

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
