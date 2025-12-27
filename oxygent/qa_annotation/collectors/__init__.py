# -*- encoding: utf-8 -*-
"""
QA标注平台 - 数据采集模块

提供QA数据的采集功能:
- HookCollector: 实时Hook采集，在Agent执行完成后自动采集
- HistoryImporter: 历史数据导入，从ES批量导入历史数据
"""

from .hook_collector import QACollectorHook
from .history_importer import QAHistoryImporter

__all__ = [
    "QACollectorHook",
    "QAHistoryImporter",
]

