from utils.packaging_patch import *  # noqa: F401,F403 — packaging 补丁，须在所有 transformers 相关导入之前

from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_conf

from model.factory import embed_model

from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, docx_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger

import os


class VectorStoreService:
    """多知识库向量存储服务

    管理4个独立的Chroma集合：
    - policy:   政策法规库
    - service:  养老服务库
    - health:   健康科普库
    - platform: 平台操作库
    """

    KB_NAMES = ["policy", "service", "health", "platform"]

    def __init__(self):
        self.collections_config = chroma_conf["collections"]
        self.persist_directory = chroma_conf["persist_directory"]

        # 为每个知识库创建独立的向量存储
        self.vector_stores = {}
        for kb_name in self.KB_NAMES:
            collection_name = self.collections_config[kb_name]["name"]
            self.vector_stores[kb_name] = Chroma(
                collection_name=collection_name,
                embedding_function=embed_model,
                persist_directory=self.persist_directory,
            )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self, kb: str = "platform"):
        """获取指定知识库的检索器

        Args:
            kb: 知识库名称 (policy/service/health/platform)，默认 platform
        """
        if kb not in self.KB_NAMES:
            logger.warning(f"[get_retriever]未知知识库'{kb}'，回退到platform")
            kb = "platform"
        return self.vector_stores[kb].as_retriever(
            search_kwargs={"k": chroma_conf["k"]}
        )

    def get_vector_count(self, kb: str) -> int:
        """获取指定知识库的向量数量"""
        if kb not in self.KB_NAMES:
            return 0
        try:
            return self.vector_stores[kb]._collection.count()
        except Exception:
            return 0

    def load_document(self, kb: str = None):
        """从指定知识库的数据文件夹加载文档并向量化

        Args:
            kb: 知识库名称，None 表示加载全部
        """

        kb_list = [kb] if kb else self.KB_NAMES

        for kb_name in kb_list:
            if kb_name not in self.KB_NAMES:
                logger.error(f"[加载知识库]未知知识库'{kb_name}'，跳过")
                continue

            data_path = get_abs_path(self.collections_config[kb_name]["data_path"])
            self._load_into_kb(kb_name, data_path)

    def _load_into_kb(self, kb_name: str, data_path: str):
        """将指定目录的文件加载到对应知识库"""

        def check_md5_hex(md5_for_check: str, md5_file: str) -> bool:
            if not os.path.exists(md5_file):
                open(md5_file, "w", encoding="utf-8").close()
                return False

            with open(md5_file, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    if line.strip() == md5_for_check:
                        return True
                return False

        def save_md5_hex(md5_for_check: str, md5_file: str):
            with open(md5_file, "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")

        def get_file_documents(read_path: str):
            if read_path.endswith("txt"):
                return txt_loader(read_path)
            if read_path.endswith("pdf"):
                return pdf_loader(read_path)
            if read_path.endswith("docx"):
                return docx_loader(read_path)
            return []

        # 每个知识库独立的MD5去重文件
        md5_file = get_abs_path(f"md5_{kb_name}.txt")

        if not os.path.isdir(data_path):
            logger.warning(f"[加载知识库]目录不存在：{data_path}，跳过 {kb_name}")
            return

        allowed_files_path = listdir_with_allowed_type(
            data_path,
            tuple(chroma_conf["allow_knowledge_file_type"]),
        )

        if not allowed_files_path:
            logger.info(f"[加载知识库]{kb_name} 无文件，跳过")
            return

        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)

            if check_md5_hex(md5_hex, md5_file):
                logger.info(f"[加载知识库][{kb_name}]文件已存在，跳过：{path}")
                continue

            try:
                documents = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库][{kb_name}]文件无有效内容，跳过：{path}")
                    continue

                split_document = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库][{kb_name}]分片无有效内容，跳过：{path}")
                    continue

                self.vector_stores[kb_name].add_documents(split_document)
                save_md5_hex(md5_hex, md5_file)

                logger.info(f"[加载知识库][{kb_name}]加载成功：{path} → {len(split_document)}个分片")
            except Exception as e:
                logger.error(f"[加载知识库][{kb_name}]加载失败：{path}，{str(e)}", exc_info=True)
                continue


if __name__ == "__main__":
    vs = VectorStoreService()

    # 加载全部知识库
    vs.load_document()

    # 打印各知识库向量数
    for kb in vs.KB_NAMES:
        count = vs.get_vector_count(kb)
        print(f"{kb}: {count} 条向量")
