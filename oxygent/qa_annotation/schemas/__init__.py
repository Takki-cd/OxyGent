# -*- encoding: utf-8 -*-
"""
QA标注平台数据模型

本模块定义了QA标注平台的核心数据结构，包括:
- MQ消息定义 (RawQAMessage, ProcessedQAMessage, TaskMessage)
- 任务模型 (QATask)
- 标注结果模型 (QAAnnotation)
- ES表映射 (ES_MAPPINGS)
"""

from .messages import (
    RawQAMessage,
    ProcessedQAMessage,
    TaskMessage,
    ReviewMessage,
    KnowledgeMessage,
    QASourceType,
    QAPriority,
)
from .task import QATask, QATaskStatus, QATaskStage
from .annotation import QAAnnotation, QualityLabel, ReviewStatus

__all__ = [
    # Messages
    "RawQAMessage",
    "ProcessedQAMessage", 
    "TaskMessage",
    "ReviewMessage",
    "KnowledgeMessage",
    "QASourceType",
    "QAPriority",
    # Task
    "QATask",
    "QATaskStatus",
    "QATaskStage",
    # Annotation
    "QAAnnotation",
    "QualityLabel",
    "ReviewStatus",
]

