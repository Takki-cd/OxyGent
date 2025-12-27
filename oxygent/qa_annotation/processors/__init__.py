# -*- encoding: utf-8 -*-
"""
QA标注平台 - Pipeline处理器模块

提供QA数据处理流水线的各个处理器:
- BaseProcessor: 处理器抽象基类
- TaskDispatcher: 任务分配器 (qa:processed -> qa:pending)
- LLMProcessor: LLM处理器 (qa:raw -> qa:processed) [TODO: 第二期]
- ReviewHandler: 审核处理器 (qa:review -> qa:knowledge) [TODO: 第二期]
"""

from .base_processor import BaseProcessor
from .task_dispatcher import TaskDispatcher

__all__ = [
    "BaseProcessor",
    "TaskDispatcher",
]

