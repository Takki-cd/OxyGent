"""
QA标注平台配置

独立配置系统，不依赖 oxygent
"""
import os
from typing import Optional, List
from pydantic import BaseModel


class ESConfig(BaseModel):
    """ES配置"""
    hosts: List[str] = ["http://localhost:9200"]
    user: Optional[str] = None
    password: Optional[str] = None
    index_prefix: str = "qa_annotation_platform"
    # 本地ES存储目录（可选，不设置则使用主项目目录）
    local_data_dir: Optional[str] = None


class AppConfig(BaseModel):
    """应用配置"""
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    es: ESConfig = ESConfig()
    cors_origins: List[str] = ["*"]
    
    # 任务配置
    task_expire_hours: int = 24
    dedup_enabled: bool = True
    min_question_length: int = 2
    batch_size: int = 100


def get_config() -> AppConfig:
    """从环境变量读取配置"""
    # ES配置
    es_hosts = os.getenv("QA_ES_HOSTS", "http://localhost:9200").split(",")
    es_user = os.getenv("QA_ES_USER")
    es_password = os.getenv("QA_ES_PASSWORD")
    es_index_prefix = os.getenv("QA_ES_INDEX_PREFIX", "qa_annotation_platform")
    es_local_data_dir = os.getenv("QA_ES_LOCAL_DATA_DIR") or None
    
    # 应用配置
    host = os.getenv("QA_HOST", "0.0.0.0")
    port = int(os.getenv("QA_PORT", "8001"))
    debug = os.getenv("QA_DEBUG", "false").lower() == "true"
    cors_origins = os.getenv("QA_CORS_ORIGINS", "*").split(",")
    
    # 任务配置
    task_expire_hours = int(os.getenv("QA_TASK_EXPIRE_HOURS", "24"))
    dedup_enabled = os.getenv("QA_DEDUP_ENABLED", "true").lower() == "true"
    min_question_length = int(os.getenv("QA_MIN_QUESTION_LENGTH", "2"))
    batch_size = int(os.getenv("QA_BATCH_SIZE", "100"))
    
    return AppConfig(
        host=host,
        port=port,
        debug=debug,
        cors_origins=cors_origins,
        es=ESConfig(
            hosts=es_hosts,
            user=es_user,
            password=es_password,
            index_prefix=es_index_prefix,
            local_data_dir=es_local_data_dir
        ),
        task_expire_hours=task_expire_hours,
        dedup_enabled=dedup_enabled,
        min_question_length=min_question_length,
        batch_size=batch_size
    )


# 全局配置实例
_config: Optional[AppConfig] = None


def get_app_config() -> AppConfig:
    """获取应用配置（单例）"""
    global _config
    if _config is None:
        _config = get_config()
    return _config


def reset_config():
    """重置配置（用于测试）"""
    global _config
    _config = None
