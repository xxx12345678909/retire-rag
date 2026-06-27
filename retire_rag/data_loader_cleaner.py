#!/usr/bin/env python3
"""
数据加载与清洗工具（养老知识库版）
功能：
1. 按4个知识库目录分别加载 txt/pdf 文件
2. 清洗数据（去重、格式化、去噪）
3. 验证数据质量
4. 分别加载到对应向量库集合
"""

import os
import re
import sys
import io
from pathlib import Path
from collections import Counter

# Windows 兼容 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("=" * 80)
print("[智慧养老知识库] 数据加载与清洗工具")
print("=" * 80)

try:
    from rag.vector_store import VectorStoreService
    from utils.logger_handler import logger
except ImportError as e:
    print(f"❌ 导入错误：{e}")
    sys.exit(1)


class DataCleaner:
    """数据清洗器"""

    @staticmethod
    def clean_text(text: str) -> str:
        """清洁文本内容"""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(
            r"[^一-鿿\w\s\.\,\!\?\;\：\；\，\。\！\？\—\-\+\(\)（）\n\《\》\【\】\d\%]",
            "",
            text,
        )
        text = text.strip()
        return text

    @staticmethod
    def validate_content(text: str, min_length: int = 20) -> bool:
        """验证内容有效性"""
        if not text or len(text.strip()) < min_length:
            return False
        if len(set(text)) < 10:
            return False
        return True


def main():
    """主流程：加载全部4个知识库"""

    print("\n📂 开始加载知识库...\n")

    kb_descriptions = {
        "policy": "政策法规库（补贴、长护险、管理条例）",
        "service": "养老服务库（项目说明、收费标准、FAQ）",
        "health": "健康科普库（慢性病护理、用药、饮食）",
        "platform": "平台操作库（使用指南、注册流程）",
    }

    vs = VectorStoreService()

    for kb_name, desc in kb_descriptions.items():
        print(f"\n{'=' * 60}")
        print(f"📚 {kb_name}: {desc}")
        print(f"{'=' * 60}")

        data_dir = Path(vs.collections_config[kb_name]["data_path"])
        if not data_dir.exists():
            print(f"  ⚠️  目录 {data_dir} 不存在，创建空目录")
            data_dir.mkdir(parents=True, exist_ok=True)
            continue

        data_files = list(data_dir.glob("*.txt")) + list(data_dir.glob("*.pdf"))
        print(f"  📄 发现 {len(data_files)} 个文件")

    print("\n" + "=" * 80)

    try:
        vs.load_document()
    except Exception as e:
        print(f"❌ 加载过程出错：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 打印统计
    print("\n📊 各知识库向量统计：")
    print("-" * 40)
    total = 0
    for kb_name, desc in kb_descriptions.items():
        count = vs.get_vector_count(kb_name)
        total += count
        print(f"  {desc}: {count} 条向量")
    print(f"  {'总计':>18}: {total} 条向量")

    print("\n" + "=" * 80)
    print("✅ 知识库数据加载完成！")
    print("=" * 80)
    print("\n下一步：python app.py 启动应用")


if __name__ == "__main__":
    main()
