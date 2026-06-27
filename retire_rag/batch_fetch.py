"""
一键批量语料采集 — Query Expansion → DDG → 下载 PDF → 自动入库

用法：
  python batch_fetch.py 养老政策          # policy 库
  python batch_fetch.py 糖尿病饮食 健康    # health 库
  python batch_fetch.py 居家养老 服务      # service 库
"""

import sys, os, time, hashlib
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote

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
REQUEST_DELAY = 3.0
MAX_PDFS = 10
MAX_RETRIES = 2

KB_ALIASES = {
    "政策": "policy", "法规": "policy", "政策法规": "policy",
    "服务": "service", "养老": "service",
    "健康": "health", "医疗": "health", "科普": "health",
    "平台": "platform", "操作": "platform",
}


def ddg_search(query: str, site: str = "gov.cn") -> list[dict]:
    """DDG 搜索，返回 [{title, url}]"""
    q = f"site:{site} {query} filetype:pdf"
    url = f"https://html.duckduckgo.com/html/?q={quote(q)}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for a in soup.select("a.result__a"):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if "/l/?uddg=" in href:
                    real_url = unquote(href.split("uddg=")[-1].split("&")[0])
                    if real_url.startswith("http") and site in real_url:
                        results.append({"title": title, "url": real_url})
            if results:
                return results
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2)
            else:
                logger.error(f"[DDG] search failed: {e}")
    return []


def download_pdf(url: str, save_dir: str) -> str | None:
    """下载 PDF，返回文件路径"""
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
        logger.error(f"[Download] {url[:60]}: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python batch_fetch.py <关键词> [kb]")
        print("  kb: policy(政策) / service(服务) / health(健康) / platform(平台)")
        return

    seed = sys.argv[1]
    kb = KB_ALIASES.get(sys.argv[2], sys.argv[2]) if len(sys.argv) > 2 else "policy"
    if kb not in ("policy", "service", "health", "platform"):
        print(f"未知知识库 '{kb}'，可选: policy, service, health, platform")
        return

    data_dir = Path(chroma_conf["collections"][kb]["data_path"])
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Target KB: {kb} -> {data_dir}")
    print(f"Seed: {seed}")

    keywords = query_expander.expand(seed, n=5)
    print(f"Expanded: {len(keywords)} keywords: {keywords}")

    downloaded = 0
    seen_urls = set()
    for kw in keywords:
        if downloaded >= MAX_PDFS:
            break
        print(f"\nSearch: {kw}")
        results = ddg_search(kw)
        print(f"  Found {len(results)} results")
        for r in results:
            if downloaded >= MAX_PDFS:
                break
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            print(f"  Download: {r['title'][:50]}...")
            path = download_pdf(r["url"], str(data_dir))
            if path:
                md5_hex = get_file_md5_hex(path)
                md5_file = Path(f"md5_{kb}.txt")
                existing = set(md5_file.read_text().splitlines()) if md5_file.exists() else set()
                if md5_hex in existing:
                    print(f"  Skip (exists)")
                    os.remove(path)
                    continue
                with open(md5_file, "a") as f:
                    f.write(md5_hex + "\n")
                downloaded += 1
                print(f"  OK [{downloaded}/{MAX_PDFS}] {os.path.basename(path)}")
            time.sleep(REQUEST_DELAY)
    print(f"\n{'='*60}")
    if downloaded == 0:
        print("No new files downloaded")
        return
    print(f"Downloaded {downloaded} PDFs, vectorizing...")
    vs = VectorStoreService()
    vs.load_document(kb=kb)
    count = vs.get_vector_count(kb)
    print(f"KB [{kb}] vectors: {count}")


if __name__ == "__main__":
    main()
