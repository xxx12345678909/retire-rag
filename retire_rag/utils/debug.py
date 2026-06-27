"""
开发者调试工具 — 请求追踪、性能计时、调试模式
"""
import os
import time
import uuid
from functools import wraps
from utils.logger_handler import logger

DEBUG = os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG"


class Trace:
    """单次请求的追踪上下文

    每个 API 请求分配唯一 trace_id，计时每个步骤耗时。
    """

    def __init__(self, query: str = ""):
        self.trace_id = uuid.uuid4().hex[:12]
        self.query = query[:80]
        self.steps: list[dict] = []
        self._start = time.time()
        self._step_start = self._start

    def step(self, name: str, detail: str = ""):
        """记录一个步骤的耗时"""
        now = time.time()
        elapsed = round((now - self._step_start) * 1000)  # ms
        self.steps.append({"step": name, "ms": elapsed, "detail": detail})
        if DEBUG:
            logger.debug(f"[trace:{self.trace_id}] {name}: {elapsed}ms {detail}")
        self._step_start = now

    def summary(self) -> dict:
        total = round((time.time() - self._start) * 1000)
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "total_ms": total,
            "steps": self.steps,
        }

    def log(self):
        """请求结束时输出汇总"""
        s = self.summary()
        timeline = " → ".join(f"{p['step']}({p['ms']}ms)" for p in s["steps"])
        logger.info(f"[trace:{self.trace_id}] {timeline} = {s['total_ms']}ms")
        if s["total_ms"] > 5000:
            logger.warning(f"[trace:{self.trace_id}] 慢请求 >5s，检查 LLM 调用次数")


def timed(step_name: str):
    """装饰器：自动记录函数耗时到当前请求的 Trace 上下文

    用法：
        @timed("expand")
        def expand(self, query): ...
    """
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            result = func(*args, **kwargs)
            elapsed = round((time.time() - t0) * 1000)
            if DEBUG:
                logger.debug(f"[{step_name}] {func.__name__}: {elapsed}ms")
            return result
        return wrapper
    return deco


# ── 全局统计（跨请求） ──

class Stats:
    """运行时统计计数器"""
    def __init__(self):
        self.llm_calls = 0
        self.llm_failures = 0
        self.rag_searches = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.requests = 0
        self.errors: list[dict] = []

    def record_error(self, module: str, error: str):
        self.errors.append({"time": time.strftime("%H:%M:%S"), "module": module, "error": str(error)[:200]})
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]

    def snapshot(self) -> dict:
        from rag.query_expander import query_expander
        return {
            "requests": self.requests,
            "llm_calls": self.llm_calls,
            "llm_failures": self.llm_failures,
            "rag_searches": self.rag_searches,
            "query_cache": query_expander.stats,
            "recent_errors": self.errors[-10:],
        }


runtime = Stats()
