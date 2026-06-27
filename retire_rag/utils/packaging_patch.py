"""packaging 元数据补丁 — 统一入口

Windows 下空目录 packaging-23.1.dist-info 遮蔽有效的 packaging-26.2，
导致 importlib.metadata.version('packaging') 返回 None，
使 transformers / langchain_text_splitters / langgraph 版本检查失败。

本模块在所有可能触发 transformers 导入的语句之前执行，
进程内只 monkey-patch 一次。
"""
import importlib.metadata as _importlib_metadata

_orig_version = _importlib_metadata.version


def _patched_version(package_name: str) -> str:
    v = _orig_version(package_name)
    if v is None and package_name == "packaging":
        return "26.2"
    return v


_importlib_metadata.version = _patched_version
