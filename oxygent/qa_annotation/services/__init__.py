# -*- encoding: utf-8 -*-
"""
QA标注平台 - 业务服务层

提供单例模式的Service访问，避免重复创建实例
"""

from typing import Optional
from .qa_extraction_service import QAExtractionService
from .task_service import TaskService
from .annotation_service import AnnotationService


# Service单例缓存
_extraction_service: Optional[QAExtractionService] = None
_task_service: Optional[TaskService] = None
_annotation_service: Optional[AnnotationService] = None
_es_client = None
_mq_client = None


def set_service_clients(es_client, mq_client=None):
    """设置Service使用的客户端"""
    global _es_client, _mq_client
    global _extraction_service, _task_service, _annotation_service
    
    _es_client = es_client
    _mq_client = mq_client
    
    # 重置单例以使用新客户端
    _extraction_service = None
    _task_service = None
    _annotation_service = None


def get_extraction_service() -> QAExtractionService:
    """获取QA提取服务（单例）"""
    global _extraction_service
    if _extraction_service is None:
        if _es_client is None:
            raise RuntimeError("ES client not set. Call set_service_clients first.")
        _extraction_service = QAExtractionService(_es_client)
    return _extraction_service


def get_task_service() -> TaskService:
    """获取任务管理服务（单例）"""
    global _task_service
    if _task_service is None:
        if _es_client is None:
            raise RuntimeError("ES client not set. Call set_service_clients first.")
        _task_service = TaskService(_es_client)
    return _task_service


def get_annotation_service() -> AnnotationService:
    """获取标注服务（单例）"""
    global _annotation_service
    if _annotation_service is None:
        if _es_client is None:
            raise RuntimeError("ES client not set. Call set_service_clients first.")
        _annotation_service = AnnotationService(_es_client, _mq_client)
    return _annotation_service


__all__ = [
    # Service Classes
    "QAExtractionService",
    "TaskService",
    "AnnotationService",
    # Singleton Getters
    "set_service_clients",
    "get_extraction_service",
    "get_task_service",
    "get_annotation_service",
]
