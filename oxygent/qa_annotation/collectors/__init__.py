# -*- encoding: utf-8 -*-
"""
QA标注平台 - 数据采集器模块

提供数据采集能力:
- QACollectorHook: 实时采集Hook（可通过配置开启）

MVP版本说明:
- 实时Hook默认关闭，需在配置中启用
- 主要使用QAExtractionService进行批量提取
"""

from .hook_collector import QACollectorHook, publish_qa_to_mq

__all__ = [
    "QACollectorHook",
    "publish_qa_to_mq",
]
