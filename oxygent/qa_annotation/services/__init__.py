# -*- encoding: utf-8 -*-
"""
QA标注平台 - 业务服务层

提供标注平台的核心业务逻辑:
- QAExtractionService: QA提取服务（从ES提取数据）
- TaskService: 任务管理服务（CRUD、树形查询）
- AnnotationService: 标注服务（标注、审核）
"""

from .qa_extraction_service import QAExtractionService
from .task_service import TaskService
from .annotation_service import AnnotationService

__all__ = [
    "QAExtractionService",
    "TaskService",
    "AnnotationService",
]
