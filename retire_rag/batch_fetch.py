"""
一键批量语料采集 — Query Expansion → Bing → 下载 PDF → 自动入库

用法：
  python batch_fetch.py 养老政策        # 默认政策库
  python batch_fetch.py 糖尿病 健康      # 指定知识库
  python batch_fetch.py 养老护理 服务    # 服务库
"""

import sys
import os
import time
import hashlib
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote

# ── 补丁 ──
import importlib.metadata as _mm
_o = _mm.version
def _p(n):
    v = _o(n)
    return "26.2" if v is None and n == "packaging" else v
_mm.version = _p

from rag.query_expander import query_expander
from rag.vector_store import VectorStoreService
from utils.file_handler import get_file_md5_hex
from utils.config_handler import chroma_conf
from utils.logger_handler import logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}
REQUEST_DELAY = 3.0   # 每次请求间隔（秒）
MAX_PDFS = 10          # 单次最大下载数
MAX_RETRIES = 2        # DDG 搜索重试次数

KB_ALIASES = {
    "政策": "policy", "法规": "policy", "政策法规": "policy",
    "服务": "service", "养老": "service",
    "健康": "health", "医疗": "health", "科普": "health",
    "平台": "platform", "操作": "platform",
}


def duckduckgo_search(query: str, site: str = "gov.cn") -> list[dict]:
    """DuckDuckGo 搜索（HTML 版），返回 [{title, url}]"""
    q = f"site:{site} {query} filetype:pdf"
    url = f"https://html.duckduckgo.com/html/?q={quote(q)}"
    try:
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")
                results = []
                for a in soup.select("a.result__a"):
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if "/l/?uddg=" in href:
                        from urllib.parse import unquote
                        real_url = unquote(href.split("uddg=")[-1].split("&")[0])
                        # DDG 已按 filetype:pdf 过滤，直接收录
                        if real_url.startswith("http") and "gov.cn" in real_url:
                            results.append({"title": title, "url": real_url})
                if results:
                    return results
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(2)
                    continue
                logger.error(f"[DDG] 搜索失败: {e}")
        return []


def download_pdf(url: str, save_dir: str) -> str | None:
    """下载 PDF 到指定目录，返回文件路径"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        if resp.status_code != 200 or "application/pdf" not in resp.headers.get("Content-Type", ""):
            return None
        fname = url.split("/")[-1].split("?")[0]
        if not fname.endswith(".pdf"):
            fname = hashlib.md5(url.encode()).hexdigest()[:12] + ".pdf"
        path = os.path.join(save_dir, fname)
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as e:
        logger.error(f"[下载] {url[:60]}: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python batch_fetch.py <关键词> [知识库: policy(默认)/service/health/platform]")
        print("示例: python batch_fetch.py 养老政策")
        print("      python batch_fetch.py 糖尿病饮食 健康")
        return

    seed = sys.argv[1]
    kb = sys.argv[2] if len(sys.argv) > 2 else "policy"
    kb = KB_ALIASES.get(kb, kb)  # 支持中文名映射
    if kb not in ("policy", "service", "health", "platform"):
        print(f"未知知识库 '{kb}'，可选: policy(政策), service(服务), health(健康), platform(平台)")
        return

    data_dir = Path(chroma_conf["collections"][kb]["data_path"])
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"📂 目标知识库: {kb} → {data_dir}")
    print(f"🔑 种子关键词: {seed}")

    # 1. 扩展关键词
    keywords = query_expander.expand(seed, n=5)
    print(f"📝 扩展为 {len(keywords)} 个检索词: {keywords}")

    # 2. 搜索 + 下载
    downloaded = 0
    seen_urls = set()

    for kw in keywords:
        if downloaded >= MAX_PDFS:
            break
        print(f"\n🔍 搜索: {kw}")
        results = duckduckgo_search(kw)
        print(f"   找到 {len(results)} 条结果")

        for r in results:
            if downloaded >= MAX_PDFS:
                break
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])

            print(f"   ⬇ 下载: {r['title'][:50]}...")
            path = download_pdf(r["url"], str(data_dir))
            if path:
                # MD5 去重检查
                md5_hex = get_file_md5_hex(path)
                md5_file = Path(f"md5_{kb}.txt")
                existing = set()
                if md5_file.exists():
                    existing = set(md5_file.read_text().splitlines())
                if md5_hex in existing:
                    print(f"   ⏭ 跳过（已存在）")
                    os.remove(path)
                    continue
                # 记录 MD5
                md5_file.write_text(md5_file.read_text() + md5_hex + "\n" if md5_file.exists() else md5_hex + "\n")
                downloaded += 1
                print(f"   ✅ [{downloaded}/{MAX_PDFS}] {os.path.basename(path)}")
            time.sleep(REQUEST_DELAY)

    print(f"\n{'='*60}")

    if downloaded == 0:
        print("⚠️ 未下载到新文件")
        return

    # 3. 自动向量化入库
    print(f"📊 共下载 {downloaded} 个新 PDF，开始向量化...")
    vs = VectorStoreService()
    vs.load_document(kb=kb)
    count = vs.get_vector_count(kb)
    print(f"✅ 知识库 [{kb}] 当前向量数: {count}")


if __name__ == "__main__":
    main()
