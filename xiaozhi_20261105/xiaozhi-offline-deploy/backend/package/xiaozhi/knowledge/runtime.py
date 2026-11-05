"""知识库运行时单例。"""

import os

from xiaozhi.config import config
from xiaozhi.knowledge.factory import KnowledgeBaseFactory
from xiaozhi.knowledge.implementations.dify import DifyKB
from xiaozhi.knowledge.implementations.milvus import MilvusKB
from xiaozhi.knowledge.implementations.notion import NotionKB
from xiaozhi.knowledge.manager import KnowledgeBaseManager

if os.environ.get("LITE_MODE", "").lower() not in ("true", "1"):
    KnowledgeBaseFactory.register(MilvusKB)
KnowledgeBaseFactory.register(DifyKB)
KnowledgeBaseFactory.register(NotionKB)

knowledge_base = KnowledgeBaseManager(os.path.join(config.save_dir, "knowledge_base_data"))
