# -*- encoding: utf-8 -*-
"""
QA标注平台数据模型

本模块定义了QA标注平台的核心数据结构:
- 任务模型 (QATask)
- 标注结果模型 (QAAnnotation)
- 数据源类型/优先级 (QASourceType, QAPriority)
"""

from .messages import QASourceType, QAPriority
from .task import QATask, QATaskStatus, QATaskStage, QA_TASK_MAPPING
from .annotation import QAAnnotation, QualityLabel, ReviewStatus, QA_ANNOTATION_MAPPING

__all__ = [
    # Source Type & Priority
    "QASourceType",
    "QAPriority",
    # Task
    "QATask",
    "QATaskStatus",
    "QATaskStage",
    "QA_TASK_MAPPING",
    # Annotation
    "QAAnnotation",
    "QualityLabel",
    "ReviewStatus",
    "QA_ANNOTATION_MAPPING",
]
