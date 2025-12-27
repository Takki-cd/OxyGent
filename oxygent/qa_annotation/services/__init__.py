# -*- encoding: utf-8 -*-
"""
QA标注平台 - 业务服务层

提供标注平台的核心业务逻辑:
- TaskService: 任务管理服务
- AnnotationService: 标注服务
- ImportService: 数据导入服务
- StatsService: 统计服务 [TODO]
"""

from .task_service import TaskService
from .annotation_service import AnnotationService
from .import_service import ImportService

__all__ = [
    "TaskService",
    "AnnotationService",
    "ImportService",
]

